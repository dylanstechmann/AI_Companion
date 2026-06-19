"""
AI Companion – Deep Research Agent
====================================
Orchestrates a multi-step research pipeline:

1. **Query expansion** – LLM generates targeted search queries from the
   user's broad research request.
2. **Search**          – Each query is sent to Tavily (or httpx fallback).
3. **Deep read**       – The top URLs are fetched with per-domain rate
   limiting (direct → optional proxy).
4. **Synthesis**       – LLM distils all collected information into a
   comprehensive, structured report.
5. **PDF generation**  – The report is rendered to PDF.
6. **Email (optional)** – The PDF is emailed to the user.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Optional

import openai

from app.config import get_settings
from app.tools import generate_pdf, read_webpage, send_email, web_search

logger = logging.getLogger(__name__)


class ResearchAgent:
    """Run a full deep-research pipeline asynchronously."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = openai.AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        self._model = settings.LLM_MODEL

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate_queries(self, research_request: str) -> list[str]:
        """Ask the LLM to decompose the research request into search queries."""
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a research assistant. Given a research request, "
                        "generate 3–5 specific web-search queries that would help "
                        "gather comprehensive information. Return ONLY a JSON array "
                        "of query strings, nothing else."
                    ),
                },
                {"role": "user", "content": research_request},
            ],
            temperature=0.4,
            max_tokens=512,
        )

        raw = resp.choices[0].message.content or "[]"
        # Strip markdown fences if the model wraps them.
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        try:
            queries = json.loads(raw)
            if isinstance(queries, list):
                return [str(q) for q in queries][:5]
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON queries: %s", raw)

        # Fallback: use the original request as the single query.
        return [research_request]

    async def _synthesise(
        self,
        research_request: str,
        gathered: list[dict],
    ) -> str:
        """Synthesise all gathered material into a long-form report."""
        context_block = "\n\n---\n\n".join(
            f"**Source:** {g.get('url', 'N/A')}\n{g.get('content', '')}"
            for g in gathered
        )[:60_000]  # Stay within context limits.

        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert research analyst. Using the provided "
                        "source material, write a comprehensive, well-structured "
                        "report that answers the user's research question. Include "
                        "key findings, supporting evidence, and cite sources by URL. "
                        "Use clear section headings and bullet points where helpful."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"## Research Question\n{research_request}\n\n"
                        f"## Source Material\n{context_block}"
                    ),
                },
            ],
            temperature=0.5,
            max_tokens=4096,
        )
        return resp.choices[0].message.content or "[No report generated]"

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    async def run(
        self,
        query: str,
        email_to: Optional[str] = None,
    ) -> dict:
        """Execute the full research pipeline.

        Parameters
        ----------
        query:
            The user's research question / topic.
        email_to:
            Optional email address – if set, the PDF report will be sent.

        Returns
        -------
        dict with ``report`` (str) and ``pdf_path`` (str) keys.
        """
        logger.info("Research agent started – query=%r", query)

        # Step 1 – generate search queries.
        search_queries = await self._generate_queries(query)
        logger.info("Generated %d search queries.", len(search_queries))

        # Step 2 – web search.
        all_results: list[dict] = []
        for sq in search_queries:
            try:
                results = await web_search(sq)
                all_results.extend(results)
            except Exception:
                logger.warning("Search failed for query: %s", sq, exc_info=True)

        # Deduplicate URLs.
        seen_urls: set[str] = set()
        unique_results = []
        for r in all_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)

        # Step 3 – deep read top URLs.
        gathered: list[dict] = []
        for r in unique_results[:10]:
            url = r.get("url", "")
            if not url:
                continue
            try:
                content = await read_webpage(url)
                gathered.append({"url": url, "content": content})
            except Exception:
                logger.warning("Failed to read %s", url, exc_info=True)

        # Also include snippets from search results.
        for r in unique_results:
            if r.get("snippet"):
                gathered.append(
                    {"url": r.get("url", ""), "content": r["snippet"]}
                )

        logger.info("Gathered content from %d sources.", len(gathered))

        # Step 4 – synthesise report.
        report = await self._synthesise(query, gathered)

        # Step 5 – generate PDF.
        pdf_dir = tempfile.mkdtemp(prefix="research_")
        pdf_path = os.path.join(pdf_dir, "research_report.pdf")
        await generate_pdf(report, output_path=pdf_path)

        # Step 6 – email (if requested).
        if email_to:
            await send_email(
                to=email_to,
                subject=f"Research Report: {query[:80]}",
                body="Please find your research report attached.",
                attachments=[pdf_path],
            )
            logger.info("Emailed report to %s.", email_to)

        logger.info("Research agent finished – pdf=%s", pdf_path)
        return {"report": report, "pdf_path": pdf_path}
