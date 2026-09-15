import { clamp, damp, frameDelta, simulatedAmplitude, waveformAmplitude } from './avatarMath.js';

// Injectable clock/scheduler makes lifecycle and mode transitions testable
// without React, Web Audio or a real-time test.
export function createAvatarAudioDriver({ amplitudeRef, schedule, cancel, now }) {
  let timer = null;
  let mode = 'stopped';
  let analyser = null;
  let samples = null;
  let visualActive = true;
  let documentVisible = true;
  let last = now();
  let phase = 0;
  const active = () => visualActive && documentVisible;
  const unschedule = () => {
    if (timer !== null) cancel(timer);
    timer = null;
  };
  const tick = () => {
    timer = null;
    if (!active() || mode === 'stopped') return;
    const timestamp = now();
    const delta = frameDelta((timestamp - last) / 1000);
    last = timestamp;
    phase += delta;
    let target = 0;
    if (mode === 'analyser') {
      try {
        if (samples.length !== analyser.fftSize) samples = new Uint8Array(analyser.fftSize);
        analyser.getByteTimeDomainData(samples);
        target = waveformAmplitude(samples);
      } catch {
        // A detached analyser must not break playback or leave an open mouth.
        mode = 'closing';
        analyser = null;
        samples = null;
      }
    } else if (mode === 'simulation') {
      target = simulatedAmplitude(phase);
    }
    const current = clamp(amplitudeRef.current);
    amplitudeRef.current = damp(current, target, target > current ? 24 : 14, delta);
    if (mode === 'closing' && amplitudeRef.current < 0.005) {
      amplitudeRef.current = 0;
      mode = 'stopped';
    }
    if (mode !== 'stopped') timer = schedule(tick);
  };
  const resume = () => {
    unschedule();
    last = now();
    if (active() && mode !== 'stopped') timer = schedule(tick);
    else amplitudeRef.current = 0;
  };
  const startSimulation = () => {
    if (mode === 'simulation') return;
    mode = 'simulation';
    analyser = null;
    samples = null;
    phase = 0;
    resume();
  };
  return {
    startSimulation,
    trackAnalyser(next) {
      if (!next || typeof next.getByteTimeDomainData !== 'function') {
        startSimulation();
        return;
      }
      if (mode === 'analyser' && analyser === next) return;
      mode = 'analyser';
      analyser = next;
      samples = new Uint8Array(Math.max(1, next.fftSize || 2048));
      resume();
    },
    stopTracking() {
      unschedule();
      analyser = null;
      samples = null;
      mode = active() && amplitudeRef.current > 0.005 ? 'closing' : 'stopped';
      if (mode === 'stopped') amplitudeRef.current = 0;
      resume();
    },
    setVisualActive(value) {
      if (visualActive === Boolean(value)) return;
      visualActive = Boolean(value);
      resume();
    },
    setDocumentVisible(value) {
      if (documentVisible === Boolean(value)) return;
      documentVisible = Boolean(value);
      resume();
    },
    dispose() {
      unschedule();
      mode = 'stopped';
      analyser = null;
      samples = null;
      amplitudeRef.current = 0;
    },
  };
}
