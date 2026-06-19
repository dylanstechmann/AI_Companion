import React, { useState, useEffect } from 'react';
import { X, Sparkles, Loader, Cpu, Save } from 'lucide-react';

export default function CreateCharacterModal({ onClose, onCreate }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('You are a helpful AI assistant.');
  const [appearanceDescription, setAppearanceDescription] = useState('');
  const [clothingStyle, setClothingStyle] = useState('casual');
  const [bodyType, setBodyType] = useState('athletic');
  const [generateImmediately, setGenerateImmediately] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [userBalance, setUserBalance] = useState(0);
  const [error, setError] = useState('');

  // Fetch current credit balance
  useEffect(() => {
    const fetchBalance = async () => {
      try {
        const res = await fetch('/api/payments/balance');
        if (res.ok) {
          const data = await res.json();
          setUserBalance(data.credits || 0);
        }
      } catch (err) {
        console.error('Failed to fetch balance:', err);
      }
    };
    fetchBalance();
  }, []);

  // Auto-check generate checkbox if user has enough balance and types an appearance description
  useEffect(() => {
    if (appearanceDescription.trim() && userBalance >= 5) {
      setGenerateImmediately(true);
    } else {
      setGenerateImmediately(false);
    }
  }, [appearanceDescription, userBalance]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Name is required.');
      return;
    }
    if (!description.trim()) {
      setError('Description is required.');
      return;
    }
    if (!systemPrompt.trim()) {
      setError('System prompt is required.');
      return;
    }

    setIsSubmitting(true);
    setError('');

    try {
      await onCreate({
        name: name.trim(),
        description: description.trim(),
        system_prompt: systemPrompt.trim(),
        appearance_description: appearanceDescription.trim(),
        clothing_style: clothingStyle,
        body_type: bodyType,
      }, generateImmediately);
    } catch (err) {
      setError(err.message || 'Failed to create character.');
      setIsSubmitting(false);
    }
  };

  const costCredits = 4.4;
  const hasEnoughBalance = userBalance >= costCredits;

  return (
    <div className="payment-modal-overlay" onClick={onClose}>
      <div className="payment-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '550px' }}>
        <button className="payment-close" onClick={onClose} disabled={isSubmitting}>
          <X size={20} />
        </button>
        
        <h2 className="payment-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Cpu size={22} /> Create New Character
        </h2>

        {error && (
          <div className="payment-error" style={{ margin: '0 0 10px 0' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          <div className="settings-field">
            <label className="settings-field-label">Name</label>
            <input
              type="text"
              className="settings-input"
              placeholder="e.g. Maya"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          <div className="settings-field">
            <label className="settings-field-label">Short Description</label>
            <input
              type="text"
              className="settings-input"
              placeholder="e.g. Deep thinker and friendly coding assistant"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          <div className="settings-field">
            <label className="settings-field-label">System Prompt (AI Persona)</label>
            <textarea
              className="settings-textarea scrollbar-custom"
              style={{ height: '90px' }}
              placeholder="Define how the AI companion should behave, speak, and respond..."
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          <div className="settings-field">
            <label className="settings-field-label">Appearance Description (Optional)</label>
            <textarea
              className="settings-textarea scrollbar-custom"
              style={{ height: '80px' }}
              placeholder="Describe what they look like (e.g. 'A professional woman in her late 20s, smiling, dark curly hair, studio lighting'). This is used by DALL-E-3 to generate their realistic avatar."
              value={appearanceDescription}
              onChange={(e) => setAppearanceDescription(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          {/* Clothing Style */}
          <div className="settings-field">
            <label className="settings-field-label">Clothing Style</label>
            <select
              className="settings-select"
              value={clothingStyle}
              onChange={(e) => setClothingStyle(e.target.value)}
              disabled={isSubmitting}
            >
              <option value="casual">Casual (T-shirt, jeans)</option>
              <option value="formal">Formal (Business suit)</option>
              <option value="sexy">Sexy (Form-fitting, revealing)</option>
              <option value="business">Business (Professional attire)</option>
              <option value="sporty">Sporty (Athletic wear)</option>
              <option value="custom">Custom (Describe below)</option>
            </select>
          </div>

          {/* Body Type */}
          <div className="settings-field">
            <label className="settings-field-label">Body Type</label>
            <select
              className="settings-select"
              value={bodyType}
              onChange={(e) => setBodyType(e.target.value)}
              disabled={isSubmitting}
            >
              <option value="slim">Slim</option>
              <option value="athletic">Athletic</option>
              <option value="curvy">Curvy</option>
              <option value="muscular">Muscular</option>
            </select>
          </div>

          {appearanceDescription.trim() && (
            <div style={{
              background: 'var(--bg-glass-hover)',
              padding: '12px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-glass)',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: 'bold' }}>
                <input
                  type="checkbox"
                  checked={generateImmediately}
                  onChange={(e) => setGenerateImmediately(e.target.checked)}
                  disabled={isSubmitting || !hasEnoughBalance}
                />
                Generate AI Avatar immediately
              </label>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-secondary)', paddingLeft: '20px' }}>
                <span>Cost: {costCredits} Credits</span>
                <span>Your Balance: {userBalance} Credits</span>
              </div>
              {!hasEnoughBalance && (
                <span style={{ fontSize: '11px', color: 'var(--danger)', paddingLeft: '20px' }}>
                  ⚠️ Insufficient balance to generate avatar immediately. (Needs 4.4 credits)
                </span>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="settings-save-btn"
            style={{ width: '100%', marginTop: '10px', padding: '12px', justifyContent: 'center' }}
          >
            {isSubmitting ? (
              <>
                <Loader size={18} className="spin" />
                <span style={{ marginLeft: '10px' }}>
                  {generateImmediately ? 'Generating character & AI avatar...' : 'Creating character...'}
                </span>
              </>
            ) : (
              <>
                <Save size={18} />
                <span style={{ marginLeft: '10px' }}>Create Character</span>
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
