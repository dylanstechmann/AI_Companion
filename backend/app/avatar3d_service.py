"""
AI Companion — 3D Avatar Generation Service
============================================
Generates Ready Player Me (RPM) 3D avatar GLB URLs from text descriptions.

The Ready Player Me REST API (https://docs.readyplayer.me) can create avatars
from a set of template assets.  When the API is unavailable (no API key
configured, network failure, rate limit, etc.) the service gracefully falls
back to a pair of pre-made male / female avatar GLB URLs so the rest of the
application keeps working.

A module-level singleton is exposed via :func:`get_avatar3d_service`.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-made fallback avatars (Ready Player Me hosted GLB models)
# ---------------------------------------------------------------------------
DEFAULT_MALE_AVATAR_URL: str = (
    "https://models.readyplayer.me/64bfa15f0e72c63d7c3934a6.glb"
)
DEFAULT_FEMALE_AVATAR_URL: str = (
    "https://models.readyplayer.me/64bfa15f0e72c63d7c3934a5.glb"
)

# Avatar IDs are the last path segment of the model URL (minus the extension).
DEFAULT_MALE_AVATAR_ID: str = "64bfa15f0e72c63d7c3934a6"
DEFAULT_FEMALE_AVATAR_ID: str = "64bfa15f0e72c63d7c3934a5"


# ---------------------------------------------------------------------------
# Feature parsing helpers
# ---------------------------------------------------------------------------
# Maps common descriptive words to RPM asset IDs / properties.  These mappings
# are intentionally permissive — the RPM template API only supports a fixed
# catalogue, so we pick the closest match and let the live API override
# everything when it is available.
_HAIR_COLOR_MAP: dict[str, str] = {
    "black": "Black",
    "dark": "Black",
    "brown": "Brown",
    "brunette": "Brown",
    "blonde": "Blonde",
    "blond": "Blonde",
    "red": "Red",
    "ginger": "Red",
    "auburn": "Red",
    "gray": "Gray",
    "grey": "Gray",
    "white": "Gray",
    "platinum": "Platinum",
}

_EYE_COLOR_MAP: dict[str, str] = {
    "blue": "Blue",
    "brown": "Brown",
    "green": "Green",
    "hazel": "Hazel",
    "gray": "Gray",
    "grey": "Gray",
    "amber": "Amber",
}

_SKIN_TONE_MAP: dict[str, str] = {
    "fair": "Light",
    "light": "Light",
    "pale": "Light",
    "medium": "Medium",
    "tan": "Medium",
    "olive": "Medium",
    "dark": "Dark",
    "brown": "Dark",
    "black": "Dark",
}


def _find_keyword(text: str, mapping: dict[str, str]) -> Optional[str]:
    """Return the first mapped value whose key appears in *text*."""
    lowered = text.lower()
    for key, value in mapping.items():
        if re.search(rf"\b{re.escape(key)}\b", lowered):
            return value
    return None


def _detect_gender(text: str) -> str:
    """Best-effort gender detection from a description.  Returns 'male' or 'female'."""
    lowered = text.lower()
    female_markers = ("woman", "female", "girl", "she ", "her ", "lady")
    male_markers = ("man", "male", "boy", "he ", "his ", "guy")
    if any(m in lowered for m in female_markers):
        return "female"
    if any(m in lowered for m in male_markers):
        return "male"
    return "male"


class Avatar3DService:
    """Generate Ready Player Me 3D avatar GLB URLs from text / photo input."""

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        rpm_api_base_url: Optional[str] = None,
    ) -> None:
        self._client: Optional[httpx.AsyncClient] = client
        settings = get_settings()
        self._rpm_api_base_url: str = (
            rpm_api_base_url
            or getattr(settings, "RPM_API_BASE_URL", "https://api.readyplayer.me/v1")
        )
        self._rpm_api_key: str = getattr(settings, "RPM_API_KEY", "")
        self._rpm_subdomain: str = getattr(settings, "RPM_SUBDOMAIN", "")

    # -- HTTP client ---------------------------------------------------------
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- Feature parsing -----------------------------------------------------
    def _parse_description(self, description: str) -> dict[str, Any]:
        """Extract avatar-relevant features from a free-text description.

        Returns a dict with keys: ``gender``, ``hair_color``, ``eye_color``,
        ``skin_tone``.  Any field that cannot be determined is ``None``.
        """
        gender = _detect_gender(description)
        return {
            "gender": gender,
            "hair_color": _find_keyword(description, _HAIR_COLOR_MAP),
            "eye_color": _find_keyword(description, _EYE_COLOR_MAP),
            "skin_tone": _find_keyword(description, _SKIN_TONE_MAP),
        }

    def _build_avatar_payload(self, features: dict[str, Any], gender: str) -> dict[str, Any]:
        """Build the JSON body for the RPM ``POST /avatars`` endpoint.

        The RPM API accepts an ``assets`` object describing the avatar's
        outward appearance.  Unknown / unsupported asset IDs are simply
        ignored by the API, so we only include the properties we detected.
        """
        payload: dict[str, Any] = {
            "data": {
                "gender": gender,
                "assets": {},
            }
        }
        if self._rpm_subdomain:
            payload["data"]["partner"] = self._rpm_subdomain

        assets: dict[str, Any] = payload["data"]["assets"]
        if features.get("hair_color"):
            assets["hairColor"] = features["hair_color"]
        if features.get("eye_color"):
            assets["eyeColor"] = features["eye_color"]
        if features.get("skin_tone"):
            assets["skinColor"] = features["skin_tone"]
        return payload

    # -- Public API ----------------------------------------------------------
    async def generate_avatar_from_description(
        self,
        description: str,
        gender: str = "male",
    ) -> dict[str, str]:
        """Generate a 3D avatar GLB URL from a text description.

        Parameters
        ----------
        description:
            Natural-language description of the character's appearance.
        gender:
            ``"male"`` or ``"female"``.  When the description clearly
            indicates a different gender, that takes precedence.

        Returns
        -------
        dict
            ``{"avatar_url", "thumbnail_url", "avatar_id"}``
        """
        detected_gender = _detect_gender(description) or gender
        # If the caller explicitly passed a gender that disagrees with the
        # auto-detected one, prefer the caller's choice (caller knows best).
        effective_gender = gender if gender in ("male", "female") else detected_gender
        features = self._parse_description(description)
        features["gender"] = effective_gender

        avatar_url: Optional[str] = None
        avatar_id: Optional[str] = None

        if self._rpm_api_key:
            try:
                avatar_url, avatar_id = await self._create_rpm_avatar(
                    features, effective_gender
                )
            except Exception:
                logger.exception(
                    "RPM avatar creation failed — falling back to default %s avatar.",
                    effective_gender,
                )
        else:
            logger.debug(
                "RPM API key not configured — using default %s avatar.",
                effective_gender,
            )

        if avatar_url is None or avatar_id is None:
            if effective_gender == "female":
                avatar_url = DEFAULT_FEMALE_AVATAR_URL
                avatar_id = DEFAULT_FEMALE_AVATAR_ID
            else:
                avatar_url = DEFAULT_MALE_AVATAR_URL
                avatar_id = DEFAULT_MALE_AVATAR_ID

        thumbnail_url = self._thumbnail_url(avatar_id, avatar_url)
        return {
            "avatar_url": avatar_url,
            "thumbnail_url": thumbnail_url,
            "avatar_id": avatar_id,
        }

    async def _create_rpm_avatar(
        self, features: dict[str, Any], gender: str
    ) -> tuple[str, str]:
        """Call the RPM API to create an avatar.

        Returns a ``(glb_url, avatar_id)`` tuple.  Raises on any error so the
        caller can fall back to a default avatar.
        """
        client = await self._get_client()
        payload = self._build_avatar_payload(features, gender)
        headers = {"Content-Type": "application/json"}
        if self._rpm_api_key:
            headers["Authorization"] = f"Bearer {self._rpm_api_key}"

        url = f"{self._rpm_api_base_url.rstrip('/')}/avatars"
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            logger.warning(
                "RPM API returned HTTP %d: %s",
                response.status_code,
                response.text[:300],
            )
            raise RuntimeError(f"RPM API error (HTTP {response.status_code})")

        data = response.json()
        avatar_id = str(data.get("id") or data.get("data", {}).get("id") or "")
        if not avatar_id:
            raise RuntimeError("RPM API response missing avatar id")

        glb_url = (
            data.get("modelUrl")
            or data.get("model_url")
            or f"https://models.readyplayer.me/{avatar_id}.glb"
        )
        return glb_url, avatar_id

    @staticmethod
    def _thumbnail_url(avatar_id: str, glb_url: str) -> str:
        """Derive a 2D thumbnail PNG URL for the given avatar."""
        if avatar_id:
            return f"https://models.readyplayer.me/{avatar_id}.png"
        # Last-ditch effort: swap the extension on the GLB URL.
        return glb_url.rsplit(".glb", 1)[0] + ".png"

    async def generate_avatar_from_photo(
        self,
        photo_bytes: bytes,
        description: str = "",
    ) -> dict[str, str]:
        """Generate a 3D avatar from a photo.

        A true photo-to-3D pipeline is out of scope for now; instead we use
        any supplied *description* (which the caller may have extracted from
        the photo via a vision model) and fall back to description-based
        generation.  If no description is provided, a default avatar is
        returned.
        """
        if not description:
            logger.info(
                "Photo-to-3D not implemented and no description supplied — "
                "returning default male avatar."
            )
            return {
                "avatar_url": DEFAULT_MALE_AVATAR_URL,
                "thumbnail_url": f"https://models.readyplayer.me/{DEFAULT_MALE_AVATAR_ID}.png",
                "avatar_id": DEFAULT_MALE_AVATAR_ID,
            }
        return await self.generate_avatar_from_description(description)

    async def get_default_male_avatar(self) -> str:
        """Return a pre-made male RPM avatar GLB URL."""
        return DEFAULT_MALE_AVATAR_URL

    async def get_default_female_avatar(self) -> str:
        """Return a pre-made female RPM avatar GLB URL."""
        return DEFAULT_FEMALE_AVATAR_URL


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_service: Optional[Avatar3DService] = None


def get_avatar3d_service() -> Avatar3DService:
    """Return the lazily-instantiated singleton ``Avatar3DService``."""
    global _service
    if _service is None:
        _service = Avatar3DService()
    return _service
