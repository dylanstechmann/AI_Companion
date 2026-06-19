import { useState, useEffect, useCallback } from 'react';
import { X, Plus, Trash2, Code, Package, RefreshCw, Loader } from 'lucide-react';

/**
 * SkillsPanel — Skill/plugin management UI.
 * List installed skills, create new ones, toggle/delete.
 *
 * Props:
 *   isOpen: boolean
 *   onClose: () => void
 */
export default function SkillsPanel({ isOpen, onClose }) {
  const [skills, setSkills] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [isCreating, setIsCreating] = useState(false);

  // Create form state
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newCode, setNewCode] = useState('');
  const [newFunctions, setNewFunctions] = useState('');

  const fetchSkills = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetch('/api/skills');
      if (res.ok) {
        const data = await res.json();
        setSkills(data.skills || []);
      }
    } catch (err) {
      console.error('Failed to fetch skills:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) fetchSkills();
  }, [isOpen, fetchSkills]);

  const handleCreate = useCallback(async () => {
    if (!newName.trim() || !newCode.trim()) return;
    setIsCreating(true);
    try {
      let functionsSchema = [];
      if (newFunctions.trim()) {
        functionsSchema = JSON.parse(newFunctions);
      }

      const res = await fetch('/api/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newName.trim(),
          description: newDesc,
          code: newCode,
          functions: functionsSchema,
        }),
      });

      if (res.ok) {
        setNewName('');
        setNewDesc('');
        setNewCode('');
        setNewFunctions('');
        setShowCreate(false);
        fetchSkills();
      } else {
        const err = await res.json();
        alert(`Failed to create skill: ${err.detail || 'Unknown error'}`);
      }
    } catch (err) {
      alert(`Error: ${err.message}`);
    } finally {
      setIsCreating(false);
    }
  }, [newName, newDesc, newCode, newFunctions, fetchSkills]);

  const handleDelete = useCallback(async (skillName) => {
    if (!confirm(`Delete skill "${skillName}"?`)) return;
    try {
      const res = await fetch(`/api/skills/${skillName}`, { method: 'DELETE' });
      if (res.ok) {
        fetchSkills();
      }
    } catch (err) {
      console.error('Delete failed:', err);
    }
  }, [fetchSkills]);

  if (!isOpen) return null;

  return (
    <div className="skills-panel glass-panel animate-slide-in-right">
      <div className="skills-panel-header">
        <h2 className="settings-title">Skills</h2>
        <div className="skills-header-actions">
          <button className="icon-btn" onClick={fetchSkills} title="Refresh">
            <RefreshCw size={16} />
          </button>
          <button className="icon-btn" onClick={() => setShowCreate(!showCreate)} title="New skill">
            <Plus size={20} />
          </button>
          <button className="icon-btn" onClick={onClose} title="Close">
            <X size={20} />
          </button>
        </div>
      </div>

      <div className="settings-body scrollbar-custom">
        {/* Create Form */}
        {showCreate && (
          <section className="settings-section">
            <h3 className="settings-section-title">
              <Code size={14} /> Create New Skill
            </h3>
            <div className="skill-create-form">
              <div className="settings-field">
                <label className="settings-field-label">Name</label>
                <input
                  className="settings-input"
                  type="text"
                  placeholder="my_skill"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
              </div>
              <div className="settings-field">
                <label className="settings-field-label">Description</label>
                <input
                  className="settings-input"
                  type="text"
                  placeholder="What this skill does"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                />
              </div>
              <div className="settings-field">
                <label className="settings-field-label">Handler Code (Python)</label>
                <textarea
                  className="settings-textarea"
                  style={{ fontFamily: 'monospace', fontSize: '0.75rem', minHeight: '200px' }}
                  placeholder={'async def my_function(arg1: str) -> dict:\n    return {"result": arg1}'}
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value)}
                />
              </div>
              <div className="settings-field">
                <label className="settings-field-label">Functions Schema (JSON)</label>
                <textarea
                  className="settings-textarea"
                  style={{ fontFamily: 'monospace', fontSize: '0.75rem', minHeight: '120px' }}
                  placeholder={'[\n  {\n    "name": "my_function",\n    "description": "Does something",\n    "parameters": {"type": "object", "properties": {"arg1": {"type": "string"}}, "required": ["arg1"]}\n  }\n]'}
                  value={newFunctions}
                  onChange={(e) => setNewFunctions(e.target.value)}
                />
              </div>
              <button
                className="settings-save-btn"
                onClick={handleCreate}
                disabled={isCreating || !newName.trim() || !newCode.trim()}
              >
                {isCreating ? <Loader size={16} className="spin" /> : <Package size={16} />}
                Create Skill
              </button>
            </div>
          </section>
        )}

        {/* Skills List */}
        <section className="settings-section">
          <h3 className="settings-section-title">
            Installed Skills ({skills.length})
          </h3>

          {isLoading && <p className="settings-hint">Loading skills...</p>}

          {!isLoading && skills.length === 0 && (
            <p className="settings-hint">
              No skills installed. Click + to create one, or ask the AI to create a skill for you.
            </p>
          )}

          {skills.map((skill) => (
            <div key={skill.name} className="skill-card">
              <div className="skill-card-info">
                <div className="skill-card-name">{skill.name}</div>
                <div className="skill-card-desc">{skill.description || 'No description'}</div>
                {skill.functions && (
                  <div className="skill-card-funcs">
                    {skill.functions.map((f) => (
                      <span key={f.name} className="skill-func-badge">{f.name}</span>
                    ))}
                  </div>
                )}
              </div>
              <div className="skill-card-actions">
                <button
                  className="skill-delete-btn"
                  onClick={() => handleDelete(skill.name)}
                  title="Delete skill"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
