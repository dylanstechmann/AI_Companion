# AI Companion - Current Codebase Map

This document maps every file in the project, what it does, and how the pieces connect.
Give this to any AI agent so they understand the existing code before making changes.

## Directory Structure

```
AI_Companion/
├── .env                          # All environment variables
├── docker-compose.yml            # Orchestrates backend + frontend containers
├── docs/                         # These planning documents
│
├── backend/
│   ├── Dockerfile                # CUDA 12.2.2 + Python 3.11 + ffmpeg
│   ├── requirements.txt          # Python dependencies
│   └── app/
│       ├── __init__.py           # Empty
│       ├── config.py             # Settings singleton (loads .env)
│       ├── database.py           # SQLite async: characters + messages tables
│       ├── schemas.py            # Pydantic request/response models
│       ├── characters.py         # Default character definitions
│       ├── stt.py                # Speech-to-text (local Whisper + cloud)
│       ├── llm.py                # LLM chat service (OpenRouter, streaming, tools)
│       ├── memory.py             # ChromaDB vector memory per character
│       ├── sandbox.py            # Code execution sandbox (Python/JS)
│       ├── tools.py              # Tool functions + OpenAI function schema
│       ├── research.py           # Research agent (search + synthesize + PDF)
│       └── main.py               # FastAPI app, all routes, lifespan init
│
├── frontend/
│   ├── Dockerfile                # Node 20 Alpine
│   ├── package.json              # React 18, Vite 6, lucide-react
│   ├── index.html                # Entry HTML with Google Fonts
│   ├── vite.config.js            # Vite config with PWA + API proxy
│   ├── public/
│   │   └── manifest.json         # PWA manifest
│   └── src/
│       ├── main.jsx              # React root render
│       ├── index.css             # Full design system (CSS custom props)
│       ├── App.jsx               # Root layout, state, sidebar + chat
│       ├── components/
│       │   ├── Sidebar.jsx       # Character list, new character button
│       │   ├── ChatArea.jsx      # Messages, streaming, input, image send
│       │   ├── VoiceRecorder.jsx # VAD-based hands-free mic (mute/unmute)
│       │   ├── ImageCapture.jsx  # Camera + photo library picker
│       │   ├── SettingsPanel.jsx # STT toggle, character editor
│       │   └── StatusBar.jsx     # Health display bar
│       └── hooks/
│           ├── useSSE.js         # SSE streaming hook (POST + GET modes)
│           └── useBackgroundAudio.js  # AudioContext + mediaSession
│
├── data/                         # Docker volume: SQLite DB + ChromaDB
└── sandbox/                      # Docker volume: code execution workspace
```

## Key Data Flows

### Text Chat Flow
1. User types message or VAD captures speech -> STT -> text
2. Frontend sends POST /api/chat with {character_id, message}
3. Backend LLMService.stream_chat():
   a. Fetches character from SQLite
   b. Gets last 50 messages for context
   c. Recalls top-5 relevant memories from ChromaDB
   d. Builds messages array (system prompt + memories + history + user turn)
   e. Calls OpenRouter streaming completion with tools
   f. If tool_calls received: executes tools, feeds results back, continues
   g. Yields text chunks as SSE data events
   h. After stream ends: saves user + assistant messages to SQLite
   i. Embeds the exchange into ChromaDB for long-term memory
4. Frontend useSSE hook reads the stream, updates UI character by character

### Image Chat Flow
1. User selects image via ImageCapture (File object)
2. Frontend sends POST /api/chat/image as multipart FormData:
   - field "file": the image File
   - field "message": text prompt
   - field "character_id": integer
3. Backend reads image bytes, base64-encodes, creates data URI
4. Passes to LLMService.stream_chat() with image_url parameter
5. build_messages() formats as OpenAI vision content (image_url type)
6. Tools are SKIPPED when image is present (some models conflict)
7. Response streams back via SSE same as text chat

### Voice Activity Detection (VAD) Flow
1. User taps mic button to "unmute" (toggles isMuted state)
2. Browser requests microphone permission
3. AudioContext + AnalyserNode monitors volume in real-time via requestAnimationFrame
4. When volume > threshold: marks isSpeaking = true
5. When volume drops below threshold for 2 seconds: 
   a. Stops current MediaRecorder chunk
   b. Sends audio blob to POST /api/stt
   c. Immediately starts new MediaRecorder for next phrase
6. STT returns transcript text
7. onVoiceMessage callback fires -> handleSend(text) -> auto-sends to AI
8. While AI is streaming (isStreaming=true), VAD loop ignores microphone input
9. When AI finishes, VAD resumes listening

### Memory System
- Each character has a ChromaDB collection named "character_{id}"
- After every chat exchange, the full "User: X\nAssistant: Y" is embedded and stored
- Before each new chat, top-5 semantically similar memories are recalled
- Memories are injected into the system prompt under "## Relevant memories"
- Embeddings use OpenRouter's text-embedding-3-small model

### Tool Calling
Available tools the LLM can invoke:
1. web_search(query) - Tavily API or fallback httpx search
2. read_webpage(url) - Fetch and extract text, respects crawl delay
3. execute_code(language, code) - Python or JavaScript via subprocess
4. generate_pdf(html_content) - ReportLab PDF generation
5. send_email(to, subject, body) - SMTP (needs config)
6. recall_memory(character_id, query) - Search ChromaDB

Tools are defined in TOOLS_SCHEMA (OpenAI function calling format) and dispatched via TOOL_DISPATCH dict.

## CSS Design System (index.css)

Key CSS custom properties:
```css
--bg-primary: #0a0a1a          /* Deep dark background */
--bg-secondary: #12122a        /* Slightly lighter */
--bg-glass: rgba(255,255,255,0.03)  /* Glassmorphism */
--bg-glass-hover: rgba(255,255,255,0.06)
--border-glass: rgba(255,255,255,0.08)
--accent-primary: #6366f1      /* Indigo */
--accent-secondary: #8b5cf6    /* Violet */
--accent-glow: rgba(99,102,241,0.3)
--text-primary: #e2e8f0
--text-secondary: #94a3b8
--text-muted: #64748b
--success: #10b981
--warning: #f59e0b
--danger: #ef4444
```

Key classes: .glass-panel (backdrop-filter blur + border), .icon-btn, .recording, .glow-danger, .animate-fade-in, .streaming-cursor

## SSE Format
All streaming endpoints use this format:
```
data: {"text": "chunk of text"}\n\n
data: {"text": "more text"}\n\n
data: [DONE]\n\n
```
The frontend useSSE hook handles both JSON and raw text fallback.
