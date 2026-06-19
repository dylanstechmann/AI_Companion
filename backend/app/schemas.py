"""
AI Companion – Pydantic Schemas
================================
Request / response models shared across routers and services.  Every field
carries a type hint and, where useful, a ``Field`` description so the
auto-generated OpenAPI docs are self-documenting.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

class CharacterCreate(BaseModel):
    """Payload for creating a new character."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    system_prompt: str = Field(..., min_length=1)
    avatar_url: Optional[str] = Field(None, max_length=500)
    appearance_description: Optional[str] = Field(None, max_length=2000, description="Describe what this character should look like for AI avatar generation.")


class CharacterUpdate(BaseModel):
    """Payload for updating an existing character (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    system_prompt: Optional[str] = Field(None, min_length=1)
    avatar_url: Optional[str] = Field(None, max_length=500)
    appearance_description: Optional[str] = Field(None, max_length=2000, description="Describe what this character should look like for AI avatar generation.")
    avatar_3d_url: Optional[str] = Field(None, max_length=500)


class CharacterResponse(BaseModel):
    """Serialised character returned by the API."""
    id: int
    name: str
    description: str
    system_prompt: str
    is_default: bool
    created_at: datetime
    avatar_url: Optional[str] = None
    appearance_description: Optional[str] = None
    avatar_3d_url: Optional[str] = None


class Avatar3DGenerateRequest(BaseModel):
    """Optional body for the 3D avatar generation endpoint."""
    description: Optional[str] = Field(
        None,
        max_length=2000,
        description="Appearance description. Defaults to the character's appearance_description.",
    )
    gender: Optional[str] = Field(
        None,
        description="'male' or 'female'. Auto-detected from the description if omitted.",
    )


# ---------------------------------------------------------------------------
# Chat / Messages
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Body sent by the frontend to initiate a chat completion."""
    character_id: int
    message: str = Field(..., min_length=1)
    image: Optional[str] = Field(
        None,
        description="Optional base64-encoded image or URL for vision models.",
    )


class MessageResponse(BaseModel):
    """A single message in the conversation history."""
    id: int
    character_id: int
    role: str
    content: str
    image_url: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Speech-to-Text
# ---------------------------------------------------------------------------

class STTResponse(BaseModel):
    """Transcription result."""
    text: str
    duration_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# Text-to-Speech
# ---------------------------------------------------------------------------

class TTSRequest(BaseModel):
    """Request to convert text to speech audio."""
    text: str = Field(..., min_length=1, max_length=4096)
    voice: str = Field(
        "alloy",
        description="Voice ID: alloy, echo, fable, onyx, nova, shimmer (OpenAI) "
        "or any voice supported by the configured TTS provider.",
    )
    speed: float = Field(1.0, ge=0.25, le=4.0, description="Playback speed multiplier.")


# ---------------------------------------------------------------------------
# Health / Config
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Health-check payload."""
    status: str = "ok"
    gpu_available: bool
    stt_mode: str
    chromadb_status: str


class ConfigResponse(BaseModel):
    """Current runtime configuration (safe subset)."""
    stt_mode: str
    whisper_model: str
    whisper_device: str
    llm_model: str
    embedding_model: str
    sandbox_timeout_seconds: int


class ConfigUpdate(BaseModel):
    """Fields the user may update at runtime."""
    stt_mode: Optional[str] = None


# ---------------------------------------------------------------------------
# Code Execution
# ---------------------------------------------------------------------------

class CodeExecuteRequest(BaseModel):
    """Request to execute code in the sandbox."""
    language: str = Field(..., pattern="^(python|javascript)$")
    code: str = Field(..., min_length=1)


class CodeExecuteResponse(BaseModel):
    """Sandbox execution result."""
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------

class ResearchRequest(BaseModel):
    """Kick off a deep-research job."""
    query: str = Field(..., min_length=1)
    email: Optional[str] = Field(
        None,
        description="If provided, the final PDF report will be emailed here.",
    )


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemorySearchRequest(BaseModel):
    """Search a character's long-term memory store."""
    character_id: int
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)


class MemorySearchResponse(BaseModel):
    """Results from a memory search."""
    results: list[dict[str, Any]]
