import { useRef, useMemo, useEffect } from 'react';
import { createAvatarAudioDriver } from '../lib/avatarAudio.js';

/**
 * Audio-reactive mouth opening, not phoneme lip-sync. Cloud audio uses an RMS
 * envelope; speechSynthesis has no waveform and uses an illustrative cadence.
 * The ref API stays compatible with ChatArea. Renderers may setVisualActive()
 * on the ref to stop analysis while the avatar is paused, hidden or unmounted.
 * This hook never stops, disconnects or disposes the actual audio playback.
 */
export default function useAvatarAudio() {
  const amplitudeRef = useRef(0);
  const driver = useMemo(() => createAvatarAudioDriver({
    amplitudeRef,
    schedule: (callback) => window.setTimeout(callback, 1000 / 30),
    cancel: (id) => window.clearTimeout(id),
    now: () => performance.now(),
  }), []);

  // A stable optional renderer handshake, separate from the numeric .current.
  amplitudeRef.setVisualActive = driver.setVisualActive;

  useEffect(() => {
    const onVisibility = () => driver.setDocumentVisible(!document.hidden);
    onVisibility();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      driver.dispose();
    };
  }, [driver]);

  return {
    amplitudeRef,
    startSimulation: driver.startSimulation,
    trackAnalyser: driver.trackAnalyser,
    stopTracking: driver.stopTracking,
  };
}
