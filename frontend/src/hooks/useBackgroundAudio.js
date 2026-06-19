import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * useBackgroundAudio — Manages TTS audio playback with Web Audio API
 * and navigator.mediaSession for lock-screen controls.
 *
 * Supports two TTS modes:
 *   - "browser": uses window.speechSynthesis (free, offline, robotic)
 *   - "cloud":   fetches audio from /api/tts and plays via Web Audio API
 *
 * Usage:
 *   const { playAudio, stopAudio, isPlaying, speakText, stopSpeaking, isSpeaking, getAvailableVoices } = useBackgroundAudio(characterName);
 */
export default function useBackgroundAudio(characterName = 'AI Companion') {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false); // browser TTS active
  const audioContextRef = useRef(null);
  const currentSourceRef = useRef(null);
  const silentIntervalRef = useRef(null);
  const audioElementRef = useRef(null);
  const voicesRef = useRef([]);
  // AnalyserNode for the currently-playing cloud-TTS clip. Exposed so the
  // avatar can lip-sync to the REAL audio amplitude instead of a simulation.
  const analyserRef = useRef(null);

  // Initialize AudioContext lazily (requires user gesture)
  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContextRef.current.state === 'suspended') {
      audioContextRef.current.resume();
    }
    return audioContextRef.current;
  }, []);

  // Set up media session metadata
  useEffect(() => {
    if ('mediaSession' in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: 'AI Companion',
        artist: characterName,
        album: 'AI Companion',
      });

      navigator.mediaSession.setActionHandler('play', () => {
        setIsPlaying(true);
      });

      navigator.mediaSession.setActionHandler('pause', () => {
        stopAudio();
      });

      navigator.mediaSession.setActionHandler('stop', () => {
        stopAudio();
      });
    }
  }, [characterName]);

  // ── Voice loading for browser TTS ──────────────────────────────────
  useEffect(() => {
    if (!('speechSynthesis' in window)) return;

    const loadVoices = () => {
      voicesRef.current = window.speechSynthesis.getVoices();
    };

    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;

    return () => {
      window.speechSynthesis.cancel();
    };
  }, []);

  // Play silent audio to keep the app alive in background (iOS/Android)
  const startSilentKeepAlive = useCallback(() => {
    if (silentIntervalRef.current) return;

    // Create a silent audio element for background keep-alive
    if (!audioElementRef.current) {
      const audio = new Audio();
      // Tiny silent WAV (base64)
      audio.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
      audio.loop = true;
      audio.volume = 0.01;
      audioElementRef.current = audio;
    }

    audioElementRef.current.play().catch(() => {
      // Autoplay blocked — will activate on next user interaction
    });

    silentIntervalRef.current = setInterval(() => {
      const ctx = audioContextRef.current;
      if (ctx && ctx.state === 'running') {
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        gain.gain.value = 0; // Silent
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.start();
        oscillator.stop(ctx.currentTime + 0.001);
      }
    }, 25000); // Every 25 seconds
  }, []);

  const stopSilentKeepAlive = useCallback(() => {
    if (silentIntervalRef.current) {
      clearInterval(silentIntervalRef.current);
      silentIntervalRef.current = null;
    }
    if (audioElementRef.current) {
      audioElementRef.current.pause();
    }
  }, []);

  /**
   * Play audio from an ArrayBuffer or Blob (cloud TTS response).
   */
  const playAudio = useCallback(async (audioData) => {
    try {
      const ctx = getAudioContext();

      // Stop any currently playing audio (including browser TTS)
      stopSpeaking();

      if (currentSourceRef.current) {
        try {
          currentSourceRef.current.stop();
        } catch {
          // Already stopped
        }
      }

      let arrayBuffer;
      if (audioData instanceof Blob) {
        arrayBuffer = await audioData.arrayBuffer();
      } else if (audioData instanceof ArrayBuffer) {
        arrayBuffer = audioData;
      } else if (typeof audioData === 'string') {
        // URL — fetch the audio
        const response = await fetch(audioData);
        arrayBuffer = await response.arrayBuffer();
      } else {
        throw new Error('Unsupported audio data format');
      }

      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;

      // Route through an AnalyserNode so consumers can read real-time amplitude
      // for accurate lip-sync: source -> analyser -> speakers.
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.6;
      source.connect(analyser);
      analyser.connect(ctx.destination);
      analyserRef.current = analyser;

      source.onended = () => {
        setIsPlaying(false);
        currentSourceRef.current = null;
        analyserRef.current = null;
        if ('mediaSession' in navigator) {
          navigator.mediaSession.playbackState = 'paused';
        }
      };

      currentSourceRef.current = source;
      source.start(0);
      setIsPlaying(true);
      startSilentKeepAlive();

      if ('mediaSession' in navigator) {
        navigator.mediaSession.playbackState = 'playing';
      }
    } catch (err) {
      console.error('Audio playback error:', err);
      setIsPlaying(false);
    }
  }, [getAudioContext, startSilentKeepAlive]);

  /**
   * Stop all audio playback (cloud TTS).
   */
  const stopAudio = useCallback(() => {
    if (currentSourceRef.current) {
      try {
        currentSourceRef.current.stop();
      } catch {
        // Already stopped
      }
      currentSourceRef.current = null;
    }
    analyserRef.current = null;
    setIsPlaying(false);
    stopSilentKeepAlive();

    if ('mediaSession' in navigator) {
      navigator.mediaSession.playbackState = 'paused';
    }
  }, [stopSilentKeepAlive]);

  // ── Browser-native TTS (SpeechSynthesis API) ───────────────────────

  /**
   * Speak text using the browser's built-in speechSynthesis.
   * Strips markdown/code blocks for cleaner speech.
   *
   * @param {string} text - The text to speak
   * @param {object} options - { rate, pitch, volume, voiceURI, lang }
   */
  const speakText = useCallback((text, options = {}) => {
    if (!('speechSynthesis' in window)) {
      console.warn('SpeechSynthesis not supported in this browser');
      return;
    }

    // Cancel any ongoing speech or cloud audio
    window.speechSynthesis.cancel();
    stopAudio();

    // Strip markdown for cleaner speech
    const cleanText = text
      .replace(/```[\s\S]*?```/g, ' code block ')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\*\*(.*?)\*\*/g, '$1')
      .replace(/!\[.*?\]\(.*?\)/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/[#*_~>]/g, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();

    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = options.rate ?? 1.0;
    utterance.pitch = options.pitch ?? 1.0;
    utterance.volume = options.volume ?? 1.0;

    // Select voice
    const voices = voicesRef.current.length
      ? voicesRef.current
      : window.speechSynthesis.getVoices();
    if (options.voiceURI) {
      const voice = voices.find((v) => v.voiceURI === options.voiceURI);
      if (voice) utterance.voice = voice;
    } else if (options.lang) {
      const voice = voices.find((v) => v.lang.startsWith(options.lang));
      if (voice) utterance.voice = voice;
    }

    utterance.onstart = () => {
      setIsSpeaking(true);
      startSilentKeepAlive();
    };

    utterance.onend = () => {
      setIsSpeaking(false);
      stopSilentKeepAlive();
    };

    utterance.onerror = (event) => {
      console.error('Speech synthesis error:', event.error);
      setIsSpeaking(false);
      stopSilentKeepAlive();
    };

    window.speechSynthesis.speak(utterance);
  }, [startSilentKeepAlive, stopAudio, stopSilentKeepAlive]);

  /**
   * Stop browser TTS playback.
   */
  const stopSpeaking = useCallback(() => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
  }, []);

  /**
   * Get available browser TTS voices.
   */
  const getAvailableVoices = useCallback(() => {
    if (!('speechSynthesis' in window)) return [];
    return voicesRef.current.length
      ? voicesRef.current
      : window.speechSynthesis.getVoices();
  }, []);

  /**
   * Stop ALL audio (both cloud and browser TTS).
   */
  const stopAll = useCallback(() => {
    stopAudio();
    stopSpeaking();
  }, [stopAudio, stopSpeaking]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopAudio();
      stopSpeaking();
      stopSilentKeepAlive();
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
      }
    };
  }, []);

  return {
    playAudio,
    stopAudio,
    isPlaying,
    speakText,
    stopSpeaking,
    isSpeaking,
    getAvailableVoices,
    stopAll,
    analyserRef,
  };
}
