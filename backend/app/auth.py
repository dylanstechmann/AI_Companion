"""
AI Companion – Authentication Service
======================================
JWT-based user authentication built on top of the async SQLite database layer.

Features
--------
* Password hashing via ``passlib[bcrypt]``.
* Access & refresh JWT tokens via ``python-jose``.
* ``AuthService`` covering register / login / refresh / current-user flows.
* FastAPI dependencies (``require_auth``, ``get_optional_user``) for routes.

Database helpers expected on ``app.database`` (added by the parent task):
* ``create_user(email, password_hash, display_name) -> dict``
* ``get_user_by_email(email) -> dict | None``
* ``get_user_by_id(user_id) -> dict | None``
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
import bcrypt as _bcrypt

from app.config import get_settings
from app import database as db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class PasswordHasher:
    """Bcrypt password hashing wrapper."""

    def hash_password(self, plain: str) -> str:
        """Return a bcrypt hash for the given plaintext password."""
        # bcrypt has a 72-byte limit — truncate to be safe
        pwd_bytes = plain.encode("utf-8")[:72]
        return _bcrypt.hashpw(pwd_bytes, _bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Return ``True`` if *plain* matches *hashed*."""
        try:
            pwd_bytes = plain.encode("utf-8")[:72]
            hash_bytes = hashed.encode("utf-8") if isinstance(hashed, str) else hashed
            return _bcrypt.checkpw(pwd_bytes, hash_bytes)
        except Exception:  # noqa: BLE001 – invalid hash format, etc.
            return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    """Strip sensitive fields before returning a user dict."""
    return {k: v for k, v in user.items() if k != "password_hash"}


def _default_secret() -> str:
    """Return the configured JWT secret, falling back to an ephemeral one.

    A non-empty ephemeral secret lets the app boot without configuration (e.g.
    during local development or tests) but is logged so operators know tokens
    will not survive a restart.
    """
    secret = get_settings().JWT_SECRET
    if secret:
        return secret
    ephemeral = secrets.token_urlsafe(32)
    logger.warning(
        "JWT_SECRET is not set – generated ephemeral secret. "
        "Tokens will be invalidated on restart."
    )
    return ephemeral


# ---------------------------------------------------------------------------
# Authentication service
# ---------------------------------------------------------------------------

class AuthService:
    """High-level authentication API used by FastAPI routes."""

    def __init__(self) -> None:
        self.hasher = PasswordHasher()

    # -- token creation ------------------------------------------------------

    def create_access_token(self, user_id: int) -> str:
        """Create a short-lived access JWT for *user_id*."""
        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        return jwt.encode(payload, _default_secret(), algorithm=settings.JWT_ALGORITHM)

    def create_refresh_token(self, user_id: int) -> str:
        """Create a longer-lived refresh JWT for *user_id*."""
        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        }
        return jwt.encode(payload, _default_secret(), algorithm=settings.JWT_ALGORITHM)

    # -- token validation ----------------------------------------------------

    def _decode(self, token: str, expected_type: str) -> dict[str, Any]:
        """Decode and validate a JWT, enforcing its *type* claim."""
        settings = get_settings()
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                _default_secret(),
                algorithms=[settings.JWT_ALGORITHM],
            )
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        if payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload

    # -- user flows ----------------------------------------------------------

    async def register(
        self,
        email: str,
        password: str,
        display_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new user and return the public user dict."""
        existing = await db.get_user_by_email(email)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with that email already exists.",
            )

        password_hash = self.hasher.hash_password(password)
        user = await db.create_user(
            email=email,
            password_hash=password_hash,
            display_name=display_name,
        )
        logger.info("Registered new user: email=%s id=%s", email, user.get("id"))
        return _public_user(user)

    async def login(self, email: str, password: str) -> dict[str, Any]:
        """Verify credentials and return a token pair plus public user."""
        user = await db.get_user_by_email(email)
        if user is None or "password_hash" not in user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not self.hasher.verify_password(password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = int(user["id"])
        return {
            "access_token": self.create_access_token(user_id),
            "refresh_token": self.create_refresh_token(user_id),
            "token_type": "bearer",
            "user": _public_user(user),
        }

    async def refresh_token(self, refresh_token_str: str) -> dict[str, Any]:
        """Validate a refresh token and return a fresh token pair."""
        payload = self._decode(refresh_token_str, expected_type="refresh")
        user_id = int(payload["sub"])
        user = await db.get_user_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User no longer exists",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {
            "access_token": self.create_access_token(user_id),
            "refresh_token": self.create_refresh_token(user_id),
            "token_type": "bearer",
            "user": _public_user(user),
        }

    async def get_current_user(self, token: str) -> dict[str, Any]:
        """Decode an access token and return the matching public user dict."""
        payload = self._decode(token, expected_type="access")
        user_id = int(payload["sub"])
        user = await db.get_user_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User no longer exists",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _public_user(user)

    async def create_or_get_demo_user(self) -> dict[str, Any]:
        """Ensure a default demo user exists and return it.

        Backward-compatibility helper: if the ``users`` table is empty, create
        a single 'demo' user so the app works without explicit registration.
        """
        demo_email = "demo@companion.local"
        existing = await db.get_user_by_email(demo_email)
        if existing is not None:
            current_balance = await db.get_user_credits(existing["id"])
            if current_balance < 100:
                await db.add_user_credits(existing["id"], 5000)
                logger.info("Topped up demo user credits.")
            return _public_user(existing)

        password = secrets.token_urlsafe(32)
        password_hash = self.hasher.hash_password(password)
        user = await db.create_user(
            email=demo_email,
            password_hash=password_hash,
            display_name="Demo User",
        )
        await db.add_user_credits(user["id"], 5000)
        logger.info("Created demo user (id=%s) and seeded credits.", user.get("id"))
        return _public_user(user)


# Shared singleton ----------------------------------------------------------
auth_service = AuthService()


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def _extract_bearer(request: Request) -> Optional[str]:
    """Return the Bearer token from the Authorization header, if present."""
    header = request.headers.get("Authorization")
    if not header:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


async def require_auth(request: Request) -> dict[str, Any]:
    """FastAPI dependency: require a valid Bearer access token.

    Returns the public user dict on success; raises 401 otherwise.
    """
    token = _extract_bearer(request)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await auth_service.get_current_user(token)


async def get_optional_user(request: Request) -> Optional[dict[str, Any]]:
    """FastAPI dependency: return the user if a valid token is supplied.

    Falls back to ``None`` so routes can work with or without auth.
    """
    token = _extract_bearer(request)
    if token is None:
        return None
    try:
        return await auth_service.get_current_user(token)
    except HTTPException:
        return None
