import unittest

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


if __name__ == "__main__":
    unittest.main()
