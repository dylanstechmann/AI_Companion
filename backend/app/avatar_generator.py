"""
AI Companion — Avatar Generator Service
========================================
Generates realistic character portrait images from text descriptions
using an AI image generation API.  Generated images are saved to the
``data/avatars/`` directory and served via a static-files endpoint.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

AVATAR_DIR = Path("data/avatars")
AVATAR_DIR.mkdir(parents=True, exist_ok=True)


class AvatarGenerator:
    """Generate realistic character portraits from text descriptions."""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def generate(
        self,
        description: str,
        character_name: str = "character",
    ) -> str:
        """Generate a portrait image and return the relative URL path.

        Uses the OpenAI Images API (or compatible provider via OpenRouter)
        to create a realistic portrait from the given description.

        Parameters
        ----------
        description:
            Natural-language description of the character's appearance.
        character_name:
            Used for the filename.

        Returns
        -------
        str
            URL path like ``/api/avatars/greg_abc123.png``
        """
        settings = get_settings()
        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for avatar generation.")

        prompt = (
            f"Professional portrait photograph, headshot style. "
            f"{description} "
            f"Dark moody background with subtle blue-purple gradient. "
            f"Photorealistic, high quality, studio lighting. "
            f"Looking directly at camera."
        )

        client = await self._get_client()

        # Try OpenAI-compatible image generation endpoint
        response = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "quality": "standard",
                "response_format": "url",
            },
        )

        if response.status_code != 200:
            logger.error(
                "Image generation failed: %d %s",
                response.status_code,
                response.text,
            )
            raise RuntimeError(
                f"Avatar generation failed (HTTP {response.status_code})"
            )

        data = response.json()
        image_url = data["data"][0]["url"]

        # Download the generated image
        img_response = await client.get(image_url)
        if img_response.status_code != 200:
            raise RuntimeError("Failed to download generated image")

        # Save to disk
        safe_name = "".join(
            c if c.isalnum() or c in "_-" else "_"
            for c in character_name.lower()
        )
        filename = f"{safe_name}_{uuid.uuid4().hex[:8]}.png"
        filepath = AVATAR_DIR / filename
        filepath.write_bytes(img_response.content)

        logger.info("Generated avatar: %s -> %s", character_name, filepath)
        return f"/api/avatars/{filename}"

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Module-level singleton
_generator: Optional[AvatarGenerator] = None


def get_avatar_generator() -> AvatarGenerator:
    """Return the lazily-instantiated singleton ``AvatarGenerator``."""
    global _generator
    if _generator is None:
        _generator = AvatarGenerator()
    return _generator
