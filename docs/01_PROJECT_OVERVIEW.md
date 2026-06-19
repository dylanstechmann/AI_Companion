# AI Companion - Project Overview

## Vision
A full-stack, self-hosted AI companion platform that provides:
- Real-time voice conversation with AI characters (hands-free, voice-activity-detected)
- Vision/image understanding
- Long-term memory per character (ChromaDB vector store)
- Tool use (web search, code execution, PDF generation, email)
- Research agent that generates reports
- Code sandbox with live streaming
- 3D avatar with lip-sync and emotion
- Multi-agent orchestration and skill creation
- Web browser control/automation
- User authentication and Bitcoin payment integration
- PWA mobile support (iOS Action Button, background audio)

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.11, FastAPI, Uvicorn | Async, streaming SSE |
| LLM | OpenRouter API (openai SDK) | Model: google/gemini-2.5-flash |
| STT | faster-whisper (local GPU) or cloud | Switchable via config |
| TTS | Stub - needs implementation | Priority: OpenRouter or browser SpeechSynthesis |
| Memory | ChromaDB (persistent) | Per-character vector collections |
| Database | SQLite via aiosqlite | Characters + message history |
| Frontend | React 18, Vite 6, Vanilla CSS | PWA with service worker |
| Styling | Dark glassmorphic design system | CSS custom properties, Inter font |
| 3D | Not yet implemented | Target: Three.js + Ready Player Me or VRM |
| Infrastructure | Docker Compose, NVIDIA CUDA 12.2.2 | GPU pass-through for Whisper |
| GPU | NVIDIA RTX 3080 | Used for local STT |

## Architecture

```
Docker Compose
+---------------------------+    +------------------------------+
|   Frontend (Vite)         |    |   Backend (FastAPI)          |
|   Port 3000               |--->|   Port 8000                  |
|                           |    |                              |
|  React Components:        |    |  Services:                   |
|  - ChatArea               |    |  - LLMService (OpenRouter)   |
|  - VoiceRecorder (VAD)    |    |  - STTService (Whisper)      |
|  - ImageCapture           |    |  - MemoryManager (ChromaDB)  |
|  - Sidebar                |    |  - CodeSandbox               |
|  - SettingsPanel          |    |  - ResearchAgent             |
|  - StatusBar              |    |  - Tools (6 functions)       |
|                           |    |                              |
|  Hooks:                   |    |  Storage:                    |
|  - useSSE                 |    |  - SQLite (messages)         |
|  - useBackgroundAudio     |    |  - ChromaDB (memory)         |
+---------------------------+    +------------------------------+

Volumes: ./data (DB + ChromaDB), ./sandbox (code exec)
```

## API Routes (All Implemented)

| Method | Route | Description | Status |
|--------|-------|-------------|--------|
| GET | /api/health | GPU, STT mode, ChromaDB status | Done |
| GET | /api/config | Current configuration | Done |
| PUT | /api/config | Update STT_MODE | Done |
| POST | /api/stt | Upload audio -> transcript | Done |
| POST | /api/tts | Text -> speech | Stub (501) |
| GET | /api/characters | List all characters | Done |
| POST | /api/characters | Create new character | Done |
| PUT | /api/characters/{id} | Update character | Done |
| DELETE | /api/characters/{id} | Delete (not defaults) | Done |
| GET | /api/characters/{id}/messages | Chat history | Done |
| POST | /api/chat | Stream text chat (SSE) | Done |
| POST | /api/chat/image | Stream vision chat (SSE) | Done |
| POST | /api/code/execute | Run code in sandbox | Done |
| POST | /api/agent/research | Research agent | Done |
| POST | /api/memory/search | Search long-term memory | Done |

## Environment Variables (.env)

```
OPENROUTER_API_KEY=sk-or-v1-...
STT_MODE=local
WHISPER_MODEL=base
WHISPER_DEVICE=cuda
DATABASE_URL=sqlite:///app/data/companion.db
CHROMA_PERSIST_DIR=/app/data/chromadb
EMBEDDING_MODEL=openai/text-embedding-3-small
SANDBOX_TIMEOUT_SECONDS=30
LLM_MODEL=google/gemini-2.5-flash
TAVILY_API_KEY=
PROXY_URL=
CRAWL_DELAY_SECONDS=3
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
```

## Default Characters

1. Greg - Witty, uncensored, humorous Grok-like personality
2. Tiffany - Analytical, empathetic, structured thinker
3. Friendly AI - Flexible, adaptable, takes on any personality

## What is Built (Phase 1)

- Full backend with 15 API routes
- Streaming SSE chat with tool calling
- Vision/image chat
- Local GPU STT (faster-whisper) + cloud fallback
- ChromaDB long-term memory per character
- Code sandbox (Python + JavaScript)
- Research agent with PDF generation
- React frontend with glassmorphic dark theme
- Voice Activity Detection (VAD) hands-free mode
- Image capture (camera + photo library)
- Character management (CRUD + settings editor)
- Docker Compose with GPU pass-through
- PWA manifest

## What is Remaining

| Phase | Feature | Complexity | Recommended Model Tier |
|-------|---------|-----------|----------------------|
| 1.5 | TTS Integration | Medium | Mid-tier (Flash/Haiku) |
| 1.5 | Frontend polish and bug fixes | Low-Med | Mid-tier |
| 2 | 3D Avatar + Lip Sync | High | Top-tier (Pro/Opus) |
| 2 | Live code streaming | Medium | Mid-tier |
| 3 | Multi-agent orchestration | High | Top-tier |
| 3 | Skill/plugin system | High | Top-tier |
| 3 | Web browser control | High | Top-tier |
| 4 | User auth + sessions | Medium | Mid-tier |
| 4 | Bitcoin/Lightning payment | Medium | Mid-tier |

## Running the Project

```bash
docker compose up --build -d
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
# API docs: http://localhost:8000/docs
```
