import { useEffect, useState } from 'react';
import { getBrowserCapabilities, getInstallHelp } from '../lib/browserCapabilities.js';

export default function BrowserPrivacyPanel() {
  const [installPrompt, setInstallPrompt] = useState(null);
  const [installed, setInstalled] = useState(() => getBrowserCapabilities().installed);
  const [installError, setInstallError] = useState('');
  const capabilities = getBrowserCapabilities();

  useEffect(() => {
    const available = (event) => { event.preventDefault(); setInstallPrompt(event); };
    const complete = () => { setInstalled(true); setInstallPrompt(null); };
    window.addEventListener('beforeinstallprompt', available);
    window.addEventListener('appinstalled', complete);
    return () => {
      window.removeEventListener('beforeinstallprompt', available);
      window.removeEventListener('appinstalled', complete);
    };
  }, []);

  const install = async () => {
    try {
      await installPrompt.prompt();
      await installPrompt.userChoice;
      setInstallPrompt(null);
    } catch {
      setInstallError('Use the installation option in your browser menu instead.');
    }
  };

  return (
    <section className="settings-section browser-privacy" aria-labelledby="browser-privacy-title">
      <h3 id="browser-privacy-title" className="settings-section-title">Browser & privacy</h3>
      <p className="settings-hint">
        Firefox is welcome. Browser compatibility and the server’s automation engine are separate choices.
      </p>
      <dl className="capability-list">
        <div><dt>Secure connection</dt><dd>{capabilities.secure ? 'Available' : 'HTTPS required'}</dd></div>
        <div><dt>Microphone API</dt><dd>{capabilities.microphone ? 'Available; permission required' : 'Unavailable; use text'}</dd></div>
        <div><dt>Browser speech</dt><dd>{capabilities.speech ? 'Available; voices vary' : 'Unavailable; use text'}</dd></div>
        <div><dt>Offline app shell</dt><dd>{capabilities.offlineShell ? 'Supported by browser' : 'Unavailable here'}</dd></div>
      </dl>
      <p className="settings-hint">{installed ? 'Running as an installed app.' : getInstallHelp(navigator.userAgent)}</p>
      {installPrompt && !installed && <button type="button" className="btn btn-secondary" onClick={install}>Install app</button>}
      {installError && <p role="status" className="settings-hint">{installError}</p>}
      <p className="settings-hint">
        Microphone starts only when you enable it and stops when the tab is hidden.
        Recordings go to your configured server for transcription. Cloud chat, speech,
        and avatar services may send content to their providers. Self-hosted does not mean fully offline.
      </p>
      <p className="settings-hint">
        Fonts and bundled 3D assets are served by this app, not a font CDN.
        Only the app shell is cached for offline use, not chat, recordings, or API responses.
        Voice and avatar display preferences last for this page session.
      </p>
      <a href="https://support.mozilla.org/en-US/kb/web-apps-firefox-windows" target="_blank" rel="noreferrer" className="settings-hint">Mozilla’s current installation guide</a>
    </section>
  );
}
