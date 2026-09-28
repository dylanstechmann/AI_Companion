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
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
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


@lru_cache(maxsize=1)
def _development_secret() -> str:
    """Use one ephemeral key per process, without writing it to disk."""
    logger.warning("JWT_SECRET is unset; development tokens expire on process restart.")
    return secrets.token_urlsafe(32)


def _default_secret() -> str:
    settings = get_settings()
    return settings.JWT_SECRET or _development_secret()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class AuthRateLimiter:
    """Sliding-window rate limiter for sensitive authentication endpoints."""

    def __init__(
        self,
        login_max: int = 5,
        login_window: int = 60,
        refresh_max: int = 20,
        refresh_window: int = 60,
    ) -> None:
        self.login_max = login_max
        self.login_window = login_window
        self.refresh_max = refresh_max
        self.refresh_window = refresh_window
        self._login_attempts: dict[str, list[float]] = {}
        self._refresh_attempts: dict[str, list[float]] = {}

    def _check(
        self,
        registry: dict[str, list[float]],
        key: str,
        limit: int,
        window: int,
        action: str,
    ) -> None:
        now = time.time()
        cutoff = now - window
        history = [t for t in registry.get(key, []) if t > cutoff]
        registry[key] = history

        if len(history) >= limit:
            oldest = history[0]
            retry_after = max(1, int(window - (now - oldest)))
            logger.warning("Rate limit exceeded for %s on key=%s (count=%d)", action, key, len(history))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many {action} attempts. Please wait {retry_after} seconds before retrying.",
                headers={"Retry-After": str(retry_after)},
            )
        history.append(now)

    def check_login(self, client_ip: str, email: str = "") -> None:
        """Rate limit login requests by IP and (IP, email)."""
        settings = get_settings()
        limit = getattr(settings, "AUTH_RATE_LIMIT_LOGIN_MAX_ATTEMPTS", self.login_max)
        window = getattr(settings, "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS", self.login_window)

        if email:
            target_key = f"{client_ip}:{email.strip().lower()}"
            self._check(self._login_attempts, target_key, limit, window, "login")
        else:
            self._check(self._login_attempts, client_ip, limit, window, "login")

    def check_refresh(self, client_ip: str) -> None:
        """Rate limit token refresh requests by IP."""
        settings = get_settings()
        limit = getattr(settings, "AUTH_RATE_LIMIT_REFRESH_MAX_ATTEMPTS", self.refresh_max)
        window = getattr(settings, "AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS", self.refresh_window)
        self._check(self._refresh_attempts, client_ip, limit, window, "token refresh")

    def reset(self) -> None:
        """Clear all recorded rate limit attempts."""
        self._login_attempts.clear()
        self._refresh_attempts.clear()


# ---------------------------------------------------------------------------
# Authentication service
# ---------------------------------------------------------------------------

class AuthService:
    """High-level authentication API used by FastAPI routes."""

    def __init__(self) -> None:
        self.hasher = PasswordHasher()
        self.rate_limiter = AuthRateLimiter()

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
                options={"require_exp": True, "require_sub": True},
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
        subject = payload.get("sub")
        if not isinstance(subject, str) or len(subject) > 19 or not subject.isascii() or not subject.isdecimal() or not 1 <= int(subject) <= 9223372036854775807:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
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
        """Create a trusted account only during explicitly enabled setup."""
        if not get_settings().ALLOW_REGISTRATION:
            raise HTTPException(status_code=403, detail="Registration is disabled on this instance.")
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
        return self._token_response(user)

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

        return self._token_response(user)

    @staticmethod
    def _check_enabled(user: dict[str, Any]) -> None:
        if user.get("email") == "demo@companion.local" and not get_settings().ALLOW_DEMO_LOGIN:
            raise HTTPException(status_code=401, detail="Demo access is disabled.",
                                headers={"WWW-Authenticate": "Bearer"})

    def _token_response(self, user: dict[str, Any]) -> dict[str, Any]:
        self._check_enabled(user)
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
        return self._token_response(user)

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
        self._check_enabled(user)
        return _public_user(user)

    async def create_or_get_demo_user(self) -> dict[str, Any]:
        """Ensure a default demo user exists and return it.

        Backward-compatibility helper: if the ``users`` table is empty, create
        a single 'demo' user so the app works without explicit registration.
        """
        if not get_settings().ALLOW_DEMO_LOGIN:
            raise HTTPException(status_code=403, detail="Demo access is disabled on this instance.")
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
    cached_user = getattr(request.state, "authenticated_user", None)
    if cached_user is not None:
        return cached_user
    token = _extract_bearer(request)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await auth_service.get_current_user(token)
    request.state.authenticated_user = user
    return user


# Every operational route is authenticated by default. Webhook endpoints
# perform their provider-specific signature verification in their handlers.
PUBLIC_ENDPOINTS = frozenset({
    ("GET", "/api/health"),
    ("GET", "/api/auth/options"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/demo"),
    ("GET", "/api/payments/credit-packs"),
    ("GET", "/api/notifications/vapid-public-key"),
    ("POST", "/api/payments/stripe/webhook"),
    ("POST", "/api/payments/btcpay/webhook"),
    ("POST", "/api/payments/webhook"),
})


async def require_api_user(request: Request) -> dict[str, Any] | None:
    if (request.method, request.url.path) in PUBLIC_ENDPOINTS:
        return None
    return await require_auth(request)


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
