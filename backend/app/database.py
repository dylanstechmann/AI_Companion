"""
AI Companion – Async SQLite Database Layer
===========================================
All database access runs through ``aiosqlite`` for non-blocking I/O.

Tables
------
* **characters** – AI personas the user can chat with.
* **messages**   – Full conversation history per character.

Public helpers
--------------
``init_db``        – create tables on first run.
``seed_defaults``  – insert built-in characters when the table is empty.
``get_all_characters``, ``get_character``, ``create_character``,
``update_character``, ``delete_character`` – character CRUD.
``get_messages``, ``add_message`` – message CRUD.
"""

from __future__ import annotations
from contextlib import asynccontextmanager

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from app.characters import DEFAULT_CHARACTERS
from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _db_path() -> str:
    """Return the resolved database file path, ensuring parent dirs exist."""
    settings = get_settings()
    path = settings.DATABASE_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


@asynccontextmanager
async def _connect():
    """Open a connection with row-factory enabled."""
    conn = await aiosqlite.connect(_db_path())
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        await conn.close()


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    """Convert an ``aiosqlite.Row`` to a plain dict."""
    return dict(row)


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create tables if they do not already exist."""
    async with _connect() as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                description TEXT    NOT NULL DEFAULT '',
                system_prompt TEXT  NOT NULL,
                is_default  BOOLEAN NOT NULL DEFAULT 0,
                created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                role         TEXT    NOT NULL,
                content      TEXT    NOT NULL,
                image_url    TEXT,
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (character_id) REFERENCES characters(id)
                    ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_character
                ON messages(character_id, created_at)
            """
        )
        # Phase 4: Users table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                display_name  TEXT    DEFAULT '',
                created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_active     BOOLEAN NOT NULL DEFAULT 1
            )
            """
        )
        # Phase 4: Add user_id to characters (nullable for backward compat)
        try:
            await db.execute("ALTER TABLE characters ADD COLUMN user_id INTEGER REFERENCES users(id)")
        except Exception:
            pass  # Column already exists
        # Phase 4: Add user_id to messages
        try:
            await db.execute("ALTER TABLE messages ADD COLUMN user_id INTEGER REFERENCES users(id)")
        except Exception:
            pass
        # Avatar support
        try:
            await db.execute("ALTER TABLE characters ADD COLUMN avatar_url TEXT DEFAULT ''")
        except Exception:
            pass  # Column already exists
        try:
            await db.execute("ALTER TABLE characters ADD COLUMN appearance_description TEXT DEFAULT ''")
        except Exception:
            pass  # Column already exists
        # 3D avatar support (Ready Player Me GLB URLs)
        try:
            await db.execute("ALTER TABLE characters ADD COLUMN avatar_3d_url TEXT DEFAULT ''")
        except Exception:
            pass  # Column already exists
        # Phase 4: Payments table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                invoice_id  TEXT UNIQUE NOT NULL,
                amount_sats INTEGER NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                paid_at     TIMESTAMP
            )
            """
        )
        # Phase 4: Subscriptions table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                plan        TEXT NOT NULL DEFAULT 'free',
                started_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at  TIMESTAMP,
                is_active   BOOLEAN NOT NULL DEFAULT 1
            )
            """
        )
        # Phase 4: Usage logs table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                action      TEXT NOT NULL,
                cost_sats   INTEGER NOT NULL DEFAULT 0,
                created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Phase 4: User credits table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_credits (
                user_id     INTEGER PRIMARY KEY REFERENCES users(id),
                balance_sats INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Web Push Subscriptions Table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                endpoint    TEXT UNIQUE NOT NULL,
                p256dh      TEXT NOT NULL,
                auth        TEXT NOT NULL,
                created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()
    logger.info("Database tables initialised.")


async def seed_defaults() -> None:
    """Insert default characters when the ``characters`` table is empty."""
    async with _connect() as db:
        cursor = await db.execute("SELECT COUNT(*) AS cnt FROM characters")
        row = await cursor.fetchone()
        if row and row["cnt"] > 0:
            logger.info("Characters table already populated – skipping seed.")
            return

        now = datetime.now(timezone.utc).isoformat()
        for char in DEFAULT_CHARACTERS:
            await db.execute(
                """
                INSERT INTO characters (name, description, system_prompt, is_default, avatar_url, appearance_description, created_at)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                """,
                (char["name"], char["description"], char["system_prompt"], char.get("avatar_url", ""), char.get("appearance_description", ""), now),
            )
        await db.commit()
    logger.info("Seeded %d default characters.", len(DEFAULT_CHARACTERS))


# ---------------------------------------------------------------------------
# Character CRUD
# ---------------------------------------------------------------------------

async def get_all_characters() -> list[dict[str, Any]]:
    """Return every character, ordered by id."""
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM characters ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


async def get_character(character_id: int) -> Optional[dict[str, Any]]:
    """Return a single character by id, or ``None``."""
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM characters WHERE id = ?", (character_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def create_character(
    name: str,
    description: str,
    system_prompt: str,
    avatar_url: str = "",
    appearance_description: str = "",
) -> dict[str, Any]:
    """Insert a new user-created character and return it."""
    async with _connect() as db:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            """
            INSERT INTO characters (name, description, system_prompt, is_default, avatar_url, appearance_description, created_at)
            VALUES (?, ?, ?, 0, ?, ?, ?)
            """,
            (name, description, system_prompt, avatar_url, appearance_description, now),
        )
        await db.commit()
        return {
            "id": cursor.lastrowid,
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "is_default": False,
            "avatar_url": avatar_url,
            "appearance_description": appearance_description,
            "created_at": now,
        }


async def update_character(
    character_id: int,
    **fields: Any,
) -> Optional[dict[str, Any]]:
    """Update one or more fields on an existing character."""
    allowed = {"name", "description", "system_prompt", "avatar_url", "appearance_description", "avatar_3d_url"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return await get_character(character_id)

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [character_id]

    async with _connect() as db:
        await db.execute(
            f"UPDATE characters SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
        await db.commit()

    return await get_character(character_id)


async def delete_character(character_id: int) -> bool:
    """Delete a non-default character. Returns ``True`` on success."""
    char = await get_character(character_id)
    if char is None:
        return False
    if char.get("is_default"):
        raise ValueError("Cannot delete a default character.")

    async with _connect() as db:
        await db.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        await db.commit()
    return True


# ---------------------------------------------------------------------------
# Message CRUD
# ---------------------------------------------------------------------------

async def get_messages(
    character_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return conversation history for a character, newest last."""
    async with _connect() as db:
        cursor = await db.execute(
            """
            SELECT * FROM messages
            WHERE character_id = ?
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
            """,
            (character_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


async def add_message(
    character_id: int,
    role: str,
    content: str,
    image_url: Optional[str] = None,
) -> dict[str, Any]:
    """Persist a new message and return it."""
    async with _connect() as db:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            """
            INSERT INTO messages (character_id, role, content, image_url, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (character_id, role, content, image_url, now),
        )
        await db.commit()
        return {
            "id": cursor.lastrowid,
            "character_id": character_id,
            "role": role,
            "content": content,
            "image_url": image_url,
            "created_at": now,
        }


# ---------------------------------------------------------------------------
# User CRUD (Phase 4)
# ---------------------------------------------------------------------------

async def create_user(email: str, password_hash: str, display_name: str = "") -> dict[str, Any]:
    """Create a new user and return it (including password_hash for internal use)."""
    async with _connect() as db:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            """
            INSERT INTO users (email, password_hash, display_name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (email, password_hash, display_name, now),
        )
        await db.commit()
        return {
            "id": cursor.lastrowid,
            "email": email,
            "password_hash": password_hash,
            "display_name": display_name,
            "created_at": now,
            "is_active": True,
        }


async def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    """Return a user by email, or None."""
    async with _connect() as db:
        cursor = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    """Return a user by id, or None."""
    async with _connect() as db:
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


# ---------------------------------------------------------------------------
# Payment / Subscription / Usage helpers (Phase 4)
# ---------------------------------------------------------------------------

async def create_payment(user_id: int, invoice_id: str, amount_sats: int) -> dict[str, Any]:
    """Record a new payment invoice."""
    async with _connect() as db:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            """
            INSERT INTO payments (user_id, invoice_id, amount_sats, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (user_id, invoice_id, amount_sats, now),
        )
        await db.commit()
        return {
            "id": cursor.lastrowid,
            "user_id": user_id,
            "invoice_id": invoice_id,
            "amount_sats": amount_sats,
            "status": "pending",
            "created_at": now,
        }


async def update_payment_status(invoice_id: str, status: str) -> bool:
    """Update a payment's status. Returns True if updated."""
    async with _connect() as db:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            "UPDATE payments SET status = ?, paid_at = ? WHERE invoice_id = ?",
            (status, now if status in ("paid", "settled", "confirmed", "complete") else None, invoice_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_payment_by_invoice(invoice_id: str) -> Optional[dict[str, Any]]:
    """Return a payment by invoice_id."""
    async with _connect() as db:
        cursor = await db.execute("SELECT * FROM payments WHERE invoice_id = ?", (invoice_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None


async def get_or_create_subscription(user_id: int) -> dict[str, Any]:
    """Get the user's subscription, creating a free one if none exists."""
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? AND is_active = 1", (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return _row_to_dict(row)
        # Create free subscription
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            "INSERT INTO subscriptions (user_id, plan, started_at, is_active) VALUES (?, 'free', ?, 1)",
            (user_id, now),
        )
        await db.commit()
        return {"id": cursor.lastrowid, "user_id": user_id, "plan": "free", "started_at": now, "expires_at": None, "is_active": True}


async def update_subscription(user_id: int, plan: str) -> dict[str, Any]:
    """Update the user's subscription plan."""
    async with _connect() as db:
        now = datetime.now(timezone.utc).isoformat()
        # Deactivate existing
        await db.execute("UPDATE subscriptions SET is_active = 0 WHERE user_id = ?", (user_id,))
        # Insert new
        cursor = await db.execute(
            "INSERT INTO subscriptions (user_id, plan, started_at, is_active) VALUES (?, ?, ?, 1)",
            (user_id, plan, now),
        )
        await db.commit()
        return {"id": cursor.lastrowid, "user_id": user_id, "plan": plan, "started_at": now, "expires_at": None, "is_active": True}


async def add_usage_log(user_id: int, action: str, cost_sats: float) -> dict[str, Any]:
    """Log a usage event."""
    async with _connect() as db:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            "INSERT INTO usage_logs (user_id, action, cost_sats, created_at) VALUES (?, ?, ?, ?)",
            (user_id, action, cost_sats, now),
        )
        await db.commit()
        return {"id": cursor.lastrowid, "user_id": user_id, "action": action, "cost_sats": cost_sats, "created_at": now}


async def get_usage_today(user_id: int) -> int:
    """Count today's chat messages for rate limiting."""
    async with _connect() as db:
        cursor = await db.execute(
            """
            SELECT COUNT(*) as cnt FROM usage_logs
            WHERE user_id = ? AND action = 'chat_message'
            AND DATE(created_at) = DATE('now')
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0


async def get_user_credits(user_id: int) -> float:
    """Get user's credit balance in satoshis."""
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT balance_sats FROM user_credits WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return float(row["balance_sats"]) if row else 0.0


async def add_user_credits(user_id: int, amount_sats: float) -> float:
    """Add credits to user's balance. Returns new balance."""
    async with _connect() as db:
        # Upsert
        await db.execute(
            """
            INSERT INTO user_credits (user_id, balance_sats)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET balance_sats = balance_sats + ?
            """,
            (user_id, amount_sats, amount_sats),
        )
        await db.commit()
    return await get_user_credits(user_id)


async def deduct_user_credits(user_id: int, amount_sats: float) -> bool:
    """Deduct credits. Returns False if insufficient balance."""
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT balance_sats FROM user_credits WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        balance = float(row["balance_sats"]) if row else 0.0
        if balance < amount_sats:
            return False
        await db.execute(
            "UPDATE user_credits SET balance_sats = balance_sats - ? WHERE user_id = ?",
            (amount_sats, user_id),
        )
        await db.commit()
        return True


async def get_usage_history(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Return usage log entries for a user."""
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM usage_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


async def get_payment_history(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Return payment records for a user."""
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Push Notification helpers
# ---------------------------------------------------------------------------

async def add_push_subscription(user_id: int, endpoint: str, p256dh: str, auth: str) -> None:
    """Add or update a web push subscription for a user."""
    async with _connect() as db:
        await db.execute(
            """
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id
            """,
            (user_id, endpoint, p256dh, auth),
        )
        await db.commit()


async def get_push_subscriptions(user_id: int) -> list[dict[str, Any]]:
    """Return all registered push subscriptions for a user."""
    async with _connect() as db:
        cursor = await db.execute(
            """
            SELECT id, user_id, endpoint, p256dh, auth, created_at
            FROM push_subscriptions
            WHERE user_id = ?
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


async def delete_push_subscription(endpoint: str) -> bool:
    """Remove a push subscription by endpoint (used when a push gateway reports
    the subscription has expired/gone — HTTP 404/410). Returns True if removed."""
    async with _connect() as db:
        cursor = await db.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
        )
        await db.commit()
        return cursor.rowcount > 0
