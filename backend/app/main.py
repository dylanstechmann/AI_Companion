"""
AI Companion – FastAPI Application Entry-Point
================================================
Wires together every service (database, STT, LLM, memory, sandbox, research)
and exposes the full REST + SSE API under the ``/api/`` prefix.

Run locally::

    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from app.avatar_generator import get_avatar_generator

from app.config import get_settings
from app.database import (
    add_message,
    create_character,
    delete_character,
    get_all_characters,
    get_character,
    get_messages,
    init_db,
    seed_defaults,
    update_character,
)
from app.llm import LLMService
from app.memory import MemoryManager
from app.research import ResearchAgent
from app.sandbox import CodeSandbox
from app.schemas import (
    Avatar3DGenerateRequest,
    CharacterCreate,
    CharacterResponse,
    CharacterUpdate,
    ChatRequest,
    CodeExecuteRequest,
    CodeExecuteResponse,
    ConfigResponse,
    ConfigUpdate,
    HealthResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MessageResponse,
    ResearchRequest,
    STTResponse,
    TTSRequest,
)
from app.stt import STTService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton service instances (populated during lifespan)
# ---------------------------------------------------------------------------
stt_service: STTService | None = None
llm_service: LLMService | None = None
memory_manager: MemoryManager | None = None
code_sandbox: CodeSandbox | None = None
skill_manager = None  # SkillManager (Phase 3)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    global stt_service, llm_service, memory_manager, code_sandbox, skill_manager

    logger.info("Starting AI Companion backend…")
    settings = get_settings()

    # Database
    await init_db()
    await seed_defaults()

    # Services
    stt_service = STTService()
    memory_manager = MemoryManager()
    llm_service = LLMService(memory=memory_manager)
    code_sandbox = CodeSandbox()

    # Skill manager (Phase 3)
    try:
        from app.skills import SkillManager
        skill_manager = SkillManager()
        skill_manager.load_all()
        logger.info("SkillManager loaded %d skills.", len(skill_manager.loaded_skills))
    except Exception:
        logger.warning("SkillManager failed to initialise.", exc_info=True)

    logger.info("All services initialised.  Server is ready.")
    yield

    logger.info("Shutting down AI Companion backend…")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Companion API",
    version="0.1.0",
    description="Backend for the AI Companion application.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================================
# Health / Config
# =========================================================================

@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Return GPU availability, STT mode, and ChromaDB status."""
    gpu_available = False
    try:
        import torch
        gpu_available = torch.cuda.is_available()
    except ImportError:
        try:
            import ctranslate2
            gpu_available = ctranslate2.get_cuda_device_count() > 0
        except ImportError:
            pass

    settings = get_settings()
    chroma_status = memory_manager.status() if memory_manager else "uninitialised"

    return HealthResponse(
        status="ok",
        gpu_available=gpu_available,
        stt_mode=settings.STT_MODE,
        chromadb_status=chroma_status,
    )


@app.get("/api/config", response_model=ConfigResponse, tags=["System"])
async def get_config():
    """Return the current (safe) runtime configuration."""
    settings = get_settings()
    return ConfigResponse(
        stt_mode=settings.STT_MODE,
        whisper_model=settings.WHISPER_MODEL,
        whisper_device=settings.WHISPER_DEVICE,
        llm_model=settings.LLM_MODEL,
        embedding_model=settings.EMBEDDING_MODEL,
        sandbox_timeout_seconds=settings.SANDBOX_TIMEOUT_SECONDS,
    )


@app.put("/api/config", response_model=ConfigResponse, tags=["System"])
async def update_config(body: ConfigUpdate):
    """Update mutable runtime settings (currently only ``stt_mode``)."""
    settings = get_settings()
    if body.stt_mode and body.stt_mode in ("local", "cloud"):
        # pydantic-settings objects are frozen; override via env is the
        # canonical way, but for a quick runtime toggle we mutate directly.
        object.__setattr__(settings, "STT_MODE", body.stt_mode)

    return ConfigResponse(
        stt_mode=settings.STT_MODE,
        whisper_model=settings.WHISPER_MODEL,
        whisper_device=settings.WHISPER_DEVICE,
        llm_model=settings.LLM_MODEL,
        embedding_model=settings.EMBEDDING_MODEL,
        sandbox_timeout_seconds=settings.SANDBOX_TIMEOUT_SECONDS,
    )


# =========================================================================
# Speech-to-Text
# =========================================================================

@app.post("/api/stt", response_model=STTResponse, tags=["STT"])
async def speech_to_text(request: Request, file: UploadFile = File(...)):
    """Accept an audio file upload and return the transcript."""
    if stt_service is None:
        raise HTTPException(503, "STT service not initialised.")

    from app.auth import get_optional_user
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()

    from app.payments import get_payment_service
    ps = get_payment_service()
    balance = await ps.get_user_balance(user["id"])
    if balance < 1:
        raise HTTPException(status_code=402, detail="Insufficient credits.")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(400, "Empty audio file.")

    result = await stt_service.transcribe(audio_bytes)
    
    # Deduct STT usage (0.3 credits)
    await ps.deduct_usage(user["id"], "stt_transcription")
    
    return STTResponse(**result)


@app.post("/api/tts", tags=["TTS"])
async def text_to_speech(http_request: Request, request: TTSRequest):
    """Convert text to speech audio via an OpenAI-compatible TTS API.

    Returns ``audio/mpeg`` bytes on success.  If no TTS API key is
    configured the endpoint returns 501 so the frontend can fall back
    to browser-native ``speechSynthesis``.
    """
    import openai

    from app.auth import get_optional_user
    user = await get_optional_user(http_request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()

    from app.payments import get_payment_service
    ps = get_payment_service()
    balance = await ps.get_user_balance(user["id"])
    if balance < 1:
        raise HTTPException(status_code=402, detail="Insufficient credits.")

    settings = get_settings()
    api_key = settings.TTS_API_KEY or settings.OPENROUTER_API_KEY
    if not api_key:
        raise HTTPException(
            501,
            "TTS API key not configured. Set TTS_API_KEY in .env "
            "or use browser TTS mode.",
        )

    client = openai.AsyncOpenAI(
        api_key=api_key,
        base_url=settings.TTS_BASE_URL,
    )
    try:
        response = await client.audio.speech.create(
            model=settings.TTS_MODEL,
            voice=request.voice or settings.TTS_VOICE,
            input=request.text,
            speed=request.speed,
        )
        
        # Deduct TTS usage (0.8 credits)
        await ps.deduct_usage(user["id"], "tts_generation")
        
        return Response(content=response.content, media_type="audio/mpeg")
    except Exception as exc:
        logger.exception("TTS generation failed")
        raise HTTPException(502, f"TTS generation failed: {exc}")


# =========================================================================
# Characters
# =========================================================================

@app.get("/api/characters", response_model=list[CharacterResponse], tags=["Characters"])
async def list_characters():
    """Return all characters."""
    rows = await get_all_characters()
    return rows


@app.post(
    "/api/characters",
    response_model=CharacterResponse,
    status_code=201,
    tags=["Characters"],
)
async def create_new_character(body: CharacterCreate):
    """Create a custom character."""
    char = await create_character(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        avatar_url=body.avatar_url or "",
        appearance_description=body.appearance_description or "",
    )
    return char


@app.put("/api/characters/{character_id}", response_model=CharacterResponse, tags=["Characters"])
async def update_existing_character(character_id: int, body: CharacterUpdate):
    """Update an existing character's fields."""
    existing = await get_character(character_id)
    if existing is None:
        raise HTTPException(404, "Character not found.")
    updated = await update_character(
        character_id,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        avatar_url=body.avatar_url,
        appearance_description=body.appearance_description,
    )
    return updated


@app.delete("/api/characters/{character_id}", tags=["Characters"])
async def remove_character(character_id: int):
    """Delete a character (refuses to delete defaults)."""
    try:
        success = await delete_character(character_id)
    except ValueError as exc:
        raise HTTPException(403, str(exc))
    if not success:
        raise HTTPException(404, "Character not found.")
    return {"detail": "Character deleted."}


@app.post("/api/characters/{character_id}/generate-avatar", tags=["Characters"])
async def generate_character_avatar(character_id: int, request: Request):
    """Generate a realistic AI avatar for a character based on their appearance description."""
    from app.auth import get_optional_user
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()

    from app.payments import get_payment_service
    ps = get_payment_service()
    balance = await ps.get_user_balance(user["id"])
    if balance < 5: # avatar generation is 4.4 credits
        raise HTTPException(status_code=402, detail="Insufficient credits.")

    char = await get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    
    description = char.get("appearance_description", "")
    if not description:
        raise HTTPException(
            status_code=400,
            detail="Character has no appearance_description. Add one first.",
        )
    
    generator = get_avatar_generator()
    try:
        avatar_url = await generator.generate(description, char["name"])
    except Exception as e:
        logger.exception("Failed to generate avatar")
        raise HTTPException(status_code=500, detail=str(e))
    
    # Deduct usage (4.4 credits)
    await ps.deduct_usage(user["id"], "avatar_generation")

    # Update the character's avatar_url in the database
    await update_character(character_id, avatar_url=avatar_url)
    
    return {"avatar_url": avatar_url}


@app.post("/api/characters/{character_id}/generate-3d-avatar", tags=["Characters"])
async def generate_character_3d_avatar(
    character_id: int,
    body: Avatar3DGenerateRequest,
    request: Request,
):
    """Generate a Ready Player Me 3D avatar (GLB URL) for a character.

    Uses the optional ``description`` / ``gender`` fields from the request
    body, falling back to the character's stored ``appearance_description``
    when none is supplied.  The resulting GLB URL is stored on the
    character's ``avatar_3d_url`` field and credits are deducted using the
    ``avatar_generation`` operation cost.
    """
    from app.auth import get_optional_user
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()

    from app.payments import get_payment_service, OPERATION_COSTS
    ps = get_payment_service()
    cost = OPERATION_COSTS.get("avatar_generation", 0.0)
    balance = await ps.get_user_balance(user["id"])
    if balance < cost:
        raise HTTPException(status_code=402, detail="Insufficient credits.")

    char = await get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    description = body.description or char.get("appearance_description", "") or ""
    gender = body.gender or "male"
    if gender not in ("male", "female"):
        gender = "male"

    from app.avatar3d_service import get_avatar3d_service
    service = get_avatar3d_service()
    try:
        result = await service.generate_avatar_from_description(description, gender=gender)
    except Exception as e:
        logger.exception("Failed to generate 3D avatar")
        raise HTTPException(status_code=500, detail=str(e))

    avatar_url = result["avatar_url"]

    # Deduct usage (avatar_generation credits)
    await ps.deduct_usage(user["id"], "avatar_generation")

    # Persist the 3D avatar URL on the character
    await update_character(character_id, avatar_3d_url=avatar_url)

    return {
        "avatar_url": avatar_url,
        "thumbnail_url": result["thumbnail_url"],
        "avatar_id": result["avatar_id"],
    }


# =========================================================================
# Messages / Chat
# =========================================================================

@app.get(
    "/api/characters/{character_id}/messages",
    response_model=list[MessageResponse],
    tags=["Chat"],
)
async def list_messages(character_id: int, limit: int = 100, offset: int = 0):
    """Return conversation history for a character."""
    char = await get_character(character_id)
    if char is None:
        raise HTTPException(404, "Character not found.")
    return await get_messages(character_id, limit=limit, offset=offset)


@app.post("/api/chat", tags=["Chat"])
async def chat(body: ChatRequest, request: Request):
    """Stream a chat response as Server-Sent Events (SSE).

    Each event is ``data: <chunk>\n\n``.  The final event is
    ``data: [DONE]\n\n``.
    """
    if llm_service is None:
        raise HTTPException(503, "LLM service not initialised.")

    char = await get_character(body.character_id)
    if char is None:
        raise HTTPException(404, "Character not found.")

    from app.auth import get_optional_user
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()

    from app.payments import get_payment_service, OPERATION_COSTS
    ps = get_payment_service()
    balance = await ps.get_user_balance(user["id"])

    settings = get_settings()
    model = settings.LLM_MODEL
    action = "chat_message_gpt4" if "gpt-4" in model.lower() or "claude" in model.lower() else "chat_message_flash"
    
    cost = OPERATION_COSTS.get(action, 0.0)
    if balance < cost:
        raise HTTPException(status_code=402, detail="Insufficient credits.")

    async def event_generator():
        try:
            async for chunk in llm_service.stream_chat(
                character_id=body.character_id,
                message=body.message,
                image_url=body.image,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            await ps.deduct_usage(user["id"], action)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/image", tags=["Chat"])
async def chat_with_image(
    request: Request,
    file: UploadFile = File(...),
    character_id: int = Form(1),
    message: str = Form("What's in this image?"),
):
    """Accept an image upload + text prompt and stream the vision-model response."""
    if llm_service is None:
        raise HTTPException(503, "LLM service not initialised.")

    from app.auth import get_optional_user
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()

    from app.payments import get_payment_service, OPERATION_COSTS
    ps = get_payment_service()
    balance = await ps.get_user_balance(user["id"])

    # Vision requests use chat_message_gpt4 rate
    action = "chat_message_gpt4"
    cost = OPERATION_COSTS.get(action, 0.0)
    if balance < cost:
        raise HTTPException(status_code=402, detail="Insufficient credits.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, "Empty image file.")

    # Convert to base64 data-URI for the vision model.
    content_type = file.content_type or "image/png"
    b64 = base64.b64encode(image_bytes).decode()
    image_url = f"data:{content_type};base64,{b64}"

    async def event_generator():
        try:
            async for chunk in llm_service.stream_chat(
                character_id=character_id,
                message=message,
                image_url=image_url,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            await ps.deduct_usage(user["id"], action)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# =========================================================================
# Code Execution
# =========================================================================

@app.post(
    "/api/code/execute",
    response_model=CodeExecuteResponse,
    tags=["Tools"],
)
async def run_code(body: CodeExecuteRequest):
    """Execute Python or JavaScript code in the sandbox."""
    if code_sandbox is None:
        raise HTTPException(503, "Sandbox not initialised.")

    result = await code_sandbox.execute(body.language, body.code)
    return CodeExecuteResponse(**result)


@app.post("/api/code/execute/stream", tags=["Tools"])
async def run_code_streaming(body: CodeExecuteRequest):
    """Stream code execution output in real-time via SSE.

    Each event is ``data: <json>\\n\\n``. Output events contain
    ``{"type":"output","text":"...","stream":"stdout|stderr"}``.
    The final event is ``{"type":"status","exit_code":N,"execution_time":F}``
    followed by ``data: [DONE]\\n\\n``.
    """
    if code_sandbox is None:
        raise HTTPException(503, "Sandbox not initialised.")

    async def event_generator():
        async for event in code_sandbox.execute_streaming(
            body.language, body.code
        ):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# =========================================================================
# Research
# =========================================================================

@app.post("/api/agent/research", tags=["Tools"])
async def start_research(body: ResearchRequest, request: Request, bg: BackgroundTasks):
    """Kick off a deep-research job in the background.

    Returns immediately with a status message.  The final report and PDF
    are generated asynchronously.
    """
    from app.auth import get_optional_user
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()

    from app.payments import get_payment_service, OPERATION_COSTS
    ps = get_payment_service()
    balance = await ps.get_user_balance(user["id"])
    
    action = "web_research"
    cost = OPERATION_COSTS.get(action, 0.0)
    if balance < cost:
        raise HTTPException(status_code=402, detail="Insufficient credits.")

    agent = ResearchAgent()

    async def _run():
        try:
            result = await agent.run(query=body.query, email_to=body.email)
            logger.info(
                "Research complete | report length=%d, pdf=%s",
                len(result.get("report", "")),
                result.get("pdf_path"),
            )
            # Deduct usage (2.2 credits)
            await ps.deduct_usage(user["id"], action)
        except Exception:
            logger.exception("Research agent failed.")

    bg.add_task(_run)
    return {
        "detail": "Research job started.",
        "query": body.query,
        "email": body.email,
    }


# =========================================================================
# Memory
# =========================================================================

@app.post(
    "/api/memory/search",
    response_model=MemorySearchResponse,
    tags=["Memory"],
)
async def search_memory(body: MemorySearchRequest):
    """Search a character's long-term memory store."""
    if memory_manager is None:
        raise HTTPException(503, "Memory manager not initialised.")

    results = await memory_manager.search(
        character_id=body.character_id,
        query=body.query,
        top_k=body.top_k,
    )
    return MemorySearchResponse(results=results)


# =========================================================================
# Multi-Agent Orchestration (Phase 3)
# =========================================================================

@app.post("/api/agents/orchestrate", tags=["Agents"])
async def orchestrate(body: dict):
    """Start a multi-agent orchestration task. Streams progress via SSE.

    Body: ``{"query": "complex request"}``
    """
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(400, "Missing 'query' field.")

    from app.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator()

    async def event_generator():
        async for event in orchestrator.run(query):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# =========================================================================
# Skill / Plugin System (Phase 3)
# =========================================================================

@app.get("/api/skills", tags=["Skills"])
async def list_skills():
    """List all installed skills."""
    if skill_manager is None:
        return {"skills": []}
    return {"skills": skill_manager.discover()}


@app.post("/api/skills", tags=["Skills"])
async def create_skill(body: dict):
    """Create a new skill from code.

    Body: ``{"name": "...", "description": "...", "code": "...", "functions": [...]}``
    """
    if skill_manager is None:
        raise HTTPException(503, "Skill manager not initialised.")

    name = body.get("name", "").strip()
    description = body.get("description", "")
    code = body.get("code", "")
    functions = body.get("functions", [])

    if not name or not code:
        raise HTTPException(400, "Missing 'name' or 'code'.")

    try:
        result = await skill_manager.create_skill(name, description, code, functions)
        return result
    except Exception as exc:
        raise HTTPException(400, f"Failed to create skill: {exc}")


@app.delete("/api/skills/{skill_name}", tags=["Skills"])
async def delete_skill(skill_name: str):
    """Delete a skill."""
    if skill_manager is None:
        raise HTTPException(503, "Skill manager not initialised.")
    success = skill_manager.delete_skill(skill_name)
    if not success:
        raise HTTPException(404, "Skill not found.")
    return {"detail": "Skill deleted."}


@app.post("/api/skills/{skill_name}/execute", tags=["Skills"])
async def execute_skill(skill_name: str, body: dict):
    """Execute a skill function.

    Body: ``{"function": "function_name", "args": {...}}``
    """
    if skill_manager is None:
        raise HTTPException(503, "Skill manager not initialised.")

    func_name = body.get("function", "")
    args = body.get("args", {})

    try:
        result = await skill_manager.execute(skill_name, func_name, args)
        return {"result": result}
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        raise HTTPException(400, f"Skill execution failed: {exc}")


# =========================================================================
# Browser Automation (Phase 3)
# =========================================================================

@app.post("/api/browser/navigate", tags=["Browser"])
async def browser_navigate(body: dict):
    """Navigate to a URL and return page content."""
    from app.browser import BrowserService
    bs = BrowserService()
    return await bs.navigate(body.get("url", ""))


@app.post("/api/browser/screenshot", tags=["Browser"])
async def browser_screenshot(body: dict):
    """Take a screenshot. Returns base64 PNG."""
    import base64 as _b64
    from app.browser import BrowserService
    bs = BrowserService()
    png = await bs.screenshot(body.get("url"))
    return {"screenshot": _b64.b64encode(png).decode(), "mime_type": "image/png"}


@app.post("/api/browser/click", tags=["Browser"])
async def browser_click(body: dict):
    """Click an element by CSS selector."""
    from app.browser import BrowserService
    bs = BrowserService()
    return await bs.click(body.get("selector", ""))


@app.post("/api/browser/type", tags=["Browser"])
async def browser_type(body: dict):
    """Type text into a field."""
    from app.browser import BrowserService
    bs = BrowserService()
    return await bs.type_text(body.get("selector", ""), body.get("text", ""))


@app.post("/api/browser/extract", tags=["Browser"])
async def browser_extract(body: dict):
    """Extract text from CSS selectors."""
    from app.browser import BrowserService
    bs = BrowserService()
    return await bs.extract(body.get("selectors", {}))


@app.post("/api/browser/fill-form", tags=["Browser"])
async def browser_fill_form(body: dict):
    """Navigate to URL and fill form fields."""
    from app.browser import BrowserService
    bs = BrowserService()
    return await bs.fill_form(body.get("url", ""), body.get("form_data", {}))


# =========================================================================
# Authentication (Phase 4)
# =========================================================================

@app.post("/api/auth/register", tags=["Auth"])
async def register(body: dict):
    """Register a new user account."""
    from app.auth import auth_service
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    display_name = body.get("display_name", "")
    if not email or not password:
        raise HTTPException(400, "Email and password are required.")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    try:
        result = await auth_service.register(email, password, display_name)
        return result
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/auth/login", tags=["Auth"])
async def login(body: dict):
    """Login and return JWT tokens."""
    from app.auth import auth_service
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    if not email or not password:
        raise HTTPException(400, "Email and password are required.")
    try:
        result = await auth_service.login(email, password)
        return result
    except ValueError as exc:
        raise HTTPException(401, str(exc))


@app.post("/api/auth/refresh", tags=["Auth"])
async def refresh(body: dict):
    """Refresh an expired access token."""
    from app.auth import auth_service
    token = body.get("refresh_token", "")
    if not token:
        raise HTTPException(400, "Missing refresh_token.")
    try:
        result = await auth_service.refresh_token(token)
        return result
    except Exception as exc:
        raise HTTPException(401, str(exc))


@app.get("/api/auth/me", tags=["Auth"])
async def get_me(request: Request):
    """Get the current user's info."""
    from app.auth import get_optional_user
    user = await get_optional_user(request)
    if not user:
        # Return demo user for backward compat
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()
    return {"user": user}


@app.post("/api/auth/demo", tags=["Auth"])
async def create_demo():
    """Create or get a demo user (for development without auth)."""
    from app.auth import auth_service
    user = await auth_service.create_or_get_demo_user()
    tokens = {
        "access_token": auth_service.create_access_token(user["id"]),
        "refresh_token": auth_service.create_refresh_token(user["id"]),
        "token_type": "bearer",
    }
    return {**tokens, "user": user}


# =========================================================================
# Payments & Credit Packs (Phase B)
# =========================================================================

@app.get("/api/payments/credit-packs", tags=["Payments"])
async def get_credit_packs():
    """List available credit packs."""
    from app.payments import CREDIT_PACKS
    return {"packs": CREDIT_PACKS}


@app.get("/api/payments/balance", tags=["Payments"])
async def get_balance(request: Request):
    """Get user's credit balance (credits and cents)."""
    from app.auth import get_optional_user
    from app.payments import get_payment_service
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()
    ps = get_payment_service()
    balance = await ps.get_user_balance(user["id"])
    # Return rounded integer values to prevent breaking Swift/Kotlin client expectations
    rounded_bal = int(round(balance))
    return {"balance_sats": rounded_bal, "credits": rounded_bal}  # keeping balance_sats for frontend compatibility


@app.post("/api/payments/stripe/checkout", tags=["Payments"])
async def create_stripe_checkout(body: dict, request: Request):
    """Create a Stripe Checkout session for a credit pack."""
    from app.auth import get_optional_user
    from app.payments import get_payment_service
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()
    
    pack_id = body.get("pack_id")
    redirect_url = body.get("redirect_url", "http://localhost:3000")
    ps = get_payment_service()
    try:
        session = await ps.create_stripe_checkout(user["id"], pack_id, redirect_url)
        return session
    except ValueError as val_err:
        raise HTTPException(400, str(val_err))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/payments/stripe/webhook", tags=["Payments"])
async def stripe_webhook(request: Request):
    """Stripe webhook handler."""
    from app.payments import get_payment_service
    body = await request.body()
    signature = request.headers.get("Stripe-Signature", "")
    ps = get_payment_service()
    result = await ps.handle_stripe_webhook(body.decode("utf-8"), signature)
    return result


@app.post("/api/payments/paypal/create-order", tags=["Payments"])
async def create_paypal_order(body: dict, request: Request):
    """Create a PayPal order for a credit pack."""
    from app.auth import get_optional_user
    from app.payments import get_payment_service
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()
        
    pack_id = body.get("pack_id")
    ps = get_payment_service()
    try:
        order = await ps.create_paypal_order(user["id"], pack_id)
        return order
    except ValueError as val_err:
        raise HTTPException(400, str(val_err))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/payments/paypal/capture-order", tags=["Payments"])
async def capture_paypal_order(body: dict, request: Request):
    """Capture a PayPal order after user approval."""
    from app.auth import get_optional_user
    from app.payments import get_payment_service
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()
        
    order_id = body.get("order_id")
    ps = get_payment_service()
    try:
        capture = await ps.capture_paypal_order(user["id"], order_id)
        return capture
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/payments/btcpay/invoice", tags=["Payments"])
async def create_btcpay_invoice(body: dict, request: Request):
    """Create a BTCPay Server invoice for a credit pack."""
    from app.auth import get_optional_user
    from app.payments import get_payment_service
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()
        
    pack_id = body.get("pack_id")
    redirect_url = body.get("redirect_url", "http://localhost:3000")
    ps = get_payment_service()
    try:
        invoice = await ps.create_btcpay_invoice(user["id"], pack_id, redirect_url)
        return invoice
    except ValueError as val_err:
        raise HTTPException(400, str(val_err))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/payments/btcpay/webhook", tags=["Payments"])
async def btcpay_webhook(request: Request):
    """BTCPay Server webhook handler."""
    from app.payments import get_payment_service
    body = await request.body()
    signature = request.headers.get("BTCPay-Sig", "")
    ps = get_payment_service()
    result = await ps.handle_btcpay_webhook(body.decode("utf-8"), signature)
    return result


@app.post("/api/payments/webhook", tags=["Payments"])
async def btcpay_webhook_compat(request: Request):
    """BTCPay Server webhook compatibility wrapper."""
    from app.payments import get_payment_service
    body = await request.body()
    signature = request.headers.get("BTCPay-Sig", "")
    ps = get_payment_service()
    result = await ps.handle_btcpay_webhook(body.decode("utf-8"), signature)
    return result


@app.get("/api/payments/invoice/{invoice_id}", tags=["Payments"])
async def check_invoice_status(invoice_id: str):
    """Check status of an invoice (Stripe, PayPal, or BTCPay)."""
    from app.payments import get_payment_service
    ps = get_payment_service()
    return await ps.check_invoice(invoice_id)


@app.get("/api/payments/history", tags=["Payments"])
async def payment_history(request: Request):
    """Get payment history for the current user."""
    from app.auth import get_optional_user
    from app.payments import get_payment_service
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()
    ps = get_payment_service()
    return {"history": await ps.get_payment_history(user["id"])}


@app.get("/api/payments/usage", tags=["Payments"])
async def usage_history(request: Request):
    """Get usage history for the current user."""
    from app.auth import get_optional_user
    from app.payments import get_payment_service
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()
    ps = get_payment_service()
    return {"usage": await ps.get_usage_history(user["id"])}


# =========================================================================
# Web Push Notifications
# =========================================================================

@app.get("/api/notifications/vapid-public-key", tags=["Notifications"])
async def get_vapid_public_key():
    """Return the VAPID public key the PWA needs to create a push subscription.

    ``configured`` is False when the server has no VAPID keys set, letting the
    frontend disable the "enable notifications" UI instead of failing silently.
    """
    from app.notifications import get_notification_service
    ns = get_notification_service()
    return {"public_key": ns.public_key, "configured": ns.is_configured}


@app.post("/api/notifications/subscribe", tags=["Notifications"])
async def subscribe_notifications(body: dict, request: Request):
    """Register a browser push subscription for the current user."""
    from app.auth import get_optional_user
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()

    endpoint = body.get("endpoint")
    keys = body.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Invalid subscription info.")

    from app import database
    await database.add_push_subscription(user["id"], endpoint, p256dh, auth)
    return {"detail": "Subscribed successfully."}


@app.post("/api/notifications/test", tags=["Notifications"])
async def send_test_notification(body: dict, request: Request):
    """Send a test push notification to the current user."""
    from app.auth import get_optional_user
    user = await get_optional_user(request)
    if not user:
        from app.auth import auth_service
        user = await auth_service.create_or_get_demo_user()

    from app.notifications import get_notification_service
    ns = get_notification_service()
    sent = await ns.send_notification(
        user["id"],
        title=body.get("title", "Test Notification"),
        body=body.get("body", "This is a test notification from your AI Companion PWA!"),
    )
    return {"sent_count": sent}


# Serve generated avatar images
import os
os.makedirs("data/avatars", exist_ok=True)
app.mount("/api/avatars", StaticFiles(directory="data/avatars"), name="avatars")