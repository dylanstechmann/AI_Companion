import React, { useState, useRef, useEffect, useId } from 'react';
import { Mic, MicOff, Loader } from 'lucide-react';
import { createVoiceCapture } from '../lib/mediaRecording.js';

export default function VoiceRecorder({ onVoiceMessage, isStreaming, disabled = false }) {
  const [status, setStatus] = useState('muted');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const descriptionId = useId();
  const captureRef = useRef(null);
  const latestRef = useRef({ onVoiceMessage, isStreaming, disabled });
  latestRef.current = { onVoiceMessage, isStreaming, disabled };

  useEffect(() => {
    let mounted = true;
    const capture = createVoiceCapture({
      onState: (state) => { if (mounted) setStatus(state); },
      onError: (message) => { if (mounted) setError(message); },
      onTranscript: (text) => {
        if (mounted && !latestRef.current.disabled) latestRef.current.onVoiceMessage?.(text);
      },
      isBlocked: () => latestRef.current.isStreaming || latestRef.current.disabled,
    });
    captureRef.current = capture;
    const hide = () => {
      if (capture.active) {
        capture.stop();
        setNotice('Microphone muted because you left this tab. Click the microphone to resume.');
      }
    };
    const visibility = () => { if (document.hidden) hide(); };
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', hide);
    return () => {
      mounted = false;
      capture.stop();
      captureRef.current = null;
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', hide);
    };
  }, []);

  useEffect(() => {
    if (disabled) captureRef.current?.stop();
  }, [disabled]);

  const toggleMute = () => {
    const capture = captureRef.current;
    if (capture?.active) {
      capture.stop();
      setNotice('Microphone muted. Pending voice input was discarded.');
    } else if (!disabled) {
      setError('');
      setNotice('');
      void capture?.start(); // The only entry point: an explicit button click.
    }
  };
  const muted = status === 'muted';
  const label = status === 'starting' ? 'Cancel microphone access' :
    muted ? 'Enable hands-free voice input' : 'Mute microphone and discard pending voice input';

  return (
    <div className="voice-recorder" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', maxWidth: 'min(16rem, 32vw)', flexShrink: 0 }}>
      <button
        type="button"
        className={`icon-btn ${!muted ? 'recording glow-danger' : ''}`}
        onClick={toggleMute}
        disabled={disabled}
        title={label}
        aria-label={label}
        aria-pressed={!muted}
        aria-describedby={descriptionId}
        data-testid="button-voice-input"
      >
        {status === 'processing' || status === 'starting' ? (
          <Loader className="icon pulse-glow" aria-hidden="true" />
        ) : muted ? <MicOff className="icon" aria-hidden="true" /> : <Mic className="icon danger" aria-hidden="true" />}
      </button>
      <span id={descriptionId} role={error ? 'alert' : 'status'} aria-live={error ? 'assertive' : 'polite'}
        style={{ fontSize: '0.75rem', maxWidth: '16rem', overflowWrap: 'anywhere' }}>
        {error || notice || (status === 'starting' ? 'Waiting for microphone permission…' :
          status === 'processing' ? 'Transcribing…' : !muted ?
            (isStreaming ? 'Microphone paused during reply.' : 'Listening…') : '')}
      </span>
    </div>
  );
}
