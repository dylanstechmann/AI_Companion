export const MAX_RECORDING_MS = 30_000;
export const SILENCE_MS = 2_000;
const MAX_RECORDING_BYTES = 8 * 1024 * 1024;

export function chooseRecordingMime(Recorder) {
  if (typeof Recorder?.isTypeSupported !== 'function') return '';
  return ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/webm']
    .find((mime) => {
      try { return Recorder.isTypeSupported(mime); } catch { return false; }
    }) || '';
}

export function recordingExtension(mime = '') {
  const type = mime.toLowerCase().split(';')[0].trim();
  return ({
    'audio/webm': 'webm', 'video/webm': 'webm',
    'audio/mp4': 'm4a', 'video/mp4': 'mp4',
    'audio/ogg': 'ogg', 'application/ogg': 'ogg',
    'audio/wav': 'wav', 'audio/x-wav': 'wav',
    'audio/mpeg': 'mp3', 'audio/aac': 'aac',
  })[type] || 'bin'; // Never label unknown bytes as WebM.
}

export function rmsVolume(data) {
  if (!data.length) return 0;
  return Math.sqrt(data.reduce((sum, value) => sum + (value - 128) ** 2, 0) / data.length);
}

export function segmentDecision({ now, startedAt, lastSpeechAt, hasSpeech, blocked }) {
  if (blocked) return 'discard';
  if (now - startedAt >= MAX_RECORDING_MS) return hasSpeech ? 'send' : 'discard';
  if (hasSpeech && now - lastSpeechAt >= SILENCE_MS) return 'send';
  return null;
}

export function stopTracks(stream) {
  stream?.getTracks().forEach((track) => { try { track.stop(); } catch { /* Already ended. */ } });
}

export function microphoneError(error) {
  if (error?.name === 'NotAllowedError' || error?.name === 'SecurityError') {
    return 'Microphone access was denied. Allow microphone access in your browser, then try again.';
  }
  if (error?.name === 'NotFoundError') return 'No microphone was found. Connect one and try again.';
  if (error?.name === 'NotReadableError') return 'The microphone is unavailable or in use by another app.';
  return error?.message || 'Voice input failed. The microphone has been muted. Please try again.';
}

/**
 * One recorder owns one chunk array. stop() resolves only after final
 * dataavailable + stop, so a replacement never steals or resets its chunks.
 * No persistent storage, object URLs, or background recording.
 */
export function createRecordingSegment(Recorder, stream, timers = globalThis) {
  const mimeType = chooseRecordingMime(Recorder);
  const recorder = mimeType ? new Recorder(stream, { mimeType }) : new Recorder(stream);
  let chunks = [];
  let bytes = 0;
  let discarded = false;
  let settled = false;
  let stopping = false;
  let stopTimer;
  let resolveResult;
  let rejectResult;
  const result = new Promise((resolve, reject) => {
    resolveResult = resolve;
    rejectResult = reject;
  });
  // A device error may precede the caller's stop(); attach a rejection handler now.
  result.catch(() => {});
  const finish = (error) => {
    if (settled) return;
    settled = true;
    timers.clearTimeout(stopTimer);
    recorder.ondataavailable = recorder.onstop = recorder.onerror = null;
    const actualMime = recorder.mimeType || chunks.find((chunk) => chunk.type)?.type || '';
    const blob = discarded || error ? null : new Blob(chunks, { type: actualMime });
    chunks = [];
    if (error) rejectResult(error);
    else resolveResult(blob);
  };
  recorder.ondataavailable = ({ data }) => {
    if (discarded || settled || !data?.size) return;
    bytes += data.size;
    if (bytes > MAX_RECORDING_BYTES) {
      discarded = true;
      chunks = [];
      try { recorder.stop(); } catch { /* Error below is authoritative. */ }
      finish(new Error('Voice recording exceeded its size limit. The microphone has been muted.'));
      return;
    }
    chunks.push(data);
  };
  recorder.onstop = () => finish();
  recorder.onerror = (event) => {
    try { if (recorder.state !== 'inactive') recorder.stop(); } catch { /* Cleanup continues. */ }
    finish(event.error || new Error('The microphone recording failed.'));
  };
  try { recorder.start(1000); } catch (error) {
    try { if (recorder.state !== 'inactive') recorder.stop(); } catch { /* Release stream at the session level. */ }
    finish(error);
    throw error;
  }
  return {
    result,
    stop(discard = false) {
      discarded ||= discard;
      if (discarded) chunks = [];
      if (!settled && !stopping) {
        stopping = true;
        stopTimer = timers.setTimeout(() => finish(new Error('The microphone did not finish recording.')), 5000);
        try {
          if (recorder.state !== 'inactive') recorder.stop();
          // An inactive recorder can still have its final events queued.
        } catch (error) { finish(error); }
      }
      return result;
    },
    cancel() {
      discarded = true;
      chunks = [];
      try { if (recorder.state !== 'inactive') recorder.stop(); } catch { /* Best effort. */ }
      finish();
    },
  };
}

/**
 * Serial capture -> final data -> upload -> next segment. While the assistant
 * replies or transcription is pending, tracks are disabled and no audio queues.
 * stop() also invalidates permission, recorder, and fetch continuations.
 */
export function createVoiceCapture({
  env = globalThis, onState = () => {}, onError = () => {},
  onTranscript = () => {}, isBlocked = () => false,
}) {
  let generation = 0;
  let active = false;
  let stream = null;
  let context = null;
  let source = null;
  let analyser = null;
  let segment = null;
  let pollTimer;
  let deadlineTimer;
  let uploadTimer;
  let controller;
  let busy = false;
  let speech = false;
  let lastSpeechAt = 0;
  let startedAt = 0;
  const current = (id) => active && generation === id && !env.document?.hidden;
  const tracksEnabled = (enabled) => stream?.getAudioTracks().forEach((track) => { track.enabled = enabled; });

  function stop() {
    active = false;
    generation += 1;
    env.clearTimeout(pollTimer);
    env.clearTimeout(deadlineTimer);
    env.clearTimeout(uploadTimer);
    controller?.abort();
    controller = null;
    segment?.cancel();
    segment = null;
    stopTracks(stream);
    stream = null;
    try { source?.disconnect(); analyser?.disconnect(); } catch { /* Already disconnected. */ }
    source = analyser = null;
    const oldContext = context;
    context = null;
    try { Promise.resolve(oldContext?.close()).catch(() => {}); } catch { /* Already closed. */ }
    busy = false;
    onState('muted');
  }
  function fail(error, id) {
    if (!active || generation !== id) return;
    stop();
    onError(microphoneError(error));
  }
  async function finishSegment(id, decision) {
    if (!current(id) || !segment || busy) return;
    busy = true;
    env.clearTimeout(deadlineTimer);
    const completed = segment;
    // Keep segment reachable until finalized so mute can cancel it immediately.
    tracksEnabled(false);
    try {
      let blob = await completed.stop(decision !== 'send');
      if (!current(id)) return;
      segment = null;
      if (blob?.size && decision === 'send' && !isBlocked()) {
        onState('processing');
        controller = new env.AbortController();
        const requestController = controller;
        let timedOut = false;
        const requestTimer = env.setTimeout(() => {
          timedOut = true;
          requestController.abort();
        }, 45_000);
        uploadTimer = requestTimer;
        const body = new env.FormData();
        body.append('file', blob, `recording.${recordingExtension(blob.type)}`);
        blob = null;
        let response;
        try {
          response = await env.fetch('/api/stt', {
            method: 'POST', body, signal: requestController.signal,
          });
          if (!response.ok) throw new Error(`Transcription failed (${response.status}). The microphone has been muted.`);
          const data = await response.json();
          if (timedOut) throw new Error('Transcription timed out. The microphone has been muted.');
          if (current(id) && !requestController.signal.aborted && !isBlocked() &&
              typeof data.text === 'string' && data.text.trim()) {
            onTranscript(data.text.trim());
          }
        } catch (error) {
          if (timedOut) throw new Error('Transcription timed out. The microphone has been muted.');
          throw error;
        } finally {
          env.clearTimeout(requestTimer);
          if (uploadTimer === requestTimer) uploadTimer = null;
          if (controller === requestController) controller = null;
        }
      }
      if (current(id)) {
        busy = false;
        onState('listening');
        // Yield for React to apply the reply/TTS state before considering capture.
        schedule(id);
      }
    } catch (error) { fail(error, id); }
  }
  function beginSegment(id) {
    tracksEnabled(true);
    segment = createRecordingSegment(env.MediaRecorder, stream, env);
    segment.result.catch((error) => fail(error, id));
    speech = false;
    startedAt = lastSpeechAt = Date.now();
    deadlineTimer = env.setTimeout(() => {
      void finishSegment(id, isBlocked() || !speech ? 'discard' : 'send');
    }, MAX_RECORDING_MS);
  }
  function schedule(id) {
    env.clearTimeout(pollTimer);
    if (current(id)) pollTimer = env.setTimeout(() => tick(id), 50);
  }
  function tick(id) {
    if (!current(id) || busy) return;
    try {
      if (isBlocked()) {
        tracksEnabled(false);
        if (segment) { void finishSegment(id, 'discard'); return; }
      } else {
        if (!segment) beginSegment(id);
        const data = new Uint8Array(analyser.fftSize);
        analyser.getByteTimeDomainData(data);
        const now = Date.now();
        if (rmsVolume(data) > 5) { speech = true; lastSpeechAt = now; }
        const decision = segmentDecision({ now, startedAt, lastSpeechAt, hasSpeech: speech, blocked: false });
        if (decision) { void finishSegment(id, decision); return; }
      }
      schedule(id);
    } catch (error) { fail(error, id); }
  }
  async function start() {
    if (active) return;
    const AudioContext = env.AudioContext || env.webkitAudioContext;
    if (env.isSecureContext === false || !env.navigator?.mediaDevices?.getUserMedia ||
        typeof env.MediaRecorder !== 'function' || typeof AudioContext !== 'function' ||
        typeof env.AbortController !== 'function') {
      onError('Voice input is unavailable. Use a supported browser over HTTPS and allow microphone access.');
      return;
    }
    if (env.document?.hidden) {
      onError('Return to this tab and click the microphone to start voice input.');
      return;
    }
    active = true;
    const id = ++generation;
    onState('starting');
    try {
      // Invoke resume during the explicit click, not after a permission dialog.
      const ctx = new AudioContext();
      context = ctx;
      const resumed = ctx.state === 'running' ? Promise.resolve() : Promise.resolve(ctx.resume());
      resumed.catch(() => {}); // Also handle a synchronous getUserMedia failure below.
      const permission = env.navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      }).then((granted) => {
        if (!current(id)) { stopTracks(granted); return null; }
        stream = granted;
        return granted;
      });
      const [, granted] = await Promise.all([resumed, permission]);
      if (!current(id) || !granted) return;
      if (ctx.state !== 'running') throw new Error('Microphone audio is suspended. Click the microphone to try again.');
      source = ctx.createMediaStreamSource(granted);
      analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      for (const track of granted.getTracks()) {
        track.addEventListener?.('ended', () => fail(new Error('The microphone disconnected. Connect it and try again.'), id), { once: true });
      }
      onState('listening');
      tick(id);
    } catch (error) { fail(error, id); }
  }
  return { start, stop, get active() { return active; } };
}
