# 🤖 AI Companion

This is a personal hobby and learning project, developed with substantial assistance from AI coding tools.

> A private, self-hosted AI assistant with persistent memory, voice interaction, and agentic capabilities — accessible as a PWA from any device, including instant launch via the iPhone Action Button.

[![Docker](https://img.shields.io/badge/Docker-Compose-2496EDlogo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ABlogo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🚀 Features

| Category | Capabilities |
|---|---|
| **🎙️ Voice Interface** | Real-time Speech-to-Text via Faster Whisper (GPU-accelerated), natural TTS responses |
| **🧠 Persistent Memory** | Stores and retrieves conversation memories using ChromaDB vector embeddings |
| **💬 Conversational AI** | Powered by OpenRouter with support for multiple LLM backends (GPT-4o, Claude, Llama, etc.) |
| **🔧 Agentic Tools** | Code execution sandbox, web research, email integration, and extensible tool system |
| **📱 PWA** | Installable Progressive Web App with offline support and iPhone Action Button integration |
| **🐳 Fully Dockerized** | One-command deployment with GPU passthrough — zero host pollution |

---

## 🛠️ Tech Stack

```
┌───────────────────────────────────────────────┐
│                  Frontend                     │
│  React / Vite  ->  PWA  ->  Web Audio API     │
├───────────────────────────────────────────────┤
│                  Backend                      │
│  FastAPI  ->  Faster Whisper  ->  ChromaDB    │
│  SQLite   ->  OpenRouter SDK  ->  TTS Engine  │
├───────────────────────────────────────────────┤
│               Infrastructure                  │
│  Docker Compose  ->  NVIDIA Container Toolkit │
└───────────────────────────────────────────────┘
```

---

## 📋 Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | 24.0+ | or Docker Engine on Linux |
| [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) | Latest | Required for GPU-accelerated STT |
| NVIDIA GPU | 6 GB+ VRAM | For Whisper `large-v3`; smaller models need less |
| [Git](https://git-scm.com/) | 2.0+ | For cloning the repository |

> [!NOTE]
> The supplied development Compose file reserves an NVIDIA GPU. The backend also accepts `STT_MODE=cloud`, which sends audio to its configured transcription provider. Changing that setting leaves the Compose GPU reservation in place.

---

## ⚡ Quick Start

The development ports bind to localhost. Registration and demo login start disabled. For the first launch, generate a `JWT_SECRET` and temporarily set `ALLOW_REGISTRATION=true` in `.env` as described in [Authentication and trusted accounts](docs/AUTHENTICATION.md#create-the-first-account-locally).

```bash
# 1. Clone the repository
git clone https://github.com/dylanstechmann/AI_Companion.git
cd AI_Companion

# 2. Create your environment file
cp .env.example .env

# 3. Configure local setup in .env
#    Set OPENROUTER_API_KEY for chat and follow the account setup above.
nano .env   # or use your preferred editor

# 4. Build and launch
docker compose up --build -d

# 5. Open the app
#    Frontend:  http://localhost:3000
#    Backend:   http://localhost:8000/docs  (Swagger UI)
```

At `http://localhost:3000`, choose **Register** to create your first trusted account. Set `ALLOW_REGISTRATION=false` again in `.env` and apply it with `docker compose up -d --force-recreate backend`. Use the same account for subsequent sign-ins.

> [!TIP]
> View service logs with `docker compose logs -f`.

---

## 🔌 API Endpoints

The development backend exposes its API at `http://localhost:8000`. See `/docs` (Swagger UI) or `/redoc` (ReDoc) for the full route list. Operational requests require an `Authorization: Bearer <access_token>` header. The frontend handles sign-in and token refresh.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Check service status without signing in |
| `GET` | `/api/auth/options` | Check which sign-in options the instance enables |
| `GET` | `/api/characters` | List companion characters |
| `GET` | `/api/characters/{character_id}/messages` | Retrieve a character's conversation history |
| `POST` | `/api/chat` | Send a text message and stream the response |
| `POST` | `/api/stt` | Upload an audio file for transcription |
| `POST` | `/api/tts` | Convert text to speech audio |
| `POST` | `/api/code/execute` | Run Python or JavaScript in the code execution service |
| `POST` | `/api/agent/research` | Start a research request |

---

## 📲 PWA Installation

### Desktop (Chrome / Edge)
1. Navigate to `http://localhost:3000`
2. Click the **install** icon in the address bar
3. Click **Install**

### iOS (Safari)
1. Open Safari and navigate to `https://your-host:3000`
2. Tap **Share** → **Add to Home Screen**
3. *(Optional)* Set up the Action Button for instant voice access — see the [iOS Action Button Setup Guide](docs/ios-action-button-setup.md)

### Android (Chrome)
1. Navigate to `https://your-host:3000`
2. Tap the **"Add to Home Screen"** banner, or Menu → **Install App**

### PWA & Security Hardening
- **Auth Rate Limiting**: The backend enforces sliding-window rate limiting on `/api/auth/login` (5 attempts/min) and `/api/auth/refresh` (20 attempts/min) returning HTTP 429 with `Retry-After` headers to protect against brute-force attacks and token replay.
- **Offline fallback** checks the Companion server and restores the original app URL, including voice and avatar shortcuts, when the API and frontend respond. [Workbox offline fallback](https://developer.chrome.com/docs/workbox/migration/migrate-from-v5#precachefallback_in_runtime_caching)
- **Rich App Manifest**: Enhanced PWA manifest with application shortcuts (*Start Voice Chat*, *3D Avatars*), categories, and maskable icons for desktop and mobile install dialogs.

### Testing & Verification

In the dev container, install the backend test dependencies from [`backend/requirements-test.txt`](backend/requirements-test.txt) and run `npm ci` in `frontend`. The commands below start at the repository root.

```bash
# From a fresh shell at the repository root, run the backend auth suite
(cd backend && python -B -m unittest discover -s tests -v)

# Run the frontend API client and PWA suite
(cd frontend && npm test)
```

For a browser check, use a production build with an active service worker and the backend reachable at `/api/health`. Sign in, then open the voice shortcut and check that focus moves to the microphone button. Recording starts only after activating the button. Add a fragment such as `#saved` to the shortcut URL, then take the browser offline and reload it in the same tab. After reconnecting, check that the fallback restores the shortcut URL and microphone focus. Open the avatar shortcut and check that the character sidebar opens and receives focus. API URLs remain outside the navigation fallback.

---

## 📁 Project Structure

```
AI_Companion/
├── backend/                  # FastAPI backend service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py               # Application entry point
│   ├── api/                   # Route handlers
│   │   ├── chat.py
│   │   ├── voice.py
│   │   ├── memory.py
│   │   └── tools.py
│   ├── core/                  # Business logic
│   │   ├── llm.py             # OpenRouter LLM integration
│   │   ├── stt.py             # Faster Whisper STT engine
│   │   ├── tts.py             # Text-to-Speech engine
│   │   ├── memory.py          # ChromaDB vector memory
│   │   └── sandbox.py         # Code execution sandbox
│   └── models/                # Pydantic schemas
├── frontend/                  # React PWA frontend
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   ├── public/
│   │   └── manifest.json      # PWA manifest
│   └── src/
│       ├── App.jsx
│       ├── components/        # UI components
│       └── services/          # API client modules
├── data/                      # Persistent data (git-ignored)
│   ├── companion.db           # SQLite database
│   └── chromadb/              # Vector embeddings
├── sandbox/                   # Code execution workspace (git-ignored)
├── docs/                      # Documentation
│   └── ios-action-button-setup.md
├── docker-compose.yml         # Container orchestration
├── .env                       # Environment variables (git-ignored)
├── .env.example               # Environment template (safe to commit)
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🗺️ Roadmap

### Phase 1 — Foundation *(current)*
- [x] Docker infrastructure with GPU passthrough
- [ ] FastAPI backend with health checks
- [ ] Faster Whisper STT integration
- [ ] OpenRouter LLM chat pipeline
- [ ] SQLite conversation persistence
- [ ] React PWA frontend with voice recording

### Phase 2 — Intelligence
- [ ] ChromaDB long-term vector memory
- [ ] Semantic memory search and recall
- [ ] Agentic tool system (code execution, web research)
- [ ] TTS voice response pipeline
- [ ] Conversation context management

### Phase 3 — Polish & Expansion
- [ ] iPhone Action Button integration & auto-record
- [ ] Email sending capability
- [ ] Multi-modal input (images, documents)
- [ ] Custom personality and system prompts
- [ ] Scheduled tasks and reminders
- [ ] Plugin architecture for community tools

---

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a pull request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Built with ❤️ and a healthy distrust of cloud-only AI
</p>
