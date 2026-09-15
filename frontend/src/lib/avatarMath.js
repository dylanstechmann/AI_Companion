// Pure avatar policies: usable in Node tests without a browser or WebGL.
export const QUALITY_PRESETS = Object.freeze({
  eco: Object.freeze({ label: 'Eco', fps: 24, dpr: 1, environment: 64, shadow: 0 }),
  balanced: Object.freeze({ label: 'Balanced', fps: 30, dpr: 1.5, environment: 128, shadow: 256 }),
  high: Object.freeze({ label: 'High', fps: 60, dpr: 2, environment: 256, shadow: 512 }),
});

export const EMOTION_POSES = Object.freeze({
  neutral: {},
  happy: { mouthSmileLeft: 0.4, mouthSmileRight: 0.4, cheekSquintLeft: 0.15, cheekSquintRight: 0.15 },
  sad: { mouthFrownLeft: 0.28, mouthFrownRight: 0.28, browInnerUp: 0.22 },
  excited: { mouthSmileLeft: 0.6, mouthSmileRight: 0.6, eyeWideLeft: 0.2, eyeWideRight: 0.2 },
  thinking: { browInnerUp: 0.18, mouthShrugLower: 0.12, eyeSquintLeft: 0.08 },
  angry: { browDownLeft: 0.32, browDownRight: 0.32, mouthPressLeft: 0.2, mouthPressRight: 0.2 },
});

export const CONTROLLED_MORPHS = Object.freeze([
  'jawOpen', 'eyeBlinkLeft', 'eyeBlinkRight',
  'eyeWideLeft', 'eyeWideRight', 'eyeSquintLeft', 'eyeSquintRight',
  'browInnerUp', 'browDownLeft', 'browDownRight',
  'mouthSmileLeft', 'mouthSmileRight', 'mouthFrownLeft', 'mouthFrownRight',
  'mouthPressLeft', 'mouthPressRight', 'mouthShrugLower',
  'cheekSquintLeft', 'cheekSquintRight',
]);

export function clamp(value, min = 0, max = 1) {
  return Math.min(max, Math.max(min, Number.isFinite(value) ? value : min));
}

// A long background-tab delta must not overshoot weights or snap the rig.
export function frameDelta(delta) {
  return clamp(delta, 0, 0.05);
}

export function dampingFactor(rate, delta) {
  return 1 - Math.exp(-Math.max(0, rate) * frameDelta(delta));
}

export function damp(current, target, rate, delta) {
  return current + (target - current) * dampingFactor(rate, delta);
}

export function avatarAssetType(url) {
  if (typeof url !== 'string' || !url.trim()) return 'fallback';
  if (/^data:image\//i.test(url)) return 'image';
  const path = url.split(/[?#]/, 1)[0].toLowerCase();
  if (/\.(glb|gltf)$/.test(path)) return 'model';
  if (/\.(png|jpe?g|webp|avif|gif|svg)$/.test(path)) return 'image';
  return 'fallback';
}

export function shouldAnimate({ paused = false, reducedMotion = false, visible = true }) {
  return !paused && !reducedMotion && visible;
}

// Includes closed -> short hold -> slower opening; no frame-dependent phases.
export function blinkWeight(seconds) {
  const smooth = (t) => { const x = clamp(t); return x * x * (3 - 2 * x); };
  if (seconds < 0 || seconds >= 0.24) return 0;
  if (seconds < 0.065) return smooth(seconds / 0.065);
  if (seconds < 0.1) return 1;
  return 1 - smooth((seconds - 0.1) / 0.14);
}

export function facialTargets(emotion, amplitude = 0, blink = 0, thinking = false) {
  const pose = EMOTION_POSES[emotion] || EMOTION_POSES.neutral;
  const targets = { ...pose };
  targets.jawOpen = clamp(amplitude) * 0.58;
  targets.eyeBlinkLeft = clamp(blink);
  targets.eyeBlinkRight = clamp(blink);
  // Avoid wide eyes fighting closed lids, and strong smiles fighting speech.
  for (const key of ['eyeWideLeft', 'eyeWideRight']) targets[key] = (pose[key] || 0) * (1 - blink);
  for (const key of ['mouthSmileLeft', 'mouthSmileRight']) targets[key] = (pose[key] || 0) * (1 - clamp(amplitude) * 0.35);
  if (thinking) targets.browInnerUp = Math.max(targets.browInnerUp || 0, 0.14);
  return targets;
}

// Compile the allowlist once. Never touch body shape keys ($md-*), visemes we
// do not own, or any other authored defaults.
export function morphBindings(dictionary = {}, influences = []) {
  return CONTROLLED_MORPHS.flatMap((name) => {
    const index = dictionary[name];
    return Number.isInteger(index) && index >= 0 && index < influences.length
      ? [{ name, index, rest: clamp(influences[index]) }] : [];
  });
}

export function applyFacialTargets(influences, bindings, targets, delta, immediate = false) {
  for (const { name, index, rest } of bindings) {
    const target = clamp(rest + (targets[name] || 0));
    const current = clamp(influences[index]);
    // One interpolation per channel, not a reset followed by a second lerp.
    const rate = name.startsWith('eyeBlink') ? 45 : name === 'jawOpen' ? 20 : 7;
    influences[index] = immediate ? target : damp(current, target, rate, delta);
  }
}

export function waveformAmplitude(samples) {
  if (!samples?.length) return 0;
  // Remove DC offset so silence with an off-centre waveform remains silence.
  let mean = 0;
  for (let i = 0; i < samples.length; i++) mean += samples[i];
  mean /= samples.length;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += ((samples[i] - mean) / 128) ** 2;
  const rms = Math.sqrt(sum / samples.length);
  return clamp((rms - 0.012) * 4.5);
}

// This is explicitly a browser-speech cadence, not phoneme/viseme inference.
export function simulatedAmplitude(time) {
  const base = 0.5 + 0.5 * Math.sin(time * 11);
  const detail = 0.5 + 0.5 * Math.sin(time * 23 + 1.3);
  const pause = Math.sin(time * 2.3) < -0.55 ? 0.12 : 1;
  return clamp((base * 0.55 + detail * 0.25) * pause);
}

export function cameraFrame({ width = 1.6, height = 2.8, depth = 0.6 }, aspect = 1, view = 'portrait', fov = 32) {
  const h = Math.max(0.01, height);
  const w = Math.max(0.01, width);
  const portrait = view === 'portrait';
  const frameHeight = h * (portrait ? 0.36 : 1.14);
  const frameWidth = portrait ? Math.min(w, h * 0.29) : w * 1.14;
  const tan = Math.tan(clamp(fov, 10, 100) * Math.PI / 360);
  const distance = Math.max(frameHeight / 2 / tan, frameWidth / 2 / tan / Math.max(0.1, aspect)) + depth / 2;
  return { target: [0, h * (portrait ? 0.84 : 0.5), 0], distance, near: 0.01, far: Math.max(50, distance * 8) };
}

export function isHelperMesh(name = '') {
  return /(^|[._ -])(high[-_ ]?poly|helper(?:[-_ ]?cage)?)([._ -]|$)/i.test(name);
}

// Only known MPFB export roles are repaired; e.g. a custom glass material must
// retain its transparency, sidedness, metalness, maps and physical properties.
export function mpfbMaterialRole(name = '', isMPFB = false) {
  if (!isMPFB) return null;
  const n = name.toLowerCase();
  if (/(^|[._ -])(hair|long\d+|short\d+|bob\d+|eyelashes?|eyebrows?)([._ -]|$)/.test(n)) return 'cutout';
  if (/^(eye|eyewhite)$/.test(n)) return 'eye';
  if (/(^|[._ -])(body|skin|lips|ears|nipple|fingernails|teeth)([._ -]|$)/.test(n)) return 'skin';
  if (/(^|[._ -])(female_casualsuit\d+|male_casualsuit\d+|female_sportsuit\d+|shoes\d+)([._ -]|$)/.test(n)) return 'opaque';
  return null;
}
