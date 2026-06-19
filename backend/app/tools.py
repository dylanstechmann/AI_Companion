"""
AI Companion – Tool Functions (LLM Function-Calling)
=====================================================
Each tool is an ``async`` function that can be invoked by the LLM via
OpenAI-compatible function calling.  ``TOOLS_SCHEMA`` exports the JSON
schema array expected by the ``tools`` parameter of a chat completion.

Tools
-----
* ``web_search``     – Tavily search (or httpx fallback).
* ``read_webpage``   – Fetch & extract text from a URL.
* ``execute_code``   – Delegate to :class:`~app.sandbox.CodeSandbox`.
* ``generate_pdf``   – Render HTML → PDF via ReportLab.
* ``send_email``     – SMTP email (placeholder config).
* ``recall_memory``  – Query a character's ChromaDB collection.
"""

from __future__ import annotations

import asyncio
import email.mime.application
import email.mime.multipart
import email.mime.text
import io
import logging
import os
import smtplib
import time
from collections import defaultdict
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.config import get_settings

logger = logging.getLogger(__name__)

# Per-domain rate-limiting tracker: domain → last_request_time
_domain_last_hit: dict[str, float] = defaultdict(float)


# =========================================================================
# Tool implementations
# =========================================================================

async def web_search(query: str) -> list[dict[str, str]]:
    """Search the web for *query*.

    Uses the **Tavily API** when a key is available; otherwise falls back to
    a simple DuckDuckGo HTML scrape via ``httpx``.

    Returns a list of ``{"title", "url", "snippet"}`` dicts.
    """
    settings = get_settings()

    # --- Tavily path -------------------------------------------------------
    if settings.TAVILY_API_KEY:
        try:
            from tavily import AsyncTavilyClient

            client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)
            response = await client.search(query=query, max_results=5)
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                }
                for r in response.get("results", [])
            ]
        except Exception:
            logger.exception("Tavily search failed – falling through to httpx.")

    # --- httpx fallback (DuckDuckGo lite) -----------------------------------
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15
        ) as client:
            resp = await client.get(
                "https://lite.duckduckgo.com/lite",
                params={"q": query},
                headers={"User-Agent": "AI-Companion/1.0"},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            results: list[dict[str, str]] = []
            for a_tag in soup.select("a.result-link")[:5]:
                results.append(
                    {
                        "title": a_tag.get_text(strip=True),
                        "url": a_tag.get("href", ""),
                        "snippet": "",
                    }
                )
            return results if results else [{"title": "No results", "url": "", "snippet": ""}]
    except Exception:
        logger.exception("httpx fallback search failed.")
        return [{"title": "Search error", "url": "", "snippet": "Search unavailable."}]


async def read_webpage(url: str) -> str:
    """Fetch *url* and return extracted text content.

    Respects ``CRAWL_DELAY_SECONDS`` per domain.  Falls through to a
    proxy if one is configured and the direct fetch fails.
    """
    settings = get_settings()
    domain = urlparse(url).netloc

    # Rate-limit per domain.
    since = time.time() - _domain_last_hit[domain]
    if since < settings.CRAWL_DELAY_SECONDS:
        await asyncio.sleep(settings.CRAWL_DELAY_SECONDS - since)
    _domain_last_hit[domain] = time.time()

    headers = {"User-Agent": "AI-Companion/1.0 (research)"}

    async def _fetch(use_proxy: bool = False) -> str:
        transport = None
        if use_proxy and settings.PROXY_URL:
            transport = httpx.AsyncHTTPTransport(proxy=settings.PROXY_URL)
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=20, transport=transport
        ) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # Remove script / style tags.
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            # Truncate to ~8 000 chars to fit context windows.
            return text[:8000]

    try:
        return await _fetch()
    except Exception:
        if settings.PROXY_URL:
            logger.warning("Direct fetch failed for %s – trying proxy.", url)
            try:
                return await _fetch(use_proxy=True)
            except Exception:
                logger.exception("Proxy fetch also failed for %s.", url)
        return f"[Error fetching {url}]"


async def execute_code(language: str, code: str) -> dict:
    """Execute code via the sandbox service."""
    from app.sandbox import CodeSandbox

    sandbox = CodeSandbox()
    return await sandbox.execute(language, code)


async def generate_pdf(html_content: str, output_path: Optional[str] = None) -> str:
    """Render *html_content* (plain text accepted too) into a PDF file.

    Returns the absolute path to the generated PDF.
    """
    if output_path is None:
        import tempfile
        fd, output_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontSize=11,
        leading=15,
        spaceAfter=8,
    )

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    story = []
    for para in html_content.split("\n\n"):
        para = para.strip()
        if para:
            # Escape XML-special chars that ReportLab's Paragraph chokes on.
            safe = (
                para.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(safe, body_style))
            story.append(Spacer(1, 6))

    doc.build(story)
    logger.info("Generated PDF at %s", output_path)
    return output_path


async def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: Optional[list[str]] = None,
) -> dict:
    """Send an email via SMTP.

    ``attachments`` is a list of file paths.  Uses placeholder SMTP config
    from settings – will need real credentials in production.
    """
    settings = get_settings()
    if not settings.SMTP_HOST:
        return {"success": False, "error": "SMTP not configured."}

    try:
        msg = email.mime.multipart.MIMEMultipart()
        msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(email.mime.text.MIMEText(body, "plain"))

        for path in attachments or []:
            with open(path, "rb") as f:
                part = email.mime.application.MIMEApplication(f.read())
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=os.path.basename(path),
                )
                msg.attach(part)

        # Run blocking SMTP in a thread.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _smtp_send, settings, msg)
        return {"success": True}
    except Exception as exc:
        logger.exception("Email send failed.")
        return {"success": False, "error": str(exc)}


def _smtp_send(settings, msg) -> None:
    """Blocking SMTP send helper."""
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


async def recall_memory(character_id: int, query: str) -> list[dict]:
    """Recall memories from a character's long-term store."""
    from app.memory import MemoryManager

    mm = MemoryManager()
    return await mm.recall(character_id, query)


# =========================================================================
# Browser automation tools (Phase 3)
# =========================================================================

async def browse_webpage(url: str) -> dict:
    """Navigate to a URL and return page content + metadata."""
    from app.browser import BrowserService

    bs = BrowserService()
    return await bs.navigate(url)


async def take_screenshot(url: Optional[str] = None) -> dict:
    """Take a screenshot of the current page (or navigate to url first)."""
    import base64

    from app.browser import BrowserService

    bs = BrowserService()
    png_bytes = await bs.screenshot(url)
    return {
        "screenshot_base64": base64.b64encode(png_bytes).decode(),
        "mime_type": "image/png",
    }


async def click_element(selector: str) -> dict:
    """Click an element on the current page by CSS selector."""
    from app.browser import BrowserService

    bs = BrowserService()
    return await bs.click(selector)


async def fill_web_form(url: str, form_data: dict) -> dict:
    """Navigate to a URL and fill form fields."""
    from app.browser import BrowserService

    bs = BrowserService()
    return await bs.fill_form(url, form_data)


# =========================================================================
# OpenAI-compatible function-calling schema
# =========================================================================

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the internet for current information on a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": "Fetch and extract text content from a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to fetch.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "Execute Python or JavaScript code in a sandboxed environment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "enum": ["python", "javascript"],
                        "description": "Programming language.",
                    },
                    "code": {
                        "type": "string",
                        "description": "Source code to execute.",
                    },
                },
                "required": ["language", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_pdf",
            "description": "Generate a PDF document from text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html_content": {
                        "type": "string",
                        "description": "The text/HTML content to render as PDF.",
                    },
                },
                "required": ["html_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email with optional attachments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body text.",
                    },
                    "attachments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of file paths to attach.",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Search the character's long-term memory for relevant past conversations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {
                        "type": "integer",
                        "description": "The character whose memory to search.",
                    },
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                },
                "required": ["character_id", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_webpage",
            "description": "Navigate to a URL in a headless browser and return the page title, URL, and text content. Useful for JavaScript-rendered pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to navigate to.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Take a screenshot of the current browser page (or navigate to a URL first). Returns a base64-encoded PNG image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Optional URL to navigate to before taking the screenshot.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Click an element on the current browser page by CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the element to click.",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill_web_form",
            "description": "Navigate to a URL and fill form fields with the given data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the page containing the form.",
                    },
                    "form_data": {
                        "type": "object",
                        "description": "Map of CSS selectors to values to fill in.",
                    },
                },
                "required": ["url", "form_data"],
            },
        },
    },
]


# Lookup map for dispatching tool calls by name.
TOOL_DISPATCH: dict[str, Any] = {
    "web_search": web_search,
    "read_webpage": read_webpage,
    "execute_code": execute_code,
    "generate_pdf": generate_pdf,
    "send_email": send_email,
    "recall_memory": recall_memory,
    "browse_webpage": browse_webpage,
    "take_screenshot": take_screenshot,
    "click_element": click_element,
    "fill_web_form": fill_web_form,
}
