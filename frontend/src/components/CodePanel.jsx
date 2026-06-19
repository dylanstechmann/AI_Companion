import { useState, useRef, useCallback, useEffect } from 'react';
import { Play, Square, Copy, Check, ChevronDown, ChevronUp, Terminal } from 'lucide-react';

/**
 * CodePanel — Terminal-style panel for live code execution output.
 *
 * Connects to POST /api/code/execute/stream and displays output in real-time.
 *
 * Props:
 *   language: 'python' | 'javascript'
 *   code: string (the code to execute)
 *   autoRun: boolean (if true, executes on mount)
 */
export default function CodePanel({ language = 'python', code, autoRun = false }) {
  const [output, setOutput] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);
  const [exitCode, setExitCode] = useState(null);
  const [executionTime, setExecutionTime] = useState(null);
  const [copied, setCopied] = useState(false);
  const abortRef = useRef(null);
  const outputEndRef = useRef(null);

  // Auto-scroll to bottom
  useEffect(() => {
    outputEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [output]);

  const runCode = useCallback(async () => {
    setOutput([]);
    setExitCode(null);
    setExecutionTime(null);
    setIsRunning(true);
    setIsExpanded(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch('/api/code/execute/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language, code }),
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
            if (event.type === 'output') {
              setOutput((prev) => [...prev, {
                text: event.text,
                stream: event.stream || 'stdout',
              }]);
            } else if (event.type === 'status') {
              setExitCode(event.exit_code);
              setExecutionTime(event.execution_time);
            }
          } catch {
            // Non-JSON line, skip
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setOutput((prev) => [...prev, {
          text: `Error: ${err.message}`,
          stream: 'stderr',
        }]);
      }
    } finally {
      setIsRunning(false);
      abortRef.current = null;
    }
  }, [language, code]);

  const stopCode = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      setIsRunning(false);
    }
  }, []);

  const copyOutput = useCallback(() => {
    const text = output.map((o) => o.text).join('\n');
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [output]);

  // Auto-run on mount if requested
  useEffect(() => {
    if (autoRun) runCode();
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const langLabel = language === 'python' ? 'Python' : 'JavaScript';
  const langColor = language === 'python' ? 'var(--accent-primary)' : 'var(--accent-secondary)';

  return (
    <div className="code-panel">
      {/* Header */}
      <div className="code-panel-header" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="code-panel-title">
          <Terminal size={14} style={{ color: langColor }} />
          <span className="code-panel-lang" style={{ color: langColor }}>{langLabel}</span>
          {isRunning && <span className="code-panel-running">● running</span>}
          {exitCode !== null && !isRunning && (
            <span className={`code-panel-exit ${exitCode === 0 ? 'exit-ok' : 'exit-err'}`}>
              {exitCode === 0 ? '✓' : '✗'} exit {exitCode}
              {executionTime !== null && ` · ${executionTime}s`}
            </span>
          )}
        </div>
        <div className="code-panel-actions" onClick={(e) => e.stopPropagation()}>
          {output.length > 0 && (
            <button className="code-panel-btn" onClick={copyOutput} title="Copy output">
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          )}
          {!isRunning ? (
            <button className="code-panel-btn code-panel-run" onClick={runCode} title="Run code">
              <Play size={14} />
            </button>
          ) : (
            <button className="code-panel-btn code-panel-stop" onClick={stopCode} title="Stop">
              <Square size={14} />
            </button>
          )}
          <button className="code-panel-btn" onClick={() => setIsExpanded(!isExpanded)}>
            {isExpanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
        </div>
      </div>

      {/* Output */}
      {isExpanded && (
        <div className="code-panel-body scrollbar-custom">
          {output.length === 0 && !isRunning && (
            <div className="code-panel-empty">
              Click ▶ to run this {langLabel} code
            </div>
          )}
          {output.map((line, i) => (
            <div
              key={i}
              className={`code-panel-line ${line.stream === 'stderr' ? 'stderr' : 'stdout'}`}
            >
              {line.text || '\u00A0'}
            </div>
          ))}
          {isRunning && (
            <div className="code-panel-line code-panel-cursor">
              <span className="cursor-blink">▊</span>
            </div>
          )}
          <div ref={outputEndRef} />
        </div>
      )}
    </div>
  );
}
