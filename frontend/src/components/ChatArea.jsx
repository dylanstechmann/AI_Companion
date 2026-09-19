import { useEffect, useRef, useState, useCallback } from 'react';
import { Send, MessageSquare, Eye, EyeOff, Pause, Play } from 'lucide-react';
import VoiceRecorder from './VoiceRecorder.jsx';
import ImageCapture from './ImageCapture.jsx';
import HumanAvatar3D from './HumanAvatar3D.jsx';
import CodePanel from './CodePanel.jsx';
import useSSE from '../hooks/useSSE.js';
import useBackgroundAudio from '../hooks/useBackgroundAudio.js';
import useSentiment from '../hooks/useSentiment.js';
import useAvatarAudio from '../hooks/useAvatarAudio.js';

function getTTSSettings() {
  try {
    return {
      enabled: localStorage.getItem('tts_enabled') !== 'false',
      mode: localStorage.getItem('tts_mode') || 'browser',
      voice: localStorage.getItem('tts_voice') || 'alloy',
      rate: parseFloat(localStorage.getItem('tts_rate')) || 1.0,
      voiceURI: localStorage.getItem('tts_voiceURI') || '',
    };
  } catch {
    return { enabled: true, mode: 'browser', voice: 'alloy', rate: 1.0, voiceURI: '' };
  }
}

export default function ChatArea({ character, characterId }) {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [pendingImage, setPendingImage] = useState(null);
  const [streamingText, setStreamingText] = useState('');
  const [showAvatar, setShowAvatar] = useState(
    localStorage.getItem('show_avatar') !== 'false'
  );
  const [avatarPaused, setAvatarPaused] = useState(
    localStorage.getItem('avatar_paused') === 'true'
  );
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const { startStream, isStreaming } = useSSE();
  const { playAudio, speakText, isSpeaking, isPlaying, stopAll, analyserRef } = useBackgroundAudio(character?.name);
  const { emotion, analyze, reset: resetEmotion } = useSentiment();
  const { amplitudeRef, startSimulation, trackAnalyser, stopTracking } = useAvatarAudio();

  // Toggle avatar visibility
  const toggleAvatar = useCallback(() => {
    const newVal = !showAvatar;
    setShowAvatar(newVal);
    localStorage.setItem('show_avatar', String(newVal));
  }, [showAvatar]);

  // Toggle avatar animation (pause to save compute)
  const toggleAvatarPause = useCallback(() => {
    const newVal = !avatarPaused;
    setAvatarPaused(newVal);
    localStorage.setItem('avatar_paused', String(newVal));
    if (newVal) stopTracking();
  }, [avatarPaused, stopTracking]);

  // Fetch messages when character changes
  useEffect(() => {
    if (!characterId) return;
    setMessages([]);
    setStreamingText('');
    resetEmotion();

    const fetchMessages = async () => {
      try {
        const res = await fetch(`/api/characters/${characterId}/messages`);
        if (res.ok) {
          const data = await res.json();
          const list = Array.isArray(data) ? data : data.messages || [];
          setMessages(list);
        }
      } catch (err) {
        console.warn('Could not fetch messages:', err.message);
      }
    };

    fetchMessages();
  }, [characterId, resetEmotion]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  // Avatar lip sync during TTS.
  // Cloud TTS plays through the Web Audio API, so we can drive the mouth from
  // the REAL audio amplitude (analyserRef). Browser speechSynthesis exposes no
  // stream, so it falls back to the simulated cadence.
  useEffect(() => {
    if (isPlaying && analyserRef?.current) {
      trackAnalyser(analyserRef.current);
    } else if (isSpeaking || isPlaying) {
      startSimulation();
    } else {
      stopTracking();
    }
  }, [isSpeaking, isPlaying, startSimulation, trackAnalyser, stopTracking, analyserRef]);

  const speakResponse = useCallback(async (text) => {
    const tts = getTTSSettings();
    if (!tts.enabled || !text) return;

    if (tts.mode === 'cloud') {
      try {
        const res = await fetch('/api/tts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, voice: tts.voice, speed: tts.rate }),
        });
        if (res.ok) {
          const blob = await res.blob();
          await playAudio(blob);
          return;
        }
      } catch (err) {
        console.warn('Cloud TTS error, falling back to browser TTS:', err);
      }
    }

    speakText(text, { rate: tts.rate, voiceURI: tts.voiceURI });
  }, [playAudio, speakText]);

  const handleSend = useCallback(async (overrideText = null) => {
    const text = typeof overrideText === 'string' ? overrideText.trim() : inputText.trim();
    if (!text && !pendingImage) return;
    if (!characterId) return;

    const userMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: text,
      image_url: pendingImage ? URL.createObjectURL(pendingImage) : null,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    if (typeof overrideText !== 'string') setInputText('');
    setStreamingText('');
    if (inputRef.current) inputRef.current.style.height = 'auto';

    if (pendingImage) {
      setPendingImage(null);
      try {
        const formData = new FormData();
        formData.append('message', text);
        formData.append('character_id', characterId);
        formData.append('file', pendingImage);

        const res = await fetch('/api/chat/image', {
          method: 'POST',
          body: formData,
        });
        if (!res.ok) throw new Error('Image chat request failed');

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let imgAccumulated = '';
        let sseBuffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          sseBuffer += decoder.decode(value, { stream: true });
          const sseLines = sseBuffer.split('\n');
          sseBuffer = sseLines.pop() || '';

          for (const line of sseLines) {
            if (line.startsWith('data: ')) {
              const sseData = line.slice(6);
              if (sseData === '[DONE]') break;
              try {
                const parsed = JSON.parse(sseData);
                imgAccumulated += parsed.text || parsed.content || parsed.delta || '';
              } catch {
                imgAccumulated += sseData;
              }
              setStreamingText(imgAccumulated);
            }
          }
        }

        if (imgAccumulated) {
          setMessages((prev) => [...prev, {
            id: `msg-${Date.now()}-resp`,
            role: 'assistant',
            content: imgAccumulated,
            timestamp: new Date().toISOString(),
          }]);
          setStreamingText('');
          analyze(imgAccumulated);
          speakResponse(imgAccumulated);
        }
      } catch (err) {
        console.error('Image chat error:', err);
        setMessages((prev) => [...prev, {
          id: `msg-${Date.now()}-err`,
          role: 'assistant',
          content: 'Sorry, I encountered an error processing your image.',
          timestamp: new Date().toISOString(),
        }]);
      }
      return;
    }

    let accumulated = '';
    startStream(
      '/api/chat',
      { character_id: characterId, message: text },
      (chunk) => {
        const newText = chunk.text || chunk.content || chunk.delta || '';
        accumulated += newText;
        setStreamingText(accumulated);
      },
      () => {
        setMessages((prev) => [...prev, {
          id: `msg-${Date.now()}-resp`,
          role: 'assistant',
          content: accumulated,
          timestamp: new Date().toISOString(),
        }]);
        setStreamingText('');
        analyze(accumulated);
        speakResponse(accumulated);
      }
    );
  }, [inputText, pendingImage, characterId, startStream, speakResponse, analyze]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e) => {
    setInputText(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 150) + 'px';
  };

  const handleVoiceMessage = useCallback((text) => { handleSend(text); }, [handleSend]);
  const handleImageSelect = useCallback((file) => { setPendingImage(file); }, []);

  // Render code blocks with CodePanel, regular text as paragraphs
  const renderContent = (content) => {
    if (!content) return null;

    const parts = content.split(/(```[\s\S]*?```)/g);

    return parts.map((part, i) => {
      // Properly closed code block: ```...```
      if (part.startsWith('```') && part.endsWith('```')) {
        const code = part.slice(3, -3);
        const firstNewline = code.indexOf('\n');
        const language = firstNewline > -1 ? code.slice(0, firstNewline).trim().toLowerCase() : '';
        const codeBody = firstNewline > -1 ? code.slice(firstNewline + 1) : code;
        const lang = (language === 'js' || language === 'javascript') ? 'javascript' : 'python';

        return (
          <div key={i} className="code-block-wrapper">
            <pre><code>{codeBody || language}</code></pre>
            <CodePanel language={lang} code={codeBody || code} />
          </div>
        );
      }

      // Unclosed code block: starts with ``` but no closing (streaming or LLM quirk)
      if (part.startsWith('```')) {
        const code = part.slice(3);
        const firstNewline = code.indexOf('\n');
        const language = firstNewline > -1 ? code.slice(0, firstNewline).trim().toLowerCase() : '';
        const codeBody = firstNewline > -1 ? code.slice(firstNewline + 1) : code;
        const lang = (language === 'js' || language === 'javascript') ? 'javascript' : 'python';

        if (codeBody.trim()) {
          return (
            <div key={i} className="code-block-wrapper">
              <pre><code>{codeBody}</code></pre>
              <CodePanel language={lang} code={codeBody} />
            </div>
          );
        }
      }

      return part.split('\n').map((line, j) => {
        if (!line) return <br key={`${i}-${j}`} />;
        const formatted = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        const withCode = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
        return (
          <p key={`${i}-${j}`} dangerouslySetInnerHTML={{ __html: withCode }} />
        );
      });
    });
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    try {
      let date;
      if (typeof timestamp === 'number') {
        date = new Date(timestamp);
      } else if (typeof timestamp === 'string') {
        const normalized = timestamp.includes('T') ? timestamp : timestamp.replace(' ', 'T');
        date = new Date(normalized);
      } else {
        date = new Date(timestamp);
      }
      if (isNaN(date.getTime())) return '';
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const aiActive = isStreaming || isSpeaking || isPlaying;

  return (
    <div className="chat-area">
      <div className="chat-with-avatar">
        {/* Avatar Panel */}
        {showAvatar && (
          <div className="avatar-panel">
            <HumanAvatar3D
              emotion={emotion}
              amplitudeRef={amplitudeRef}
              isStreaming={isStreaming}
              isPaused={avatarPaused}
              characterName={character?.name}
              avatarUrl={character?.avatar_3d_url || character?.avatar_url}
              clothingStyle={character?.clothing_style || 'casual'}
              clothingDescription={character?.clothing_description || ''}
              bodyType={character?.body_type || 'athletic'}
            />
            <div className="avatar-info">
              <span className="avatar-name">{character?.name || 'AI'}</span>
              <span className="avatar-emotion">{emotion}</span>
            </div>
            {/* Pause/Play avatar animation button */}
            <button
              className="avatar-pause-btn"
              onClick={toggleAvatarPause}
              title={avatarPaused ? 'Resume animation' : 'Pause animation (save compute)'}
            >
              {avatarPaused ? <Play size={14} /> : <Pause size={14} />}
              {avatarPaused ? 'Resume' : 'Pause'}
            </button>
            {/* Zoom hint */}
            <span className="avatar-zoom-hint" style={{ fontSize: '10px', color: 'var(--text-secondary)', opacity: 0.6 }}>
              Scroll = zoom · Right-drag = pan · Left-drag = rotate
            </span>
          </div>
        )}

        {/* Avatar toggle button (floating, top-left of chat) */}
        <button
          className="avatar-toggle-btn"
          onClick={toggleAvatar}
          title={showAvatar ? 'Hide avatar' : 'Show avatar'}
        >
          {showAvatar ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>

        {/* Chat Messages */}
        <div className="chat-messages">
          {messages.length === 0 && !isStreaming && (
            <div className="chat-empty">
              <div className="chat-empty-icon">
                <MessageSquare size={36} />
              </div>
              <h2 className="chat-empty-title">
                {character ? `Chat with ${character.name}` : 'Select a Character'}
              </h2>
              <p className="chat-empty-subtitle">
                {character
                  ? character.description || 'Start a conversation to begin.'
                  : 'Choose a character from the sidebar to start chatting.'}
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className={`message message-${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user'
                  ? 'Y'
                  : character?.avatar_emoji || character?.name?.charAt(0) || 'A'}
              </div>
              <div>
                <div className="message-content">
                  {msg.image_url && (
                    <img src={msg.image_url} alt="Attached" loading="lazy" />
                  )}
                  {renderContent(msg.content)}
                </div>
                <div className="message-timestamp">{formatTime(msg.timestamp)}</div>
              </div>
            </div>
          ))}

          {isStreaming && streamingText && (
            <div className="message message-assistant">
              <div className="message-avatar">
                {character?.avatar_emoji || character?.name?.charAt(0) || 'A'}
              </div>
              <div>
                <div className="message-content">
                  {renderContent(streamingText)}
                  <span className="streaming-cursor" />
                </div>
              </div>
            </div>
          )}

          {isStreaming && !streamingText && (
            <div className="message message-assistant">
              <div className="message-avatar">
                {character?.avatar_emoji || character?.name?.charAt(0) || 'A'}
              </div>
              <div className="typing-indicator">
                <div className="typing-dot" />
                <div className="typing-dot" />
                <div className="typing-dot" />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="chat-input-area">
        {pendingImage && (
          <div className="chat-input-preview animate-fade-in">
            <img
              src={URL.createObjectURL(pendingImage)}
              alt="Preview"
              className="image-preview-thumb"
            />
            <button
              className="image-preview-remove"
              onClick={() => setPendingImage(null)}
              title="Remove image"
            >✕</button>
          </div>
        )}

        <div className="chat-input-row">
          <ImageCapture onImageSelect={handleImageSelect} />
          <div className="chat-input-wrapper">
            <textarea
              ref={inputRef}
              className="chat-input"
              placeholder={character ? `Message ${character.name}...` : 'Select a character to start...'}
              value={inputText}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={!characterId}
            />
          </div>
          <VoiceRecorder onVoiceMessage={handleVoiceMessage} isStreaming={aiActive} />
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={(!inputText.trim() && !pendingImage) || !characterId || isStreaming}
            title="Send message"
          >
            <Send size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}
