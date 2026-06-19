"""
AI Companion – Specialised Agents
==================================
Specialised agent classes used for multi-agent orchestration.  Each agent
wraps a focused system prompt and a curated subset of the tools defined in
:mod:`app.tools`, then drives an OpenRouter chat completion (non-streaming)
with automatic tool-call looping until a final textual answer is produced.

Agents
------
* :class:`BaseAgent`     – Shared OpenRouter client + tool-calling loop.
* :class:`ResearchAgent` – Web research (``web_search`` + ``read_webpage``).
* :class:`WriterAgent`   – Document writing / formatting (``generate_pdf``).
* :class:`CodeAgent`     – Code generation / execution (``execute_code``).
* :class:`AnalysisAgent` – Data analysis (``execute_code`` + ``web_search``).

All agents follow the same conventions as :class:`~app.llm.LLMService`:
configuration is pulled from :func:`app.config.get_settings`, the
``openai`` async SDK is used to talk to OpenRouter, and tool dispatch is
delegated to the ``TOOLS_SCHEMA`` / ``TOOL_DISPATCH`` mappings exported by
:mod:`app.tools`.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import openai

from app.config import get_settings
from app.tools import TOOLS_SCHEMA, TOOL_DISPATCH

logger = logging.getLogger(__name__)

# Maximum number of tool-call round trips before we force a stop.  This guards
# against models that get stuck in a tool-calling loop.
_MAX_TOOL_ROUNDS = 8


def _filter_tool_schema(tool_names: list[str]) -> list[dict[str, Any]]:
    """Return only the entries from ``TOOLS_SCHEMA`` whose function name is
    in *tool_names*."""
    wanted = set(tool_names)
    return [
        entry for entry in TOOLS_SCHEMA
        if entry.get("function", {}).get("name") in wanted
    ]


class BaseAgent:
    """Base class for all specialised agents.

    Subclasses customise :attr:`name`, :attr:`description`,
    :attr:`system_prompt`, and :attr:`tool_names`; everything else is handled
    by :meth:`run`.
    """

    #: Human-readable identifier for this agent.
    name: str = "base"
    #: Short description of the agent's role (useful for orchestrator prompts).
    description: str = "A generic AI agent."
    #: System prompt steering the agent's behaviour.
    system_prompt: str = "You are a helpful AI assistant."
    #: Names of tools (from ``app.tools``) this agent is permitted to call.
    tool_names: list[str] = []

    def __init__(self) -> None:
        settings = get_settings()
        self._client = openai.AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        self._model = settings.LLM_MODEL
        self._tools_schema = _filter_tool_schema(self.tool_names)
        logger.info(
            "Agent '%s' initialised – model=%s, tools=%s",
            self.name,
            self._model,
            self.tool_names,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, message: str, context: str = "") -> str:
        """Run the agent on *message*, optionally seeded with *context*.

        The agent drives a non-streaming chat completion with tool calling.
        Tool calls are executed and fed back into the conversation, looping
        until the model produces a final textual response (or the
        :data:`_MAX_TOOL_ROUNDS` safety limit is reached).

        Parameters
        ----------
        message:
            The user-facing instruction / question for this agent.
        context:
            Optional supporting context (e.g. prior agent output, retrieved
            data) prepended to the user message.

        Returns
        -------
        str
            The full final response text from the agent.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        user_content = f"{context}\n\n{message}".strip() if context else message
        messages.append({"role": "user", "content": user_content})

        create_kwargs: dict[str, Any] = dict(
            model=self._model,
            messages=messages,
            max_tokens=4096,
            temperature=0.7,
        )
        if self._tools_schema:
            create_kwargs["tools"] = self._tools_schema

        for round_idx in range(_MAX_TOOL_ROUNDS):
            try:
                response = await self._client.chat.completions.create(
                    **create_kwargs
                )
            except Exception:
                logger.exception(
                    "Agent '%s' completion failed on round %d.", self.name, round_idx
                )
                return "[Error: agent completion failed.]"

            choice = response.choices[0]
            assistant_msg = choice.message

            # If the model finished with tool calls, execute them and loop.
            tool_calls = getattr(assistant_msg, "tool_calls", None)
            if tool_calls:
                # Record the assistant's tool-call message.
                messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )

                for tc in tool_calls:
                    func_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        logger.warning(
                            "Agent '%s' received malformed tool args for %s: %s",
                            self.name,
                            func_name,
                            tc.function.arguments,
                        )
                        args = {}

                    handler = TOOL_DISPATCH.get(func_name)
                    if handler is None:
                        result_str = json.dumps(
                            {"error": f"Unknown tool: {func_name}"}
                        )
                        logger.warning(
                            "Agent '%s' attempted unknown tool '%s'.",
                            self.name,
                            func_name,
                        )
                    else:
                        try:
                            result = await handler(**args)
                            result_str = json.dumps(result, default=str)
                        except Exception as exc:
                            logger.exception(
                                "Agent '%s' tool '%s' raised an exception.",
                                self.name,
                                func_name,
                            )
                            result_str = json.dumps({"error": str(exc)})

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_str,
                        }
                    )

                # Refresh messages for the next round; keep other kwargs.
                create_kwargs["messages"] = messages
                logger.debug(
                    "Agent '%s' round %d executed %d tool call(s).",
                    self.name,
                    round_idx,
                    len(tool_calls),
                )
                continue

            # No tool calls → we have the final answer.
            final_text = assistant_msg.content or ""
            logger.debug(
                "Agent '%s' finished after %d round(s).", self.name, round_idx
            )
            return final_text

        # Safety valve: ran out of rounds.
        logger.warning(
            "Agent '%s' hit the %d-round tool-call limit; returning last response.",
            self.name,
            _MAX_TOOL_ROUNDS,
        )
        try:
            # Ask the model (no tools this time) to summarise whatever it has.
            summary_response = await self._client.chat.completions.create(
                model=self._model,
                messages=create_kwargs["messages"],
                max_tokens=4096,
                temperature=0.7,
            )
            return summary_response.choices[0].message.content or ""
        except Exception:
            logger.exception("Agent '%s' fallback summary also failed.", self.name)
            return "[Error: agent exceeded tool-call round limit.]"


# =========================================================================
# Specialised agents
# =========================================================================


class ResearchAgent(BaseAgent):
    """Agent specialised in web research.

    Equipped with ``web_search`` and ``read_webpage`` so it can discover and
    ingest up-to-date information from the internet, then synthesise it into
    a concise, well-cited answer.
    """

    name = "research"
    description = (
        "Researches topics on the web using search engines and webpage "
        "extraction, then synthesises findings into a clear, cited summary."
    )
    tool_names = ["web_search", "read_webpage"]
    system_prompt = (
        "You are the Research Agent for the AI Companion system.\n"
        "Your job is to find accurate, up-to-date information on the web.\n\n"
        "Workflow:\n"
        "1. Use `web_search` to find relevant sources for the query.\n"
        "2. Use `read_webpage` to extract the full text of the most "
        "promising results.\n"
        "3. Cross-check facts across multiple sources when possible.\n"
        "4. Synthesise the findings into a clear, concise answer.\n\n"
        "Rules:\n"
        "- Always cite sources by URL when you use information from them.\n"
        "- Prefer primary and reputable sources over aggregators.\n"
        "- If you cannot find a reliable answer, say so explicitly rather "
        "than guessing.\n"
        "- Stay focused on the research task; do not attempt to write code "
        "or generate documents."
    )


class WriterAgent(BaseAgent):
    """Agent specialised in document writing and formatting.

    Equipped with ``generate_pdf`` so it can produce polished, downloadable
    documents from prose content.
    """

    name = "writer"
    description = (
        "Drafts and formats written documents, rendering the final output "
        "as a PDF when requested."
    )
    tool_names = ["generate_pdf"]
    system_prompt = (
        "You are the Writer Agent for the AI Companion system.\n"
        "Your job is to produce well-structured, polished written content "
        "and, when appropriate, render it as a PDF.\n\n"
        "Workflow:\n"
        "1. Understand the writing request and the intended audience.\n"
        "2. Draft clear, well-organised prose with appropriate headings and "
        "paragraph breaks (use blank lines between paragraphs).\n"
        "3. When the user asks for a document or a PDF, call `generate_pdf` "
        "with the final text content.\n"
        "4. Report the resulting file path to the user.\n\n"
        "Rules:\n"
        "- Match the requested tone and format (report, letter, article, …).\n"
        "- Keep paragraphs separated by blank lines for clean PDF rendering.\n"
        "- Do not invent facts; if research is needed, defer to the Research "
        "Agent rather than guessing."
    )


class CodeAgent(BaseAgent):
    """Agent specialised in code generation and execution.

    Equipped with ``execute_code`` so it can write, run, and iterate on
    code inside the sandbox.
    """

    name = "code"
    description = (
        "Writes, executes, and iterates on code (Python or JavaScript) "
        "inside a sandbox to solve programming tasks."
    )
    tool_names = ["execute_code"]
    system_prompt = (
        "You are the Code Agent for the AI Companion system.\n"
        "Your job is to write, run, and debug code.\n\n"
        "Workflow:\n"
        "1. Analyse the programming task and plan your approach.\n"
        "2. Write clean, well-commented code (Python or JavaScript).\n"
        "3. Use `execute_code` to run it in the sandbox.\n"
        "4. Inspect stdout, stderr, and the result; iterate until it works.\n"
        "5. Explain the final solution and its output.\n\n"
        "Rules:\n"
        "- Always verify code by executing it before declaring success.\n"
        "- Prefer simple, readable solutions over clever ones.\n"
        "- Handle errors gracefully and report them honestly.\n"
        "- Do not perform web research or write documents; stay focused on "
        "code."
    )


class AnalysisAgent(BaseAgent):
    """Agent specialised in data analysis.

    Equipped with ``execute_code`` (for numerical / data work) and
    ``web_search`` (to pull in reference data or definitions), letting it
    reason about datasets and produce quantitative insights.
    """

    name = "analysis"
    description = (
        "Analyses data using sandboxed code execution and targeted web "
        "lookups, producing quantitative insights and summaries."
    )
    tool_names = ["execute_code", "web_search"]
    system_prompt = (
        "You are the Analysis Agent for the AI Companion system.\n"
        "Your job is to analyse data and produce clear, quantitative "
        "insights.\n\n"
        "Workflow:\n"
        "1. Clarify the analytical question and identify the data needed.\n"
        "2. Use `web_search` to gather reference data, definitions, or "
        "context when the information is not already provided.\n"
        "3. Use `execute_code` to perform calculations, statistics, or data "
        "transformations.\n"
        "4. Interpret the results and present them with clear reasoning.\n\n"
        "Rules:\n"
        "- Show your work: include the key computations and their outputs.\n"
        "- Distinguish clearly between what the data shows and your "
        "interpretation.\n"
        "- Flag uncertainty and assumptions explicitly.\n"
        "- Do not write documents or debug arbitrary code; stay focused on "
        "analysis."
    )


#: Convenience registry for orchestrators that need to look up agents by name.
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    ResearchAgent.name: ResearchAgent,
    WriterAgent.name: WriterAgent,
    CodeAgent.name: CodeAgent,
    AnalysisAgent.name: AnalysisAgent,
}


def get_agent(name: str) -> BaseAgent:
    """Instantiate and return the agent registered under *name*.

    Raises :class:`KeyError` if no agent with that name is registered.
    """
    if name not in AGENT_REGISTRY:
        raise KeyError(
            f"No agent registered with name '{name}'. "
            f"Available: {list(AGENT_REGISTRY)}"
        )
    return AGENT_REGISTRY[name]()
