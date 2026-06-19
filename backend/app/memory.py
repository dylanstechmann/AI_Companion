"""
AI Companion – Long-Term Memory (ChromaDB)
===========================================
Each character gets its own ChromaDB collection so memories stay isolated.

Embedding is performed via the OpenRouter ``/embeddings`` endpoint (same
``openai`` SDK, different ``base_url``).  The class exposes three public
methods:

* ``store``  – add a text + optional metadata to a character's memory.
* ``recall`` – retrieve the top-*k* semantically similar memories.
* ``search`` – public wrapper used by the ``/api/memory/search`` route.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Optional

import chromadb
import openai

from app.config import get_settings

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages per-character vector memory via ChromaDB."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self._oai = openai.AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        self._embedding_model = settings.EMBEDDING_MODEL
        logger.info(
            "MemoryManager initialised – persist_dir=%s, model=%s",
            settings.CHROMA_PERSIST_DIR,
            self._embedding_model,
        )

    # ------------------------------------------------------------------
    # Collection helpers
    # ------------------------------------------------------------------

    def get_or_create_collection(self, character_id: int) -> chromadb.Collection:
        """Return (or create) the ChromaDB collection for *character_id*."""
        name = f"character_{character_id}"
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        """Get embedding vectors from the configured model."""
        response = await self._oai.embeddings.create(
            model=self._embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store(
        self,
        character_id: int,
        text: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Embed *text* and persist it in the character's collection."""
        if not text or not text.strip():
            return

        collection = self.get_or_create_collection(character_id)
        embeddings = await self._embed([text])

        # Deterministic ID based on content + timestamp for dedup safety.
        doc_id = hashlib.sha256(
            f"{character_id}:{text}:{time.time()}".encode()
        ).hexdigest()[:24]

        meta = {"character_id": character_id, "stored_at": time.time()}
        if metadata:
            meta.update(metadata)

        collection.add(
            ids=[doc_id],
            embeddings=embeddings,
            documents=[text],
            metadatas=[meta],
        )
        logger.debug("Stored memory for character %d (id=%s).", character_id, doc_id)

    async def recall(
        self,
        character_id: int,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return up to *top_k* memories most relevant to *query*."""
        collection = self.get_or_create_collection(character_id)

        if collection.count() == 0:
            return []

        embeddings = await self._embed([query])
        results = collection.query(
            query_embeddings=embeddings,
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        memories: list[dict[str, Any]] = []
        if results and results.get("documents"):
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                memories.append(
                    {"text": doc, "metadata": meta, "distance": dist}
                )
        return memories

    async def search(
        self,
        character_id: int,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Public search endpoint wrapper – delegates to ``recall``."""
        return await self.recall(character_id, query, top_k)

    # ------------------------------------------------------------------
    # Health check helper
    # ------------------------------------------------------------------

    def status(self) -> str:
        """Return a short string describing ChromaDB health."""
        try:
            heartbeat = self._client.heartbeat()
            return "ok" if heartbeat else "degraded"
        except Exception:
            logger.exception("ChromaDB health check failed.")
            return "error"
