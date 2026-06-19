"""
AI Companion — Web Push Notification Service
============================================
Handles registration and delivery of web push notifications to PWA clients
using the standard VAPID authentication protocol.

Delivery is performed with ``pywebpush``. This service is *honest*:

* If VAPID keys are not configured (or ``pywebpush`` is not installed), it does
  NOT pretend to deliver — it logs a clear warning and reports ``0`` sent.
* Subscriptions that the push gateway reports as expired/gone (HTTP 404/410)
  are removed from the database automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from app.config import get_settings
from app import database

logger = logging.getLogger(__name__)

# pywebpush is an optional dependency — guard the import so the rest of the app
# keeps working (and we can report an honest warning) if it isn't installed yet.
try:
    from pywebpush import webpush, WebPushException  # type: ignore
    _PYWEBPUSH_AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    webpush = None  # type: ignore
    WebPushException = Exception  # type: ignore
    _PYWEBPUSH_AVAILABLE = False


class NotificationService:
    """Service to send web push notifications to PWA clients."""

    def __init__(self) -> None:
        settings = get_settings()
        self._public_key = settings.VAPID_PUBLIC_KEY.strip()
        self._private_key = settings.VAPID_PRIVATE_KEY.strip()
        self._subject = settings.VAPID_SUBJECT or "mailto:admin@example.com"

    @property
    def public_key(self) -> str:
        """The VAPID public key the frontend uses to subscribe (may be empty)."""
        return self._public_key

    @property
    def is_configured(self) -> bool:
        """True when real delivery is possible."""
        return bool(_PYWEBPUSH_AVAILABLE and self._public_key and self._private_key)

    async def close(self) -> None:  # kept for API compatibility
        return None

    def _send_one(self, sub: dict[str, Any], payload: str) -> None:
        """Blocking single send (runs in a worker thread)."""
        subscription_info = {
            "endpoint": sub["endpoint"],
            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
        }
        webpush(  # type: ignore[misc]
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=self._private_key,
            vapid_claims={"sub": self._subject},
        )

    async def send_notification(
        self, user_id: int, title: str, body: str, icon: str = "/logo.png"
    ) -> int:
        """Send a push notification to all of a user's subscriptions.

        Returns the number of successfully delivered messages.
        """
        if not self.is_configured:
            reason = (
                "pywebpush not installed"
                if not _PYWEBPUSH_AVAILABLE
                else "VAPID keys not configured (set VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY)"
            )
            logger.warning(
                "Web push not delivered for user %s — %s. No message was sent.",
                user_id,
                reason,
            )
            return 0

        subscriptions = await database.get_push_subscriptions(user_id)
        if not subscriptions:
            logger.info("No push subscriptions found for user %s", user_id)
            return 0

        payload = json.dumps(
            {
                "notification": {
                    "title": title,
                    "body": body,
                    "icon": icon,
                    "vibrate": [100, 50, 100],
                    "data": {"primaryKey": user_id},
                }
            }
        )

        success_count = 0
        for sub in subscriptions:
            try:
                await asyncio.to_thread(self._send_one, sub, payload)
                success_count += 1
            except WebPushException as exc:  # type: ignore[misc]
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in (404, 410):
                    # Subscription is dead — clean it up so we stop trying.
                    removed = await database.delete_push_subscription(sub["endpoint"])
                    logger.info(
                        "Removed expired push subscription (status %s, removed=%s).",
                        status,
                        removed,
                    )
                else:
                    logger.warning("Web push delivery failed (status %s): %s", status, exc)
            except Exception:
                logger.exception("Unexpected error delivering push notification")

        logger.info(
            "Delivered %d/%d push notifications for user %s.",
            success_count,
            len(subscriptions),
            user_id,
        )
        return success_count


_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service