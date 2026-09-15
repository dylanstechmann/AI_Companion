import { useState, useEffect, useRef, useCallback } from 'react';
import {
  cleanSpeechText, createMediaGeneration, decodeMediaAudio, selectSpeechVoice,
  registerMediaActions, setMediaPlaybackState,
} from '../lib/mediaPlayback.js';

/**
 * Audio is transient. No silent keepalive, storage, or implicit remote TTS.
 * playAudio resolves true only after playback starts; false on cancellation or
 * failure (audioError describes failures). speakText returns true when queued,
 * false on failure; later browser errors also appear in audioError.
 */
export default function useBackgroundAudio(characterName = 'AI Companion') {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [audioError, setAudioError] = useState('');
  const mountedRef = useRef(true);
  const audioContextRef = useRef(null);
  const currentSourceRef = useRef(null);
  const utteranceRef = useRef(null);
  const analyserRef = useRef(null);
  const voicesRef = useRef([]);
  const audioGeneration = useRef(createMediaGeneration());
  const speechGeneration = useRef(createMediaGeneration());
  const fetchControllerRef = useRef(null);
  const audioPausedRef = useRef(false);
  const speechPausedRef = useRef(false);
  const session = typeof navigator !== 'undefined' ? navigator.mediaSession : null;

  const reportError = useCallback((message) => {
    if (mountedRef.current) setAudioError(message);
  }, []);

  const syncSession = useCallback(() => {
    const playing = (currentSourceRef.current && !audioPausedRef.current) ||
      (utteranceRef.current && !speechPausedRef.current);
    const paused = currentSourceRef.current || utteranceRef.current;
    setMediaPlaybackState(session, playing ? 'playing' : paused ? 'paused' : 'none');
  }, [session]);

  const stopAudio = useCallback(() => {
    audioGeneration.current.next();
    fetchControllerRef.current?.abort();
    fetchControllerRef.current = null;
    const source = currentSourceRef.current;
    currentSourceRef.current = null;
    if (source) {
      source.onended = null;
      try { source.stop(); } catch { /* Source already finished. */ }
      try { source.disconnect(); } catch { /* Already disconnected. */ }
    }
    try { analyserRef.current?.disconnect(); } catch { /* Already disconnected. */ }
    analyserRef.current = null;
    audioPausedRef.current = false;
    if (mountedRef.current) setIsPlaying(false);
    syncSession();
  }, [syncSession]);

  const stopSpeaking = useCallback(() => {
    speechGeneration.current.next();
    const utterance = utteranceRef.current;
    utteranceRef.current = null;
    if (utterance) {
      utterance.onstart = utterance.onend = utterance.onerror = utterance.onpause = utterance.onresume = null;
      try { window.speechSynthesis?.cancel(); } catch { /* Browser shutting down. */ }
    }
    speechPausedRef.current = false;
    if (mountedRef.current) setIsSpeaking(false);
    syncSession();
  }, [syncSession]);

  const stopAll = useCallback(() => {
    stopAudio();
    stopSpeaking();
  }, [stopAudio, stopSpeaking]);

  const playAudio = useCallback(async (audioData) => {
    if (!mountedRef.current) return false;
    stopAll();
    reportError('');
    const token = audioGeneration.current.next();
    const current = () => mountedRef.current && audioGeneration.current.isCurrent(token);
    let source = null;
    let analyser = null;
    let requestController = null;
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (typeof AudioContext !== 'function') throw new Error('Audio playback is unavailable in this browser.');
      let ctx = audioContextRef.current;
      if (!ctx || ctx.state === 'closed') {
        ctx = new AudioContext();
        audioContextRef.current = ctx;
      }
      if (ctx.state !== 'running') await ctx.resume();
      if (!current()) return false;
      if (ctx.state !== 'running') throw new Error('Playback is blocked. Click a playback control to try again.');

      let bytes;
      if (audioData instanceof Blob) bytes = await audioData.arrayBuffer();
      else if (audioData instanceof ArrayBuffer) bytes = audioData.slice(0);
      else if (typeof audioData === 'string') {
        requestController = new AbortController();
        fetchControllerRef.current = requestController;
        const response = await fetch(audioData, { signal: requestController.signal });
        if (!response.ok) throw new Error(`Audio download failed (${response.status}).`);
        bytes = await response.arrayBuffer();
      } else throw new Error('Unsupported audio data format.');
      if (!current()) return false;
      const buffer = await decodeMediaAudio(ctx, bytes);
      // stopAll, a replacement clip, or unmount may have happened during decode.
      if (!current()) return false;
      if (ctx.state !== 'running') await ctx.resume();
      if (!current()) return false;
      if (ctx.state !== 'running') throw new Error('Playback is suspended. Click a playback control to try again.');
      source = ctx.createBufferSource();
      source.buffer = buffer;
      analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.6;
      source.connect(analyser);
      analyser.connect(ctx.destination);
      source.onended = () => {
        try { source.disconnect(); analyser.disconnect(); } catch { /* Already disconnected. */ }
        // An older source's queued end event must never clear a newer source.
        if (!current() || currentSourceRef.current !== source) return;
        currentSourceRef.current = null;
        analyserRef.current = null;
        audioPausedRef.current = false;
        setIsPlaying(false);
        syncSession();
      };
      currentSourceRef.current = source;
      analyserRef.current = analyser;
      source.start(0);
      setIsPlaying(true);
      syncSession();
      return true;
    } catch (error) {
      try { source?.disconnect(); analyser?.disconnect(); } catch { /* Cleanup continues. */ }
      if (current()) {
        stopAudio();
        reportError(error?.message || 'Audio playback failed. Try another voice or browser.');
      }
      return false;
    } finally {
      if (fetchControllerRef.current === requestController) fetchControllerRef.current = null;
    }
  }, [stopAll, stopAudio, reportError, syncSession]);

  const getAvailableVoices = useCallback(() => {
    try {
      voicesRef.current = window.speechSynthesis?.getVoices() || [];
      return [...voicesRef.current];
    } catch { return []; }
  }, []);

  useEffect(() => {
    const synth = window.speechSynthesis;
    if (!synth) return undefined;
    getAvailableVoices();
    // Do not overwrite Settings or another component's listener.
    synth.addEventListener?.('voiceschanged', getAvailableVoices);
    return () => synth.removeEventListener?.('voiceschanged', getAvailableVoices);
  }, [getAvailableVoices]);

  const speakText = useCallback((text, options = {}) => {
    if (!mountedRef.current) return false;
    stopAll();
    reportError('');
    const token = speechGeneration.current.next();
    const current = () => mountedRef.current && speechGeneration.current.isCurrent(token);
    try {
      const synth = window.speechSynthesis;
      if (!synth || typeof window.SpeechSynthesisUtterance !== 'function') {
        throw new Error('Browser speech playback is unavailable in this browser.');
      }
      const cleanText = cleanSpeechText(text);
      if (!cleanText) return false;
      const voice = selectSpeechVoice(getAvailableVoices(), options);
      const utterance = new window.SpeechSynthesisUtterance(cleanText);
      utterance.voice = voice; // Always explicit, including when localOnly defaults true.
      utterance.lang = options.lang || voice.lang;
      utterance.rate = options.rate ?? 1;
      utterance.pitch = options.pitch ?? 1;
      utterance.volume = options.volume ?? 1;
      utteranceRef.current = utterance;
      const isOwn = () => current() && utteranceRef.current === utterance;
      const finished = (event) => {
        if (!isOwn()) return;
        utteranceRef.current = null;
        speechPausedRef.current = false;
        utterance.onstart = utterance.onend = utterance.onerror = utterance.onpause = utterance.onresume = null;
        setIsSpeaking(false);
        syncSession();
        if (event?.error && !['canceled', 'interrupted'].includes(event.error)) {
          reportError(`Browser speech failed (${event.error}). Choose an available voice or try again.`);
        }
      };
      utterance.onstart = () => {
        if (isOwn()) { setIsSpeaking(true); syncSession(); }
      };
      utterance.onend = finished;
      utterance.onerror = finished;
      utterance.onpause = () => {
        if (isOwn()) { speechPausedRef.current = true; setIsSpeaking(false); syncSession(); }
      };
      utterance.onresume = () => {
        if (isOwn()) { speechPausedRef.current = false; setIsSpeaking(true); syncSession(); }
      };
      // Mark active while queued as well, so VAD never captures the start of TTS.
      setIsSpeaking(true);
      if (synth.paused) synth.resume();
      synth.speak(utterance);
      syncSession();
      return true;
    } catch (error) {
      if (current()) {
        stopSpeaking();
        reportError(error?.message || 'Browser speech playback failed.');
      }
      return false;
    }
  }, [stopAll, stopSpeaking, reportError, getAvailableVoices, syncSession]);

  const pause = useCallback(async () => {
    try {
      if (utteranceRef.current) {
        window.speechSynthesis.pause();
        speechPausedRef.current = true;
        if (mountedRef.current) setIsSpeaking(false);
      }
      const source = currentSourceRef.current;
      if (source) {
        await audioContextRef.current.suspend();
        if (mountedRef.current && currentSourceRef.current === source) {
          audioPausedRef.current = true;
          setIsPlaying(false);
        }
      }
      syncSession();
    } catch { reportError('This browser could not pause playback. Use Stop instead.'); }
  }, [reportError, syncSession]);

  const resume = useCallback(async () => {
    try {
      if (utteranceRef.current && speechPausedRef.current) {
        window.speechSynthesis.resume();
        speechPausedRef.current = false;
        if (mountedRef.current) setIsSpeaking(true);
      }
      const source = currentSourceRef.current;
      if (source && audioPausedRef.current) {
        const ctx = audioContextRef.current;
        await ctx.resume();
        if (mountedRef.current && currentSourceRef.current === source) {
          if (ctx.state !== 'running') throw new Error('Playback remains suspended.');
          audioPausedRef.current = false;
          setIsPlaying(true);
        }
      }
      syncSession(); // No source/utterance means no fictitious "playing" state.
    } catch { reportError('This browser could not resume playback. Try playing the message again.'); }
  }, [reportError, syncSession]);

  useEffect(() => {
    if (!session) return undefined;
    let metadata = null;
    try {
      if (typeof window.MediaMetadata === 'function') {
        metadata = new window.MediaMetadata({ title: 'AI Companion', artist: characterName, album: 'AI Companion' });
        session.metadata = metadata;
      }
    } catch { /* Metadata is optional, even if mediaSession exists. */ }
    const unregister = registerMediaActions(session, {
      play: () => { void resume(); }, pause: () => { void pause(); }, stop: stopAll,
    });
    return () => {
      unregister();
      try { if (metadata && session.metadata === metadata) session.metadata = null; } catch { /* Optional API. */ }
    };
  }, [characterName, session, pause, resume, stopAll]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopAll();
      const ctx = audioContextRef.current;
      audioContextRef.current = null;
      try { Promise.resolve(ctx?.close()).catch(() => {}); } catch { /* Already closed. */ }
      voicesRef.current = [];
    };
  }, [stopAll]);

  return {
    playAudio, stopAudio, isPlaying, speakText, stopSpeaking, isSpeaking,
    getAvailableVoices, stopAll, analyserRef, audioError,
  };
}
