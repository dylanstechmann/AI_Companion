import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createMediaGeneration, selectSpeechVoice, cleanSpeechText,
  decodeMediaAudio, registerMediaActions, setMediaPlaybackState,
} from '../src/lib/mediaPlayback.js';

const local = { voiceURI: 'local', localService: true, default: false, lang: 'en-US' };
const remote = { voiceURI: 'remote', localService: false, default: true, lang: 'en-US' };
const unknown = { voiceURI: 'unknown', default: true, lang: 'en-US' };

test('browser speech is local-only by default, including when the default voice is remote', () => {
  assert.equal(selectSpeechVoice([remote, local, unknown]), local);
  assert.throws(() => selectSpeechVoice([remote, unknown]), /No on-device/);
  assert.throws(() => selectSpeechVoice([remote, local], { voiceURI: 'remote' }), /not available on this device/);
  assert.throws(() => selectSpeechVoice([local], { voiceURI: 'missing' }), /not available/);
  assert.throws(() => selectSpeechVoice([]), /No on-device/);
});

test('remote browser speech requires explicit localOnly false', () => {
  assert.equal(selectSpeechVoice([remote, local], { localOnly: false }), remote);
  assert.equal(selectSpeechVoice([remote, local], { localOnly: false, voiceURI: 'remote' }), remote);
  for (const value of [undefined, null, 0, 'false']) {
    assert.equal(selectSpeechVoice([remote, local], { localOnly: value }), local);
  }
});

test('language selection stays within the local-only voice pool', () => {
  const french = { ...local, voiceURI: 'fr', lang: 'fr-FR' };
  assert.equal(selectSpeechVoice([remote, local, french], { lang: 'fr' }), french);
  assert.equal(selectSpeechVoice([remote, local], { lang: 'fr' }), local);
});

test('stop/replacement invalidates a pending decode token', async () => {
  const generation = createMediaGeneration();
  const oldToken = generation.next();
  let finishDecode;
  const decoded = decodeMediaAudio({
    decodeAudioData(_bytes, resolve) { finishDecode = resolve; },
  }, new ArrayBuffer(4));
  const replacement = generation.next();
  finishDecode({ duration: 1 });
  await decoded;
  assert.equal(generation.isCurrent(oldToken), false);
  assert.equal(generation.isCurrent(replacement), true);
  generation.next(); // Stop/unmount invalidates even the latest request.
  assert.equal(generation.isCurrent(replacement), false);
});

test('decode supports callback-only WebKit, promises, synchronous exceptions and failures', async () => {
  const buffer = { duration: 1 };
  assert.equal(await decodeMediaAudio({ decodeAudioData(_bytes, success) { success(buffer); } }, new ArrayBuffer(1)), buffer);
  assert.equal(await decodeMediaAudio({ decodeAudioData() { return Promise.resolve(buffer); } }, new ArrayBuffer(1)), buffer);
  await assert.rejects(decodeMediaAudio({ decodeAudioData() { throw new Error('bad data'); } }, new ArrayBuffer(1)), /bad data/);
  await assert.rejects(decodeMediaAudio({ decodeAudioData(_bytes, _success, fail) { fail(new Error('bad codec')); } }, new ArrayBuffer(1)), /bad codec/);
});

test('media session handlers are guarded and registered actions are cleaned up', () => {
  const calls = [];
  const session = {
    setActionHandler(action, handler) {
      if (action === 'stop') throw new Error('unsupported');
      calls.push([action, handler]);
    },
  };
  const play = () => {};
  const pause = () => {};
  const dispose = registerMediaActions(session, { play, pause, stop() {} });
  assert.deepEqual(calls, [['play', play], ['pause', pause]]);
  dispose();
  assert.deepEqual(calls.slice(2), [['play', null], ['pause', null]]);
  assert.doesNotThrow(() => registerMediaActions(undefined, {})());
  assert.doesNotThrow(() => registerMediaActions({}, {})());
  assert.doesNotThrow(() => setMediaPlaybackState({ set playbackState(_) { throw new Error(); } }, 'playing'));
  setMediaPlaybackState(session, 'paused');
  assert.equal(session.playbackState, 'paused');
});

test('speech text removes markup without retaining code or image URLs', () => {
  assert.equal(cleanSpeechText('**Hello** [friend](https://example.com)\n```js\nsecret()\n``` ![image](https://example.com/private.png)'),
    'Hello friend\n code block');
  assert.equal(cleanSpeechText(null), '');
});
