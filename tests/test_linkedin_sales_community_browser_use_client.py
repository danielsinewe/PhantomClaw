import os
import json
import subprocess
import unittest
from unittest.mock import patch

from linkedin.sales_community_engagement.browser_use_client import BrowserUseClient, BrowserUseError


class LinkedInSalesCommunityBrowserUseClientTests(unittest.TestCase):
    def test_focus_tab_for_url_switches_until_expected_tab(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.urls = [
                    "https://www.linkedin.com/feed/",
                    "https://scommunity.linkedin.com/",
                ]
                self.index = 0
                self.switches: list[int] = []

            def get_page_state(self) -> dict[str, object]:
                return {"url": self.urls[self.index], "title": ""}

            def _page_matches_expected_url(self, expected_url: str) -> bool:
                return BrowserUseClient._page_matches_expected_url(self, expected_url)

            def _urls_match(self, current_url: str, expected_url: str) -> bool:
                return BrowserUseClient._urls_match(current_url, expected_url)

            def _run(self, *args: str) -> str:
                if args[0] != "switch":
                    raise AssertionError(args)
                new_index = int(args[1])
                if new_index >= len(self.urls):
                    raise BrowserUseError(f"Invalid tab index {new_index}. Available: 0-{len(self.urls)-1}")
                self.index = new_index
                self.switches.append(new_index)
                return f"switched: {new_index}"

        client = FakeClient()
        BrowserUseClient._focus_tab_for_url(client, "https://scommunity.linkedin.com/")
        self.assertEqual(client.index, 1)
        self.assertEqual(client.switches, [0, 1])

    def test_run_raises_browser_use_error_on_timeout(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)
        client.binary = "browser-use"
        client.session_name = "session"
        client.chrome_profile = "profile"
        client.cdp_url = None
        client.browser_start_timeout_seconds = 60.0
        client.command_timeout_seconds = 9.0

        with patch(
            "linkedin.sales_community_engagement.browser_use_client.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["browser-use"], timeout=9.0),
        ):
            with self.assertRaises(BrowserUseError) as ctx:
                client._run("state")

        self.assertIn("timed out after 9s", str(ctx.exception))
        self.assertIn("state", str(ctx.exception))

    def test_run_passes_browser_start_timeout_to_subprocess_env(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)
        client.binary = "browser-use"
        client.session_name = "session"
        client.chrome_profile = "profile"
        client.cdp_url = None
        client.browser_start_timeout_seconds = 75.0
        client.command_timeout_seconds = 120.0
        seen_env: dict[str, str] = {}

        def fake_run(*args, **kwargs):
            nonlocal seen_env
            seen_env = kwargs["env"]
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok", stderr="")

        with patch("linkedin.sales_community_engagement.browser_use_client.subprocess.run", side_effect=fake_run):
            result = client._run("open", "https://scommunity.linkedin.com/")

        self.assertEqual(result, "ok")
        self.assertEqual(seen_env["TIMEOUT_BrowserStartEvent"], "75")

    def test_run_retries_transient_websocket_errors(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)
        client.binary = "browser-use"
        client.session_name = "session"
        client.chrome_profile = "profile"
        client.cdp_url = None
        client.browser_start_timeout_seconds = 75.0
        client.command_timeout_seconds = 120.0
        responses = [
            subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Error: WebSocket error: tungstenite error"),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        ]

        with patch("linkedin.sales_community_engagement.browser_use_client.time.sleep") as sleep, patch(
            "linkedin.sales_community_engagement.browser_use_client.subprocess.run",
            side_effect=responses,
        ) as run:
            result = client._run("open", "https://scommunity.linkedin.com/")

        self.assertEqual(result, "ok")
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once()

    def test_run_retries_browser_use_socket_timeout_errors(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)
        client.binary = "browser-use"
        client.session_name = "session"
        client.chrome_profile = "profile"
        client.cdp_url = None
        client.browser_start_timeout_seconds = 75.0
        client.command_timeout_seconds = 120.0
        responses = [
            subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="TimeoutError: timed out"),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        ]

        with patch("linkedin.sales_community_engagement.browser_use_client.time.sleep") as sleep, patch(
            "linkedin.sales_community_engagement.browser_use_client.subprocess.run",
            side_effect=responses,
        ) as run:
            result = client._run("open", "https://scommunity.linkedin.com/")

        self.assertEqual(result, "ok")
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once()

    def test_run_retries_subprocess_timeout_before_raising(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)
        client.binary = "browser-use"
        client.session_name = "session"
        client.chrome_profile = "profile"
        client.cdp_url = None
        client.browser_start_timeout_seconds = 75.0
        client.command_timeout_seconds = 120.0
        responses = [
            subprocess.TimeoutExpired(cmd=["browser-use"], timeout=120.0),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr=""),
        ]

        with patch("linkedin.sales_community_engagement.browser_use_client.time.sleep") as sleep, patch(
            "linkedin.sales_community_engagement.browser_use_client.subprocess.run",
            side_effect=responses,
        ) as run:
            result = client._run("open", "https://scommunity.linkedin.com/")

        self.assertEqual(result, "ok")
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once()

    def test_run_prefers_cdp_url_when_configured(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)
        client.binary = "browser-use"
        client.session_name = "session"
        client.chrome_profile = "profile"
        client.cdp_url = "wss://example.test/devtools/browser/1"
        client.browser_start_timeout_seconds = 75.0
        client.command_timeout_seconds = 120.0
        seen_cmd: list[str] = []

        def fake_run(*args, **kwargs):
            nonlocal seen_cmd
            seen_cmd = args[0]
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok", stderr="")

        with patch("linkedin.sales_community_engagement.browser_use_client.subprocess.run", side_effect=fake_run):
            result = client._run("open", "https://scommunity.linkedin.com/")

        self.assertEqual(result, "ok")
        self.assertIn("--cdp-url", seen_cmd)
        self.assertIn("wss://example.test/devtools/browser/1", seen_cmd)
        self.assertNotIn("--profile", seen_cmd)

    def test_import_linkedin_cookies_from_env_imports_temp_cookie_file(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)
        calls: list[tuple[str, ...]] = []

        def fake_run(*args: str) -> str:
            calls.append(args)
            if args[:2] == ("cookies", "import"):
                with open(args[2]) as handle:
                    cookies = json.load(handle)
                self.assertEqual(cookies[0]["name"], "li_at")
            return "ok"

        client._run = fake_run

        with patch.dict(os.environ, {"LINKEDIN_COOKIES_JSON": '[{"name":"li_at","value":"redacted","domain":".linkedin.com","path":"/"}]'}):
            imported = client.import_linkedin_cookies_from_env()

        self.assertTrue(imported)
        self.assertEqual(calls[0], ("open", "https://www.linkedin.com/"))
        self.assertEqual(calls[1][:2], ("cookies", "import"))

    def test_click_linkedin_oauth_consent_if_safe_returns_false_on_credential_form(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)

        def fake_run(*args: str) -> str:
            self.assertEqual(args[0], "eval")
            return 'result: {"clicked": false, "reason": "credential_form"}'

        client._run = fake_run

        self.assertFalse(client._click_linkedin_oauth_consent_if_safe())

    def test_bootstrap_sales_community_sso_opens_sso_then_original_url(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)
        opened: list[str] = []
        consent_clicks = 0

        def fake_open(url: str) -> None:
            opened.append(url)

        def fake_page_state() -> dict[str, object]:
            return {"url": "https://www.linkedin.com/oauth/v2/login-success", "title": "LinkedIn"}

        def fake_click() -> bool:
            nonlocal consent_clicks
            consent_clicks += 1
            return True

        client.open = fake_open
        client.get_page_state = fake_page_state
        client._click_linkedin_oauth_consent_if_safe = fake_click

        with patch("linkedin.sales_community_engagement.browser_use_client.time.sleep"):
            self.assertTrue(client.bootstrap_sales_community_sso("https://scommunity.linkedin.com/"))

        self.assertEqual(
            opened,
            [
                "https://scommunity.linkedin.com/sso/login?ssoType=linkedin",
                "https://scommunity.linkedin.com/",
            ],
        )
        self.assertEqual(consent_clicks, 1)

    def test_init_keeps_command_timeout_above_browser_start_timeout(self) -> None:
        with patch.object(BrowserUseClient, "_resolve_binary", return_value="browser-use"), patch.dict(os.environ, {}, clear=True):
            client = BrowserUseClient(session_name="session", chrome_profile="profile")

        self.assertEqual(client.browser_start_timeout_seconds, 240.0)
        self.assertGreaterEqual(client.command_timeout_seconds, 270.0)


if __name__ == "__main__":
    unittest.main()
