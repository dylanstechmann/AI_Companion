from __future__ import annotations

import asyncio
import importlib
import logging
import os
import re
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import auth, config, database

TEST_SECRET = "test-only-secret-" * 4


class AuthConfigurationTests(unittest.TestCase):
    def settings(self, **values):
        defaults = dict(APP_ENV="development", JWT_SECRET="", ALLOW_REGISTRATION=False,
                        ALLOW_DEMO_LOGIN=False)
        defaults.update(values)
        return config.Settings(_env_file=None, **defaults)

    def test_registration_and_demo_default_to_disabled(self):
        settings = self.settings()
        self.assertFalse(settings.ALLOW_REGISTRATION)
        self.assertFalse(settings.ALLOW_DEMO_LOGIN)

    def test_development_tokens_share_one_process_key(self):
        with patch.object(auth, "get_settings", return_value=self.settings()):
            first = auth.auth_service.create_access_token(7)
            second = auth.auth_service.create_refresh_token(7)
            self.assertEqual(auth.AuthService()._decode(first, "access")["sub"], "7")
            self.assertEqual(auth.auth_service._decode(second, "refresh")["sub"], "7")

    def test_production_rejects_missing_weak_or_placeholder_keys_and_bootstrap_modes(self):
        for secret in ("", "short", "change-me-to-a-random-secret", "change-me" + "x" * 40):
            with self.subTest(secret=secret), self.assertRaises(ValidationError):
                self.settings(APP_ENV="production", JWT_SECRET=secret)
        for option in ("ALLOW_REGISTRATION", "ALLOW_DEMO_LOGIN"):
            with self.subTest(option=option), self.assertRaises(ValidationError):
                self.settings(APP_ENV="production", JWT_SECRET=TEST_SECRET, **{option: True})
        self.assertEqual(self.settings(APP_ENV="production", JWT_SECRET=TEST_SECRET).JWT_SECRET, TEST_SECRET)


class AuthRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.import_dir = tempfile.TemporaryDirectory()
        # Keep auth, routing, config and database real; exclude unrelated model imports.
        doubles = {}
        for module_name, service_name in (("app.llm", "LLMService"),
                                           ("app.memory", "MemoryManager"),
                                           ("app.research", "ResearchAgent")):
            module = types.ModuleType(module_name)
            setattr(module, service_name, type(service_name, (), {}))
            doubles[module_name] = module
        previous_cwd = Path.cwd()
        try:
            os.chdir(cls.import_dir.name)
            with patch.dict(sys.modules, doubles):
                cls.main = importlib.import_module("app.main")
        finally:
            os.chdir(previous_cwd)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    @classmethod
    def tearDownClass(cls):
        cls.import_dir.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = config.Settings(
            _env_file=None, APP_ENV="development", JWT_SECRET=TEST_SECRET,
            ALLOW_REGISTRATION=False, ALLOW_DEMO_LOGIN=False,
            DATABASE_PATH=str(Path(self.directory.name) / "auth.sqlite3"),
        )
        for module in (auth, config, database, self.main):
            patcher = patch.object(module, "get_settings", return_value=self.settings)
            patcher.start()
            self.addCleanup(patcher.stop)
        asyncio.run(database.init_db())
        # Lifespan is intentionally not started: no external providers or model services.
        self.client = TestClient(self.main.app)
        self.addCleanup(self.client.close)

    def register(self):
        self.settings.ALLOW_REGISTRATION = True
        response = self.client.post("/api/auth/register", json={
            "email": "owner@example.test", "password": "correct-password", "display_name": "Owner",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.settings.ALLOW_REGISTRATION = False
        return response.json()

    def headers(self, tokens):
        return {"Authorization": "Bearer " + tokens["access_token"]}

    def test_registration_login_refresh_and_me_use_one_contract(self):
        tokens = self.register()
        self.assertNotIn("password_hash", tokens["user"])
        me = self.client.get("/api/auth/me", headers=self.headers(tokens))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["id"], tokens["user"]["id"])
        login = self.client.post("/api/auth/login", json={
            "email": "OWNER@example.test", "password": "correct-password",
        })
        self.assertEqual(login.status_code, 200)
        refreshed = self.client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        self.assertEqual(refreshed.status_code, 200)
        for result in (tokens, login.json(), refreshed.json()):
            self.assertEqual(set(result), {"access_token", "refresh_token", "token_type", "user"})
            self.assertEqual(result["token_type"], "bearer")
            self.assertEqual(self.client.get("/api/auth/me", headers=self.headers(result)).status_code, 200)
        wrong = self.client.post("/api/auth/login", json={"email": "owner@example.test", "password": "wrong"})
        self.assertEqual(wrong.status_code, 401)

    def test_bootstrap_is_disabled_before_database_mutation(self):
        with patch.object(database, "create_user", new_callable=AsyncMock) as create:
            self.assertEqual(self.client.post("/api/auth/register", json={
                "email": "new@example.test", "password": "password",
            }).status_code, 403)
            self.assertEqual(self.client.post("/api/auth/demo").status_code, 403)
            self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
            create.assert_not_awaited()
        self.assertEqual(self.client.get("/api/auth/options").json(), {
            "registration_enabled": False, "demo_enabled": False,
        })

    def test_all_operational_routes_reject_unauthenticated_requests(self):
        expired = jwt.encode({"sub": "1", "type": "access",
                              "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                             TEST_SECRET, algorithm="HS256")
        credentials = [None, "Basic invalid", "Bearer invalid", "Bearer " + expired,
                       "Bearer " + auth.auth_service.create_refresh_token(1)]
        checked = 0
        for route in self.main.app.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods:
                if (method, route.path) in auth.PUBLIC_ENDPOINTS:
                    continue
                path = re.sub(r"\{[^}]+\}", "1", route.path)
                for credential in credentials:
                    with self.subTest(path=path, method=method, credential=credential):
                        headers = {"Authorization": credential} if credential else {}
                        response = self.client.request(method, path, headers=headers, json={})
                        self.assertEqual(response.status_code, 401, response.text)
                        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")
                checked += 1
        self.assertGreater(checked, 30)

    def test_unauthorized_skills_browser_and_code_never_reach_services(self):
        skills = Mock(create_skill=AsyncMock(), execute=AsyncMock())
        sandbox = Mock(execute=AsyncMock())
        with patch.object(self.main, "skill_manager", skills), \
             patch.object(self.main, "code_sandbox", sandbox), \
             patch.dict(sys.modules, {"app.browser": None}):
            for path, body in (("/api/skills", {"name": "test", "code": "raise RuntimeError()"}),
                               ("/api/skills/test/execute", {"function": "test"}),
                               ("/api/code/execute", {"language": "python", "code": "print(1)"}),
                               ("/api/browser/navigate", {"url": "https://example.test"})):
                self.assertEqual(self.client.post(path, json=body).status_code, 401)
        skills.create_skill.assert_not_awaited()
        skills.execute.assert_not_awaited()
        sandbox.execute.assert_not_awaited()

    def test_valid_token_reaches_skills_browser_and_streaming_handlers(self):
        tokens = self.register()
        skills = Mock(create_skill=AsyncMock(return_value={"name": "test"}))
        browser = types.ModuleType("app.browser")
        browser_instance = Mock(navigate=AsyncMock(return_value={"title": "test"}))
        browser.BrowserService = Mock(return_value=browser_instance)
        async def events(*args):
            yield {"type": "output", "text": "test"}
        sandbox = Mock(execute_streaming=events)
        with patch.object(self.main, "skill_manager", skills), \
             patch.object(self.main, "code_sandbox", sandbox), \
             patch.dict(sys.modules, {"app.browser": browser}):
            headers = self.headers(tokens)
            result = self.client.post("/api/skills", headers=headers, json={"name": "test", "code": "# test"})
            self.assertEqual(result.status_code, 200)
            skills.create_skill.assert_awaited_once()
            result = self.client.post("/api/browser/navigate", headers=headers, json={"url": "https://example.test"})
            self.assertEqual(result.status_code, 200)
            browser_instance.navigate.assert_awaited_once_with("https://example.test")
            result = self.client.post("/api/code/execute/stream", headers=headers,
                                      json={"language": "python", "code": "print(1)"})
            self.assertEqual(result.status_code, 200)
            self.assertIn("text/event-stream", result.headers["content-type"])
            self.assertIn("data: [DONE]", result.text)

    def test_demo_tokens_stop_working_when_demo_is_disabled(self):
        self.settings.ALLOW_DEMO_LOGIN = True
        response = self.client.post("/api/auth/demo")
        self.assertEqual(response.status_code, 200, response.text)
        tokens = response.json()
        self.assertEqual(self.client.get("/api/auth/me", headers=self.headers(tokens)).status_code, 200)
        self.settings.ALLOW_DEMO_LOGIN = False
        self.assertEqual(self.client.get("/api/auth/me", headers=self.headers(tokens)).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code, 401)

    def test_bad_or_missing_jwt_subjects_return_401(self):
        for subject in (None, "", "abc", "-1", "0", "1.5", "9" * 5000):
            payload = {"type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=1)}
            if subject is not None:
                payload["sub"] = subject
            token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
            with self.subTest(subject=str(subject)[:20]):
                self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code, 401)

    def test_public_auth_metadata_and_health_remain_accessible(self):
        self.assertEqual(self.client.get("/api/auth/options").status_code, 200)
        self.assertEqual(self.client.get("/api/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
