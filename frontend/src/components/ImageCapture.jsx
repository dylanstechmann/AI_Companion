import React, { useRef, useState } from 'react';
import { Camera, Image as ImageIcon } from 'lucide-react';

export default function ImageCapture({ onImageSelect }) {
  const [showOptions, setShowOptions] = useState(false);
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      onImageSelect(file); // Pass raw File object
    }
    setShowOptions(false);
    // Reset input so the same file can be re-selected
    e.target.value = '';
  };

  return (
    <div style={{ position: 'relative' }}>
      <button 
        type="button"
        className="icon-btn" 
        onClick={() => setShowOptions(!showOptions)}
        title="Attach Image"
      >
        <Camera className="icon" />
      </button>

      {showOptions && (
        <div className="image-capture-dropdown glass-panel animate-fade-in" style={{
          position: 'absolute',
          bottom: '100%',
          left: 0,
          marginBottom: '8px',
          padding: '8px',
          borderRadius: 'var(--radius-md)',
          minWidth: '150px',
          zIndex: 10,
          display: 'flex',
          flexDirection: 'column',
          gap: '4px'
        }}>
          <button 
            type="button"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              background: 'transparent',
              color: 'var(--text-primary)',
              fontSize: '0.875rem',
              cursor: 'pointer',
              transition: 'background var(--transition-fast)'
            }}
            onMouseEnter={e => e.target.style.background = 'var(--bg-glass-hover)'}
            onMouseLeave={e => e.target.style.background = 'transparent'}
            onClick={() => fileInputRef.current.click()}
          >
            <ImageIcon size={16} />
            Photo Library
          </button>
          
          <button 
            type="button"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              background: 'transparent',
              color: 'var(--text-primary)',
              fontSize: '0.875rem',
              cursor: 'pointer',
              transition: 'background var(--transition-fast)'
            }}
            onMouseEnter={e => e.target.style.background = 'var(--bg-glass-hover)'}
            onMouseLeave={e => e.target.style.background = 'transparent'}
            onClick={() => cameraInputRef.current.click()}
          >
            <Camera size={16} />
            Take Photo
          </button>
        </div>
      )}

      {/* Hidden file inputs */}
      <input 
        type="file" 
        accept="image/*" 
        style={{ display: 'none' }}
        ref={fileInputRef} 
        onChange={handleFileChange} 
      />
      <input 
        type="file" 
        accept="image/*" 
        capture="environment" 
        style={{ display: 'none' }}
        ref={cameraInputRef} 
        onChange={handleFileChange} 
      />
    </div>
  );
}
