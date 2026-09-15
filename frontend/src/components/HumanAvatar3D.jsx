import {
  Component, Suspense, memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState,
} from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Environment, Lightformer, OrbitControls, useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import {
  QUALITY_PRESETS, applyFacialTargets, avatarAssetType, blinkWeight, cameraFrame,
  clamp, damp, dampingFactor, facialTargets, frameDelta, shouldAnimate,
} from '../lib/avatarMath.js';
import { poseJoint, prepareAvatar, releaseAvatar } from '../lib/avatarModel.js';
import { createAvatarShadow } from '../lib/avatarShadow.js';
import { avatarWebGLAvailable } from '../lib/avatarCapabilities.js';
import './avatar.css';

const FALLBACK_BOUNDS = Object.freeze({ width: 2, height: 2.8, depth: 1.5 });
const FOV = 32;

class AvatarErrorBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) {
    console.warn('[Avatar] Unable to display the 3D view:', error?.message || error);
    this.props.onError?.();
  }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

function useMotionAvailability(ref) {
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || !document.hidden);
  const [reducedMotion, setReducedMotion] = useState(() =>
    typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    let intersects = true;
    const update = () => setVisible(!document.hidden && intersects);
    const media = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    const motionChange = () => setReducedMotion(!!media?.matches);
    const observer = typeof IntersectionObserver !== 'undefined' ? new IntersectionObserver(([entry]) => {
      intersects = entry.isIntersecting && entry.intersectionRatio > 0;
      update();
    }, { threshold: [0, 0.01] }) : null;
    if (ref.current) observer?.observe(ref.current);
    document.addEventListener('visibilitychange', update);
    media?.addEventListener?.('change', motionChange);
    update();
    motionChange();
    return () => {
      observer?.disconnect();
      document.removeEventListener('visibilitychange', update);
      media?.removeEventListener?.('change', motionChange);
    };
  }, [ref]);
  return { visible, reducedMotion };
}

function FrameBudget({ active, fps }) {
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => {
    invalidate(); // One frame on stop/resume, then no idle GPU work when stopped.
    if (!active) return undefined;
    const timer = window.setInterval(invalidate, 1000 / fps);
    return () => window.clearInterval(timer);
  }, [active, fps, invalidate]);
  return null;
}

function ContextMonitor({ onLost }) {
  const gl = useThree((state) => state.gl);
  useEffect(() => {
    const canvas = gl.domElement;
    const lost = (event) => {
      event.preventDefault();
      onLost();
    };
    canvas.addEventListener('webglcontextlost', lost);
    return () => canvas.removeEventListener('webglcontextlost', lost);
  }, [gl, onLost]);
  return null;
}

// Memoization prevents a fresh environment cube render when emotion changes.
const StudioLighting = memo(function StudioLighting({ resolution }) {
  return (
    <>
      <hemisphereLight args={['#e7e6ff', '#3b3041', 0.65]} />
      <directionalLight position={[3, 4, 5]} intensity={2.1} color="#fff0e3" />
      <directionalLight position={[-3, 2.4, 3]} intensity={0.8} color="#d7dfff" />
      <directionalLight position={[1, 3.5, -3]} intensity={1.5} color="#d9ccff" />
      <Environment resolution={resolution} frames={1}>
        <Lightformer form="rect" intensity={2} position={[1, 4, 4]} scale={[5, 3, 1]} color="#fff5ed" />
        <Lightformer form="rect" intensity={1.1} position={[-4, 2, 2]} rotation-y={Math.PI / 4} scale={[2, 4, 1]} color="#e5ebff" />
        <Lightformer form="rect" intensity={1.5} position={[3, 3, -3]} rotation-y={-Math.PI / 3} scale={[3, 4, 1]} color="#e1d5ff" />
      </Environment>
    </>
  );
});

function ContactShadow({ resolution, width }) {
  const shadow = useMemo(() => createAvatarShadow(resolution, Math.max(3.5, width * 1.8)), [resolution, width]);
  const plane = useRef();
  const baked = useRef(false);
  useLayoutEffect(() => {
    baked.current = false;
    return () => shadow.dispose();
  }, [shadow]);
  useFrame(({ gl, scene }) => {
    if (baked.current || !plane.current) return;
    shadow.bake(gl, scene, plane.current);
    baked.current = true;
  });
  return (
    <mesh ref={plane} position={[0, -0.012, 0]} rotation-x={-Math.PI / 2} renderOrder={-1}>
      <planeGeometry args={[shadow.width, shadow.width]} />
      <meshBasicMaterial map={shadow.texture} transparent opacity={0.4} depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

function CameraRig({ bounds, view, resetToken, reducedMotion, visible, interacting }) {
  const controls = useRef();
  const { camera, size, invalidate } = useThree();
  const framing = useMemo(() => cameraFrame(bounds, size.width / Math.max(1, size.height), view, FOV),
    [bounds, size.width, size.height, view]);
  useLayoutEffect(() => {
    const orbit = controls.current;
    if (!orbit) return;
    // Discard residual orbit/pan inertia before applying an explicit reset.
    orbit.reset();
    orbit.target.fromArray(framing.target);
    camera.position.set(0, framing.target[1], framing.distance);
    camera.near = framing.near;
    camera.far = framing.far;
    camera.lookAt(orbit.target);
    camera.updateProjectionMatrix();
    orbit.minDistance = framing.distance * 0.48;
    orbit.maxDistance = framing.distance * 2.8;
    orbit.update();
    orbit.saveState();
    invalidate();
  }, [camera, framing, resetToken, invalidate]);
  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enabled={visible}
      enableZoom
      enablePan
      autoRotate={false}
      enableDamping={!reducedMotion}
      dampingFactor={0.12}
      minPolarAngle={Math.PI * 0.24}
      maxPolarAngle={Math.PI * 0.7}
      rotateSpeed={0.5}
      zoomSpeed={0.7}
      panSpeed={0.5}
      onStart={() => { interacting.current = true; }}
      onEnd={() => { interacting.current = false; }}
      mouseButtons={{ LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN }}
    />
  );
}

function GLBAvatar({ url, emotion, amplitudeRef, isStreaming, active, gaze, interacting, onReady, shadowResolution }) {
  const { scene } = useGLTF(url);
  const avatar = useMemo(() => prepareAvatar(scene), [scene]);
  const group = useRef();
  const time = useRef(0);
  const nextBlink = useRef(1.8 + Math.random() * 2);
  const gazeAngles = useRef({ yaw: 0, pitch: 0 });
  useLayoutEffect(() => {
    onReady(avatar.bounds);
  }, [avatar, onReady]);
  useEffect(() => () => releaseAvatar(avatar), [avatar]);
  useLayoutEffect(() => {
    if (active) return;
    // Calm, open-eyed rest rather than freezing in the middle of a blink.
    const targets = facialTargets(emotion, 0, 0, isStreaming);
    avatar.faces.forEach(({ mesh, bindings }) => applyFacialTargets(mesh.morphTargetInfluences, bindings, targets, 0, true));
    [avatar.head, avatar.neck, avatar.chest, ...avatar.eyes].forEach((joint) => poseJoint(joint, 0, 0));
    group.current?.rotation.set(0, 0, 0);
    gazeAngles.current = { yaw: 0, pitch: 0 };
  }, [avatar, active, emotion, isStreaming]);
  useFrame((_, delta) => {
    if (!active || !group.current) return;
    const dt = frameDelta(delta);
    time.current += dt;
    const t = time.current;
    if (t > nextBlink.current + 0.24) nextBlink.current = t + 2.6 + Math.random() * 3;
    const blink = blinkWeight(t - nextBlink.current);
    const amplitude = clamp(amplitudeRef?.current || 0);
    const targets = facialTargets(emotion, amplitude, blink, isStreaming);
    for (const { mesh, bindings } of avatar.faces) applyFacialTargets(mesh.morphTargetInfluences, bindings, targets, dt);

    // Feet stay planted: no whole-body scale pumping or continuous turntable.
    group.current.rotation.z = Math.sin(t * 0.65) * 0.006;
    group.current.rotation.y = Math.sin(t * 0.37) * 0.008;
    const following = !interacting.current && gaze.current.inside;
    const yaw = (following ? gaze.current.x * 0.13 : Math.sin(t * 0.43) * 0.025);
    const pitch = (following ? -gaze.current.y * 0.06 : Math.sin(t * 0.57) * 0.012) + (isStreaming ? 0.025 : 0);
    const angles = gazeAngles.current;
    angles.yaw = damp(angles.yaw, yaw, 3.5, dt);
    angles.pitch = damp(angles.pitch, pitch, 3.5, dt);
    poseJoint(avatar.head, angles.yaw, angles.pitch + amplitude * Math.sin(t * 3.1) * 0.015);
    poseJoint(avatar.neck, angles.yaw * 0.2, angles.pitch * 0.2);
    poseJoint(avatar.chest, Math.sin(t * 0.42) * 0.006, Math.sin(t * 1.35) * 0.008);
    for (const eye of avatar.eyes) poseJoint(eye, angles.yaw * 0.25, angles.pitch * 0.2);
  });
  return (
    <>
      <group ref={group} dispose={null}>
        <primitive object={avatar.root} dispose={null} />
      </group>
      {shadowResolution > 0 && <ContactShadow resolution={shadowResolution} width={avatar.bounds.width} />}
    </>
  );
}

function ProceduralAvatar({ emotion, amplitudeRef, active, onReady }) {
  const body = useRef();
  const mouth = useRef();
  const leftEye = useRef();
  const rightEye = useRef();
  const t = useRef(0);
  const nextBlink = useRef(2.5);
  const colors = { happy: '#9886da', excited: '#c19acb', sad: '#7391c9', angry: '#bd7a98', thinking: '#a083d4' };
  const color = colors[emotion] || '#9384cc';
  const target = useMemo(() => new THREE.Color(color), [color]);
  useLayoutEffect(() => { onReady(FALLBACK_BOUNDS); }, [onReady]);
  useLayoutEffect(() => {
    if (active) return;
    if (body.current) body.current.rotation.set(0, 0, 0);
    if (mouth.current) mouth.current.scale.y = 0.35;
    if (leftEye.current) leftEye.current.scale.y = 1;
    if (rightEye.current) rightEye.current.scale.y = 1;
  }, [active]);
  useFrame((_, delta) => {
    if (!active) return;
    const dt = frameDelta(delta);
    t.current += dt;
    if (t.current > nextBlink.current + 0.24) nextBlink.current = t.current + 2.8 + Math.random() * 3;
    const eyeScale = 1 - blinkWeight(t.current - nextBlink.current) * 0.94;
    leftEye.current.scale.y = rightEye.current.scale.y = eyeScale;
    body.current.rotation.y = Math.sin(t.current * 0.4) * 0.04;
    body.current.material.emissive.lerp(target, dampingFactor(4, dt));
    mouth.current.scale.y = damp(mouth.current.scale.y, 0.35 + clamp(amplitudeRef?.current || 0) * 2, 20, dt);
  });
  return (
    <group position={[0, 1.75, 0]} scale={0.8}>
      <mesh ref={body}>
        <sphereGeometry args={[1, 32, 24]} />
        <meshStandardMaterial color="#30283f" emissive={color} emissiveIntensity={0.16} metalness={0.25} roughness={0.36} />
      </mesh>
      {[-0.33, 0.33].map((x, index) => (
        <mesh key={x} ref={index === 0 ? leftEye : rightEye} position={[x, 0.21, 0.93]}>
          <sphereGeometry args={[0.105, 16, 12]} />
          <meshStandardMaterial color="#f1ecff" emissive="#aa9cde" emissiveIntensity={0.35} roughness={0.24} />
        </mesh>
      ))}
      <mesh ref={mouth} position={[0, -0.22, 0.96]} scale={[1, 0.35, 1]}>
        <sphereGeometry args={[0.13, 16, 12]} />
        <meshStandardMaterial color="#14101f" roughness={0.8} />
      </mesh>
    </group>
  );
}

function StaticAvatar({ name, onRetry }) {
  return (
    <div className="avatar3d-unavailable" role="status">
      <div className="avatar3d-monogram" aria-hidden="true">{(name || 'AI').slice(0, 2).toUpperCase()}</div>
      <strong>3D view unavailable</strong>
      <span>Your conversation is still available.</span>
      <button type="button" onClick={onRetry}>Retry 3D view</button>
    </div>
  );
}

function AvatarStage({ avatarUrl, characterName, emotion, amplitudeRef, isStreaming, isPaused, visible, reducedMotion }) {
  const assetType = avatarAssetType(avatarUrl);
  const [modelFailed, setModelFailed] = useState(false);
  const [graphicsFailed, setGraphicsFailed] = useState(() => assetType !== 'image' && !avatarWebGLAvailable());
  const [ready, setReady] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [view, setView] = useState('portrait');
  const [quality, setQuality] = useState('balanced');
  const [resetToken, setResetToken] = useState(0);
  const [bounds, setBounds] = useState(FALLBACK_BOUNDS);
  const gaze = useRef({ x: 0, y: 0, inside: false });
  const interacting = useRef(false);
  const preset = QUALITY_PRESETS[quality];
  const isModel = assetType === 'model' && !modelFailed;
  const isImage = assetType === 'image' && !modelFailed;
  const active = shouldAnimate({ paused: isPaused, reducedMotion, visible }) && !graphicsFailed;
  const handleReady = useCallback((nextBounds) => {
    setBounds(nextBounds);
    setReady(true);
  }, []);
  const handleModelFailure = useCallback(() => {
    setModelFailed(true);
    setReady(false);
    if (!avatarWebGLAvailable()) setGraphicsFailed(true);
  }, []);
  const handleGraphicsFailure = useCallback(() => setGraphicsFailed(true), []);
  const retry = useCallback(() => {
    // Clear only a failed load on explicit retry; normal mounts reuse the URL
    // and parsed GLTF cache, including existing query/hash/version parameters.
    if (assetType === 'model' && modelFailed) useGLTF.clear(avatarUrl);
    setModelFailed(false);
    setGraphicsFailed(assetType !== 'image' && !avatarWebGLAvailable(true));
    setReady(false);
    setAttempt((value) => value + 1);
  }, [assetType, avatarUrl, modelFailed]);
  useEffect(() => {
    amplitudeRef?.setVisualActive?.(active && !isImage && ready);
    return () => amplitudeRef?.setVisualActive?.(false);
  }, [amplitudeRef, active, isImage, ready]);
  const motionStatus = isPaused ? 'Motion paused' : reducedMotion ? 'Reduced motion' : !visible ? 'Motion resting' : 'Live motion';
  const status = modelFailed ? 'Simple avatar · model unavailable' : !ready ? (isImage ? 'Loading portrait…' : 'Loading 3D avatar…') :
    isImage ? 'Portrait' : assetType === 'fallback' ? `Simple avatar · ${motionStatus.toLowerCase()}` : motionStatus;
  const fallback = <StaticAvatar name={characterName} onRetry={retry} />;
  return (
    <div
      className="avatar3d-stage"
      data-motion={active ? 'active' : 'still'}
      onContextMenu={(event) => event.preventDefault()}
      onPointerMove={(event) => {
        if (!active || event.pointerType === 'touch') return;
        const rect = event.currentTarget.getBoundingClientRect();
        gaze.current = {
          x: clamp((event.clientX - rect.left) / rect.width * 2 - 1, -1, 1),
          y: clamp(1 - (event.clientY - rect.top) / rect.height * 2, -1, 1),
          inside: true,
        };
      }}
      onPointerLeave={() => { gaze.current.inside = false; }}
    >
      {graphicsFailed ? fallback : isImage ? (
        <div className={`avatar-portrait ${active && isStreaming ? 'avatar-portrait-streaming' : ''}`}>
          <div className="avatar-portrait-ring" />
          <img src={avatarUrl} alt={`${characterName || 'Companion'} portrait`} className="avatar-portrait-img"
            onLoad={() => setReady(true)} onError={handleModelFailure} />
        </div>
      ) : (
        <AvatarErrorBoundary key={attempt} onError={handleGraphicsFailure} fallback={fallback}>
          <Canvas
            frameloop="demand"
            camera={{ position: [0, 2.24, 4.5], fov: FOV, near: 0.01, far: 50 }}
            dpr={[1, preset.dpr]}
            gl={{ antialias: true, alpha: true, powerPreference: 'default', toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1 }}
            fallback={fallback}
            aria-label={`Interactive 3D view of ${characterName || 'your companion'}`}
          >
            <ContextMonitor onLost={handleGraphicsFailure} />
            <FrameBudget active={active && ready} fps={preset.fps} />
            <StudioLighting resolution={preset.environment} />
            <Suspense fallback={null}>
              {isModel ? (
                <AvatarErrorBoundary key={`${avatarUrl}:${attempt}`} onError={handleModelFailure} fallback={null}>
                  <GLBAvatar url={avatarUrl} emotion={emotion} amplitudeRef={amplitudeRef} isStreaming={isStreaming}
                    active={active} gaze={gaze} interacting={interacting} onReady={handleReady} shadowResolution={preset.shadow} />
                </AvatarErrorBoundary>
              ) : (
                <ProceduralAvatar emotion={emotion} amplitudeRef={amplitudeRef} active={active} onReady={handleReady} />
              )}
            </Suspense>
            <CameraRig bounds={bounds} view={isModel ? view : 'portrait'} resetToken={resetToken}
              reducedMotion={reducedMotion || isPaused} visible={visible} interacting={interacting} />
          </Canvas>
        </AvatarErrorBoundary>
      )}
      {!isImage && !graphicsFailed && (
        <div className="avatar3d-toolbar" aria-label="3D view controls" onPointerMove={(event) => event.stopPropagation()}>
          {isModel && <div className="avatar3d-view-toggle" role="group" aria-label="Camera framing">
            <button type="button" aria-pressed={view === 'portrait'} onClick={() => setView('portrait')}>Portrait</button>
            <button type="button" aria-pressed={view === 'body'} onClick={() => setView('body')}>Body</button>
          </div>}
          <button type="button" onClick={() => setResetToken((value) => value + 1)} title="Reset camera position and zoom">Reset</button>
          <select aria-label="Avatar rendering quality" title="Eco: 24 fps / Balanced: 30 fps / High: 60 fps"
            value={quality} onChange={(event) => setQuality(event.target.value)}>
            {Object.entries(QUALITY_PRESETS).map(([key, option]) => <option key={key} value={key}>{option.label}</option>)}
          </select>
        </div>
      )}
      {!graphicsFailed && (
        <div className={`avatar3d-status ${!ready ? 'avatar3d-status-loading' : ''}`} role="status" aria-live="polite"
          title="Mouth motion uses audio volume; browser speech uses a simulated cadence. Not phoneme lip-sync.">
          <span className="avatar3d-status-dot" aria-hidden="true" />
          <span>{status}</span>
          {modelFailed && <button type="button" onClick={retry}>Retry</button>}
        </div>
      )}
    </div>
  );
}

export default function HumanAvatar3D({
  avatarUrl = null, emotion = 'neutral', amplitudeRef, isStreaming = false, isPaused = false, characterName,
}) {
  const wrapper = useRef();
  const availability = useMotionAvailability(wrapper);
  return (
    <div className="avatar-canvas-wrapper avatar3d-wrapper" ref={wrapper}>
      <AvatarStage key={avatarUrl || 'procedural'} avatarUrl={avatarUrl} emotion={emotion}
        amplitudeRef={amplitudeRef} isStreaming={isStreaming} isPaused={isPaused} characterName={characterName}
        {...availability} />
    </div>
  );
}
