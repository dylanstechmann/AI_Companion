import { useEffect, useState, useCallback } from 'react';
import { Menu, Settings, Cpu, Bot, Puzzle, Globe, Bitcoin } from 'lucide-react';

export default function StatusBar({
  character,
  health,
  onHealthUpdate,
  onToggleSidebar,
  onOpenSettings,
  onOpenAgents,
  onOpenSkills,
  onOpenBrowser,
  onOpenPayments,
  user,
}) {
  const [isOnline, setIsOnline] = useState(true);

  // Poll health endpoint
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/api/health');
        if (res.ok) {
          const data = await res.json();
          onHealthUpdate(data);
          setIsOnline(true);
        } else {
          setIsOnline(false);
        }
      } catch {
        setIsOnline(false);
        onHealthUpdate(null);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, [onHealthUpdate]);

  const gpuStatus = health?.gpu_available ? 'GPU' : health ? 'CPU' : null;

  return (
    <div className="status-bar">
      <div className="status-bar-left">
        <button
          className="hamburger-btn"
          onClick={onToggleSidebar}
          aria-label="Toggle sidebar"
        >
          <Menu size={20} />
        </button>

        <div className="status-item">
          <span
            className={`status-dot ${
              isOnline ? 'status-dot-online' : 'status-dot-offline'
            }`}
          />
          {isOnline ? 'Connected' : 'Offline'}
        </div>

        {gpuStatus && (
          <div className="status-item">
            <Cpu size={14} />
            {gpuStatus}
          </div>
        )}
      </div>

      <div className="status-bar-right">
        {character && (
          <span className="status-character-name">{character.name}</span>
        )}

        {/* Phase 3: Agent Orchestrator */}
        {onOpenAgents && (
          <button
            className="btn-icon-sm btn-ghost"
            onClick={onOpenAgents}
            aria-label="Agents"
            title="Agent Orchestrator"
          >
            <Bot size={18} />
          </button>
        )}

        {/* Phase 3: Skills */}
        {onOpenSkills && (
          <button
            className="btn-icon-sm btn-ghost"
            onClick={onOpenSkills}
            aria-label="Skills"
            title="Skills"
          >
            <Puzzle size={18} />
          </button>
        )}

        {/* Phase 3: Browser */}
        {onOpenBrowser && (
          <button
            className="btn-icon-sm btn-ghost"
            onClick={onOpenBrowser}
            aria-label="Browser"
            title="Browser Control"
          >
            <Globe size={18} />
          </button>
        )}

        {/* Phase 4: Payments */}
        {onOpenPayments && (
          <button
            className="btn-icon-sm btn-ghost"
            onClick={onOpenPayments}
            aria-label="Payments"
            title="Subscription & Payments"
          >
            <Bitcoin size={18} />
          </button>
        )}

        <button
          className="btn-icon-sm btn-ghost"
          onClick={onOpenSettings}
          aria-label="Settings"
        >
          <Settings size={18} />
        </button>
      </div>
    </div>
  );
}
