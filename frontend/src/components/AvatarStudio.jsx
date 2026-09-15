import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Pause, Play, ShieldCheck } from 'lucide-react';
import BrowserPrivacyPanel from './BrowserPrivacyPanel.jsx';
import useAvatarAudio from '../hooks/useAvatarAudio.js';
import './studio.css';

const HumanAvatar3D = lazy(() => import('./HumanAvatar3D.jsx'));
const CHARACTERS = [
  { id: 'greg', name: 'Greg', file: 'greg_3d.glb', detail: 'Direct & quick-witted' },
  { id: 'tiffany', name: 'Tiffany', file: 'tiffany_3d.glb', detail: 'Thoughtful & analytical' },
  { id: 'friendly_ai', name: 'Friendly AI', file: 'friendly_ai_3d.glb', detail: 'Warm & adaptable' },
  { id: 'fallback', name: 'Procedural companion', file: null, detail: 'Lightweight fallback' },
];
const EMOTIONS = ['neutral', 'happy', 'thinking', 'excited', 'sad', 'angry'];

export default function AvatarStudio() {
  const [character, setCharacter] = useState(CHARACTERS[0]);
  const [emotion, setEmotion] = useState('neutral');
  const [paused, setPaused] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const { amplitudeRef, startSimulation, stopTracking } = useAvatarAudio();
  const timerRef = useRef(null);
  useEffect(() => () => clearTimeout(timerRef.current), []);
  useEffect(() => {
    if (speaking && !paused) startSimulation();
    else stopTracking();
  }, [speaking, paused, startSimulation, stopTracking]);
  const testSpeech = () => {
    clearTimeout(timerRef.current);
    setSpeaking(!speaking);
    if (!speaking) timerRef.current = setTimeout(() => setSpeaking(false), 6000);
  };
  return (
    <main className="studio">
      <header className="studio-header">
        <div className="studio-brand">
          <img src={`${import.meta.env.BASE_URL}icons/companion.svg`} width="40" height="40" alt="" />
          <div><h1>AI Companion</h1><p>Avatar studio</p></div>
        </div>
        <button className="studio-button" onClick={() => setPrivacyOpen(!privacyOpen)} aria-expanded={privacyOpen}>
          <ShieldCheck size={16} /> Browser & privacy
        </button>
      </header>
      <div className="studio-notice" role="note">
        Visual preview only. Your backend, chat history, microphone, and AI services are not connected.
      </div>
      <div className="studio-workspace">
        <aside className="studio-sidebar" aria-label="Character selection">
          <p className="studio-eyebrow">Your companions</p>
          {CHARACTERS.map(item => (
            <button key={item.id} className={`studio-character ${character.id === item.id ? 'selected' : ''}`}
              onClick={() => setCharacter(item)} aria-pressed={character.id === item.id}>
              <span className="studio-initial">{item.name[0]}</span>
              <span><strong>{item.name}</strong><small>{item.detail}</small></span>
            </button>
          ))}
          <div className="studio-sidebar-note">
            <h2>A closer conversation</h2>
            <p>Explore the existing models with improved framing, lighting, and animation. Drag to orbit and scroll or pinch to zoom.</p>
            <p>These are the project’s original stylized assets, not newly sculpted photorealistic characters.</p>
          </div>
        </aside>
        <section className="studio-stage" aria-label={`${character.name} avatar preview`}>
          <div className="studio-stage-title"><span>LIVE 3D</span><span>{paused ? 'Paused' : speaking ? 'Motion test' : 'Idle'}</span></div>
          <Suspense fallback={<div className="studio-loading" role="status">Loading 3D renderer…</div>}>
            <HumanAvatar3D
              avatarUrl={character.file ? `${import.meta.env.BASE_URL}avatars/${character.file}` : null}
              characterName={character.name}
              emotion={emotion}
              isStreaming={emotion === 'thinking'}
              amplitudeRef={amplitudeRef}
              isPaused={paused}
            />
          </Suspense>
          <div className="studio-stage-caption"><h2>{character.name}</h2><p>{character.detail}</p></div>
        </section>
        <aside className="studio-controls" aria-label="Animation controls">
          <p className="studio-eyebrow">Expression</p>
          <div className="studio-emotions">
            {EMOTIONS.map(value => <button key={value} className={`studio-button ${emotion === value ? 'selected' : ''}`}
              onClick={() => setEmotion(value)} aria-pressed={emotion === value}>{value}</button>)}
          </div>
          <h2>Motion & playback</h2>
          <button className="studio-button studio-wide" onClick={() => setPaused(!paused)} aria-pressed={paused}>
            {paused ? <Play size={16} /> : <Pause size={16} />}{paused ? 'Resume animation' : 'Pause animation'}
          </button>
          <button className="studio-button studio-wide" onClick={testSpeech} disabled={paused} aria-pressed={speaking}>
            {speaking ? 'Stop mouth motion' : 'Test mouth motion'}
          </button>
          <p>Six-second silent simulation. Live cloud speech uses measured audio amplitude, not phoneme timing.</p>
          <div className="studio-details">
            <h2>Designed for your browser</h2>
            <p>No font CDN. No microphone access here. Local bundled models and procedural studio lighting.</p>
            <p>Try the renderer’s quality and camera controls, or use the lightweight fallback on constrained devices.</p>
          </div>
          {import.meta.env.VITE_AVATAR_PREVIEW !== 'true' &&
            <a className="studio-button" href="./"><ArrowLeft size={16} /> Back to companion</a>}
        </aside>
      </div>
      {privacyOpen && <div className="studio-privacy"><BrowserPrivacyPanel /></div>}
      <footer className="studio-footer">AI Companion / Self-hosted project <span>3D · Voice · Browser compatibility</span></footer>
    </main>
  );
}
