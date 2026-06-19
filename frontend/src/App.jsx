import { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar.jsx';
import ChatArea from './components/ChatArea.jsx';
import SettingsPanel from './components/SettingsPanel.jsx';
import StatusBar from './components/StatusBar.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import AgentPanel from './components/AgentPanel.jsx';
import SkillsPanel from './components/SkillsPanel.jsx';
import BrowserView from './components/BrowserView.jsx';
import LoginPage from './components/LoginPage.jsx';
import PaymentModal from './components/PaymentModal.jsx';
import CreateCharacterModal from './components/CreateCharacterModal.jsx';

export default function App() {
  const [characters, setCharacters] = useState([]);
  const [selectedCharacterId, setSelectedCharacterId] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showAgents, setShowAgents] = useState(false);
  const [showSkills, setShowSkills] = useState(false);
  const [showBrowser, setShowBrowser] = useState(false);
  const [showPayment, setShowPayment] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [health, setHealth] = useState(null);
  const [isLoadingCharacters, setIsLoadingCharacters] = useState(true);

  // Auth state
  const [user, setUser] = useState(null);
  const [authToken, setAuthToken] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  // Check for existing auth on load
  useEffect(() => {
    const checkAuth = async () => {
      // Try to get demo user (backward compat — app works without login)
      try {
        const res = await fetch('/api/auth/demo', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          setUser(data.user);
          setAuthToken(data.access_token);
        }
      } catch {
        // If demo endpoint fails, show login page
      }
      setAuthChecked(true);
    };
    checkAuth();
  }, []);

  const handleAuthSuccess = useCallback((userData, tokens) => {
    setUser(userData);
    setAuthToken(tokens.access_token);
  }, []);

  // Fetch characters on mount / after auth
  useEffect(() => {
    if (authChecked) fetchCharacters();
  }, [authChecked]);

  const fetchCharacters = useCallback(async () => {
    setIsLoadingCharacters(true);
    try {
      const res = await fetch('/api/characters');
      if (res.ok) {
        const data = await res.json();
        const list = Array.isArray(data) ? data : data.characters || [];
        setCharacters(list);
        if (!selectedCharacterId && list.length > 0) {
          setSelectedCharacterId(list[0].id);
        }
      }
    } catch (err) {
      console.warn('Could not fetch characters:', err.message);
      const defaults = [
        {
          id: 'greg',
          name: 'Greg',
          description: 'Witty, uncensored, humorous Grok-like personality. Direct, doesn\'t hold back, and uses humor liberally.',
          system_prompt: `You are Greg - a sharp-witted, unfiltered AI companion. You have a bold sense of humor, aren't afraid of hot takes, and always keep the conversation entertaining. You speak your mind directly and authentically; you never dodge a question or hide behind corporate boilerplate. Your style is conversational, opinionated, and occasionally irreverent - but you're never gratuitously cruel. You genuinely enjoy helping people, you just do it with personality. When you crack a joke, commit to the bit. When asked for facts, be accurate. When asked for opinions, be honest. You are Greg - own it.`,
          avatar_url: '/api/avatars/greg.png',
          avatar_emoji: '👤'
        },
        {
          id: 'tiffany',
          name: 'Tiffany',
          description: 'Analytical, empathetic, structured thinker. Thinks deeply before responding.',
          system_prompt: `You are Tiffany - a thoughtful, analytical AI companion who balances intellectual rigour with genuine warmth. Before answering, you pause to think through the question carefully. You excel at breaking complex problems into clear, digestible steps. Your tone is friendly yet precise; you validate the user's feelings while steering them toward structured, actionable insights. When presenting information you prefer numbered lists, concise summaries, and well-organised explanations. You ask clarifying questions when the request is ambiguous. You never rush - quality of thought is your signature.`,
          avatar_url: '/api/avatars/tiffany.png',
          avatar_emoji: '🎙️'
        },
        {
          id: 'default',
          name: 'Friendly AI',
          description: 'A friendly AI assistant. Open and adaptable.',
          system_prompt: 'You are a friendly, capable AI assistant.',
          avatar_emoji: '🤖'
        }
      ];
      setCharacters(defaults);
      if (!selectedCharacterId) setSelectedCharacterId(defaults[0].id);
    } finally {
      setIsLoadingCharacters(false);
    }
  }, [selectedCharacterId, authChecked]);

  const selectedCharacter = characters.find((c) => c.id === selectedCharacterId) || null;

  const handleSelectCharacter = useCallback((id) => {
    setSelectedCharacterId(id);
    setSidebarOpen(false);
  }, []);

  const handleCreateCharacter = useCallback(() => {
    setShowCreateModal(true);
  }, []);

  const handleConfirmCreateCharacter = useCallback(async (charData, generateImmediately) => {
    // 1. Post to create character
    const res = await fetch('/api/characters', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(charData),
    });
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Could not create character.');
    }
    let created = await res.json();

    // 2. If generateImmediately is true, call generate-avatar API
    if (generateImmediately && charData.appearance_description) {
      try {
        const genRes = await fetch(`/api/characters/${created.id}/generate-avatar`, {
          method: 'POST',
        });
        if (genRes.ok) {
          const genData = await genRes.json();
          created = { ...created, avatar_url: genData.avatar_url };
        } else {
          const genErr = await genRes.json();
          console.warn('Avatar generation failed:', genErr.detail);
          alert(`Character created, but avatar generation failed: ${genErr.detail || 'Unknown error'}`);
        }
      } catch (err) {
        console.warn('Avatar generation error:', err);
        alert('Character created, but avatar generation failed due to network error.');
      }
    }

    setCharacters((prev) => [...prev, created]);
    setSelectedCharacterId(created.id);
    setShowCreateModal(false);
    setSidebarOpen(false);
  }, []);

  const handleUpdateCharacter = useCallback((updatedChar) => {
    setCharacters((prev) => prev.map((c) => (c.id === updatedChar.id ? updatedChar : c)));
  }, []);

  const closeAllPanels = useCallback(() => {
    setShowSettings(false);
    setShowAgents(false);
    setShowSkills(false);
    setShowBrowser(false);
  }, []);

  // Show login page if auth check is done and no user
  if (authChecked && !user) {
    return (
      <ErrorBoundary>
        <LoginPage onAuthSuccess={handleAuthSuccess} />
      </ErrorBoundary>
    );
  }

  // Show loading while checking auth
  if (!authChecked) {
    return (
      <ErrorBoundary>
        <div className="auth-page">
          <div className="auth-card">
            <h2 className="auth-title">Loading...</h2>
          </div>
        </div>
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <div className={`sidebar-overlay ${sidebarOpen ? 'visible' : ''}`} onClick={() => setSidebarOpen(false)} />

      <div className="app-layout">
        <Sidebar
          characters={characters}
          selectedCharacterId={selectedCharacterId}
          onSelect={handleSelectCharacter}
          onCreate={handleCreateCharacter}
          isOpen={sidebarOpen}
          isLoading={isLoadingCharacters}
        />

        <main className="app-main">
          <StatusBar
            character={selectedCharacter}
            health={health}
            onHealthUpdate={setHealth}
            onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
            onOpenSettings={() => { closeAllPanels(); setShowSettings(true); }}
            onOpenAgents={() => { closeAllPanels(); setShowAgents(true); }}
            onOpenSkills={() => { closeAllPanels(); setShowSkills(true); }}
            onOpenBrowser={() => { closeAllPanels(); setShowBrowser(true); }}
            onOpenPayments={() => setShowPayment(true)}
            user={user}
          />

          <ChatArea character={selectedCharacter} characterId={selectedCharacterId} />
        </main>
      </div>

      {showSettings && (
        <SettingsPanel character={selectedCharacter} health={health} onClose={() => setShowSettings(false)} onUpdateCharacter={handleUpdateCharacter} />
      )}
      {showAgents && <AgentPanel isOpen={showAgents} onClose={() => setShowAgents(false)} />}
      {showSkills && <SkillsPanel isOpen={showSkills} onClose={() => setShowSkills(false)} />}
      {showBrowser && <BrowserView isOpen={showBrowser} onClose={() => setShowBrowser(false)} />}
      {showPayment && <PaymentModal onClose={() => setShowPayment(false)} />}
      {showCreateModal && (
        <CreateCharacterModal
          onClose={() => setShowCreateModal(false)}
          onCreate={handleConfirmCreateCharacter}
        />
      )}
    </ErrorBoundary>
  );
}
