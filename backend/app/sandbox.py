"""
AI Companion – Code Sandbox
============================
Executes user-submitted Python or JavaScript code in a restricted subprocess
with hard time-outs and working-directory isolation.

Security notes
--------------
* The process runs inside ``/app/sandbox/`` (created by the Dockerfile).
* A ``SANDBOX_TIMEOUT_SECONDS`` cap kills long-running processes.
* Temp script files are cleaned up after each run.
* In production, consider adding ``seccomp`` / ``nsjail`` for stronger
  isolation – this implementation is a reasonable starting point.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import tempfile
import time
from pathlib import Path
from typing import AsyncGenerator, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# On Windows (dev), fall back to a local sandbox folder.
_IS_WINDOWS = platform.system() == "Windows"
_SANDBOX_DIR = (
    Path("sandbox").resolve() if _IS_WINDOWS else Path("/app/sandbox")
)


class CodeSandbox:
    """Execute Python / JavaScript in a subprocess with resource limits."""

    def __init__(self) -> None:
        settings = get_settings()
        self._timeout = settings.SANDBOX_TIMEOUT_SECONDS
        _SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "CodeSandbox ready – timeout=%ds, dir=%s",
            self._timeout,
            _SANDBOX_DIR,
        )

    async def execute(self, language: str, code: str) -> dict:
        """Run *code* in *language* and return execution results.

        Parameters
        ----------
        language:
            ``"python"`` or ``"javascript"``.
        code:
            Source code to execute.

        Returns
        -------
        dict with keys ``stdout``, ``stderr``, ``exit_code``,
        ``execution_time`` (seconds).
        """
        language = language.lower().strip()
        if language not in ("python", "javascript"):
            return {
                "stdout": "",
                "stderr": f"Unsupported language: {language}",
                "exit_code": 1,
                "execution_time": 0.0,
            }

        ext = ".py" if language == "python" else ".js"
        cmd_prefix = ["python"] if language == "python" else ["node"]

        script_path: Optional[str] = None
        try:
            # Write code to a temp file inside the sandbox directory.
            fd, script_path = tempfile.mkstemp(
                suffix=ext, dir=str(_SANDBOX_DIR)
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(code)

            t0 = time.perf_counter()
            proc = await asyncio.create_subprocess_exec(
                *cmd_prefix,
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_SANDBOX_DIR),
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                elapsed = time.perf_counter() - t0
                return {
                    "stdout": "",
                    "stderr": f"Execution timed out after {self._timeout}s.",
                    "exit_code": -1,
                    "execution_time": round(elapsed, 3),
                }

            elapsed = time.perf_counter() - t0
            return {
                "stdout": stdout_bytes.decode(errors="replace"),
                "stderr": stderr_bytes.decode(errors="replace"),
                "exit_code": proc.returncode or 0,
                "execution_time": round(elapsed, 3),
            }

        except Exception as exc:
            logger.exception("Sandbox execution failed.")
            return {
                "stdout": "",
                "stderr": str(exc),
                "exit_code": 1,
                "execution_time": 0.0,
            }
        finally:
            # Clean up the temp script.
            if script_path and os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except OSError:
                    pass

    async def execute_streaming(
        self, language: str, code: str
    ) -> AsyncGenerator[dict, None]:
        """Run *code* and yield output lines as they arrive (real-time).

        Yields dicts with one of these shapes:
            {"type": "output",  "text": "..."}     — stdout/stderr line
            {"type": "status",  "exit_code": N,
             "execution_time": F}                   — final status

        Timeout is still enforced via ``SANDBOX_TIMEOUT_SECONDS``.
        """
        language = language.lower().strip()
        if language not in ("python", "javascript"):
            yield {
                "type": "output",
                "text": f"Unsupported language: {language}",
            }
            yield {"type": "status", "exit_code": 1, "execution_time": 0.0}
            return

        ext = ".py" if language == "python" else ".js"
        cmd_prefix = ["python"] if language == "python" else ["node"]

        script_path: Optional[str] = None
        try:
            fd, script_path = tempfile.mkstemp(
                suffix=ext, dir=str(_SANDBOX_DIR)
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(code)

            t0 = time.perf_counter()
            proc = await asyncio.create_subprocess_exec(
                *cmd_prefix,
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_SANDBOX_DIR),
            )

            # Merge stdout + stderr so we can stream both.
            # We read line-by-line from whichever pipe has data.
            try:
                async with asyncio.timeout(self._timeout):
                    while True:
                        # Check if process has finished
                        if proc.stdout.at_eof() and proc.stderr.at_eof():
                            break

                        # Read a line from stdout or stderr
                        stdout_line = await proc.stdout.readline()
                        stderr_line = await proc.stderr.readline()

                        if stdout_line:
                            yield {
                                "type": "output",
                                "text": stdout_line.decode(errors="replace").rstrip("\n\r"),
                                "stream": "stdout",
                            }
                        if stderr_line:
                            yield {
                                "type": "output",
                                "text": stderr_line.decode(errors="replace").rstrip("\n\r"),
                                "stream": "stderr",
                            }

                        # If both were empty but process is still running, wait briefly
                        if not stdout_line and not stderr_line:
                            if proc.returncode is not None:
                                break
                            await asyncio.sleep(0.05)

            except (asyncio.TimeoutError, TimeoutError):
                proc.kill()
                await proc.wait()
                elapsed = time.perf_counter() - t0
                yield {
                    "type": "output",
                    "text": f"\n[Execution timed out after {self._timeout}s]",
                    "stream": "stderr",
                }
                yield {
                    "type": "status",
                    "exit_code": -1,
                    "execution_time": round(elapsed, 3),
                }
                return

            await proc.wait()
            elapsed = time.perf_counter() - t0

            # Drain any remaining output
            remaining_stdout = await proc.stdout.read()
            remaining_stderr = await proc.stderr.read()
            if remaining_stdout:
                for line in remaining_stdout.decode(errors="replace").splitlines():
                    yield {"type": "output", "text": line, "stream": "stdout"}
            if remaining_stderr:
                for line in remaining_stderr.decode(errors="replace").splitlines():
                    yield {"type": "output", "text": line, "stream": "stderr"}

            yield {
                "type": "status",
                "exit_code": proc.returncode or 0,
                "execution_time": round(elapsed, 3),
            }

        except Exception as exc:
            logger.exception("Streaming sandbox execution failed.")
            yield {"type": "output", "text": str(exc), "stream": "stderr"}
            yield {"type": "status", "exit_code": 1, "execution_time": 0.0}
        finally:
            if script_path and os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
