# 🤖 AI Companion

> A self-hosted AI companion prototype with memory, voice, browser tools, and animated 3D avatars. Self-hosting does not make configured cloud providers local or private.

> [!WARNING]
> Do not expose this prototype's backend to the public internet. Authentication, per-user ownership, and code/skill execution isolation remain incomplete. The existing execution environment is not a hardened sandbox. Read the [browser and privacy audit](docs/browser-privacy-audit.md) before deploying or entering sensitive information.

## Avatar, browser, and privacy update

- Repaired bundled eye placement and appearance; preserved body morphs and isolated skeletons.
- Added portrait/body framing, reset, rendering-quality controls, and reduced-motion/visibility-aware demand rendering.
- Added cross-browser recorder format detection, cancellation-safe voice playback, and local-only browser voices by default.
- Removed remote font loading and sensitive API runtime caching. Preferences now last for the current page session, not across reloads.
- Added an optional Firefox backend automation engine, independent of which browser opens the frontend.

See the [implementation and validation report](docs/avatar-firefox-update.md) for exact scope, test results, and remaining limitations.

### Safe visual preview

```bash
cd frontend
npm ci
npm run dev
# Open http://localhost:3000/#avatar-studio
```

The avatar studio does not connect chat, microphone, or AI providers. `npm run build:studio` creates a separate static visual preview in `frontend/dist-studio`; `npm run build` creates the normal companion frontend.

### Validation

```bash
cd frontend
npm test
npm run build
npx playwright install chromium firefox
npm run test:e2e
cd ..
python -m pip install pydantic-settings
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s backend/tests -v
```

Browser tests use mocked backend responses, not real API credentials. Firefox rendering checks that require WebGL are excluded in the headless test environment; physical Firefox GPU, microphone, and Safari/iOS testing remains necessary.

[![Docker](https://img.shields.io/badge/Docker-Compose-2496EDlogo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ABlogo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🚀 Features

| Category | Capabilities |
|---|---|
| **🎙️ Voice Interface** | Real-time Speech-to-Text via Faster Whisper (GPU-accelerated), natural TTS responses |
| **🧠 Persistent Memory** | Long-term memory with ChromaDB vector embeddings — your companion remembers everything |
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
> GPU is required for local Whisper STT. If you don't have an NVIDIA GPU, you can switch `STT_MODE` to `api` in your `.env` to use a cloud-based STT provider instead.

---

## ⚡ Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/dylanstechmann/AI_Companion.git
cd AI_Companion

# 2. Create your environment file
cp .env.example .env

# 3. Edit .env with your API keys
#    At minimum, set OPENROUTER_API_KEY
nano .env   # or use your preferred editor

# 4. Build and launch
docker compose up --build

# 5. Open the app
#    Frontend:  http://localhost:3000
#    Backend:   http://localhost:8000/docs  (Swagger UI)
```

> [!TIP]
> Use `docker compose up --build -d` to run in detached mode. View logs with `docker compose logs -f`.

---

## 🔌 API Endpoints

The backend exposes a RESTful API at `http://localhost:8000`. Full interactive documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Send a text message and receive an AI response |
| `POST` | `/api/voice/transcribe` | Upload audio for Speech-to-Text transcription |
| `POST` | `/api/voice/synthesize` | Convert text to speech audio |
| `GET` | `/api/memory/search` | Search long-term memory by semantic query |
| `POST` | `/api/memory/add` | Manually add an entry to long-term memory |
| `GET` | `/api/conversations` | List all conversation sessions |
| `GET` | `/api/conversations/{id}` | Retrieve a specific conversation history |
| `DELETE` | `/api/conversations/{id}` | Delete a conversation session |
| `POST` | `/api/tools/execute` | Execute code in the sandboxed environment |
| `POST` | `/api/tools/research` | Perform web research on a topic |
| `GET` | `/api/health` | Health check and system status |

---

## 📲 PWA Installation

Use HTTPS outside localhost. Installation UI depends on browser and platform; the app's Settings → Browser & privacy panel explains detected capabilities. Offline support covers the app shell, not working offline AI/chat, and does not precache the large avatar models.

### Firefox

- Firefox on Android can use its install/add-to-home-screen menu where available.
- Firefox on Windows supports web apps starting with Firefox 143; Microsoft Store builds require Firefox 150 or later. Firefox on macOS/Linux can use the app in a normal tab or bookmark instead. See [Mozilla's current Windows web-app guidance](https://support.mozilla.org/en-US/kb/web-apps-firefox-windows).
- To use Firefox for the backend's separate Playwright browser tool, set `BROWSER_ENGINE=firefox` in `.env` and rebuild the backend container. Both engine binaries are installed; Chromium remains the default.
- Switching browser engines does not change the configured chat, embedding, or cloud speech providers. URL checks are defense-in-depth, not a complete network sandbox.

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
