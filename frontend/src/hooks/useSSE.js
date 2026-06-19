import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * useSSE — Server-Sent Events hook for streaming AI responses.
 *
 * Usage:
 *   const { startStream, isStreaming, error, close } = useSSE();
 *   startStream('/api/chat/stream', { character_id, message }, (chunk) => { ... });
 */
export default function useSSE() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const eventSourceRef = useRef(null);
  const abortControllerRef = useRef(null);

  const close = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  const startStream = useCallback((url, body, onChunk, onComplete) => {
    // Close any existing stream
    close();
    setError(null);
    setIsStreaming(true);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    // Use fetch for POST-based SSE (more flexible than EventSource)
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: abortController.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Stream failed: ${response.status} ${response.statusText}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        function read() {
          reader
            .read()
            .then(({ done, value }) => {
              if (done) {
                // Process any remaining buffer
                if (buffer.trim()) {
                  processSSEBuffer(buffer, onChunk);
                }
                setIsStreaming(false);
                onComplete?.();
                return;
              }

              buffer += decoder.decode(value, { stream: true });

              // Process complete SSE events from buffer
              const lines = buffer.split('\n');
              buffer = lines.pop() || ''; // Keep incomplete last line

              let currentData = '';
              for (const line of lines) {
                if (line.startsWith('data: ')) {
                  currentData = line.slice(6);
                  if (currentData === '[DONE]') {
                    setIsStreaming(false);
                    onComplete?.();
                    return;
                  }
                  try {
                    const parsed = JSON.parse(currentData);
                    onChunk(parsed);
                  } catch {
                    // If it's not JSON, pass the raw text
                    onChunk({ text: currentData });
                  }
                } else if (line.startsWith('event: error')) {
                  // Next data line will contain the error
                } else if (line === '') {
                  // Empty line = event separator, continue
                }
              }

              read();
            })
            .catch((err) => {
              if (err.name !== 'AbortError') {
                setError(err.message);
                setIsStreaming(false);
              }
            });
        }

        read();
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setError(err.message);
          setIsStreaming(false);
        }
      });
  }, [close]);

  // For GET-based SSE using native EventSource
  const connectSSE = useCallback((url, onChunk, onComplete) => {
    close();
    setError(null);
    setIsStreaming(true);

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      if (event.data === '[DONE]') {
        setIsStreaming(false);
        onComplete?.();
        es.close();
        return;
      }
      try {
        const parsed = JSON.parse(event.data);
        onChunk(parsed);
      } catch {
        onChunk({ text: event.data });
      }
    };

    es.onerror = () => {
      setError('Connection lost. Attempting to reconnect...');
      setIsStreaming(false);
      es.close();
    };
  }, [close]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      close();
    };
  }, [close]);

  return { startStream, connectSSE, isStreaming, error, close };
}

function processSSEBuffer(buffer, onChunk) {
  const lines = buffer.split('\n');
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = line.slice(6);
      if (data !== '[DONE]') {
        try {
          onChunk(JSON.parse(data));
        } catch {
          onChunk({ text: data });
        }
      }
    }
  }
}
