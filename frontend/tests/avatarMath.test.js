import test from 'node:test';
import assert from 'node:assert/strict';
import {
  QUALITY_PRESETS, applyFacialTargets, avatarAssetType, blinkWeight, cameraFrame,
  damp, dampingFactor, facialTargets, frameDelta, isHelperMesh, morphBindings,
  mpfbMaterialRole, shouldAnimate, simulatedAmplitude, waveformAmplitude,
} from '../src/lib/avatarMath.js';

test('asset detection preserves signed/versioned URLs and does not confuse GLB with portraits', () => {
  assert.equal(avatarAssetType('/avatars/greg_3d.GLB?v=7#head'), 'model');
  assert.equal(avatarAssetType('https://example.com/avatar.gltf?signature=abc'), 'model');
  assert.equal(avatarAssetType('/avatars/face.WEBP?version=2'), 'image');
  assert.equal(avatarAssetType('data:image/png;base64,abc'), 'image');
  assert.equal(avatarAssetType('/avatars/invalid.glb.exe'), 'fallback');
  assert.equal(avatarAssetType(null), 'fallback');
});

test('damping is monotonic, bounded, and approximately refresh-rate independent', () => {
  for (const delta of [0, -1, 1 / 60, 1 / 24, 60, Infinity, NaN]) {
    assert.ok(dampingFactor(8, delta) >= 0 && dampingFactor(8, delta) <= 1);
    assert.ok(damp(0.2, 0.8, 8, delta) >= 0.2 && damp(0.2, 0.8, 8, delta) <= 0.8);
  }
  assert.equal(frameDelta(120), 0.05);
  let at30 = 0; let at60 = 0;
  for (let i = 0; i < 30; i++) at30 = damp(at30, 1, 8, 1 / 30);
  for (let i = 0; i < 60; i++) at60 = damp(at60, 1, 8, 1 / 60);
  assert.ok(Math.abs(at30 - at60) < 1e-10);
});

test('one interpolation per facial target converges fully without resetting body defaults', () => {
  const weights = [0.79216, 0, 0, 0.3];
  const bindings = morphBindings({ '$md-body': 0, mouthSmileLeft: 1, jawOpen: 2, authoredShape: 3 }, weights);
  assert.equal(bindings.length, 2);
  for (let i = 0; i < 300; i++) applyFacialTargets(weights, bindings, { mouthSmileLeft: 0.6, jawOpen: 0.4 }, 1 / 30);
  assert.equal(weights[0], 0.79216);
  assert.equal(weights[3], 0.3);
  assert.ok(Math.abs(weights[1] - 0.6) < 1e-8);
  assert.ok(Math.abs(weights[2] - 0.4) < 1e-8);
  applyFacialTargets(weights, bindings, {}, 0, true);
  assert.equal(weights[1], 0);
  assert.equal(weights[2], 0);
});

test('authored facial rest weights survive neutral and invalid bindings are ignored', () => {
  const weights = [0.15, 0];
  const bindings = morphBindings({ mouthSmileLeft: 0, jawOpen: 99, eyeBlinkLeft: -1 }, weights);
  applyFacialTargets(weights, bindings, {}, 0, true);
  assert.deepEqual(weights, [0.15, 0]);
  applyFacialTargets(weights, bindings, { mouthSmileLeft: 5 }, 0, true);
  assert.equal(weights[0], 1);
});

test('blinks finish open and suppress eye-widening during closure', () => {
  for (let time = -0.1; time < 0.5; time += 0.001) assert.ok(blinkWeight(time) >= 0 && blinkWeight(time) <= 1);
  assert.equal(blinkWeight(-0.1), 0);
  assert.equal(blinkWeight(0.08), 1);
  assert.equal(blinkWeight(0.24), 0);
  assert.equal(facialTargets('excited', 0, 1).eyeWideLeft, 0);
  assert.equal(facialTargets('unknown', 5).jawOpen, 0.58);
});

test('RMS envelope rejects silence/DC offset and stays in range', () => {
  assert.equal(waveformAmplitude(new Uint8Array(128).fill(128)), 0);
  assert.equal(waveformAmplitude(new Uint8Array(128).fill(145)), 0);
  assert.equal(waveformAmplitude([]), 0);
  assert.ok(waveformAmplitude(Uint8Array.from([100, 156, 100, 156])) > 0.5);
  assert.equal(waveformAmplitude(Uint8Array.from([0, 255, 0, 255])), 1);
  for (let t = 0; t < 100; t += 0.03) assert.ok(simulatedAmplitude(t) >= 0 && simulatedAmplitude(t) <= 1);
});

test('portrait is closer than body; body framing contains width and height on narrow screens', () => {
  const bounds = { width: 1.7, height: 2.8, depth: 0.7 };
  for (const aspect of [0.3, 0.55, 1, 2.5]) {
    const portrait = cameraFrame(bounds, aspect, 'portrait');
    const body = cameraFrame(bounds, aspect, 'body');
    assert.ok(portrait.distance < body.distance);
    assert.ok(portrait.target[1] > body.target[1]);
    const availableHeight = 2 * (body.distance - bounds.depth / 2) * Math.tan(32 * Math.PI / 360);
    assert.ok(availableHeight >= bounds.height * 1.14 - 1e-8);
    assert.ok(availableHeight * aspect >= bounds.width * 1.14 - 1e-8);
  }
  assert.ok(Number.isFinite(cameraFrame({ width: 0, height: 0, depth: 0 }, 0).distance));
});

test('pause, hidden views and reduced motion all stop autonomous rendering', () => {
  assert.equal(shouldAnimate({}), true);
  assert.equal(shouldAnimate({ paused: true }), false);
  assert.equal(shouldAnimate({ reducedMotion: true }), false);
  assert.equal(shouldAnimate({ visible: false }), false);
  assert.equal(QUALITY_PRESETS.eco.shadow, 0);
  assert.ok(QUALITY_PRESETS.balanced.dpr < QUALITY_PRESETS.high.dpr);
  assert.equal(QUALITY_PRESETS.balanced.fps, 30);
});

test('MPFB repairs are scoped to known roles and include all bundled hairstyles', () => {
  assert.equal(mpfbMaterialRole('tiffany_3d.body', false), null);
  assert.equal(mpfbMaterialRole('customGlass', true), null);
  assert.equal(mpfbMaterialRole('eyelashGlass', true), null);
  assert.equal(mpfbMaterialRole('tiffany_3d.body', true), 'skin');
  assert.equal(mpfbMaterialRole('tiffany_3d.long01', true), 'cutout');
  assert.equal(mpfbMaterialRole('greg_3d.short01', true), 'cutout');
  assert.equal(mpfbMaterialRole('friendly_ai_3d.bob02', true), 'cutout');
  assert.equal(mpfbMaterialRole('greg_3d.male_casualsuit01', true), 'opaque');
  assert.equal(mpfbMaterialRole('eyewhite', true), 'eye');
  assert.equal(isHelperMesh('Human.high-poly'), true);
  assert.equal(isHelperMesh('Human.highpoly'), true);
  assert.equal(isHelperMesh('Human'), false);
});
