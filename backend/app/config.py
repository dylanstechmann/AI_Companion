"""
AI Companion – Application Configuration
=========================================
Loads all configuration from environment variables (or a ``.env`` file in the
project root).  Uses *pydantic-settings* ``BaseSettings`` so values are
validated at startup.  Access the singleton via ``get_settings()``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings, populated from environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- OpenRouter / LLM ---------------------------------------------------
    OPENROUTER_API_KEY: str = ""
    LLM_MODEL: str = "openai/gpt-4o"

    # ---- Speech-to-Text -----------------------------------------------------
    STT_MODE: Literal["local", "cloud"] = "local"
    WHISPER_MODEL: str = "large-v3"
    WHISPER_DEVICE: str = "cuda"  # "cuda" | "cpu"

    # ---- Database ------------------------------------------------------------
    DATABASE_URL: str = "sqlite+aiosqlite:///data/companion.db"
    DATABASE_PATH: str = "data/companion.db"

    # ---- ChromaDB / Embeddings -----------------------------------------------
    CHROMA_PERSIST_DIR: str = "data/chroma"
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"

    # ---- Code Sandbox --------------------------------------------------------
    SANDBOX_TIMEOUT_SECONDS: int = 30

    # ---- Research / Web ------------------------------------------------------
    TAVILY_API_KEY: str = ""
    PROXY_URL: str = ""
    CRAWL_DELAY_SECONDS: float = 2.0

    # ---- Text-to-Speech ------------------------------------------------------
    # Separate API key for TTS (OpenAI-compatible).  Falls back to
    # OPENROUTER_API_KEY if not set, though note that OpenRouter does not
    # proxy audio endpoints — a direct OpenAI key (or compatible provider)
    # is required for cloud TTS.
    TTS_API_KEY: str = ""
    TTS_BASE_URL: str = "https://api.openai.com/v1"
    TTS_MODEL: str = "tts-1"  # "tts-1" or "tts-1-hd"
    TTS_VOICE: str = "alloy"

    # ---- Auth / JWT ----------------------------------------------------------
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---- Email (placeholder) -------------------------------------------------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""

    # ---- Bitcoin / Lightning (BTCPay Server) ---------------------------------
    BTCPAY_URL: str = ""
    BTCPAY_API_KEY: str = ""
    BTCPAY_STORE_ID: str = ""
    BTCPAY_WEBHOOK_SECRET: str = ""

    # ---- Stripe Config ------------------------------------------------------
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ---- PayPal Config ------------------------------------------------------
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_SECRET: str = ""
    PAYPAL_MODE: str = "sandbox"

    # ---- Exchange Config ----------------------------------------------------
    EXCHANGE_API_KEY: str = ""
    EXCHANGE_API_SECRET: str = ""
    EXCHANGE_NAME: str = ""

    # ---- Ready Player Me (3D Avatars) ---------------------------------------
    RPM_API_KEY: str = ""
    RPM_API_BASE_URL: str = "https://api.readyplayer.me/v1"
    RPM_SUBDOMAIN: str = ""  # e.g. "myapp" -> https://myapp.readyplayer.me

    # ---- Web Push (VAPID) ---------------------------------------------------
    # Generate a key pair with:  `python -m py_vapid --gen`  (or any VAPID tool).
    # When both keys are present, the backend delivers REAL web push messages via
    # pywebpush. When unset, notification delivery is skipped (and logged) rather
    # than silently faked.
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_SUBJECT: str = "mailto:admin@example.com"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton ``Settings`` instance."""
    return Settings()  # type: ignore[call-arg]
