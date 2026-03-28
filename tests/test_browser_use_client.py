import unittest

from trustoutreach_linkedin.browser_use_client import BrowserUseClient, BrowserUseError


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


if __name__ == "__main__":
    unittest.main()
