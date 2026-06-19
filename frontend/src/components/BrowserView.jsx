import { useState, useCallback } from 'react';
import { X, Camera, Navigation, Globe, Loader } from 'lucide-react';

/**
 * BrowserView — Browser automation display.
 * Lets the user watch and interact with the AI's browser sessions.
 *
 * Props:
 *   isOpen: boolean
 *   onClose: () => void
 */
export default function BrowserView({ isOpen, onClose }) {
  const [url, setUrl] = useState('');
  const [screenshot, setScreenshot] = useState(null);
  const [pageContent, setPageContent] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const navigate = useCallback(async () => {
    if (!url.trim() || isLoading) return;
    setIsLoading(true);
    setError(null);
    setScreenshot(null);

    try {
      const res = await fetch('/api/browser/navigate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      setPageContent(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [url, isLoading]);

  const takeScreenshot = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch('/api/browser/screenshot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(url.trim() ? { url } : {}),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      if (data.screenshot) {
        setScreenshot(`data:${data.mime_type || 'image/png'};base64,${data.screenshot}`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [url, isLoading]);

  if (!isOpen) return null;

  return (
    <div className="browser-view glass-panel animate-slide-in-right">
      <div className="browser-view-header">
        <h2 className="settings-title">Browser</h2>
        <button onClick={onClose} className="icon-btn" title="Close">
          <X size={20} />
        </button>
      </div>

      <div className="settings-body scrollbar-custom">
        {/* URL Bar */}
        <div className="browser-url-bar">
          <Globe size={16} className="browser-url-icon" />
          <input
            type="text"
            className="browser-url-input"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && navigate()}
          />
          <button
            className="browser-action-btn"
            onClick={navigate}
            disabled={isLoading || !url.trim()}
            title="Navigate"
          >
            <Navigation size={14} /> Go
          </button>
          <button
            className="browser-action-btn"
            onClick={takeScreenshot}
            disabled={isLoading}
            title="Screenshot"
          >
            <Camera size={14} /> Shot
          </button>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="browser-loading">
            <Loader size={24} className="spin" />
            <p>Loading...</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="agent-final-result" style={{ color: 'var(--danger)', borderColor: 'var(--danger)' }}>
            {error}
          </div>
        )}

        {/* Screenshot */}
        {screenshot && (
          <div className="browser-screenshot">
            <img src={screenshot} alt="Browser screenshot" />
          </div>
        )}

        {/* Page Content */}
        {pageContent && (
          <div className="settings-section">
            <h3 className="settings-section-title">Page Content</h3>
            <div className="agent-task-output scrollbar-custom" style={{ maxHeight: '400px' }}>
              <strong>{pageContent.title}</strong>
              <br />
              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{pageContent.url}</span>
              <br /><br />
              <div style={{ whiteSpace: 'pre-wrap' }}>
                {pageContent.text_content?.slice(0, 3000)}
              </div>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !error && !screenshot && !pageContent && (
          <div className="settings-hint" style={{ textAlign: 'center', padding: '40px 16px' }}>
            Enter a URL above to navigate and take screenshots.
            The AI can also control the browser through its tool-calling system.
          </div>
        )}
      </div>
    </div>
  );
}
