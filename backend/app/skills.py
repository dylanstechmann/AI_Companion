"""
AI Companion – Skill / Plugin System
=====================================
A lightweight plugin architecture that lets users **and the AI itself** create
reusable tool definitions at runtime.  Each *skill* is a self-contained
directory under ``skills_dir`` containing two files:

* ``skill.json`` – metadata describing the skill and its function schemas.
* ``handler.py`` – Python module exposing one ``async`` function per declared
  function in ``skill.json``.

Loaded skills are exposed to the LLM as additional OpenAI-compatible
function-calling tools, integrating transparently with
:mod:`app.tools` (see ``TOOLS_SCHEMA`` / ``TOOL_DISPATCH``).

Directory layout
----------------
::

    skills_dir/
    └── my_skill/
        ├── skill.json
        └── handler.py

``skill.json`` format
---------------------
::

    {
        "name": "my_skill",
        "description": "What this skill does.",
        "version": "1.0.0",
        "author": "user",
        "functions": [
            {
                "name": "do_thing",
                "description": "Does a thing.",
                "parameters": {
                    "type": "object",
                    "properties": { ... },
                    "required": [ ... ]
                }
            }
        ],
        "triggers": ["keyword1", "keyword2"],
        "requirements": ["some-pip-package"]
    }

``handler.py`` format
---------------------
Each entry in ``skill.json``'s ``functions`` array maps to an ``async``
function of the same name inside ``handler.py``.  The function receives the
keyword arguments defined by its ``parameters`` schema::

    async def do_thing(**kwargs):
        ...
        return {"result": "..."}
"""

from __future__ import annotations

import importlib.util
import json
import logging
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# On Windows (dev), fall back to a local data folder; on Linux/Docker use /app.
_IS_WINDOWS = platform.system() == "Windows"
_DEFAULT_SKILLS_DIR = (
    Path("data/skills").resolve() if _IS_WINDOWS else Path("/app/data/skills")
)


class SkillManager:
    """Discover, load, and execute user/AI-defined skills.

    The manager treats every subdirectory of ``skills_dir`` that contains a
    ``skill.json`` file as a candidate skill.  Calling :meth:`load` imports
    the skill's ``handler.py`` via :mod:`importlib`, validates that every
    declared function exists on the module, and registers the callables for
    later dispatch through :meth:`execute`.
    """

    def __init__(self, skills_dir: Optional[Path | str] = None) -> None:
        """Initialise the manager and ensure the skills directory exists.

        Parameters
        ----------
        skills_dir:
            Optional override for the skills directory.  When ``None`` the
            platform-aware default is used (``/app/data/skills`` on Linux,
            ``data/skills`` on Windows).
        """
        if skills_dir is None:
            skills_dir = _DEFAULT_SKILLS_DIR
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # loaded_skills maps skill_name -> {
        #     "metadata": <skill.json dict>,
        #     "module":   <imported handler module>,
        #     "functions": {func_name: callable, ...},
        # }
        self.loaded_skills: dict[str, dict[str, Any]] = {}

        logger.info(
            "SkillManager ready – skills_dir=%s", self.skills_dir
        )

    # ------------------------------------------------------------------
    # Discovery & loading
    # ------------------------------------------------------------------

    def discover(self) -> list[dict[str, Any]]:
        """Scan ``skills_dir`` for subdirectories containing ``skill.json``.

        Returns
        -------
        list[dict]
            A list of parsed ``skill.json`` metadata dicts.  Skills whose
            metadata cannot be read are skipped with a warning.
        """
        discovered: list[dict[str, Any]] = []
        if not self.skills_dir.is_dir():
            return discovered

        for child in sorted(self.skills_dir.iterdir()):
            if not child.is_dir():
                continue
            manifest = child / "skill.json"
            if not manifest.is_file():
                continue
            try:
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
                # Ensure the directory name and declared name agree, falling
                # back to the directory name if the manifest omits it.
                metadata.setdefault("name", child.name)
                discovered.append(metadata)
            except (json.JSONDecodeError, OSError):
                logger.warning(
                    "Failed to parse skill.json in %s – skipping.", child
                )
        return discovered

    def load(self, skill_name: str) -> bool:
        """Load a single skill by name.

        Reads ``skills_dir/<skill_name>/skill.json``, dynamically imports
        ``handler.py`` via :mod:`importlib`, and registers every declared
        function as a callable.

        Returns
        -------
        bool
            ``True`` on success, ``False`` if the skill is missing or its
            handler cannot be imported / does not expose the declared
            functions.
        """
        skill_path = self.skills_dir / skill_name
        manifest_path = skill_path / "skill.json"
        handler_path = skill_path / "handler.py"

        if not manifest_path.is_file():
            logger.warning("Skill %r has no skill.json – cannot load.", skill_name)
            return False
        if not handler_path.is_file():
            logger.warning("Skill %r has no handler.py – cannot load.", skill_name)
            return False

        try:
            metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Could not read skill.json for %r: %s", skill_name, exc)
            return False

        metadata.setdefault("name", skill_name)
        declared_funcs = metadata.get("functions", []) or []

        # Dynamically import handler.py under a unique module name so that
        # multiple skills (or a reloaded skill) don't collide in sys.modules.
        module_name = f"_skill_{skill_name}"
        spec = importlib.util.spec_from_file_location(module_name, handler_path)
        if spec is None or spec.loader is None:
            logger.error("Could not build import spec for %r.", skill_name)
            return False

        module = importlib.util.module_from_spec(spec)
        # Register in sys.modules before exec so the module can import itself
        # relatively if needed (and so reloads replace the prior version).
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            # Roll back the partial registration on failure.
            sys.modules.pop(module_name, None)
            logger.exception("Failed to import handler.py for %r.", skill_name)
            return False

        # Map declared function names -> callables on the imported module.
        functions: dict[str, Any] = {}
        for func_def in declared_funcs:
            func_name = func_def.get("name")
            if not func_name:
                logger.warning(
                    "Skill %r declares a function without a name – skipping entry.",
                    skill_name,
                )
                continue
            callable_obj = getattr(module, func_name, None)
            if callable_obj is None or not callable(callable_obj):
                logger.error(
                    "Skill %r declares function %r but handler.py does not "
                    "expose it – aborting load.",
                    skill_name,
                    func_name,
                )
                sys.modules.pop(module_name, None)
                return False
            functions[func_name] = callable_obj

        self.loaded_skills[skill_name] = {
            "metadata": metadata,
            "module": module,
            "functions": functions,
        }
        logger.info(
            "Loaded skill %r with %d function(s): %s",
            skill_name,
            len(functions),
            ", ".join(functions) or "(none)",
        )
        return True

    def load_all(self) -> None:
        """Discover and load every skill found in ``skills_dir``."""
        for metadata in self.discover():
            name = metadata.get("name")
            if not name:
                continue
            if name in self.loaded_skills:
                continue
            self.load(name)

    def unload(self, skill_name: str) -> None:
        """Remove a skill from the loaded set (does not delete files)."""
        entry = self.loaded_skills.pop(skill_name, None)
        if entry is not None:
            # Drop the dynamically imported module so a future reload picks
            # up the latest handler.py content.
            module = entry.get("module")
            if module is not None:
                sys.modules.pop(getattr(module, "__name__", ""), None)
            logger.info("Unloaded skill %r.", skill_name)
        else:
            logger.warning("unload: skill %r was not loaded.", skill_name)

    # ------------------------------------------------------------------
    # Schema / introspection
    # ------------------------------------------------------------------

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """Return the OpenAI function-calling schema for all loaded skills.

        Each ``functions`` entry from a skill's ``skill.json`` is converted to
        a tool schema entry of the form::

            {"type": "function", "function": {name, description, parameters}}

        matching the shape used by :data:`app.tools.TOOLS_SCHEMA`.
        """
        schemas: list[dict[str, Any]] = []
        for entry in self.loaded_skills.values():
            metadata = entry["metadata"]
            for func_def in metadata.get("functions", []) or []:
                schemas.append(
                    {
                        "type": "function",
                        "function": {
                            "name": func_def["name"],
                            "description": func_def.get("description", ""),
                            "parameters": func_def.get(
                                "parameters",
                                {"type": "object", "properties": {}},
                            ),
                        },
                    }
                )
        return schemas

    def get_skill_info(self, skill_name: str) -> dict[str, Any]:
        """Return metadata for *skill_name*.

        If the skill is currently loaded, its in-memory metadata is returned.
        Otherwise the manifest is read fresh from disk so callers can inspect
        a skill without loading it.  Returns an empty dict if the skill does
        not exist.
        """
        if skill_name in self.loaded_skills:
            return dict(self.loaded_skills[skill_name]["metadata"])
        manifest = self.skills_dir / skill_name / "skill.json"
        if not manifest.is_file():
            return {}
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.exception("Could not read skill info for %r.", skill_name)
            return {}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        skill_name: str,
        function_name: str,
        args: dict[str, Any] | None = None,
    ) -> Any:
        """Invoke *function_name* on skill *skill_name* with *args*.

        Parameters
        ----------
        skill_name:
            Name of a currently-loaded skill.
        function_name:
            Name of a function declared in the skill's ``skill.json``.
        args:
            Keyword arguments to pass through to the handler function.

        Returns
        -------
        Any
            Whatever the handler function returns.

        Raises
        ------
        KeyError
            If the skill is not loaded or the function is not registered.
        """
        entry = self.loaded_skills.get(skill_name)
        if entry is None:
            raise KeyError(f"Skill {skill_name!r} is not loaded.")
        func = entry["functions"].get(function_name)
        if func is None:
            raise KeyError(
                f"Skill {skill_name!r} does not expose function {function_name!r}."
            )

        kwargs = args or {}
        logger.debug(
            "Executing skill %r / function %r with args=%r",
            skill_name,
            function_name,
            kwargs,
        )
        return await func(**kwargs)

    # ------------------------------------------------------------------
    # Creation / deletion
    # ------------------------------------------------------------------

    async def create_skill(
        self,
        name: str,
        description: str,
        code: str,
        functions_schema: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create a new skill on disk and load it immediately.

        Parameters
        ----------
        name:
            Skill (and directory) name.  Must be a valid directory name and
            not collide with an existing skill unless overwriting is desired.
        description:
            Human-readable description written into ``skill.json``.
        code:
            Full contents of the ``handler.py`` file.  Must define an
            ``async`` function for every entry in *functions_schema*.
        functions_schema:
            List of function definitions, each a dict with at least
            ``name``, ``description``, and ``parameters`` keys.  Written
            verbatim into the ``functions`` array of ``skill.json``.

        Returns
        -------
        dict
            The metadata of the newly created (and loaded) skill.
        """
        settings = get_settings()
        # Sanitise the name so it can't escape skills_dir.
        safe_name = Path(name).name
        if safe_name != name or not safe_name:
            raise ValueError(f"Invalid skill name: {name!r}")

        skill_dir = self.skills_dir / safe_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "name": safe_name,
            "description": description,
            "version": "1.0.0",
            "author": "ai-companion",
            "functions": functions_schema,
            "triggers": [],
            "requirements": [],
        }

        (skill_dir / "skill.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        (skill_dir / "handler.py").write_text(code, encoding="utf-8")
        logger.info("Created skill %r at %s.", safe_name, skill_dir)

        # If a prior version was loaded, unload it first so we pick up the
        # new handler.py cleanly.
        if safe_name in self.loaded_skills:
            self.unload(safe_name)

        if not self.load(safe_name):
            logger.error(
                "Skill %r was written to disk but failed to load.", safe_name
            )
        return metadata

    def delete_skill(self, skill_name: str) -> bool:
        """Delete a skill's directory and unload it from memory.

        Returns
        -------
        bool
            ``True`` if the directory was removed, ``False`` if it did not
            exist.
        """
        if skill_name in self.loaded_skills:
            self.unload(skill_name)

        skill_dir = self.skills_dir / skill_name
        if not skill_dir.is_dir():
            logger.warning("delete_skill: %r does not exist.", skill_name)
            return False

        try:
            shutil.rmtree(skill_dir)
            logger.info("Deleted skill %r.", skill_name)
            return True
        except OSError as exc:
            logger.error("Could not delete skill %r: %s", skill_name, exc)
            return False
