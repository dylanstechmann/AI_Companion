"""
AI Companion – Speech-to-Text Service
=======================================
Supports two modes controlled by ``STT_MODE``:

* **local** – runs *faster-whisper* on-device (GPU or CPU).
* **cloud** – forwards audio to an OpenRouter-compatible Whisper endpoint.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class STTService:
    """Unified speech-to-text service with local / cloud backends."""

    def __init__(self) -> None:
        self._model = None  # lazy-loaded faster-whisper model
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Local (faster-whisper)
    # ------------------------------------------------------------------

    def _get_model(self):
        """Lazy-load the faster-whisper ``WhisperModel``."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel

                device = self._settings.WHISPER_DEVICE
                compute_type = "float16" if device == "cuda" else "int8"
                logger.info(
                    "Loading Whisper model '%s' on %s (%s)…",
                    self._settings.WHISPER_MODEL,
                    device,
                    compute_type,
                )
                self._model = WhisperModel(
                    self._settings.WHISPER_MODEL,
                    device=device,
                    compute_type=compute_type,
                )
                logger.info("Whisper model loaded successfully.")
            except Exception:
                logger.exception("Failed to load local Whisper model.")
                raise
        return self._model

    async def transcribe_local(self, audio_bytes: bytes) -> dict:
        """Transcribe *audio_bytes* using the local faster-whisper model.

        Returns ``{"text": str, "duration_seconds": float}``.
        """
        tmp_path: Optional[str] = None
        try:
            # Write to a temp file – faster-whisper reads from path.
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False
            ) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            t0 = time.perf_counter()
            model = self._get_model()
            segments, info = model.transcribe(
                tmp_path,
                beam_size=5,
                language=None,  # auto-detect
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments)
            elapsed = time.perf_counter() - t0

            logger.info(
                "Local STT: %.1fs audio → %.1fs processing, detected=%s",
                info.duration,
                elapsed,
                info.language,
            )
            return {"text": text, "duration_seconds": round(elapsed, 3)}

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # Cloud (OpenRouter Whisper-compatible endpoint)
    # ------------------------------------------------------------------

    async def transcribe_cloud(self, audio_bytes: bytes) -> dict:
        """Transcribe using an OpenRouter-compatible Whisper API.

        Returns ``{"text": str, "duration_seconds": float}``.
        """
        import openai

        client = openai.AsyncOpenAI(
            api_key=self._settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )

        t0 = time.perf_counter()
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.wav"

        transcript = await client.audio.transcriptions.create(
            model="openai/whisper-large-v3",
            file=audio_file,
        )
        elapsed = time.perf_counter() - t0

        text = transcript.text if hasattr(transcript, "text") else str(transcript)
        logger.info("Cloud STT: %.1fs processing.", elapsed)
        return {"text": text, "duration_seconds": round(elapsed, 3)}

    # ------------------------------------------------------------------
    # Public unified entry-point
    # ------------------------------------------------------------------

    async def transcribe(self, audio_bytes: bytes) -> dict:
        """Route to the configured STT backend.

        Returns ``{"text": str, "duration_seconds": float}``.
        """
        if self._settings.STT_MODE == "cloud":
            return await self.transcribe_cloud(audio_bytes)
        return await self.transcribe_local(audio_bytes)
