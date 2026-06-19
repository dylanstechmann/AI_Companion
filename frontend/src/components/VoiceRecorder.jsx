import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Mic, MicOff, Loader } from 'lucide-react';

const SILENCE_THRESHOLD_MS = 2000; // 2 seconds of silence
const VOLUME_THRESHOLD = 5; // Minimal RMS volume out of 255 to trigger speaking

export default function VoiceRecorder({ onVoiceMessage, isStreaming, sttMode }) {
  const [isMuted, setIsMuted] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  
  const streamRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  
  // VAD refs
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const requestAnimationFrameRef = useRef(null);
  const isSpeakingRef = useRef(false);
  const lastSpokeTimeRef = useRef(0);
  
  // Keep track of streaming state inside the VAD loop
  const isStreamingRef = useRef(isStreaming);
  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      stopListening();
    };
  }, []);

  const stopListening = () => {
    if (requestAnimationFrameRef.current) {
      cancelAnimationFrame(requestAnimationFrameRef.current);
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.onstop = null;
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
  };

  const startListening = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        } 
      });
      streamRef.current = stream;

      // Set up AudioContext for volume analysis
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      analyserRef.current = analyser;

      startRecordingChunk();
      startVADLoop();
      setIsMuted(false);
    } catch (err) {
      console.error('Error accessing microphone:', err);
      alert('Could not access microphone. Please check permissions.');
      setIsMuted(true);
    }
  };

  const startRecordingChunk = () => {
    if (!streamRef.current) return;
    
    // Stop old one if exists
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.onstop = null;
        mediaRecorderRef.current.stop();
    }

    mediaRecorderRef.current = new MediaRecorder(streamRef.current);
    audioChunksRef.current = [];

    mediaRecorderRef.current.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunksRef.current.push(event.data);
      }
    };

    mediaRecorderRef.current.onstop = async () => {
      const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
      await sendAudioToServer(audioBlob);
    };

    mediaRecorderRef.current.start();
  };

  const startVADLoop = () => {
    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    
    const checkVolume = () => {
      // If muted or stream stopped, end loop
      if (!streamRef.current) return;

      analyserRef.current.getByteTimeDomainData(dataArray);
      
      // Calculate RMS (Root Mean Square) for volume
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        const val = (dataArray[i] - 128);
        sum += val * val;
      }
      const rms = Math.sqrt(sum / dataArray.length);

      const now = Date.now();

      // If AI is currently replying, ignore our own voice
      if (isStreamingRef.current) {
        // Just reset timers so we don't accidentally trigger a send right after it finishes
        isSpeakingRef.current = false;
        lastSpokeTimeRef.current = now;
      } else {
        if (rms > VOLUME_THRESHOLD) {
          isSpeakingRef.current = true;
          lastSpokeTimeRef.current = now;
        } else {
          if (isSpeakingRef.current) {
            // Check if silence exceeded threshold
            if (now - lastSpokeTimeRef.current > SILENCE_THRESHOLD_MS) {
              isSpeakingRef.current = false;
              // We finished speaking! Trigger audio processing
              if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
                 // Stop it to trigger the 'onstop' event and send data
                 mediaRecorderRef.current.stop();
                 // Immediately start a new recording chunk to catch the next phrase
                 startRecordingChunk();
              }
            }
          }
        }
      }

      requestAnimationFrameRef.current = requestAnimationFrame(checkVolume);
    };
    
    checkVolume();
  };

  const toggleMute = () => {
    if (isMuted) {
      startListening();
    } else {
      stopListening();
      setIsMuted(true);
    }
  };

  const sendAudioToServer = async (audioBlob) => {
    // If the chunk is extremely tiny, ignore it
    if (audioBlob.size < 500) return; 

    setIsProcessing(true);
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.webm');

    try {
      const response = await fetch('/api/stt', {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      if (data.text && data.text.trim()) {
        // VAD triggered send! We pass it up to auto-send
        if (onVoiceMessage) {
            onVoiceMessage(data.text.trim());
        }
      }
    } catch (error) {
      console.error('Error processing audio:', error);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <button 
      type="button"
      className={`icon-btn ${!isMuted ? 'recording glow-danger' : ''}`}
      onClick={toggleMute}
      title={isMuted ? "Unmute for hands-free mode" : "Mute microphone"}
    >
      {isProcessing ? (
         <Loader className="icon pulse-glow" />
      ) : !isMuted ? (
         <Mic className="icon danger pulse-glow" />
      ) : (
         <MicOff className="icon" />
      )}
    </button>
  );
}
