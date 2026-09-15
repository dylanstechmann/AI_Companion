import test from 'node:test';
import assert from 'node:assert/strict';
import { probeAvatarWebGL } from '../src/lib/avatarCapabilities.js';

test('WebGL2 capability failure degrades without a thrown renderer error', () => {
  assert.equal(probeAvatarWebGL(() => ({ getContext: () => null })), false);
  assert.equal(probeAvatarWebGL(() => ({ getContext() { throw new Error('GPU disabled'); } })), false);
});

test('successful capability probe releases its temporary GPU context', () => {
  let lost = false;
  let type;
  const supported = probeAvatarWebGL(() => ({
    getContext(value) {
      type = value;
      return { getExtension: () => ({ loseContext() { lost = true; } }) };
    },
  }));
  assert.equal(supported, true);
  assert.equal(type, 'webgl2');
  assert.equal(lost, true);
});
