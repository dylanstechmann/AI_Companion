"""Offline browser unit tests; no Playwright, web access or GPU stack required.

Run from the repository root:
    python -m unittest discover -s backend/tests -p 'test_browser*.py' -v
"""

import asyncio
import importlib.util
import socket
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch


# Load only browser.py, not the application's heavy dependency graph. The
# temporary module replacement is restored immediately after the import.
_PATH = Path(__file__).resolve().parents[1] / "app" / "browser.py"
_CONFIG = types.ModuleType("app.config")
_CONFIG.get_settings = Mock()
_SPEC = importlib.util.spec_from_file_location("_browser_under_test", _PATH)
browser_module = importlib.util.module_from_spec(_SPEC)
with patch.dict(sys.modules, {"app.config": _CONFIG}):
    _SPEC.loader.exec_module(browser_module)
BrowserService = browser_module.BrowserService


def dns_answer(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    endpoint = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", endpoint)


class BrowserURLTests(unittest.TestCase):
    def test_blocks_nonpublic_literals_and_local_names(self):
        for url in (
            "http://localhost/", "http://LOCALHOST./", "http://a.localhost/",
            "http://127.0.0.1/", "http://10.2.3.4/", "http://172.16.2.3/",
            "http://192.168.0.2/", "http://169.254.169.254/",
            "http://100.64.0.1/", "http://0.0.0.0/", "http://224.0.0.1/",
            "http://255.255.255.255/", "http://[::]/", "http://[::1]/",
            "http://[fc01::1]/", "http://[fe80::1]/", "http://[ff02::1]/",
            "http://[::ffff:127.0.0.1]/", "http://[::ffff:10.0.0.1]/",
            "http://metadata.internal/", "http://printer.local/", "http://backend/",
        ):
            with self.subTest(url=url):
                self.assertTrue(BrowserService.is_private_url(url))

    def test_blocks_malformed_ambiguous_and_credential_urls(self):
        for url in (
            None, 42, "", "file:///etc/passwd", "data:text/html,hello",
            "javascript:alert(1)", "ftp://example.test/", "//example.test/",
            "https://", "http://[::1", "https://example.test:abc",
            "https://example.test:65536", "https://example.test:0",
            "https://user:secret@example.test/", "https://@example.test/",
            "http://example.test\\@127.0.0.1/", "http://%31%32%37.0.0.1/",
            "http://[fe80::1%25eth0]/", "http://bad_host.example/",
            "https://example.test/\nsecret", " https://example.test/",
            "http://example..test/", "http://-example.test/",
        ):
            with self.subTest(url=url):
                self.assertTrue(BrowserService.is_private_url(url))

    def test_allows_public_syntax_without_claiming_dns_safety(self):
        for url in (
            "https://example.test/path?query=value", "http://93.184.216.34/",
            "https://[2606:4700:4700::1111]/", "https://example.test.:8443/",
            "https://bücher.example/",
        ):
            with self.subTest(url=url):
                self.assertFalse(BrowserService.is_private_url(url))


class BrowserDNSTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = BrowserService()
        self.resolver = AsyncMock(return_value=[dns_answer("93.184.216.34")])
        self.patch = patch.object(asyncio.get_running_loop(), "getaddrinfo", self.resolver)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    async def test_public_dns_is_allowed(self):
        self.assertIsNone(await self.service._check_request_url_safe("https://example.test/"))
        self.resolver.assert_awaited_once_with(
            "example.test", 443, type=socket.SOCK_STREAM
        )

    async def test_public_ipv4_and_ipv6_answers_are_allowed(self):
        self.resolver.return_value = [
            dns_answer("93.184.216.34"), dns_answer("2606:4700:4700::1111"),
        ]
        self.assertIsNone(await self.service._check_request_url_safe("https://example.test/"))

    async def test_any_nonpublic_dns_answer_blocks_request(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1",
                        "::ffff:192.168.1.1", "100.64.0.1", "224.0.0.1"):
            with self.subTest(address=address):
                self.resolver.return_value = [
                    dns_answer("93.184.216.34"), dns_answer(address),
                ]
                self.assertIsNotNone(
                    await self.service._check_request_url_safe("https://example.test/")
                )

    async def test_empty_dns_answer_is_blocked(self):
        self.resolver.return_value = []
        self.assertIsNotNone(await self.service._check_request_url_safe("https://example.test/"))

    async def test_dns_failure_and_timeout_fail_closed(self):
        for error in (socket.gaierror("private resolver detail"), TimeoutError()):
            with self.subTest(error=type(error).__name__):
                self.resolver.side_effect = error
                result = await self.service._check_request_url_safe("https://example.test/")
                self.assertIn("could not be safely resolved", result)
                self.assertNotIn("private resolver detail", result)

    async def test_slow_dns_times_out(self):
        async def slow(*args, **kwargs):
            await asyncio.sleep(1)
        self.resolver.side_effect = slow
        with patch.object(browser_module, "_DNS_TIMEOUT_SECONDS", 0.001):
            result = await self.service._check_request_url_safe("https://example.test/")
        self.assertIn("could not be safely resolved", result)

    async def test_literals_do_not_need_dns(self):
        self.assertIsNone(await self.service._check_request_url_safe("https://93.184.216.34/"))
        self.assertIsNotNone(await self.service._check_request_url_safe("https://127.0.0.1/"))
        self.resolver.assert_not_awaited()

    async def test_legacy_ipv4_forms_are_checked_after_resolution(self):
        self.resolver.return_value = [dns_answer("127.0.0.1")]
        for url in ("http://127.1/", "http://0177.0.0.1/", "http://0x7f.0.0.1/",
                    "http://2130706433/"):
            with self.subTest(url=url):
                self.assertIsNotNone(await self.service._check_request_url_safe(url))

    async def test_dns_checks_are_not_cached(self):
        self.resolver.side_effect = [
            [dns_answer("93.184.216.34")], [dns_answer("127.0.0.1")],
        ]
        self.assertIsNone(await self.service._check_request_url_safe("https://example.test/"))
        self.assertIsNotNone(await self.service._check_request_url_safe("https://example.test/"))
        self.assertEqual(self.resolver.await_count, 2)

    async def test_idna_and_trailing_dot_normalization(self):
        self.assertIsNone(await self.service._check_request_url_safe("https://bücher.example./"))
        self.resolver.assert_awaited_once_with(
            "xn--bcher-kva.example", 443, type=socket.SOCK_STREAM
        )

    async def test_initial_private_navigation_does_not_launch_browser(self):
        self.resolver.return_value = [dns_answer("192.168.1.1")]
        self.service._ensure_started = AsyncMock()
        self.assertIn("error", await self.service.navigate("https://example.test/"))
        with self.assertRaises(ValueError):
            await self.service.screenshot("https://example.test/")
        result = await self.service.fill_form("https://example.test/", {"#field": "secret"})
        self.assertFalse(result["success"])
        self.service._ensure_started.assert_not_awaited()

    async def test_route_checks_subresources_and_frames_not_only_navigation(self):
        for resource_type in ("document", "image", "script", "xhr", "fetch"):
            with self.subTest(resource_type=resource_type):
                route = types.SimpleNamespace(
                    request=types.SimpleNamespace(
                        url="http://169.254.169.254/", resource_type=resource_type,
                    ),
                    abort=AsyncMock(), continue_=AsyncMock(),
                )
                await self.service._route_request(route)
                route.abort.assert_awaited_once_with("blockedbyclient")
                route.continue_.assert_not_awaited()

    async def test_route_checks_private_dns(self):
        self.resolver.return_value = [dns_answer("10.0.0.1")]
        route = types.SimpleNamespace(
            request=types.SimpleNamespace(url="https://example.test/"),
            abort=AsyncMock(), continue_=AsyncMock(),
        )
        await self.service._route_request(route)
        route.abort.assert_awaited_once()
        route.continue_.assert_not_awaited()

    async def test_route_continues_public_request(self):
        route = types.SimpleNamespace(
            request=types.SimpleNamespace(url="https://example.test/"),
            abort=AsyncMock(), continue_=AsyncMock(),
        )
        await self.service._route_request(route)
        route.continue_.assert_awaited_once()
        route.abort.assert_not_awaited()

    async def test_unexpected_guard_error_aborts_without_secret_logging(self):
        route = types.SimpleNamespace(
            request=types.SimpleNamespace(url="https://example.test/?secret"),
            abort=AsyncMock(), continue_=AsyncMock(),
        )
        self.service._check_request_url_safe = AsyncMock(side_effect=RuntimeError("secret"))
        with self.assertLogs(browser_module.logger, "WARNING") as logs:
            await self.service._route_request(route)
        route.abort.assert_awaited_once()
        route.continue_.assert_not_awaited()
        self.assertNotIn("secret", "\n".join(logs.output))


class BrowserLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = types.SimpleNamespace(BROWSER_ENGINE="chromium", PROXY_URL="")
        self.page = types.SimpleNamespace(
            set_default_navigation_timeout=Mock(),
            goto=AsyncMock(), title=AsyncMock(return_value="Example"),
            evaluate=AsyncMock(return_value="Page text"), url="https://example.test/",
            screenshot=AsyncMock(return_value=b"png"),
            click=AsyncMock(), fill=AsyncMock(), query_selector=AsyncMock(),
        )
        self.context = types.SimpleNamespace(
            route=AsyncMock(), new_page=AsyncMock(return_value=self.page), close=AsyncMock(),
        )
        self.browser = types.SimpleNamespace(
            new_context=AsyncMock(return_value=self.context), close=AsyncMock(),
        )
        self.playwright = types.SimpleNamespace(
            chromium=types.SimpleNamespace(launch=AsyncMock(return_value=self.browser)),
            firefox=types.SimpleNamespace(launch=AsyncMock(return_value=self.browser)),
            stop=AsyncMock(),
        )
        self.manager = types.SimpleNamespace(start=AsyncMock(return_value=self.playwright))
        api = types.ModuleType("playwright.async_api")
        api.async_playwright = Mock(return_value=self.manager)
        package = types.ModuleType("playwright")
        package.__path__ = []
        for patcher in (
            patch.object(browser_module, "get_settings", return_value=self.settings),
            patch.dict(sys.modules, {"playwright": package, "playwright.async_api": api}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = BrowserService()
        self.addAsyncCleanup(self.service.close)

    async def test_chromium_default_options_and_private_context(self):
        await self.service.start()
        self.playwright.chromium.launch.assert_awaited_once_with(
            headless=True, proxy=None, args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self.playwright.firefox.launch.assert_not_awaited()
        self.browser.new_context.assert_awaited_once_with(
            viewport={"width": 1280, "height": 720},
            user_agent="AI-Companion/1.0 (browser-automation)",
            permissions=[], service_workers="block", accept_downloads=False,
        )
        self.context.route.assert_awaited_once_with("**/*", self.service._route_request)
        self.page.set_default_navigation_timeout.assert_called_once_with(30_000)

    async def test_firefox_has_no_chromium_flags_and_proxy_is_not_logged(self):
        self.settings.BROWSER_ENGINE = "firefox"
        self.settings.PROXY_URL = "http://alice:proxy-secret@proxy.example:3128/?token=secret"
        with self.assertLogs(browser_module.logger, "INFO") as logs:
            await self.service.start()
        self.playwright.firefox.launch.assert_awaited_once_with(
            headless=True, proxy={"server": self.settings.PROXY_URL},
        )
        self.playwright.chromium.launch.assert_not_awaited()
        self.assertNotIn("alice", "\n".join(logs.output))
        self.assertNotIn("secret", "\n".join(logs.output))
        self.assertNotIn("proxy.example", "\n".join(logs.output))

    async def test_invalid_engine_rejected_even_if_settings_replaced(self):
        self.settings.BROWSER_ENGINE = "webkit"
        with self.assertRaises(ValueError):
            await self.service.start()
        self.manager.start.assert_not_awaited()

    async def test_concurrent_start_is_idempotent(self):
        await asyncio.gather(self.service.start(), self.service.start(), self.service.start())
        self.manager.start.assert_awaited_once()
        self.context.new_page.assert_awaited_once()

    async def test_launch_failure_stops_driver_and_sanitizes_error(self):
        self.playwright.chromium.launch.side_effect = RuntimeError("proxy-secret")
        with self.assertLogs(browser_module.logger, "WARNING") as logs:
            with self.assertRaises(RuntimeError) as caught:
                await self.service.start()
        self.playwright.stop.assert_awaited_once()
        self.assertIsNone(self.service.playwright)
        self.assertIsNone(self.service.page)
        self.assertNotIn("proxy-secret", str(caught.exception) + "\n".join(logs.output))
        self.assertTrue(caught.exception.__suppress_context__)

    async def test_context_creation_failure_closes_browser_and_driver(self):
        self.browser.new_context.side_effect = RuntimeError("private details")
        with self.assertLogs(browser_module.logger, "WARNING"):
            with self.assertRaises(RuntimeError):
                await self.service.start()
        self.browser.close.assert_awaited_once()
        self.playwright.stop.assert_awaited_once()

    async def test_route_install_failure_closes_context_before_browser(self):
        self.context.route.side_effect = RuntimeError("private details")
        events = []
        for obj, method, label in (
            (self.context, "close", "context"),
            (self.browser, "close", "browser"),
            (self.playwright, "stop", "driver"),
        ):
            getattr(obj, method).side_effect = lambda label=label: events.append(label)
        with self.assertLogs(browser_module.logger, "WARNING"):
            with self.assertRaises(RuntimeError):
                await self.service.start()
        self.assertEqual(events, ["context", "browser", "driver"])
        self.context.new_page.assert_not_awaited()

    async def test_page_creation_failure_releases_all_resources(self):
        self.context.new_page.side_effect = RuntimeError("private details")
        with self.assertLogs(browser_module.logger, "WARNING"):
            with self.assertRaises(RuntimeError):
                await self.service.start()
        self.context.close.assert_awaited_once()
        self.browser.close.assert_awaited_once()
        self.playwright.stop.assert_awaited_once()
        self.assertIsNone(self.service.context)

    async def test_cancellation_during_start_cleans_up_and_propagates(self):
        self.context.new_page.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.service.start()
        self.context.close.assert_awaited_once()
        self.browser.close.assert_awaited_once()
        self.playwright.stop.assert_awaited_once()
        self.assertIsNone(self.service.page)

    async def test_close_attempts_all_resources_despite_errors_and_is_idempotent(self):
        await self.service.start()
        self.context.close.side_effect = RuntimeError("proxy-secret")
        self.browser.close.side_effect = RuntimeError("proxy-secret")
        with self.assertLogs(browser_module.logger, "WARNING") as logs:
            await self.service.close()
        await self.service.close()
        self.context.close.assert_awaited_once()
        self.browser.close.assert_awaited_once()
        self.playwright.stop.assert_awaited_once()
        self.assertNotIn("proxy-secret", "\n".join(logs.output))
        for attribute in ("page", "context", "browser", "playwright"):
            self.assertIsNone(getattr(self.service, attribute))

    async def test_restart_after_close(self):
        await self.service.start()
        await self.service.close()
        await self.service.start()
        self.assertEqual(self.manager.start.await_count, 2)

    async def test_cleanup_cancellation_still_attempts_remaining_resources(self):
        await self.service.start()
        self.context.close.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.service.close()
        self.browser.close.assert_awaited_once()
        self.playwright.stop.assert_awaited_once()
        self.assertIsNone(self.service.page)

    async def test_navigation_failures_do_not_disclose_urls_or_raw_errors(self):
        await self.service.start()
        self.page.goto.side_effect = RuntimeError("proxy-secret")
        self.service._check_request_url_safe = AsyncMock(return_value=None)
        self.service._min_nav_interval = 0
        with self.assertLogs(browser_module.logger, "WARNING") as logs:
            result = await self.service.navigate("https://example.test/?token=secret")
            with self.assertRaises(RuntimeError) as caught:
                await self.service.screenshot("https://example.test/?token=secret")
        combined = str(result) + str(caught.exception) + "\n".join(logs.output)
        self.assertNotIn("secret", combined)
        self.assertNotIn("example.test", combined)

    async def test_interaction_errors_do_not_log_selectors_text_or_scripts(self):
        await self.service.start()
        for operation in (self.page.click, self.page.fill, self.page.evaluate,
                          self.page.query_selector):
            operation.side_effect = RuntimeError("proxy-secret")
        with self.assertLogs(browser_module.logger, "WARNING") as logs:
            results = [
                await self.service.click("[data-secret]"),
                await self.service.type_text("[data-secret]", "secret-value"),
                await self.service.execute_js("'secret-script'"),
                await self.service.extract({"value": "[data-secret]"}),
            ]
        self.assertNotIn("secret", str(results) + "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
