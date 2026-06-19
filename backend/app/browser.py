"""
AI Companion – Browser Automation Service
=========================================
Provides a :class:`BrowserService` that wraps **Playwright** (headless Chromium)
to give the LLM tool-calling system safe, rate-limited web automation
capabilities (navigation, screenshots, clicking, typing, form filling,
JavaScript execution, and CSS extraction).

Security
--------
* Navigation to private / internal IP ranges is blocked (``is_private_url``).
* Navigations are rate-limited (minimum ``_min_nav_interval`` seconds between
  consecutive navigations) to avoid hammering remote hosts.
* Playwright is imported lazily so the rest of the app does not pay the import
  cost unless browser automation is actually used.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse

from app.config import get_settings

logger = logging.getLogger(__name__)

# Minimum seconds between consecutive navigations (rate limiting).
_MIN_NAV_INTERVAL: float = 1.0
# Default navigation timeout (milliseconds).
_NAV_TIMEOUT_MS: int = 30_000
# Maximum characters of page text returned by ``navigate``.
_MAX_TEXT_CHARS: int = 5_000

# Hostname patterns considered private/internal.
_PRIVATE_HOST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^localhost$", re.IGNORECASE),
    re.compile(r"^.*\.localhost$", re.IGNORECASE),
    re.compile(r"^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$"),
    re.compile(r"^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$"),
    re.compile(r"^192\.168\.\d{1,3}\.\d{1,3}$"),
    # 172.16.0.0/12 → 172.16.x.x – 172.31.x.x
    re.compile(r"^172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}$"),
    re.compile(r"^0\.0\.0\.0$"),
    re.compile(r"^\[?::1\]?$"),  # IPv6 loopback
    re.compile(r"^\[?fc00:", re.IGNORECASE),  # IPv6 ULA
    re.compile(r"^\[?fe80:", re.IGNORECASE),  # IPv6 link-local
)


class BrowserService:
    """Asynchronous Playwright wrapper for headless Chromium automation.

    The browser is started lazily on first use via :meth:`_ensure_started` and
    should be closed with :meth:`close` when no longer needed (e.g. on app
    shutdown).  All public methods are coroutines.
    """

    def __init__(self) -> None:
        self.playwright: Any = None
        self.browser: Any = None
        self.page: Any = None

        self._nav_timeout_ms: int = _NAV_TIMEOUT_MS
        self._min_nav_interval: float = _MIN_NAV_INTERVAL
        self._last_nav_time: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch headless Chromium and create a new page.

        Playwright is imported lazily so the dependency is only required when
        browser automation is actually used.
        """
        if self.page is not None:
            logger.debug("BrowserService already started – skipping.")
            return

        settings = get_settings()
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise RuntimeError(
                "Playwright is not installed. Install it with "
                "`pip install playwright` and run `playwright install chromium`."
            ) from exc

        logger.info("Starting headless Chromium browser.")
        self.playwright = await async_playwright().start()

        launch_args: list[str] = ["--no-sandbox", "--disable-dev-shm-usage"]
        if settings.PROXY_URL:
            logger.info("Browser using proxy: %s", settings.PROXY_URL)

        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=launch_args,
            proxy={"server": settings.PROXY_URL} if settings.PROXY_URL else None,
        )

        context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="AI-Companion/1.0 (browser-automation)",
        )
        self.page = await context.new_page()
        self.page.set_default_navigation_timeout(self._nav_timeout_ms)
        logger.info("Browser ready (viewport 1280x720).")

    async def _ensure_started(self) -> None:
        """Start the browser if it is not already running."""
        if self.page is None:
            await self.start()

    async def close(self) -> None:
        """Close the browser and shut down Playwright."""
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                logger.exception("Error closing browser.")
            self.browser = None
        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception:
                logger.exception("Error stopping playwright.")
            self.playwright = None
        self.page = None
        logger.info("Browser closed.")

    # ------------------------------------------------------------------
    # Security helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_private_url(url: str) -> bool:
        """Return ``True`` if *url* points at a private/internal host.

        Checks against common private IPv4 ranges, loopback, link-local, and
        ``localhost`` hostnames.  Non-HTTP(S) schemes are also rejected.
        """
        try:
            parsed = urlparse(url)
        except Exception:
            return True  # treat unparseable URLs as unsafe

        if parsed.scheme not in ("http", "https"):
            return True

        host = (parsed.hostname or "").strip("[]")
        if not host:
            return True

        # Hostname-based patterns (localhost etc.).
        for pattern in _PRIVATE_HOST_PATTERNS:
            if pattern.match(host):
                return True

        # Try IP-based detection for literal addresses.
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        except ValueError:
            # Not an IP literal (it's a DNS name) – hostname patterns above
            # already covered `localhost`; allow other DNS names.
            pass

        return False

    async def _rate_limit(self) -> None:
        """Sleep if necessary to enforce the minimum navigation interval."""
        now = time.monotonic()
        elapsed = now - self._last_nav_time
        if elapsed < self._min_nav_interval:
            await asyncio.sleep(self._min_nav_interval - elapsed)
        self._last_nav_time = time.monotonic()

    def _check_url_safe(self, url: str) -> Optional[str]:
        """Return an error message if *url* is unsafe, else ``None``."""
        if not url or not isinstance(url, str):
            return "Invalid URL: empty or non-string."
        if self.is_private_url(url):
            return f"Blocked navigation to private/internal URL: {url}"
        return None

    # ------------------------------------------------------------------
    # Public automation API
    # ------------------------------------------------------------------

    async def navigate(self, url: str) -> dict[str, Any]:
        """Navigate to *url* and return page metadata.

        Returns a dict with ``title``, ``url``, and ``text_content`` (first
        ``_MAX_TEXT_CHARS`` characters of visible text).
        """
        err = self._check_url_safe(url)
        if err:
            return {"error": err}

        await self._ensure_started()
        assert self.page is not None

        async with self._lock:
            await self._rate_limit()
            try:
                await self.page.goto(url, wait_until="domcontentloaded")
            except Exception as exc:
                logger.exception("Navigation to %s failed.", url)
                return {"error": f"Navigation failed: {exc}"}

        title: str = await self.page.title()
        final_url: str = self.page.url
        # Extract visible text via the body's innerText.
        try:
            text_content: str = await self.page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
        except Exception:
            text_content = ""
        return {
            "title": title,
            "url": final_url,
            "text_content": text_content[:_MAX_TEXT_CHARS],
        }

    async def screenshot(self, url: Optional[str] = None) -> bytes:
        """Take a PNG screenshot.

        If *url* is provided, navigate to it first (subject to safety checks
        and rate limiting).  Returns the raw PNG bytes.
        """
        if url is not None:
            err = self._check_url_safe(url)
            if err:
                raise ValueError(err)
            await self._ensure_started()
            assert self.page is not None
            async with self._lock:
                await self._rate_limit()
                try:
                    await self.page.goto(url, wait_until="domcontentloaded")
                except Exception as exc:
                    logger.exception("Screenshot navigation to %s failed.", url)
                    raise RuntimeError(f"Navigation failed: {exc}") from exc
        else:
            await self._ensure_started()
            assert self.page is not None

        return await self.page.screenshot(type="png", full_page=False)

    async def click(self, selector: str) -> dict[str, Any]:
        """Click the element matching *selector* (CSS).

        Returns ``{"success": bool, "error": str | None}``.
        """
        await self._ensure_started()
        assert self.page is not None
        try:
            await self.page.click(selector, timeout=self._nav_timeout_ms)
            return {"success": True, "error": None}
        except Exception as exc:
            logger.warning("Click on '%s' failed: %s", selector, exc)
            return {"success": False, "error": str(exc)}

    async def type_text(self, selector: str, text: str) -> dict[str, Any]:
        """Type *text* into the element matching *selector* (CSS).

        Returns ``{"success": bool, "error": str | None}``.
        """
        await self._ensure_started()
        assert self.page is not None
        try:
            await self.page.fill(selector, text, timeout=self._nav_timeout_ms)
            return {"success": True, "error": None}
        except Exception as exc:
            logger.warning("Type into '%s' failed: %s", selector, exc)
            return {"success": False, "error": str(exc)}

    async def extract(self, selectors: dict[str, str]) -> dict[str, str]:
        """Extract text content from multiple CSS selectors.

        *selectors* maps a result name to a CSS selector.  Returns a dict of
        ``{name: text}``; missing or errored selectors yield an empty string.
        """
        await self._ensure_started()
        assert self.page is not None

        result: dict[str, str] = {}
        for name, css in selectors.items():
            try:
                element = await self.page.query_selector(css)
                if element is None:
                    result[name] = ""
                else:
                    result[name] = (await element.inner_text()) or ""
            except Exception as exc:
                logger.warning("Extract '%s' (selector '%s') failed: %s", name, css, exc)
                result[name] = ""
        return result

    async def execute_js(self, script: str) -> Any:
        """Run *script* (JavaScript) in the page context and return the result."""
        await self._ensure_started()
        assert self.page is not None
        try:
            return await self.page.evaluate(script)
        except Exception as exc:
            logger.exception("JavaScript execution failed.")
            return {"error": str(exc)}

    async def fill_form(
        self, url: str, form_data: dict[str, str]
    ) -> dict[str, Any]:
        """Navigate to *url* and fill multiple form fields.

        *form_data* maps CSS selectors to the values to type into them.
        Returns ``{"success": bool, "fields_filled": int, "errors": [...]}``.
        """
        err = self._check_url_safe(url)
        if err:
            return {"success": False, "fields_filled": 0, "errors": [err]}

        nav_result = await self.navigate(url)
        if "error" in nav_result:
            return {
                "success": False,
                "fields_filled": 0,
                "errors": [nav_result["error"]],
            }

        fields_filled = 0
        errors: list[str] = []
        for selector, value in form_data.items():
            res = await self.type_text(selector, value)
            if res.get("success"):
                fields_filled += 1
            else:
                errors.append(f"{selector}: {res.get('error', 'unknown')}")

        return {
            "success": fields_filled == len(form_data),
            "fields_filled": fields_filled,
            "errors": errors,
        }
