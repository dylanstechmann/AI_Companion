"""Configuration contract tests with stdlib-only checks and optional integration."""

import ast
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "backend" / "app" / "config.py"
HAS_SETTINGS = importlib.util.find_spec("pydantic_settings") is not None


class BrowserConfigurationContractTests(unittest.TestCase):
    def test_engine_is_exact_literal_with_unchanged_default(self):
        tree = ast.parse(CONFIG.read_text())
        settings = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Settings")
        field = next(
            n for n in settings.body if isinstance(n, ast.AnnAssign)
            and isinstance(n.target, ast.Name) and n.target.id == "BROWSER_ENGINE"
        )
        self.assertEqual(ast.unparse(field.annotation), "Literal['chromium', 'firefox']")
        self.assertEqual(ast.literal_eval(field.value), "chromium")

    def test_both_compose_variants_pass_engine_and_load_env_file(self):
        for name in ("docker-compose.yml", "docker-compose.production.yml"):
            with self.subTest(name=name):
                text = (ROOT / name).read_text()
                self.assertIn("BROWSER_ENGINE=${BROWSER_ENGINE:-chromium}", text)
                self.assertIn("env_file: .env", text)

    def test_image_installs_both_browsers_and_env_example_keeps_default(self):
        self.assertIn(
            "python -m playwright install --with-deps chromium firefox",
            (ROOT / "backend" / "Dockerfile").read_text(),
        )
        example = (ROOT / ".env.example").read_text()
        self.assertIn("\nBROWSER_ENGINE=chromium\n", example)
        self.assertIn("\nPROXY_URL=\n", example)

    def test_production_command_replaces_development_default(self):
        dockerfile = (ROOT / "backend" / "Dockerfile").read_text()
        self.assertIn(
            'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]',
            dockerfile,
        )
        self.assertFalse(any(line.startswith("ENTRYPOINT ") for line in dockerfile.splitlines()))
        production = (ROOT / "docker-compose.production.yml").read_text()
        self.assertIn(
            'command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]',
            production,
        )


@unittest.skipUnless(HAS_SETTINGS, "Optional real-settings test requires pydantic-settings.")
class BrowserSettingsIntegrationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("_browser_config_under_test", CONFIG)
        self.module = importlib.util.module_from_spec(spec)
        # Pydantic resolves postponed annotations through the defining module.
        # Register it exactly as a normal import does before executing config.py.
        registration = patch.dict(sys.modules, {spec.name: self.module})
        registration.start()
        self.addCleanup(registration.stop)
        spec.loader.exec_module(self.module)

    def test_default_and_environment_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.module.Settings(_env_file=None).BROWSER_ENGINE, "chromium")
            os.environ["BROWSER_ENGINE"] = "firefox"
            self.assertEqual(self.module.Settings(_env_file=None).BROWSER_ENGINE, "firefox")

    def test_invalid_environment_value_is_rejected(self):
        from pydantic import ValidationError
        for value in ("webkit", "Firefox", "", "chrome", "chromium --no-sandbox"):
            with self.subTest(value=value), patch.dict(os.environ, {"BROWSER_ENGINE": value}, clear=True):
                with self.assertRaises(ValidationError):
                    self.module.Settings(_env_file=None)

    def test_normal_app_config_import_and_validation_in_fresh_process(self):
        script = """
import os
from unittest.mock import patch
from pydantic import ValidationError
from app.config import Settings
with patch.dict(os.environ, {}, clear=True):
    assert Settings(_env_file=None).BROWSER_ENGINE == "chromium"
    os.environ["BROWSER_ENGINE"] = "firefox"
    assert Settings(_env_file=None).BROWSER_ENGINE == "firefox"
    os.environ["BROWSER_ENGINE"] = "webkit"
    try:
        Settings(_env_file=None)
    except ValidationError:
        pass
    else:
        raise AssertionError("invalid engine was accepted")
print("Normal app.config import: default, Firefox override, rejection OK")
"""
        result = subprocess.run(
            [sys.executable, "-B", "-W", "error", "-c", script],
            cwd=ROOT / "backend", capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("rejection OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
