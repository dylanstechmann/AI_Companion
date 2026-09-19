import React, { useState, useEffect, useCallback } from 'react';
import { X, Save, Server, Cpu, Volume2, Loader, Sparkles } from 'lucide-react';

const CLOUD_VOICES = [
  { value: 'alloy', label: 'Alloy' },
  { value: 'echo', label: 'Echo' },
  { value: 'fable', label: 'Fable' },
  { value: 'onyx', label: 'Onyx' },
  { value: 'nova', label: 'Nova' },
  { value: 'shimmer', label: 'Shimmer' },
];

export default function SettingsPanel({ character, health, onClose, onUpdateCharacter }) {
  const [sttMode, setSttMode] = useState('local');
  const [embeddingModel, setEmbeddingModel] = useState('');
  const [charData, setCharData] = useState(null);
  const [isGeneratingAvatar, setIsGeneratingAvatar] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [healthData, setHealthData] = useState(health);

  // TTS settings (stored in localStorage)
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [ttsMode, setTtsMode] = useState('browser');
  const [ttsVoice, setTtsVoice] = useState('alloy');
  const [ttsRate, setTtsRate] = useState(1.0);
  const [browserVoices, setBrowserVoices] = useState([]);

  // Load config and health
  useEffect(() => {
    fetch('/api/config')
      .then(res => res.json())
      .then(data => {
        setSttMode(data.stt_mode || data.STT_MODE);
        setEmbeddingModel(data.embedding_model || data.EMBEDDING_MODEL);
      })
      .catch(err => console.error("Failed to load config", err));

    fetch('/api/health')
      .then(res => res.json())
      .then(data => setHealthData(data))
      .catch(err => console.error("Failed to load health", err));
  }, []);

  // Load TTS settings from localStorage
  useEffect(() => {
    try {
      setTtsEnabled(localStorage.getItem('tts_enabled') !== 'false');
      setTtsMode(localStorage.getItem('tts_mode') || 'browser');
      setTtsVoice(localStorage.getItem('tts_voice') || 'alloy');
      setTtsRate(parseFloat(localStorage.getItem('tts_rate')) || 1.0);
    } catch { /* localStorage unavailable */ }

    // Load browser voices
    if ('speechSynthesis' in window) {
      const loadVoices = () => {
        setBrowserVoices(window.speechSynthesis.getVoices());
      };
      loadVoices();
      window.speechSynthesis.onvoiceschanged = loadVoices;
    }
  }, []);

  // Load selected character data
  useEffect(() => {
    if (character) {
      setCharData({ ...character });
    }
  }, [character]);

  const handleConfigSave = async (key, value) => {
    try {
      await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value })
      });
      if (key === 'STT_MODE' || key === 'stt_mode') setSttMode(value);
      if (key === 'EMBEDDING_MODEL' || key === 'embedding_model') setEmbeddingModel(value);
    } catch (err) {
      console.error("Failed to update config", err);
    }
  };

  // Save TTS setting to localStorage
  const handleTTSSave = useCallback((key, value) => {
    try {
      localStorage.setItem(key, String(value));
    } catch { /* ignore */ }
  }, []);

  const handleTtsEnabledChange = (enabled) => {
    setTtsEnabled(enabled);
    handleTTSSave('tts_enabled', enabled);
  };

  const handleTtsModeChange = (mode) => {
    setTtsMode(mode);
    handleTTSSave('tts_mode', mode);
  };

  const handleTtsVoiceChange = (voice) => {
    setTtsVoice(voice);
    handleTTSSave('tts_voice', voice);
    if (ttsMode === 'browser') {
      handleTTSSave('tts_voiceURI', voice);
    }
  };

  const handleTtsRateChange = (rate) => {
    setTtsRate(rate);
    handleTTSSave('tts_rate', rate);
  };

  const handleCharSave = async () => {
    if (!charData) return;
    setIsSaving(true);
    try {
      const res = await fetch(`/api/characters/${charData.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: charData.name,
          description: charData.description,
          system_prompt: charData.system_prompt,
          avatar_url: charData.avatar_url,
          appearance_description: charData.appearance_description
        })
      });
      if (res.ok) {
        const updated = await res.json();
        if (onUpdateCharacter) onUpdateCharacter(updated);
        if (onClose) onClose();
      } else {
        const errorData = await res.json();
        alert(`Failed to save: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (err) {
      console.error("Failed to save character", err);
      alert("Network error while saving character.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="settings-panel glass-panel animate-slide-in-right">
      <div className="settings-header">
        <h2 className="settings-title">Settings</h2>
        <button onClick={onClose} className="icon-btn" title="Close settings">
          <X size={20} />
        </button>
      </div>

      <div className="settings-body scrollbar-custom">
        {/* ── TTS Settings ──────────────────────────────────────── */}
        <section className="settings-section">
          <h3 className="settings-section-title">
            <Volume2 size={14} /> Text-to-Speech
          </h3>

          {/* TTS Enable Toggle */}
          <div className="settings-row">
            <label className="settings-label">Enable TTS</label>
            <button
              className={`toggle-btn ${ttsEnabled ? 'toggle-on' : ''}`}
              onClick={() => handleTtsEnabledChange(!ttsEnabled)}
              title={ttsEnabled ? 'TTS is on' : 'TTS is off'}
            >
              <span className="toggle-slider" />
            </button>
          </div>

          {/* TTS Mode */}
          {ttsEnabled && (
            <>
              <div className="settings-row">
                <label className="settings-label">TTS Engine</label>
                <div className="toggle-group">
                  <button
                    className={`toggle-option ${ttsMode === 'browser' ? 'active' : ''}`}
                    onClick={() => handleTtsModeChange('browser')}
                  >
                    Browser
                  </button>
                  <button
                    className={`toggle-option ${ttsMode === 'cloud' ? 'active' : ''}`}
                    onClick={() => handleTtsModeChange('cloud')}
                  >
                    Cloud
                  </button>
                </div>
              </div>

              {/* Voice Selector */}
              <div className="settings-field">
                <label className="settings-field-label">Voice</label>
                <select
                  className="settings-select"
                  value={ttsVoice}
                  onChange={(e) => handleTtsVoiceChange(e.target.value)}
                >
                  {ttsMode === 'cloud'
                    ? CLOUD_VOICES.map((v) => (
                        <option key={v.value} value={v.value}>{v.label}</option>
                      ))
                    : browserVoices.map((v) => (
                        <option key={v.voiceURI} value={v.voiceURI}>
                          {v.name} ({v.lang})
                        </option>
                      ))
                  }
                </select>
                {ttsMode === 'browser' && browserVoices.length === 0 && (
                  <p className="settings-hint">No voices detected. Your browser may not support TTS.</p>
                )}
                {ttsMode === 'cloud' && (
                  <p className="settings-hint">Cloud TTS requires a TTS API key configured on the backend.</p>
                )}
              </div>

              {/* Speed Slider */}
              <div className="settings-field">
                <label className="settings-field-label">
                  Speed: {ttsRate.toFixed(1)}x
                </label>
                <input
                  type="range"
                  className="settings-slider"
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  value={ttsRate}
                  onChange={(e) => handleTtsRateChange(parseFloat(e.target.value))}
                />
              </div>
            </>
          )}
        </section>

        <hr className="settings-divider" />

        {/* ── System Config ─────────────────────────────────────── */}
        <section className="settings-section">
          <h3 className="settings-section-title">
            <Server size={14} /> System Configuration
          </h3>

          <div className="settings-field">
            <label className="settings-field-label">
              STT Mode
              <span className={`settings-badge ${healthData?.gpu_available ? 'badge-success' : 'badge-warning'}`}>
                {healthData?.gpu_available ? 'GPU Available' : 'CPU Only'}
              </span>
            </label>
            <div className="toggle-group">
              <button
                className={`toggle-option ${sttMode === 'local' ? 'active' : ''}`}
                onClick={() => handleConfigSave('stt_mode', 'local')}
              >
                Local Whisper
              </button>
              <button
                className={`toggle-option ${sttMode === 'cloud' ? 'active' : ''}`}
                onClick={() => handleConfigSave('stt_mode', 'cloud')}
              >
                Cloud API
              </button>
            </div>
            <p className="settings-hint">
              Local runs on your machine (GPU if available). Cloud uses OpenRouter/Groq API.
            </p>
          </div>
        </section>

        <hr className="settings-divider" />

        {/* ── Character Editor ──────────────────────────────────── */}
        {charData && (
          <section className="settings-section">
            <h3 className="settings-section-title">
              <Cpu size={14} /> Character Editor
            </h3>

            {charData.is_default && (
              <div className="settings-notice">
                This is a default character. Modifying it is allowed, but deleting is protected.
              </div>
            )}

            <div className="settings-field">
              <label className="settings-field-label">Name</label>
              <input
                type="text"
                className="settings-input"
                value={charData.name}
                onChange={e => setCharData({ ...charData, name: e.target.value })}
              />
            </div>

            <div className="settings-field">
              <label className="settings-field-label">Description (UI only)</label>
              <input
                type="text"
                className="settings-input"
                value={charData.description}
                onChange={e => setCharData({ ...charData, description: e.target.value })}
              />
            </div>

            <div className="settings-field">
              <label className="settings-field-label">System Prompt (AI Persona)</label>
              <textarea
                className="settings-textarea scrollbar-custom"
                value={charData.system_prompt}
                onChange={e => setCharData({ ...charData, system_prompt: e.target.value })}
              />
            </div>

            <div className="settings-field">
              <label className="settings-field-label">Appearance Description (for AI Avatar)</label>
              <textarea
                className="settings-textarea scrollbar-custom"
                style={{ height: '80px' }}
                placeholder="Describe what this character should look like..."
                value={charData.appearance_description || ''}
                onChange={e => setCharData({ ...charData, appearance_description: e.target.value })}
              />
            </div>

            <div className="settings-field">
              <label className="settings-field-label">Avatar Portrait</label>
              <div style={{ display: 'flex', gap: '15px', alignItems: 'center', marginTop: '5px' }}>
                {charData.avatar_url ? (
                  <img
                    src={charData.avatar_url}
                    alt="Avatar Preview"
                    style={{ width: '60px', height: '60px', borderRadius: '50%', objectFit: 'cover', border: '1px solid var(--border-glass)' }}
                  />
                ) : (
                  <div style={{ width: '60px', height: '60px', borderRadius: '50%', background: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--border-glass)', fontSize: '20px' }}>
                    🤖
                  </div>
                )}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <button
                    type="button"
                    onClick={async () => {
                      if (!charData.appearance_description) {
                        alert("Please specify what the character looks like first.");
                        return;
                      }
                      setIsGeneratingAvatar(true);
                      try {
                        const response = await fetch(`/api/characters/${charData.id}/generate-avatar`, {
                          method: 'POST',
                        });
                        if (response.ok) {
                          const data = await response.json();
                          const updated = { ...charData, avatar_url: data.avatar_url };
                          setCharData(updated);
                          if (onUpdateCharacter) {
                            onUpdateCharacter(updated);
                          }
                        } else {
                          const err = await response.json();
                          alert(`Error: ${err.detail || 'Could not generate avatar'}`);
                        }
                      } catch (err) {
                        console.error(err);
                        alert("Failed to generate avatar.");
                      } finally {
                        setIsGeneratingAvatar(false);
                      }
                    }}
                    disabled={isGeneratingAvatar || !charData.id}
                    className="settings-save-btn"
                    style={{ margin: 0, padding: '6px 12px', width: 'fit-content' }}
                  >
                    {isGeneratingAvatar ? <Loader size={14} className="spin" /> : <Sparkles size={14} />}
                    <span style={{ marginLeft: '5px' }}>Generate Avatar</span>
                  </button>
                  <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                    Requires OpenAI or compatible API key.
                  </span>
                </div>
              </div>
            </div>

            <button
              onClick={handleCharSave}
              disabled={isSaving}
              className="settings-save-btn"
            >
              {isSaving ? <Loader size={18} className="spin" /> : <Save size={18} />}
              Save Character
            </button>
          </section>
        )}
      </div>
    </div>
  );
}
