"""
AI Companion â€“ LLM Service
============================
Manages all chat-completion interactions via the OpenRouter API using the
``openai`` async SDK.

Key responsibilities
--------------------
* Build the full ``messages`` array (system prompt + memory context + recent
  history + current user turn, with optional vision content).
* Stream tokens back as an async generator.
* Persist both user and assistant messages to the database and long-term
  memory after completion.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Optional

import openai

from app.config import get_settings
from app.database import add_message, get_character, get_messages
from app.memory import MemoryManager
from app.tools import TOOLS_SCHEMA, TOOL_DISPATCH

logger = logging.getLogger(__name__)


def get_skill_manager():
    """Lazily get the global SkillManager instance (initialised in lifespan)."""
    from app.main import skill_manager
    return skill_manager


class LLMService:
    """High-level chat service backed by OpenRouter."""

    def __init__(self, memory: MemoryManager) -> None:
        settings = get_settings()
        self._client = openai.AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        self._model = settings.LLM_MODEL
        self._memory = memory
        logger.info("LLMService initialised â€“ model=%s", self._model)

    # ------------------------------------------------------------------
    # Message-array builder
    # ------------------------------------------------------------------

    @staticmethod
    def build_messages(
        character: dict[str, Any],
        recent_messages: list[dict[str, Any]],
        memories: list[dict[str, Any]],
        user_message: str,
        image_url: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Assemble the full ``messages`` list for an OpenAI chat completion.

        Parameters
        ----------
        character:
            Row dict from the ``characters`` table.
        recent_messages:
            Recent conversation history rows.
        memories:
            Recalled long-term memories (``text`` key).
        user_message:
            The current user turn.
        image_url:
            Optional image URL / base64 for vision.

        Returns
        -------
        list[dict] suitable for ``client.chat.completions.create(messages=â€¦)``.
        """
        messages: list[dict[str, Any]] = []

        # 1 â”€ System prompt
        system_text = character.get("system_prompt", "You are a helpful assistant.")
        if memories:
            memory_block = "\n".join(
                f"- {m['text']}" for m in memories if m.get("text")
            )
            system_text += (
                "\n\n## Relevant memories from past conversations\n"
                f"{memory_block}"
            )
        messages.append({"role": "system", "content": system_text})

        # 2 â”€ Recent conversation history
        for msg in recent_messages:
            entry: dict[str, Any] = {
                "role": msg["role"],
                "content": msg["content"],
            }
            messages.append(entry)

        # 3 â”€ Current user turn
        if image_url:
            content: list[dict[str, Any]] = [
                {"type": "text", "text": user_message},
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                },
            ]
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_message})

        return messages

    # ------------------------------------------------------------------
    # Streaming chat
    # ------------------------------------------------------------------

    async def stream_chat(
        self,
        character_id: int,
        message: str,
        image_url: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Async generator that yields text chunks from a streaming completion.

        After the stream finishes, the user message and the full assistant
        response are persisted to the database and embedded into long-term
        memory.
        """
        # Fetch character data.
        character = await get_character(character_id)
        if character is None:
            yield "[Error: character not found]"
            return

        # Retrieve recent messages for context.
        recent = await get_messages(character_id, limit=50)

        # Recall relevant memories.
        memories: list[dict[str, Any]] = []
        try:
            memories = await self._memory.recall(character_id, message, top_k=5)
        except Exception:
            logger.warning("Memory recall failed â€“ proceeding without.", exc_info=True)

        # Build the full prompt.
        messages = self.build_messages(
            character, recent, memories, message, image_url
        )

        # Start streaming.
        full_response = ""
        try:
            # Skip tools for vision requests (some models don't support both)
            # Merge built-in tools with skill tools
            all_tools = list(TOOLS_SCHEMA)
            sm = get_skill_manager()
            if sm:
                try:
                    skill_tools = sm.get_tools_schema()
                    all_tools.extend(skill_tools)
                except Exception:
                    logger.warning("Failed to get skill tools schema.", exc_info=True)

            create_kwargs = dict(
                model=self._model,
                messages=messages,
                stream=True,
            )
            if not image_url:
                create_kwargs["tools"] = all_tools
            stream = await self._client.chat.completions.create(**create_kwargs,
                max_tokens=4096,
                temperature=0.7,
            )

            tool_calls_accum: dict[int, dict] = {}

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                # --- Handle tool calls ---
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_accum:
                            tool_calls_accum[idx] = {
                                "id": tc.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.function:
                            if tc.function.name:
                                tool_calls_accum[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_accum[idx]["arguments"] += tc.function.arguments

                # --- Handle content ---
                if delta.content:
                    full_response += delta.content
                    yield delta.content

                # --- Finish reason ---
                finish = chunk.choices[0].finish_reason if chunk.choices else None
                if finish == "tool_calls" and tool_calls_accum:
                    # Execute accumulated tool calls, then continue the conversation.
                    async for text in self._handle_tool_calls(
                        messages, tool_calls_accum
                    ):
                        full_response += text
                        yield text

        except Exception:
            logger.exception("Streaming completion failed.")
            error_msg = "[Error: LLM request failed. Please try again.]"
            yield error_msg
            full_response += error_msg

        # Persist messages.
        await add_message(character_id, "user", message, image_url)
        if full_response:
            await add_message(character_id, "assistant", full_response)

        # Embed into long-term memory.
        try:
            exchange = f"User: {message}\nAssistant: {full_response}"
            await self._memory.store(character_id, exchange)
        except Exception:
            logger.warning("Memory store failed.", exc_info=True)

    # ------------------------------------------------------------------
    # Tool-call handling
    # ------------------------------------------------------------------

    async def _handle_tool_calls(
        self,
        messages: list[dict[str, Any]],
        tool_calls: dict[int, dict],
    ) -> AsyncGenerator[str, None]:
        """Execute tool calls, feed results back, and continue generation."""
        # Build the assistant message with tool_calls.
        tc_list = []
        for idx in sorted(tool_calls.keys()):
            tc = tool_calls[idx]
            tc_list.append(
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
            )
        messages.append({"role": "assistant", "content": None, "tool_calls": tc_list})

        # Execute each tool and append result messages.
        for tc in tc_list:
            func_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}

            handler = TOOL_DISPATCH.get(func_name)
            if handler:
                try:
                    result = await handler(**args)
                    result_str = json.dumps(result, default=str)
                except Exception as exc:
                    result_str = json.dumps({"error": str(exc)})
            else:
                # Check if it's a skill tool
                sm = get_skill_manager()
                if sm and sm.loaded_skills:
                    # Try to find which skill owns this function
                    found = False
                    for skill_name, skill_info in sm.loaded_skills.items():
                        if func_name in skill_info.get("functions", {}):
                            try:
                                result = await sm.execute(skill_name, func_name, args)
                                result_str = json.dumps(result, default=str)
                                found = True
                            except Exception as exc:
                                result_str = json.dumps({"error": str(exc)})
                            break
                    if not found:
                        result_str = json.dumps({"error": f"Unknown tool: {func_name}"})
                else:
                    result_str = json.dumps({"error": f"Unknown tool: {func_name}"})

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str,
                }
            )

        # Continue completion with tool results.
        try:
            follow_up = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
                max_tokens=4096,
                temperature=0.7,
            )
            async for chunk in follow_up:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception:
            logger.exception("Follow-up completion after tool calls failed.")
            yield "[Error during tool result processing]"
