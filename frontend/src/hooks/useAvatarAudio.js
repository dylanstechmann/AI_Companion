import { useRef, useCallback, useEffect } from 'react';

/**
 * useAvatarAudio — Drives the avatar's mouth (lip-sync) amplitude.
 *
 * Returns:
 *   - amplitudeRef: a React ref whose `.current` holds the current mouth-open
 *     amplitude in the range [0, 1]. The 3D avatar reads this every frame to
 *     drive the `jawOpen` morph target.
 *   - startSimulation(): begin a simulated talking animation (used for browser
 *     speechSynthesis, where we have no access to the raw audio stream).
 *   - trackAnalyser(analyser): drive the mouth from a real Web Audio
 *     AnalyserNode (used for cloud TTS) for accurate lip-sync.
 *   - stopTracking(): stop the animation and ease the mouth closed.
 *
 * The simulation produces natural-looking, slightly randomized amplitude values
 * so the mouth appears to be forming syllables rather than flapping uniformly.
 */
export default function useAvatarAudio() {
  const amplitudeRef = useRef(0);
  const rafRef = useRef(null);
  const runningRef = useRef(false);
  const phaseRef = useRef(0);

  const stopTracking = useCallback(() => {
    runningRef.current = false;
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    // Ease the mouth closed.
    const close = () => {
      amplitudeRef.current *= 0.7;
      if (amplitudeRef.current > 0.01) {
        rafRef.current = requestAnimationFrame(close);
      } else {
        amplitudeRef.current = 0;
        rafRef.current = null;
      }
    };
    rafRef.current = requestAnimationFrame(close);
  }, []);

  const startSimulation = useCallback(() => {
    if (runningRef.current) return;
    runningRef.current = true;
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }

    let last = performance.now();
    const tick = (now) => {
      if (!runningRef.current) return;
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      phaseRef.current += dt;

      // Combine a couple of sine waves at different rates plus a touch of noise
      // to mimic the cadence of speech (open/close syllables).
      const t = phaseRef.current;
      const base = 0.5 + 0.5 * Math.sin(t * 11.0);
      const fast = 0.5 + 0.5 * Math.sin(t * 23.0 + 1.3);
      const noise = Math.random() * 0.25;
      let amp = base * 0.55 + fast * 0.25 + noise;
      // Occasional pauses between words.
      if (Math.sin(t * 2.3) < -0.6) amp *= 0.2;
      amplitudeRef.current = Math.max(0, Math.min(1, amp));

      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  /**
   * Drive the mouth from a live Web Audio AnalyserNode (real cloud-TTS audio).
   * Falls back to the simulation if no analyser is supplied.
   */
  const trackAnalyser = useCallback((analyser) => {
    if (!analyser) {
      startSimulation();
      return;
    }
    runningRef.current = true;
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }

    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      if (!runningRef.current) return;
      analyser.getByteTimeDomainData(data);
      // Root-mean-square of the waveform → perceived loudness.
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / data.length);
      // Map RMS to a mouth-open amount and smooth toward it.
      const target = Math.max(0, Math.min(1, rms * 3.2));
      amplitudeRef.current = amplitudeRef.current * 0.55 + target * 0.45;
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [startSimulation]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      runningRef.current = false;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return { amplitudeRef, startSimulation, trackAnalyser, stopTracking };
}