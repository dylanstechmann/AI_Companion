import { useRef, useState, useEffect, useMemo, Suspense, useCallback, Component } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, useGLTF, Environment, Lightformer, ContactShadows } from '@react-three/drei';
import * as THREE from 'three';

// Catches errors thrown while loading/parsing the GLB (inside the Canvas tree)
// so we can log the real reason and fall back to the procedural avatar.
class GLBErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('[GLB_ERROR]', error?.message || error, info);
    if (this.props.onError) this.props.onError(error);
  }
  render() {
    if (this.state.hasError) return null;
    return this.props.children;
  }
}

const EMOTION_POSES = {
  neutral: {},
  happy: { mouthSmileLeft: 0.7, mouthSmileRight: 0.7, cheekSquintLeft: 0.4, cheekSquintRight: 0.4 },
  sad: { mouthFrownLeft: 0.6, mouthFrownRight: 0.6, browInnerUp: 0.4 },
  excited: { mouthSmileLeft: 0.9, mouthSmileRight: 0.9, eyeWideLeft: 0.5, eyeWideRight: 0.5 },
  thinking: { browInnerUp: 0.3, mouthShrugLower: 0.3, eyeSquintLeft: 0.1 },
  angry: { browDownLeft: 0.7, browDownRight: 0.7, mouthPressLeft: 0.4, mouthPressRight: 0.4 },
};

// Only these facial morph targets are driven/reset each frame. MPFB GLBs also
// ship internal macro shape keys (body shape: muscle, cupsize, height, etc.,
// named like "$md-...") which are exported with non-zero default weights. Those
// MUST be left untouched, otherwise every character collapses to an identical
// neutral body. So we explicitly reset only the face morphs we control.
const CONTROLLED_MORPHS = [
  'jawOpen',
  'eyeBlinkLeft', 'eyeBlinkRight',
  'eyeWideLeft', 'eyeWideRight',
  'eyeSquintLeft', 'eyeSquintRight',
  'browInnerUp', 'browDownLeft', 'browDownRight',
  'mouthSmileLeft', 'mouthSmileRight',
  'mouthFrownLeft', 'mouthFrownRight',
  'mouthPressLeft', 'mouthPressRight',
  'mouthShrugLower',
  'cheekSquintLeft', 'cheekSquintRight',
];

function GLBAvatar({ url, emotion, amplitudeRef, isStreaming, isPaused }) {
  const { scene } = useGLTF(url);
  const groupRef = useRef();
  const morphRefs = useRef({});
  const time = useRef(0);
  const blinkTimer = useRef(0);
  const blinkPhase = useRef(0);
  const nextBlink = useRef(2 + Math.random() * 3);
  const currentEmotion = useRef({});

  useEffect(() => {
    return () => {
      useGLTF.clear(url);
      morphRefs.current = {};
    };
  }, [url]);

  const cloned = useMemo(() => {
    const clone = scene.clone(true);
    clone.traverse((child) => {
      if (child.isMesh && child.material) {
        // Properly clone materials, handling arrays (multi-primitive meshes)
        if (Array.isArray(child.material)) {
          child.material = child.material.map(m => m.clone());
        } else {
          child.material = child.material.clone();
        }
      }
    });

    // ---------------------------------------------------------------------
    // NORMALIZE SIZE & POSITION. The MPFB GLB is exported at scale=0.1, so the
    // mesh is only ~0.18 units tall with feet at the origin. With the camera at
    // [0, 0.8, 5.5] that renders as a near-invisible speck. Wrap the model in a
    // group, recenter it on the origin and scale it up to a consistent height so
    // every character frames the same way regardless of their exported size.
    // ---------------------------------------------------------------------
    const box = new THREE.Box3().setFromObject(clone);
    const size = new THREE.Vector3();
    const center = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(center);
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    const targetHeight = 2.8;
    const scaleFactor = targetHeight / maxDim;

    // Recenter the model so its bounding-box center sits at the origin.
    clone.position.sub(center);

    const wrapper = new THREE.Group();
    wrapper.add(clone);
    wrapper.scale.setScalar(scaleFactor);
    return wrapper;
  }, [scene]);

  useEffect(() => {
    // =======================================================================
    // NOTE FOR NEXT DEVELOPER / BLENDER MCP AGENT:
    // - The GLB model was exported from MakeHuman/MPFB.
    // - It contains two major meshes:
    //   1. "Human" (Node name 'Human', Mesh name 'base'): The main body mesh
    //      which contains vertex morph targets (hasMorphs = true, 14291 vertices).
    //   2. "Human.high-poly" (Mesh name 'high-poly'): A helper mesh cage 
    //      (1072 vertices) that has no morphs.
    // - ISSUE: In the rendering, the skin mesh (head, face, and arms) of the base mesh
    //      is invisible or distorted, resulting in a "headless body" render.
    //      Hiding the 'high-poly' mesh leaves only the animated base mesh visible.
    // =======================================================================
    cloned.traverse((child) => {
      if (!child.isMesh) return;

      const name = (child.name || '').toLowerCase();
      if (name.includes('high-poly') || name.includes('highpoly')) {
        child.visible = false;
        return;
      }

      if (child.morphTargetDictionary) {
        morphRefs.current[child.uuid] = child;
        // Body mesh is now mostly exposed skin (face/neck/arms/legs).
        // Give it a small polygon offset to keep it behind clothes in any overlap.
        const applyOffset = (mat) => {
          mat.polygonOffset = true;
          mat.polygonOffsetFactor = 2;
          mat.polygonOffsetUnits = 2;
        };
        if (child.material) {
          if (Array.isArray(child.material)) {
            child.material.forEach(applyOffset);
          } else {
            applyOffset(child.material);
          }
        }
      }

      // Fix material transparency: MPFB exports ALL materials as BLEND, which makes
      // the body mesh (face/neck/arms/legs) invisible in Three.js. Only hair/eyebrows/
      // eyelashes actually need transparency. Everything else must be OPAQUE.
      if (child.material) {
        const fixMat = (mat) => {
          const n = (mat.name || '').toLowerCase();
          const needsTransparency = n.includes('eyelash') || n.includes('eyebrow') ||
            n.includes('hair') || n.includes('long01');
          if (needsTransparency) {
            mat.transparent = true;
            mat.alphaTest = 0.5;
            mat.side = THREE.DoubleSide;
            mat.depthWrite = true;  // still write depth so hair sorts properly
          } else {
            // Force opaque for body, clothes, eyes, teeth, shoes
            mat.transparent = false;
            mat.alphaTest = 0;
            mat.opacity = 1.0;
            mat.depthWrite = true;
            mat.side = THREE.FrontSide;
            // Clear any blend mode artifacts
            mat.blending = THREE.NormalBlending;
          }

          // -----------------------------------------------------------------
          // VISUAL QUALITY: the MPFB GLB ships flat solid-colour materials with
          // NO textures. To avoid the "grey clay mannequin" look we tune how
          // each material responds to the image-based lighting (Environment),
          // and add subtle realism (soft skin, glossy eyes, matte clothes).
          // -----------------------------------------------------------------
          if ('envMapIntensity' in mat) {
            if (n.includes('skin') || n.includes('lips')) {
              mat.envMapIntensity = 0.5;
              mat.roughness = Math.min(mat.roughness ?? 0.6, 0.62);
            } else if (n.includes('eye')) {
              // Glossy, reflective eyes catch a highlight and read as "alive".
              mat.envMapIntensity = 1.4;
              mat.roughness = 0.12;
            } else if (n.includes('hair')) {
              mat.envMapIntensity = 0.7;
              mat.roughness = 0.4;
            } else {
              // Clothes / shoes: gentle sheen.
              mat.envMapIntensity = 0.85;
            }
          }
          mat.needsUpdate = true;
        };
        if (Array.isArray(child.material)) {
          child.material.forEach(fixMat);
        } else {
          fixMat(child.material);
        }
      }
    });
  }, [cloned]);

  useEffect(() => {
    currentEmotion.current = EMOTION_POSES[emotion] || EMOTION_POSES.neutral;
  }, [emotion]);

  useFrame((_, delta) => {
    if (isPaused || !groupRef.current) return;
    time.current += delta;

    groupRef.current.scale.set(1, 1 + Math.sin(time.current * 1.5) * 0.015, 1);
    groupRef.current.rotation.z = Math.sin(time.current * 0.4) * 0.02;
    groupRef.current.rotation.y = Math.sin(time.current * 0.2) * 0.05;

    // Blink
    blinkTimer.current += delta;
    let eyeBlink = 0;
    if (blinkPhase.current === 0 && blinkTimer.current > nextBlink.current) {
      blinkPhase.current = 1; blinkTimer.current = 0;
    }
    if (blinkPhase.current === 1) {
      eyeBlink = Math.min(1, blinkTimer.current / 0.08);
      if (eyeBlink >= 1) { blinkPhase.current = 2; blinkTimer.current = 0; }
    } else if (blinkPhase.current === 2) {
      eyeBlink = 1;
      if (blinkTimer.current > 0.05) { blinkPhase.current = 3; blinkTimer.current = 0; }
    } else if (blinkPhase.current === 3) {
      eyeBlink = Math.max(0, 1 - blinkTimer.current / 0.1);
      if (eyeBlink <= 0) { blinkPhase.current = 0; blinkTimer.current = 0; nextBlink.current = 2 + Math.random() * 4; }
    }

    const amp = amplitudeRef?.current || 0;
    const targetMorphs = {
      ...currentEmotion.current,
      jawOpen: Math.max(amp * 0.8, currentEmotion.current.jawOpen || 0),
      eyeBlinkLeft: eyeBlink,
      eyeBlinkRight: eyeBlink,
    };
    if (isStreaming) {
      targetMorphs.eyeSquintLeft = 0.15;
      targetMorphs.eyeSquintRight = 0.15;
      targetMorphs.browInnerUp = 0.2;
    }

    Object.values(morphRefs.current).forEach((mesh) => {
      if (!mesh.morphTargetDictionary || !mesh.morphTargetInfluences) return;
      const dict = mesh.morphTargetDictionary;
      // Reset ONLY the face morphs we control; leave MPFB body-shape morphs alone.
      for (const name of CONTROLLED_MORPHS) {
        const idx = dict[name];
        if (idx !== undefined) {
          mesh.morphTargetInfluences[idx] = THREE.MathUtils.lerp(mesh.morphTargetInfluences[idx] || 0, 0, delta * 5);
        }
      }
      for (const [name, value] of Object.entries(targetMorphs)) {
        const idx = dict[name];
        if (idx !== undefined) {
          mesh.morphTargetInfluences[idx] = THREE.MathUtils.lerp(mesh.morphTargetInfluences[idx] || 0, value, delta * 8);
        }
      }
    });
  });

  return (
    <group ref={groupRef} dispose={null}>
      <primitive object={cloned} />
    </group>
  );
}

function ProceduralAvatar({ emotion, amplitudeRef, isStreaming, isPaused }) {
  const groupRef = useRef();
  const bodyRef = useRef();
  const mouthRef = useRef();
  const leftEyeRef = useRef();
  const rightEyeRef = useRef();
  const time = useRef(0);
  const blinkTimer = useRef(0);
  const blinkPhase = useRef(0);
  const nextBlink = useRef(2 + Math.random() * 3);

  const colors = {
    neutral: { emissive: '#6366f1', glow: '#818cf8' },
    happy: { emissive: '#10b981', glow: '#34d399' },
    excited: { emissive: '#f59e0b', glow: '#fbbf24' },
    sad: { emissive: '#3b82f6', glow: '#60a5fa' },
    thinking: { emissive: '#8b5cf6', glow: '#a78bfa' },
    angry: { emissive: '#ef4444', glow: '#f87171' },
  }[emotion] || { emissive: '#6366f1', glow: '#818cf8' };

  const targetEmissive = useMemo(() => new THREE.Color(colors.emissive), [colors.emissive]);
  const currentEmissive = useMemo(() => new THREE.Color(colors.emissive), []);

  useFrame((_, delta) => {
    if (isPaused) return;
    time.current += delta;
    if (!groupRef.current) return;

    groupRef.current.position.y = Math.sin(time.current * 1.5) * 0.08;
    groupRef.current.rotation.y = Math.sin(time.current * 0.3) * 0.15;

    if (bodyRef.current) {
      const breathe = 1 + Math.sin(time.current * 2) * 0.02;
      bodyRef.current.scale.set(breathe, breathe * 1.01, breathe);
      currentEmissive.lerp(targetEmissive, delta * 3);
      bodyRef.current.material.emissive.copy(currentEmissive);
      bodyRef.current.material.emissiveIntensity = 0.3 + Math.sin(time.current * 2) * 0.05;
    }

    blinkTimer.current += delta;
    let eyeScaleY = 1;
    if (blinkPhase.current === 0 && blinkTimer.current > nextBlink.current) {
      blinkPhase.current = 1; blinkTimer.current = 0;
    }
    if (blinkPhase.current === 1) {
      eyeScaleY = 1 - blinkTimer.current / 0.08;
      if (eyeScaleY <= 0.1) { blinkPhase.current = 2; blinkTimer.current = 0; }
    } else if (blinkPhase.current === 2) {
      eyeScaleY = 0.1;
      if (blinkTimer.current > 0.05) { blinkPhase.current = 3; blinkTimer.current = 0; }
    } else if (blinkPhase.current === 3) {
      eyeScaleY = 0.1 + blinkTimer.current / 0.1;
      if (eyeScaleY >= 1) { eyeScaleY = 1; blinkPhase.current = 0; blinkTimer.current = 0; nextBlink.current = 2 + Math.random() * 4; }
    }
    if (isStreaming) eyeScaleY = 0.5 + Math.sin(time.current * 10) * 0.3;
    if (leftEyeRef.current) leftEyeRef.current.scale.y = eyeScaleY;
    if (rightEyeRef.current) rightEyeRef.current.scale.y = eyeScaleY;

    const amp = amplitudeRef?.current || 0;
    if (mouthRef.current) {
      mouthRef.current.scale.y = THREE.MathUtils.lerp(mouthRef.current.scale.y, 0.3 + amp * 2.5, 0.3);
      mouthRef.current.scale.x = 1 + amp * 0.5;
    }
  });

  return (
    <group ref={groupRef}>
      <mesh ref={bodyRef}>
        <icosahedronGeometry args={[1, 4]} />
        <meshStandardMaterial color="#1a1a3e" emissive={colors.emissive} emissiveIntensity={0.3} metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh ref={leftEyeRef} position={[-0.35, 0.2, 0.85]}>
        <sphereGeometry args={[0.12, 16, 16]} />
        <meshStandardMaterial color="#ffffff" emissive={colors.glow} emissiveIntensity={0.8} />
      </mesh>
      <mesh ref={rightEyeRef} position={[0.35, 0.2, 0.85]}>
        <sphereGeometry args={[0.12, 16, 16]} />
        <meshStandardMaterial color="#ffffff" emissive={colors.glow} emissiveIntensity={0.8} />
      </mesh>
      <mesh ref={mouthRef} position={[0, -0.25, 0.85]}>
        <sphereGeometry args={[0.15, 16, 16]} />
        <meshStandardMaterial color="#2a2a4e" emissive={colors.emissive} emissiveIntensity={0.3} />
      </mesh>
    </group>
  );
}

export default function HumanAvatar3D({
  avatarUrl = null, emotion = 'neutral', amplitudeRef,
  isStreaming = false, isPaused = false, characterName,
  clothingStyle = 'casual', clothingDescription = '', bodyType = 'athletic',
}) {
  const [hasError, setHasError] = useState(false);
  const [useFallback, setUseFallback] = useState(false);

  useEffect(() => {
    setHasError(false);
    setUseFallback(false);
  }, [avatarUrl]);

  const handleError = useCallback((e) => {
    const msg = e?.message || e?.error?.message || (typeof e === 'string' ? e : '') || '(no error object)';
    // eslint-disable-next-line no-console
    console.error('[AVATAR_FALLBACK] reason:', msg, e);
    setUseFallback(true);
  }, []);

  const effectiveUrl = (hasError || useFallback) ? null : avatarUrl;
  if (effectiveUrl && !window.__GLOBAL_CACHE_BUSTS) {
    window.__GLOBAL_CACHE_BUSTS = {};
  }
  if (effectiveUrl && !window.__GLOBAL_CACHE_BUSTS[effectiveUrl]) {
    window.__GLOBAL_CACHE_BUSTS[effectiveUrl] = Date.now();
  }
  const cacheBust = effectiveUrl ? window.__GLOBAL_CACHE_BUSTS[effectiveUrl] : null;

  const cacheBustedUrl = effectiveUrl ? `${effectiveUrl}?v=${cacheBust}` : null;

  const isGlbUrl = !!(effectiveUrl && (effectiveUrl.endsWith('.glb') || effectiveUrl.includes('.glb')));
  // NOTE: GLB must take priority. 3D avatar URLs live under "/avatars/*.glb", so the
  // generic "/avatars/" substring check below would otherwise (incorrectly) treat the
  // GLB as a 2D portrait image and render a broken <img>. Exclude GLBs explicitly.
  const isImageUrl = !isGlbUrl && !!(effectiveUrl && (effectiveUrl.endsWith('.png') || effectiveUrl.endsWith('.jpg') || effectiveUrl.endsWith('.jpeg') || effectiveUrl.includes('/avatars/')));



  // If character has a 2D image avatar, show portrait mode
  if (isImageUrl) {
    const emotionColors = {
      neutral: 'var(--accent-primary)',
      happy: 'var(--success)',
      excited: '#f59e0b',
      sad: '#6366f1',
      angry: 'var(--danger)',
      thinking: 'var(--accent-secondary)',
    };
    const glowColor = emotionColors[emotion] || emotionColors.neutral;

    return (
      <div className="avatar-canvas-wrapper">
        <div
          className={`avatar-portrait ${isStreaming ? 'avatar-portrait-streaming' : ''}`}
          style={{ '--avatar-glow-color': glowColor }}
        >
          <div className="avatar-portrait-ring" />
          <img
            src={effectiveUrl}
            alt="Character avatar"
            className="avatar-portrait-img"
            onError={handleError}
          />
          {isStreaming && (
            <div className="avatar-portrait-thinking">
              <span /><span /><span />
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="avatar-canvas-wrapper" onContextMenu={(e) => e.preventDefault()}>
      <Canvas
        camera={{ position: [0, 0.8, 5.5], fov: 35 }}
        gl={{
          antialias: true,
          alpha: true,
          powerPreference: 'high-performance',
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.15,
          outputColorSpace: THREE.SRGBColorSpace,
        }}
        dpr={[1, 2]}
        onError={handleError}
        style={{ width: '100%', height: '100%' }}
      >
        {/* Soft three-point lighting: warm key, cool fill, bright rim for separation */}
        <ambientLight intensity={0.3} />
        <directionalLight position={[3, 5, 4]} intensity={1.5} color="#fff4e6" />
        <directionalLight position={[-4, 2, 2]} intensity={0.5} color="#bcd2ff" />
        <directionalLight position={[0, 3, -5]} intensity={0.9} color="#ffffff" />

        {/* In-memory studio HDRI — realistic image-based lighting with NO external
            CDN fetch (critical for a self-hosted/offline deployment). This is what
            turns the flat solid-colour materials into believable surfaces. */}
        <Environment resolution={256} frames={1}>
          <Lightformer form="rect" intensity={2.2} position={[0, 3, 3]} scale={[9, 4, 1]} color="#ffffff" />
          <Lightformer form="rect" intensity={1.0} position={[-5, 1, 2]} scale={[4, 5, 1]} color="#cfe0ff" />
          <Lightformer form="rect" intensity={1.0} position={[5, 1, -3]} scale={[4, 5, 1]} color="#ffe8cc" />
          <Lightformer form="ring" intensity={0.5} position={[0, -2, 4]} scale={3} color="#ffffff" />
        </Environment>

        <Suspense fallback={null}>
          {isGlbUrl ? (
            <GLBErrorBoundary onError={handleError}>
              <GLBAvatar
                key={cacheBustedUrl}
                url={cacheBustedUrl}
                emotion={emotion}
                amplitudeRef={amplitudeRef}
                isStreaming={isStreaming}
                isPaused={isPaused}
              />
            </GLBErrorBoundary>
          ) : (
            <ProceduralAvatar
              emotion={emotion}
              amplitudeRef={amplitudeRef}
              isStreaming={isStreaming}
              isPaused={isPaused}
            />
          )}
        </Suspense>

        {/* Grounding contact shadow so the figure doesn't appear to float */}
        {isGlbUrl && (
          <ContactShadows
            position={[0, -1.45, 0]}
            opacity={0.35}
            scale={7}
            blur={2.8}
            far={4}
            resolution={512}
            color="#000000"
          />
        )}

        <OrbitControls
          enableZoom={true}
          enablePan={true}
          autoRotate={!isPaused}
          autoRotateSpeed={0.3}
          minPolarAngle={Math.PI / 6}
          maxPolarAngle={Math.PI / 1.4}
          minDistance={1.5}
          maxDistance={10}
          enableDamping={true}
          dampingFactor={0.05}
          mouseButtons={{
            LEFT: THREE.MOUSE.ROTATE,
            MIDDLE: THREE.MOUSE.DOLLY,
            RIGHT: THREE.MOUSE.PAN,
          }}
        />
      </Canvas>
    </div>
  );
}

