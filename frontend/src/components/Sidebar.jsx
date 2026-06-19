import { Sparkles, Plus } from 'lucide-react';

export default function Sidebar({
  characters = [],
  selectedCharacterId,
  onSelect,
  onCreate,
  isOpen,
  isLoading = false,
}) {
  const getInitial = (name) => {
    return name ? name.charAt(0).toUpperCase() : '?';
  };

  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
      {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <Sparkles size={20} />
        </div>
        <div>
          <div className="sidebar-title">AI Companion</div>
          <div className="sidebar-subtitle">Your AI Friends</div>
        </div>
      </div>

      {/* Character List */}
      <div className="sidebar-list">
        {isLoading && (
          <>
            {[0, 1, 2].map((i) => (
              <div key={`skeleton-${i}`} className="character-card skeleton-card">
                <div className="character-avatar skeleton-avatar" />
                <div className="character-info">
                  <div className="skeleton-line skeleton-line-w70" />
                  <div className="skeleton-line skeleton-line-w50" />
                </div>
              </div>
            ))}
          </>
        )}

        {!isLoading && characters.length === 0 && (
          <div
            style={{
              padding: '32px 16px',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: '13px',
            }}
          >
            No characters yet. Create one to get started!
          </div>
        )}

        {characters.map((character, index) => (
          <div
            key={character.id}
            className={`character-card ${
              selectedCharacterId === character.id ? 'active' : ''
            }`}
            onClick={() => onSelect(character.id)}
            style={{ animationDelay: `${index * 50}ms` }}
          >
            <div className="character-avatar">
              {character.avatar_url ? (
                <img
                  src={character.avatar_url}
                  alt={character.name}
                  className="character-avatar-img"
                />
              ) : (
                character.avatar_emoji || getInitial(character.name)
              )}
            </div>
            <div className="character-info">
              <div className="character-name">{character.name}</div>
              <div className="character-desc">
                {character.description || 'No description'}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Footer — New Character */}
      <div className="sidebar-footer">
        <button className="new-character-btn" onClick={onCreate}>
          <Plus size={18} />
          New Character
        </button>
      </div>
    </aside>
  );
}
