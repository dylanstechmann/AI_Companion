"""
AI Companion – Browser Automation Service
=========================================
Provides a :class:`BrowserService` that wraps **Playwright** (headless Chromium
by default, optionally Firefox) to give the LLM tool-calling system web automation
capabilities (navigation, screenshots, clicking, typing, form filling,
JavaScript execution, and CSS extraction).

Security
--------
* Initial URLs and intercepted HTTP(S) requests are checked for non-public
  addresses, including DNS answers. This is defense in depth, NOT an egress
  sandbox: DNS rebinding, redirects and non-HTTP traffic need network controls.
* Contexts grant no permissions, block service workers and disable downloads.
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
import socket
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
# Fail closed rather than holding a browser request indefinitely on DNS.
_DNS_TIMEOUT_SECONDS: float = 5.0

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
    """Asynchronous Playwright wrapper for configurable headless automation.

    The browser is started lazily on first use via :meth:`_ensure_started` and
    should be closed with :meth:`close` when no longer needed (e.g. on app
    shutdown).  All public methods are coroutines.
    """

    def __init__(self) -> None:
        self.playwright: Any = None
        self.browser: Any = None
        self.context: Any = None
        self.page: Any = None

        self._nav_timeout_ms: int = _NAV_TIMEOUT_MS
        self._min_nav_interval: float = _MIN_NAV_INTERVAL
        self._last_nav_time: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()
        self._lifecycle_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the selected engine, cleaning up partially started resources."""
        async with self._lifecycle_lock:
            await self._start_locked()

    async def _start_locked(self) -> None:
        """Start once; caller holds the lifecycle lock.

        Playwright is imported lazily so the dependency is only required when
        browser automation is actually used.
        """
        if self.page is not None:
            logger.debug("BrowserService already started – skipping.")
            return

        settings = get_settings()
        engine = settings.BROWSER_ENGINE
        # Settings validates this too; fail closed if callers replace/mutate it.
        if engine not in ("chromium", "firefox"):
            raise ValueError("BROWSER_ENGINE must be 'chromium' or 'firefox'.")
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise RuntimeError(
                "Playwright is not installed. Install it with "
                "`pip install playwright` and run "
                "`python -m playwright install chromium firefox`."
            ) from exc

        logger.info("Starting headless %s browser.", engine)
        if settings.PROXY_URL:
            # Never log the proxy URL: userinfo and queries can contain secrets.
            logger.info("Browser proxy configured.")
        launch_options: dict[str, Any] = {
            "headless": True,
            "proxy": {"server": settings.PROXY_URL} if settings.PROXY_URL else None,
        }
        if engine == "chromium":
            # Retain existing container compatibility; NOT a secure sandbox.
            # Firefox must not receive Chromium command-line switches.
            launch_options["args"] = ["--no-sandbox", "--disable-dev-shm-usage"]
        try:
            self.playwright = await async_playwright().start()
            self.browser = await getattr(self.playwright, engine).launch(**launch_options)
            self.context = await self.browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="AI-Companion/1.0 (browser-automation)",
                permissions=[],
                service_workers="block",
                accept_downloads=False,
            )
            # Context routing covers popups/frames as well as the primary page.
            # Service workers are blocked because they can bypass page routing.
            await self.context.route("**/*", self._route_request)
            self.page = await self.context.new_page()
            self.page.set_default_navigation_timeout(self._nav_timeout_ms)
        except asyncio.CancelledError:
            await self._close_resources()
            raise
        except Exception:
            await self._close_resources()
            # Playwright launch errors may include proxy credentials or args.
            logger.warning("Browser startup failed; resources released.")
            raise RuntimeError(
                "Browser startup failed. Check engine installation and proxy configuration."
            ) from None
        logger.info("Browser ready (viewport 1280x720).")

    async def _ensure_started(self) -> None:
        """Start the browser if it is not already running."""
        if self.page is None:
            await self.start()

    async def close(self) -> None:
        """Close context, browser and Playwright; safe to call more than once."""
        async with self._lifecycle_lock:
            await self._close_resources()
        logger.info("Browser closed.")

    async def _close_resources(self) -> None:
        """Attempt every cleanup even if an earlier resource fails to close."""
        context, browser, playwright = self.context, self.browser, self.playwright
        self.context = self.browser = self.playwright = None
        self.page = None
        self._last_nav_time = 0.0
        cancelled = False
        for resource, method, label in (
            (context, "close", "context"),
            (browser, "close", "browser"),
            (playwright, "stop", "Playwright"),
        ):
            if resource is not None:
                try:
                    await getattr(resource, method)()
                except asyncio.CancelledError:
                    # Still release remaining resources, then honor cancellation.
                    cancelled = True
                except Exception:
                    # Raw browser exceptions can disclose URL/proxy secrets.
                    logger.warning("Error closing %s.", label)
        if cancelled:
            raise asyncio.CancelledError

    # ------------------------------------------------------------------
    # Security helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_public_address(address: str) -> bool:
        """Accept globally routable unicast only, including mapped IPv4 checks."""
        ip = ipaddress.ip_address(address)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        return ip.is_global and not ip.is_multicast and not ip.is_reserved

    @staticmethod
    def is_private_url(url: str) -> bool:
        """Conservative syntactic check; DNS is checked separately before use.

        Reject non-HTTP(S), credentials, ambiguous URL syntax and literal
        non-public addresses. A False result does NOT mean DNS is safe.
        """
        if not isinstance(url, str) or not url:
            return True
        # Avoid differences between Python URL parsing and browser URL parsing.
        if "\\" in url or any(ord(char) <= 32 or ord(char) == 127 for char in url):
            return True
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").rstrip(".").lower()
            port = parsed.port  # also validates malformed/out-of-range ports
        except ValueError:
            return True  # treat unparseable URLs as unsafe

        if parsed.scheme not in ("http", "https") or port == 0:
            return True

        if not host or parsed.username is not None or parsed.password is not None:
            return True
        # Percent-encoded hosts and IPv6 scope IDs introduce parser ambiguity.
        if "%" in host:
            return True
        if host.endswith((".local", ".internal")):
            return True

        # Hostname-based patterns (localhost etc.).
        for pattern in _PRIVATE_HOST_PATTERNS:
            if pattern.match(host):
                return True

        # Try IP-based detection for literal addresses.
        try:
            return not BrowserService._is_public_address(host)
        except ValueError:
            # Validate IDNA names conservatively; no search-domain shortnames.
            try:
                ascii_host = host.encode("idna").decode("ascii")
            except UnicodeError:
                return True
            labels = ascii_host.split(".")
            if len(labels) < 2 or len(ascii_host) > 253:
                return True
            if any(not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                   for label in labels):
                return True
        return False

    async def _check_request_url_safe(self, url: str) -> Optional[str]:
        """Fail closed unless ALL locally resolved addresses are public.

        Resolution is deliberately not cached here. Browser/proxy DNS may
        differ or change between check and connect; enforce egress separately.
        """
        error = self._check_url_safe(url)
        if error:
            return error
        parsed = urlparse(url)
        host = (parsed.hostname or "").rstrip(".")
        try:
            ipaddress.ip_address(host)
            return None  # literal already checked by _check_url_safe
        except ValueError:
            pass
        try:
            addresses = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(
                    host.encode("idna").decode("ascii"),
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                ),
                timeout=_DNS_TIMEOUT_SECONDS,
            )
            if not addresses or any(
                not self._is_public_address(info[4][0]) for info in addresses
            ):
                return "Blocked request: destination is not a public address."
        except (OSError, ValueError, UnicodeError, asyncio.TimeoutError):
            return "Blocked request: destination could not be safely resolved."
        return None

    async def _route_request(self, route: Any) -> None:
        """Check each intercepted HTTP request, including frames/subresources.

        Playwright routing is not complete network mediation (in particular,
        redirect chains and WebSockets must not be assumed to be covered).
        """
        try:
            error = await self._check_request_url_safe(route.request.url)
            if error:
                await route.abort("blockedbyclient")
            else:
                await route.continue_()
        except Exception:
            logger.warning("Browser request guard failed; blocking request.")
            try:
                await route.abort("blockedbyclient")
            except Exception:
                logger.warning("Could not abort browser request (page may be closed).")

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
            return "Blocked URL: only unambiguous public HTTP(S) destinations are allowed."
        return None

    # ------------------------------------------------------------------
    # Public automation API
    # ------------------------------------------------------------------

    async def navigate(self, url: str) -> dict[str, Any]:
        """Navigate to *url* and return page metadata.

        Returns a dict with ``title``, ``url``, and ``text_content`` (first
        ``_MAX_TEXT_CHARS`` characters of visible text).
        """
        err = await self._check_request_url_safe(url)
        if err:
            return {"error": err}

        await self._ensure_started()
        assert self.page is not None

        async with self._lock:
            await self._rate_limit()
            try:
                await self.page.goto(url, wait_until="domcontentloaded")
            except Exception:
                logger.warning("Browser navigation failed.")
                return {"error": "Navigation failed or was blocked by the browser request guard."}

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
            err = await self._check_request_url_safe(url)
            if err:
                raise ValueError(err)
            await self._ensure_started()
            assert self.page is not None
            async with self._lock:
                await self._rate_limit()
                try:
                    await self.page.goto(url, wait_until="domcontentloaded")
                except Exception:
                    logger.warning("Screenshot navigation failed.")
                    raise RuntimeError("Screenshot navigation failed or was blocked.") from None
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
        except Exception:
            logger.warning("Browser click failed.")
            return {"success": False, "error": "Browser click failed."}

    async def type_text(self, selector: str, text: str) -> dict[str, Any]:
        """Type *text* into the element matching *selector* (CSS).

        Returns ``{"success": bool, "error": str | None}``.
        """
        await self._ensure_started()
        assert self.page is not None
        try:
            await self.page.fill(selector, text, timeout=self._nav_timeout_ms)
            return {"success": True, "error": None}
        except Exception:
            logger.warning("Browser text entry failed.")
            return {"success": False, "error": "Browser text entry failed."}

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
            except Exception:
                logger.warning("Browser text extraction failed.")
                result[name] = ""
        return result

    async def execute_js(self, script: str) -> Any:
        """Run *script* (JavaScript) in the page context and return the result."""
        await self._ensure_started()
        assert self.page is not None
        try:
            return await self.page.evaluate(script)
        except Exception:
            logger.warning("JavaScript execution failed.")
            return {"error": "JavaScript execution failed."}

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
