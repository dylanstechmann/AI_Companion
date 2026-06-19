import { useState, useRef, useCallback } from 'react';
import { X, Play, Square, CheckCircle, AlertCircle, Loader, Clock } from 'lucide-react';

/**
 * AgentPanel — Multi-agent orchestration UI.
 * Shows the orchestrator's plan as a visual task list with live progress.
 *
 * Props:
 *   isOpen: boolean
 *   onClose: () => void
 */
export default function AgentPanel({ isOpen, onClose }) {
  const [query, setQuery] = useState('');
  const [tasks, setTasks] = useState([]);
  const [taskOutputs, setTaskOutputs] = useState({});
  const [finalResult, setFinalResult] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const abortRef = useRef(null);

  const runOrchestration = useCallback(async () => {
    if (!query.trim() || isRunning) return;
    setTasks([]);
    setTaskOutputs({});
    setFinalResult('');
    setProgress(0);
    setIsRunning(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch('/api/agents/orchestrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6);
          if (data === '[DONE]') continue;

          try {
            const event = JSON.parse(data);

            if (event.type === 'plan') {
              const plannedTasks = (event.tasks || []).map((t, i) => ({
                ...t,
                status: 'queued',
                output: '',
              }));
              setTasks(plannedTasks);
            } else if (event.type === 'task_started') {
              setTasks((prev) => prev.map((t) =>
                t.id === event.task_id ? { ...t, status: 'running' } : t
              ));
            } else if (event.type === 'task_output') {
              setTaskOutputs((prev) => ({
                ...prev,
                [event.task_id]: (prev[event.task_id] || '') + (event.text || ''),
              }));
            } else if (event.type === 'task_completed') {
              setTasks((prev) => prev.map((t) =>
                t.id === event.task_id ? { ...t, status: 'done', result: event.result } : t
              ));
              setProgress((prev) => prev + 1);
            } else if (event.type === 'final_result') {
              setFinalResult(event.text || '');
            }
          } catch {}
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error('Orchestration error:', err);
        setFinalResult(`Error: ${err.message}`);
      }
    } finally {
      setIsRunning(false);
      abortRef.current = null;
    }
  }, [query, isRunning]);

  const cancelOrchestration = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      setIsRunning(false);
    }
  }, []);

  if (!isOpen) return null;

  const totalTasks = tasks.length;
  const completedTasks = tasks.filter((t) => t.status === 'done').length;
  const progressPct = totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 0;

  return (
    <div className="agent-panel glass-panel animate-slide-in-right">
      <div className="agent-panel-header">
        <h2 className="settings-title">Agent Orchestrator</h2>
        <button onClick={onClose} className="icon-btn" title="Close">
          <X size={20} />
        </button>
      </div>

      <div className="settings-body scrollbar-custom">
        {/* Query Input */}
        <section className="settings-section">
          <h3 className="settings-section-title">Task Request</h3>
          <div className="settings-field">
            <textarea
              className="settings-textarea"
              placeholder="Describe a complex task for the AI agents to work on..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={3}
              style={{ minHeight: '80px', resize: 'vertical' }}
            />
          </div>
          <div className="agent-controls">
            {!isRunning ? (
              <button
                className="settings-save-btn"
                onClick={runOrchestration}
                disabled={!query.trim()}
              >
                <Play size={16} /> Start Orchestration
              </button>
            ) : (
              <button className="settings-save-btn" onClick={cancelOrchestration} style={{ background: 'var(--danger)' }}>
                <Square size={16} /> Cancel
              </button>
            )}
          </div>
        </section>

        {/* Progress Bar */}
        {totalTasks > 0 && (
          <div className="agent-progress-bar">
            <div className="agent-progress-fill" style={{ width: `${progressPct}%` }} />
            <span className="agent-progress-text">{completedTasks}/{totalTasks} tasks</span>
          </div>
        )}

        {/* Task List */}
        {tasks.length > 0 && (
          <section className="settings-section">
            <h3 className="settings-section-title">Execution Plan</h3>
            <div className="agent-plan">
              {tasks.map((task) => (
                <div key={task.id} className={`agent-task-card status-${task.status}`}>
                  <div className="agent-task-header">
                    <span className="agent-task-name">
                      {task.status === 'running' && <Loader size={12} className="spin" />}
                      {task.status === 'done' && <CheckCircle size={12} />}
                      {task.status === 'queued' && <Clock size={12} />}
                      {task.agent} — {task.description}
                    </span>
                    <span className={`agent-task-status status-${task.status}`}>{task.status}</span>
                  </div>
                  {taskOutputs[task.id] && (
                    <div className="agent-task-output scrollbar-custom">
                      {taskOutputs[task.id].slice(-500)}
                    </div>
                  )}
                  {task.result && task.status === 'done' && !taskOutputs[task.id] && (
                    <div className="agent-task-output scrollbar-custom">
                      {typeof task.result === 'string' ? task.result.slice(0, 500) : JSON.stringify(task.result).slice(0, 500)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Final Result */}
        {finalResult && (
          <section className="settings-section">
            <h3 className="settings-section-title">Final Result</h3>
            <div className="agent-final-result">
              {finalResult}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
