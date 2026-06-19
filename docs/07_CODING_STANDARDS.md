# AI Companion - Coding Standards and Conventions

Give this file to any AI agent working on the project so they follow existing patterns.

---

## General Rules

1. DO NOT delete or modify existing comments/docstrings unless directly related to your change
2. DO NOT refactor unrelated code while making changes
3. DO NOT change the design system colors or fonts without explicit approval
4. ALL new backend files must have module-level docstrings
5. ALL new functions must have type hints
6. ALL API responses should use Pydantic models from schemas.py
7. Use existing patterns - do not introduce new libraries without justification

---

## Backend Conventions (Python / FastAPI)

### File Structure
```python
"""
Module docstring explaining purpose.
"""

from __future__ import annotations

import stdlib_modules
import third_party_modules
from app.internal_modules import stuff

logger = logging.getLogger(__name__)

class ServiceName:
    """Docstring."""
    
    def __init__(self) -> None:
        settings = get_settings()
        # ... init
    
    async def public_method(self, arg: str) -> ReturnType:
        """Docstring with description."""
        pass
```

### Settings
- All configuration comes from environment variables via app/config.py
- Access via: `from app.config import get_settings; settings = get_settings()`
- Add new env vars to both config.py AND .env

### Database
- All DB operations are async via aiosqlite
- Use the helper functions in database.py (get_character, add_message, etc.)
- Do NOT create new database connections - use the existing helpers
- Parameterized queries only (no f-strings in SQL)

### Streaming
- All streaming endpoints use SSE format: `data: {json}\n\n` with `data: [DONE]\n\n` terminator
- Return StreamingResponse with media_type="text/event-stream"
- Include headers: Cache-Control: no-cache, X-Accel-Buffering: no

### Error Handling
- Use HTTPException for API errors
- Log errors with logger.exception() for stack traces
- Return user-friendly error messages
- Never expose internal details in error responses

### Tools
- New tools go in tools.py
- Must be added to both TOOLS_SCHEMA (JSON schema) and TOOL_DISPATCH (function map)
- Tool functions must be async
- Tool functions should return JSON-serializable results

---

## Frontend Conventions (React / Vanilla CSS)

### Component Structure
```jsx
import React, { useState, useEffect } from 'react';
import { IconName } from 'lucide-react';

export default function ComponentName({ prop1, prop2 }) {
  const [state, setState] = useState(initialValue);
  
  useEffect(() => {
    // side effects
  }, [dependencies]);
  
  const handleAction = () => {
    // handler
  };
  
  return (
    <div className="component-name">
      {/* JSX */}
    </div>
  );
}
```

### Styling
- USE vanilla CSS with the design system from index.css
- DO NOT use Tailwind utility classes (flex, p-2, space-y-4, etc.)
- Reference CSS custom properties: var(--bg-primary), var(--accent-primary), etc.
- For component-specific styles, add classes to index.css
- For one-off styles, use inline style={{ }} objects
- The design aesthetic is: dark glassmorphic, indigo/violet accents, Inter font

### Key CSS Classes Available
- .glass-panel - Glassmorphic container (backdrop-filter blur, border, gradient)
- .icon-btn - Icon button base style
- .recording - Active recording state (red glow)
- .glow-danger - Red pulsing glow animation
- .animate-fade-in - Fade in animation
- .animate-slide-in-right - Slide from right
- .streaming-cursor - Blinking cursor for streaming text
- .chat-area, .chat-messages, .chat-input-area - Chat layout
- .message, .message-user, .message-assistant - Message bubbles
- .send-btn - Send button

### API Calls
- Use fetch() for all API calls
- For streaming: use the useSSE hook's startStream() method
- For file uploads: use FormData
- Proxy is configured: just use /api/... paths (no need for full URLs)

### State Management
- Use React useState/useCallback/useEffect (no Redux/Zustand)
- Shared state is lifted to App.jsx and passed as props
- API data is fetched in the component that needs it

### Icons
- Use lucide-react for all icons
- Import only the icons you need: `import { Mic, Send } from 'lucide-react'`

---

## Docker Conventions

### Volumes
- ./data/ - Persistent data (SQLite DB, ChromaDB)
- ./sandbox/ - Code execution workspace
- Source code is volume-mounted for hot reload in dev

### Networking
- Frontend proxies /api/* to backend:8000
- Services communicate via Docker network (use service names: backend, frontend)

### GPU
- Backend container has GPU access via NVIDIA Container Toolkit
- Use deploy.resources.reservations.devices in docker-compose.yml

---

## Testing

### Backend
```bash
# Test health
curl http://localhost:8000/api/health

# Test chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"character_id": 1, "message": "Hello"}'

# Test STT
curl -X POST http://localhost:8000/api/stt \
  -F "file=@recording.webm"

# Test image
curl -X POST http://localhost:8000/api/chat/image \
  -F "file=@photo.jpg" \
  -F "message=What is this?" \
  -F "character_id=1"
```

### Frontend
- Open browser devtools console for errors
- Check Network tab for failed requests
- Test on mobile viewport (Chrome DevTools device toolbar)
