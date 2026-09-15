import test from 'node:test';
import assert from 'node:assert/strict';
import {
  chooseRecordingMime, recordingExtension, rmsVolume, segmentDecision,
  createRecordingSegment, createVoiceCapture, MAX_RECORDING_MS, SILENCE_MS,
} from '../src/lib/mediaRecording.js';

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const flush = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };

function fakeEnvironment({ permission, fetcher, resumeError } = {}) {
  let id = 0;
  const timers = new Map();
  const tracks = [{ enabled: true, stopped: false, stop() { this.stopped = true; }, addEventListener() {} }];
  const stream = { getTracks: () => tracks, getAudioTracks: () => tracks };
  const recorders = [];
  const contexts = [];
  let requested = 0;
  let volume = 128;
  class Recorder {
    static isTypeSupported(mime) { return mime === 'audio/mp4'; }
    constructor(_stream, options) {
      this.mimeType = options?.mimeType || 'audio/mp4';
      this.state = 'inactive';
      recorders.push(this);
    }
    start() { this.state = 'recording'; }
    stop() {
      this.state = 'inactive';
      queueMicrotask(() => {
        this.ondataavailable?.({ data: new Blob(['a'.repeat(600)], { type: this.mimeType }) });
        this.onstop?.();
      });
    }
  }
  class AudioContext {
    constructor() { this.state = 'suspended'; contexts.push(this); }
    async resume() {
      if (resumeError) throw resumeError;
      this.state = 'running';
    }
    async close() { this.state = 'closed'; }
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createAnalyser() {
      return { fftSize: 512, disconnect() {}, getByteTimeDomainData(data) { data.fill(volume); } };
    }
  }
  const env = {
    isSecureContext: true, document: { hidden: false },
    navigator: { mediaDevices: { getUserMedia() { requested++; return permission?.promise || Promise.resolve(stream); } } },
    AudioContext, MediaRecorder: Recorder, FormData, AbortController,
    setTimeout(fn, delay) { timers.set(++id, { fn, delay }); return id; },
    clearTimeout(timer) { timers.delete(timer); },
    fetch: fetcher || (async () => ({ ok: true, json: async () => ({ text: 'hello' }) })),
  };
  return {
    env, recorders, contexts, tracks, stream, timers,
    get requested() { return requested; },
    speak() { volume = 140; },
    runTimer(delay) {
      const entry = [...timers.entries()].find(([, timer]) => timer.delay === delay);
      assert.ok(entry, `Expected a ${delay}ms timer`);
      timers.delete(entry[0]);
      entry[1].fn();
    },
  };
}

test('MIME selection detects support, including Safari MP4 and Firefox Ogg', () => {
  assert.equal(chooseRecordingMime({ isTypeSupported: (mime) => mime === 'audio/mp4' }), 'audio/mp4');
  assert.equal(chooseRecordingMime({ isTypeSupported: (mime) => mime === 'audio/ogg;codecs=opus' }), 'audio/ogg;codecs=opus');
  assert.equal(chooseRecordingMime({}), '');
  assert.equal(chooseRecordingMime({ isTypeSupported() { throw new Error(); } }), '');
  assert.equal(recordingExtension('audio/mp4;codecs=mp4a.40.2'), 'm4a');
  assert.equal(recordingExtension('audio/ogg;codecs=opus'), 'ogg');
  assert.equal(recordingExtension('audio/webm;codecs=opus'), 'webm');
  assert.equal(recordingExtension(''), 'bin');
});

test('silence is bounded and discarded; speech is segmented; blocked input is always discarded', () => {
  const state = { now: MAX_RECORDING_MS, startedAt: 0, lastSpeechAt: MAX_RECORDING_MS, hasSpeech: false, blocked: false };
  assert.equal(segmentDecision(state), 'discard');
  assert.equal(segmentDecision({ ...state, hasSpeech: true }), 'send');
  assert.equal(segmentDecision({ ...state, hasSpeech: true, blocked: true }), 'discard');
  assert.equal(segmentDecision({ ...state, now: SILENCE_MS, hasSpeech: true, lastSpeechAt: 0 }), 'send');
  assert.equal(segmentDecision({ ...state, now: SILENCE_MS - 1, hasSpeech: true, lastSpeechAt: 0 }), null);
  assert.equal(rmsVolume(new Uint8Array([128, 128])), 0);
  assert.equal(rmsVolume(new Uint8Array([140, 116])), 12);
});

test('each recorder retains its own late chunks and actual MIME', async () => {
  const f = fakeEnvironment();
  const a = createRecordingSegment(f.env.MediaRecorder, f.stream, f.env);
  const resultA = a.stop();
  const b = createRecordingSegment(f.env.MediaRecorder, f.stream, f.env);
  f.recorders[1].mimeType = 'audio/ogg;codecs=opus';
  const resultB = b.stop();
  const [blobA, blobB] = await Promise.all([resultA, resultB]);
  assert.equal(blobA.type, 'audio/mp4');
  assert.equal(blobB.type, 'audio/ogg;codecs=opus');
  assert.equal(blobA.size, 600);
  assert.equal(blobB.size, 600);
  assert.equal(f.timers.size, 0);
});

test('unknown recorder MIME uses the actual chunk type, never forced WebM', async () => {
  class Recorder {
    constructor() { this.state = 'inactive'; this.mimeType = ''; }
    start() { this.state = 'recording'; }
    stop() {
      this.state = 'inactive';
      queueMicrotask(() => {
        this.ondataavailable?.({ data: new Blob(['mp4 bytes'], { type: 'audio/mp4' }) });
        this.onstop?.();
      });
    }
  }
  const segment = createRecordingSegment(Recorder, {});
  assert.equal((await segment.stop()).type, 'audio/mp4');
});

test('capture never asks permission before start and stops tracks granted after mute', async () => {
  const permission = deferred();
  const f = fakeEnvironment({ permission });
  const capture = createVoiceCapture({ env: f.env });
  assert.equal(f.requested, 0);
  const starting = capture.start();
  assert.equal(f.requested, 1);
  await capture.start(); // A double-click cannot start a second permission request.
  assert.equal(f.requested, 1);
  capture.stop();
  permission.resolve(f.stream);
  await starting;
  assert.equal(f.tracks[0].stopped, true);
  assert.equal(f.contexts[0].state, 'closed');
  assert.equal(f.recorders.length, 0);
});

test('failed AudioContext resume cleans up even when permission resolves later', async () => {
  const permission = deferred();
  const f = fakeEnvironment({ permission, resumeError: new Error('Audio blocked') });
  const errors = [];
  const capture = createVoiceCapture({ env: f.env, onError: (error) => errors.push(error) });
  await capture.start();
  permission.resolve(f.stream);
  await flush();
  assert.equal(f.tracks[0].stopped, true);
  assert.equal(f.contexts[0].state, 'closed');
  assert.equal(capture.active, false);
  assert.deepEqual(errors, ['Audio blocked']);
});

test('silent capture rotates after its hard deadline without uploading', async () => {
  let uploads = 0;
  const f = fakeEnvironment({ fetcher: async () => { uploads++; throw new Error('Must not upload silence'); } });
  const capture = createVoiceCapture({ env: f.env });
  await capture.start();
  assert.equal(f.recorders.length, 1);
  f.runTimer(MAX_RECORDING_MS);
  await flush();
  assert.equal(uploads, 0);
  assert.equal(f.recorders.length, 1); // No replacement until final stop was delivered.
  f.runTimer(50);
  assert.equal(f.recorders.length, 2);
  capture.stop();
  assert.equal(f.timers.size, 0);
});

test('mute aborts in-flight transcription and prevents a late callback or restart', async () => {
  const response = deferred();
  let signal, submittedFile;
  const f = fakeEnvironment({ fetcher: async (_url, options) => {
    signal = options.signal;
    submittedFile = options.body.get('file');
    return response.promise;
  } });
  f.speak();
  const messages = [];
  const capture = createVoiceCapture({ env: f.env, onTranscript: (text) => messages.push(text) });
  await capture.start();
  f.runTimer(MAX_RECORDING_MS);
  await flush();
  assert.equal(submittedFile.name, 'recording.m4a');
  assert.equal(submittedFile.type, 'audio/mp4');
  assert.equal(f.tracks[0].enabled, false);
  assert.equal(f.recorders.length, 1);
  capture.stop();
  assert.equal(signal.aborted, true);
  response.resolve({ ok: true, json: async () => ({ text: 'do not send me' }) });
  await flush();
  assert.deepEqual(messages, []);
  assert.equal(f.recorders.length, 1);
  assert.equal(f.tracks[0].stopped, true);
  assert.equal(f.timers.size, 0);
});

test('assistant playback suppresses recording and discards a segment already in progress', async () => {
  const f = fakeEnvironment();
  f.speak();
  let blocked = true;
  const capture = createVoiceCapture({ env: f.env, isBlocked: () => blocked });
  await capture.start();
  assert.equal(f.recorders.length, 0);
  assert.equal(f.tracks[0].enabled, false);
  blocked = false;
  f.runTimer(50);
  assert.equal(f.recorders.length, 1);
  blocked = true;
  f.runTimer(50);
  await flush();
  assert.equal(f.tracks[0].enabled, false);
  assert.equal(f.recorders.length, 1);
  capture.stop();
});

test('unsupported APIs and hidden tabs fail without permission prompts', async () => {
  const f = fakeEnvironment();
  const errors = [];
  f.env.MediaRecorder = undefined;
  const capture = createVoiceCapture({ env: f.env, onError: (error) => errors.push(error) });
  await capture.start();
  assert.equal(f.requested, 0);
  assert.match(errors[0], /supported browser/);
  const hidden = fakeEnvironment();
  hidden.env.document.hidden = true;
  await createVoiceCapture({ env: hidden.env }).start();
  assert.equal(hidden.requested, 0);
});

test('recorder setup failure stops tracks and closes the audio context', async () => {
  const f = fakeEnvironment();
  f.env.MediaRecorder.prototype.start = function () { throw new Error('Unsupported codec'); };
  const errors = [];
  const capture = createVoiceCapture({ env: f.env, onError: (error) => errors.push(error) });
  await capture.start();
  assert.equal(capture.active, false);
  assert.equal(f.tracks[0].stopped, true);
  assert.equal(f.contexts[0].state, 'closed');
  assert.equal(f.timers.size, 0);
  assert.deepEqual(errors, ['Unsupported codec']);
});

test('recording size cap fails closed and releases the chunks', async () => {
  const f = fakeEnvironment();
  const segment = createRecordingSegment(f.env.MediaRecorder, f.stream, f.env);
  f.recorders[0].ondataavailable({ data: new Blob([new Uint8Array(8 * 1024 * 1024 + 1)]) });
  await assert.rejects(segment.result, /size limit/);
  assert.equal(f.recorders[0].state, 'inactive');
  assert.equal(f.recorders[0].ondataavailable, null);
});

test('a missing recorder stop event times out instead of hanging capture', async () => {
  const f = fakeEnvironment();
  f.env.MediaRecorder.prototype.stop = function () { this.state = 'inactive'; };
  const segment = createRecordingSegment(f.env.MediaRecorder, f.stream, f.env);
  const result = segment.stop();
  f.runTimer(5000);
  await assert.rejects(result, /did not finish/);
  assert.equal(f.recorders[0].onstop, null);
});

test('transcription failures mute, stop tracks, close audio and show an actionable error', async () => {
  const f = fakeEnvironment({ fetcher: async () => ({ ok: false, status: 503 }) });
  f.speak();
  const errors = [];
  const capture = createVoiceCapture({ env: f.env, onError: (error) => errors.push(error) });
  await capture.start();
  f.runTimer(MAX_RECORDING_MS);
  await flush();
  assert.equal(capture.active, false);
  assert.equal(f.tracks[0].stopped, true);
  assert.equal(f.contexts[0].state, 'closed');
  assert.equal(f.timers.size, 0);
  assert.match(errors[0], /503.*muted/);
});

test('a stale upload cannot clear the timeout belonging to a new listening session', async () => {
  const first = deferred(), second = deferred();
  let uploads = 0;
  const f = fakeEnvironment({ fetcher: () => (++uploads === 1 ? first.promise : second.promise) });
  f.speak();
  const messages = [];
  const capture = createVoiceCapture({ env: f.env, onTranscript: (text) => messages.push(text) });
  await capture.start();
  f.runTimer(MAX_RECORDING_MS);
  await flush();
  capture.stop();
  await capture.start();
  f.runTimer(MAX_RECORDING_MS);
  await flush();
  first.resolve({ ok: true, json: async () => ({ text: 'stale' }) });
  await flush();
  assert.deepEqual(messages, []);
  assert.equal([...f.timers.values()].some((timer) => timer.delay === 45_000), true);
  capture.stop();
  second.resolve({ ok: true, json: async () => ({ text: 'also stale' }) });
  await flush();
  assert.deepEqual(messages, []);
});
