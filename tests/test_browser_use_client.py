import os
import subprocess
import unittest
from unittest.mock import patch

from linkedin.company_profile_engagement.browser_use_client import BrowserUseClient, BrowserUseError


class BrowserUseClientTests(unittest.TestCase):
    def test_urls_match_requires_same_host_path_and_query_subset(self) -> None:
        self.assertTrue(
            BrowserUseClient._urls_match(
                "https://www.linkedin.com/company/109821516/admin/dashboard/?manageFollowing=true&foo=bar",
                "https://www.linkedin.com/company/109821516/admin/dashboard/?manageFollowing=true",
            )
        )
        self.assertFalse(
            BrowserUseClient._urls_match(
                "https://www.linkedin.com/search/results/content/?keywords=opportunities",
                "https://www.linkedin.com/company/109821516/admin/dashboard/?manageFollowing=true",
            )
        )

    def test_focus_tab_for_url_switches_until_expected_tab(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.urls = [
                    "https://app-eu1.hubspot.com/contacts/26629482/objects/0-3/views/all/board?noprefetch=",
                    "https://tasks.google.com/tasks/",
                    "https://www.linkedin.com/company/109821516/admin/dashboard/?manageFollowing=true",
                ]
                self.index = 0
                self.switches: list[int] = []

            def get_page_state(self) -> dict[str, object]:
                return {"url": self.urls[self.index], "title": "", "has_actor_selector": False, "logged_out": False}

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
        BrowserUseClient._focus_tab_for_url(client, "https://www.linkedin.com/company/109821516/admin/dashboard/?manageFollowing=true")
        self.assertEqual(client.index, 2)
        self.assertEqual(client.switches, [0, 1, 2])

    def test_run_raises_browser_use_error_on_timeout(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)
        client.binary = "browser-use"
        client.session_name = "session"
        client.chrome_profile = "profile"
        client.browser_start_timeout_seconds = 60.0
        client.command_timeout_seconds = 12.0

        with patch(
            "linkedin.company_profile_engagement.browser_use_client.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["browser-use"], timeout=12.0),
        ):
            with self.assertRaises(BrowserUseError) as ctx:
                client._run("open", "https://www.linkedin.com/")

        self.assertIn("timed out after 12s", str(ctx.exception))
        self.assertIn("open https://www.linkedin.com/", str(ctx.exception))

    def test_run_passes_browser_start_timeout_to_subprocess_env(self) -> None:
        client = BrowserUseClient.__new__(BrowserUseClient)
        client.binary = "browser-use"
        client.session_name = "session"
        client.chrome_profile = "profile"
        client.browser_start_timeout_seconds = 75.0
        client.command_timeout_seconds = 120.0
        seen_env: dict[str, str] = {}

        def fake_run(*args, **kwargs):
            nonlocal seen_env
            seen_env = kwargs["env"]
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok", stderr="")

        with patch("linkedin.company_profile_engagement.browser_use_client.subprocess.run", side_effect=fake_run):
            result = client._run("open", "https://www.linkedin.com/")

        self.assertEqual(result, "ok")
        self.assertEqual(seen_env["TIMEOUT_BrowserStartEvent"], "75")

    def test_init_keeps_command_timeout_above_browser_start_timeout(self) -> None:
        with patch.object(BrowserUseClient, "_resolve_binary", return_value="browser-use"), patch.dict(os.environ, {}, clear=False):
            client = BrowserUseClient(session_name="session", chrome_profile="profile")

        self.assertEqual(client.browser_start_timeout_seconds, 120.0)
        self.assertGreaterEqual(client.command_timeout_seconds, 150.0)


if __name__ == "__main__":
    unittest.main()
