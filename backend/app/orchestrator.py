"""
AI Companion – Multi-Agent Orchestrator
========================================
The :class:`AgentOrchestrator` decomposes complex user requests into a set of
inter-dependent sub-tasks, dispatches each sub-task to the most appropriate
specialised agent (see :mod:`app.agents`), executes independent sub-tasks
concurrently, feeds the outputs of upstream tasks into their dependents, and
finally synthesises all agent outputs into a single coherent response.

The orchestrator is designed to be driven asynchronously and to stream
progress events to the caller (typically a FastAPI endpoint) so the UI can
render task-by-task updates in real time.

Key components
--------------
* :class:`AgentTask`         – Typed dict describing a single planned sub-task.
* :class:`AgentOrchestrator` – The orchestrator itself (plan → execute → merge).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator, TypedDict

import openai

from app.agents import AGENT_REGISTRY, BaseAgent, get_agent
from app.config import get_settings

logger = logging.getLogger(__name__)


# =========================================================================
# Type definitions
# =========================================================================

class AgentTask(TypedDict):
    """Structured description of a single sub-task produced by the planner.

    Attributes
    ----------
    id:
        Numeric task identifier (used by other tasks' ``dependencies``).
    agent:
        Name of the agent to run – one of ``"research"``, ``"writer"``,
        ``"code"``, ``"analysis"`` (keys of :data:`app.agents.AGENT_REGISTRY`).
    description:
        Short human-readable summary of what the task should accomplish.
    dependencies:
        List of task ids whose results must be available before this task
        can start.
    input:
        Context / instructions passed into the agent alongside its
        ``description``.
    """

    id: int
    agent: str
    description: str
    dependencies: list[int]
    input: str


# =========================================================================
# Orchestrator
# =========================================================================

#: Fallback task used when the planner returns an unparseable response.
_FALLBACK_SINGLE_TASK: AgentTask = {
    "id": 0,
    "agent": "research",
    "description": "Answer the user's request directly.",
    "dependencies": [],
    "input": "",
}


class AgentOrchestrator:
    """Plan, execute, and merge multi-agent workflows.

    The orchestrator owns a dedicated OpenRouter async client (used for the
    *planning* and *merging* LLM calls; sub-task execution is delegated to
    the individual :class:`~app.agents.BaseAgent` instances, which create
    their own clients).
    """

    #: System prompt instructing the LLM to act as a task planner.
    _PLANNER_SYSTEM_PROMPT = (
        "You are the Planner for a multi-agent AI Companion system.\n"
        "Your job is to decompose a complex user request into a set of "
        "sub-tasks, each assigned to one of the following specialised "
        "agents:\n\n"
        "- research: Finds accurate, up-to-date information on the web and "
        "synthesises it into a cited summary.\n"
        "- writer: Drafts and formats written documents, rendering output "
        "as a PDF when requested.\n"
        "- code: Writes, executes, and iterates on code (Python/JavaScript) "
        "in a sandbox.\n"
        "- analysis: Performs data analysis using sandboxed code execution "
        "and web lookups.\n\n"
        "Decomposition rules:\n"
        "1. Only create sub-tasks that are genuinely needed; a single task "
        "is fine for simple requests.\n"
        "2. Assign each task to the single most appropriate agent.\n"
        "3. Express ordering with dependencies (list of task ids that must "
        "complete first). Tasks with no dependencies run concurrently.\n"
        "4. The `input` field should contain any context the agent needs "
        "(it may reference prior tasks by id, but the orchestrator will "
        "automatically feed dependency results to the agent).\n\n"
        "Respond with STRICT JSON only – no markdown, no prose. The schema "
        "is:\n"
        '{"tasks": [{"id": 0, "agent": "research|writer|code|analysis", '
        '"description": "what to do", "dependencies": [list of task ids], '
        '"input": "context for the agent"}]}'
    )

    #: System prompt instructing the LLM to merge agent outputs.
    _MERGER_SYSTEM_PROMPT = (
        "You are the Merger for a multi-agent AI Companion system.\n"
        "Several specialised agents have each completed a sub-task. You are "
        "given their individual results. Synthesise them into a single, "
        "coherent, well-structured final response for the user.\n\n"
        "Rules:\n"
        "- Integrate information rather than listing agent outputs verbatim.\n"
        "- Resolve contradictions by preferring research/analysis findings.\n"
        "- Preserve any file paths or citations produced by the agents.\n"
        "- If only one agent ran, you may lightly polish its output.\n"
        "- Do not invent information that is not present in the results."
    )

    def __init__(self) -> None:
        """Create the orchestrator with its own OpenRouter async client."""
        settings = get_settings()
        self._client = openai.AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        self._model = settings.LLM_MODEL
        logger.info(
            "AgentOrchestrator initialised – model=%s, agents=%s",
            self._model,
            list(AGENT_REGISTRY),
        )

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def plan(self, user_request: str) -> list[dict]:
        """Decompose *user_request* into a list of sub-task dicts.

        Calls the LLM with a planning prompt and parses the JSON response.
        Returns a list of plain dicts shaped like :class:`AgentTask` so the
        caller can iterate / serialise them freely. Falls back to a single
        research task if the LLM response cannot be parsed.
        """
        logger.info("Planning sub-tasks for request (%d chars).", len(user_request))
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_request},
                ],
                max_tokens=2048,
                temperature=0.3,
            )
        except Exception:
            logger.exception("Planner LLM call failed; using fallback single task.")
            return [dict(_FALLBACK_SINGLE_TASK)]

        raw = response.choices[0].message.content or ""
        tasks = self._parse_plan_json(raw)

        if not tasks:
            logger.warning(
                "Planner produced no usable tasks; using fallback. Raw=%s",
                raw[:500],
            )
            return [dict(_FALLBACK_SINGLE_TASK)]

        logger.info("Planner produced %d task(s).", len(tasks))
        return tasks

    @staticmethod
    def _parse_plan_json(raw: str) -> list[dict]:
        """Extract and validate the task list from a raw LLM response.

        Tolerates responses that wrap the JSON in markdown fences or
        surround it with stray prose.
        """
        # Strip markdown code fences if present.
        fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        candidate = fence_match.group(1) if fence_match else raw

        # Fall back to the first {...} block if the whole string isn't JSON.
        if not candidate.strip().startswith("{"):
            brace_match = re.search(r"\{.*\}", candidate, re.DOTALL)
            if not brace_match:
                return []
            candidate = brace_match.group(0)

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            logger.warning("Failed to parse planner JSON: %s", candidate[:500])
            return []

        raw_tasks = data.get("tasks") if isinstance(data, dict) else None
        if not isinstance(raw_tasks, list):
            return []

        tasks: list[dict] = []
        for entry in raw_tasks:
            if not isinstance(entry, dict):
                continue
            agent_name = str(entry.get("agent", "")).strip().lower()
            if agent_name not in AGENT_REGISTRY:
                logger.warning(
                    "Planner returned unknown agent '%s'; skipping task.",
                    agent_name,
                )
                continue
            deps = entry.get("dependencies", [])
            if not isinstance(deps, list):
                deps = []
            try:
                task_id = int(entry.get("id", len(tasks)))
            except (TypeError, ValueError):
                task_id = len(tasks)
            tasks.append(
                {
                    "id": task_id,
                    "agent": agent_name,
                    "description": str(entry.get("description", "")),
                    "dependencies": [
                        int(d) for d in deps if str(d).lstrip("-").isdigit()
                    ],
                    "input": str(entry.get("input", "")),
                }
            )
        return tasks

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self, tasks: list[dict]
    ) -> AsyncGenerator[dict, None]:
        """Execute *tasks* respecting dependency ordering.

        Tasks are grouped into "levels" – each level contains all tasks
        whose dependencies have all been satisfied by previous levels.
        Tasks within a level run concurrently via :func:`asyncio.gather`.

        Progress events are yielded as dicts so callers can stream updates::

            {"type": "task_started",  "task_id": N, "agent": "research"}
            {"type": "task_output",   "task_id": N, "text": "..."}
            {"type": "task_completed", "task_id": N, "result": "..."}
            {"type": "all_completed", "results": {0: "...", 1: "..."}}

        After all tasks finish, a final ``all_completed`` event is yielded
        containing a mapping of ``{task_id: result}``.
        """
        async for event in self._execute_streaming(tasks):
            yield event

    async def _execute_streaming(
        self, tasks: list[dict]
    ) -> AsyncGenerator[dict, None]:
        """Execute tasks with live progress events, yielding each event.

        Tasks at the same dependency level run concurrently via
        :func:`asyncio.gather`; events from concurrent tasks may interleave.
        """
        results: dict[int, str] = {}
        pending: list[dict] = list(tasks)

        while pending:
            ready = [
                t for t in pending
                if all(d in results for d in t.get("dependencies", []))
            ]
            if not ready:
                logger.warning(
                    "Execution deadlock – %d task(s) have unsatisfiable "
                    "dependencies; running them anyway.",
                    len(pending),
                )
                ready = pending

            # Kick off all ready tasks concurrently. Each task pushes its
            # own events into a shared asyncio.Queue so we can stream them
            # in arrival order.
            queue: asyncio.Queue[dict] = asyncio.Queue()
            done_flag = asyncio.Event()

            async def run_one(task: dict) -> None:
                task_id = task["id"]
                agent_name = task["agent"]
                await queue.put(
                    {"type": "task_started", "task_id": task_id, "agent": agent_name}
                )
                # Build context from dependency results.
                dep_context = ""
                for dep_id in task.get("dependencies", []):
                    dep_context += (
                        f"\n\n[Result of task {dep_id}]\n"
                        f"{results.get(dep_id, '')}"
                    )
                message = task.get("description", "")
                user_input = task.get("input", "")
                full_context = "\n\n".join(
                    part for part in [user_input, dep_context.strip()] if part
                )

                try:
                    agent: BaseAgent = get_agent(agent_name)
                    await queue.put(
                        {
                            "type": "task_output",
                            "task_id": task_id,
                            "text": f"Dispatching to {agent_name} agent: {message}",
                        }
                    )
                    result_text = await agent.run(message, context=full_context)
                except Exception as exc:
                    logger.exception(
                        "Task %d (%s) failed.", task_id, agent_name
                    )
                    result_text = f"[Error: {agent_name} agent failed – {exc}]"

                results[task_id] = result_text
                await queue.put(
                    {
                        "type": "task_completed",
                        "task_id": task_id,
                        "result": result_text,
                    }
                )

            async def runner() -> None:
                await asyncio.gather(*(run_one(t) for t in ready))
                done_flag.set()

            runner_task = asyncio.create_task(runner())

            # Stream events as they arrive until all ready tasks finish.
            while not (done_flag.is_set() and queue.empty()):
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                yield event

            await runner_task
            pending = [t for t in pending if t not in ready]

        yield {"type": "all_completed", "results": dict(results)}

    # ------------------------------------------------------------------
    # Merging
    # ------------------------------------------------------------------

    async def merge_results(self, results: dict) -> str:
        """Synthesise all agent results into a single coherent response.

        Parameters
        ----------
        results:
            Mapping of ``{task_id: result_text}`` as produced by
            :meth:`execute`.
        """
        logger.info("Merging %d agent result(s).", len(results))
        if not results:
            return ""
        if len(results) == 1:
            # Single result – no synthesis needed.
            return next(iter(results.values()))

        formatted = "\n\n".join(
            f"--- Task {tid} result ---\n{text}" for tid, text in results.items()
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._MERGER_SYSTEM_PROMPT},
                    {"role": "user", "content": formatted},
                ],
                max_tokens=4096,
                temperature=0.5,
            )
            merged = response.choices[0].message.content or ""
        except Exception:
            logger.exception("Merger LLM call failed; concatenating raw results.")
            merged = "\n\n".join(results.values())
        return merged

    # ------------------------------------------------------------------
    # Convenience: full pipeline
    # ------------------------------------------------------------------

    async def run(self, user_request: str) -> AsyncGenerator[dict, None]:
        """Run the full plan → execute → merge pipeline.

        Yields a stream of events:

        * ``{"type": "plan", "tasks": [...]}``                – after planning
        * ``{"type": "task_started", ...}``                   – per task start
        * ``{"type": "task_output", ...}``                    – per task output
        * ``{"type": "task_completed", ...}``                 – per task done
        * ``{"type": "all_completed", "results": {...}}``      – all tasks done
        * ``{"type": "final_result", "text": "..."}``         – after merging
        """
        tasks = await self.plan(user_request)
        yield {"type": "plan", "tasks": tasks}

        results: dict[int, str] = {}
        async for event in self.execute(tasks):
            if event["type"] == "all_completed":
                results = event["results"]
            yield event

        merged = await self.merge_results(results)
        yield {"type": "final_result", "text": merged}
