from pathlib import Path
import unittest

from linkedin.company_profile_engagement.parser import parse_browser_payload, parse_feed_html


FIXTURES = Path("tests/fixtures")


class ParserTests(unittest.TestCase):
    def test_parse_normal_feed_fixture(self) -> None:
        html = (FIXTURES / "normal_feed.html").read_text()
        snapshot = parse_feed_html(html, "Example Company")
        self.assertTrue(snapshot.actor_verified)
        self.assertTrue(snapshot.search_shape_ok)
        self.assertEqual(len(snapshot.posts), 2)
        self.assertEqual(snapshot.posts[0].post_id, "urn:li:activity:1001")
        self.assertEqual(snapshot.posts[0].post_url, "https://www.linkedin.com/feed/update/urn:li:activity:1001")
        self.assertEqual(snapshot.posts[0].comments[1].parent_comment_id, "comment-1")

    def test_parse_promoted_fixture(self) -> None:
        html = (FIXTURES / "promoted_feed.html").read_text()
        snapshot = parse_feed_html(html, "Example Company")
        self.assertTrue(snapshot.posts[0].sponsored)
        self.assertTrue(snapshot.posts[0].already_liked)

    def test_parse_actor_missing_fixture(self) -> None:
        html = (FIXTURES / "actor_missing.html").read_text()
        snapshot = parse_feed_html(html, "Example Company")
        self.assertFalse(snapshot.actor_verified)
        self.assertIsNone(snapshot.actor_name)

    def test_parse_browser_payload_maps_activity_ids_from_html(self) -> None:
        payload = """
        {
          "actor_name": null,
          "actor_verified": false,
          "search_shape_ok": true,
          "search_markers": ["keyword:opportunities", "content-view", "latest-sort", "photo-filter", "org-filter"],
          "challenge_signals": [],
          "posts": [
            {
              "post_id": "fp-111",
              "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:1001",
              "text": "Post one",
              "sponsored": false,
              "already_liked": false,
              "interactable": true,
              "like_selector": "card:0:like",
              "comments_expanded": false,
              "comment_toggle_selector": "card:0:comment-toggle",
              "reply_toggle_selectors": [],
              "comments": []
            },
            {
              "post_id": "fp-222",
              "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:1002",
              "text": "Post two",
              "sponsored": false,
              "already_liked": false,
              "interactable": true,
              "like_selector": "card:1:like",
              "comments_expanded": false,
              "comment_toggle_selector": "card:1:comment-toggle",
              "reply_toggle_selectors": [],
              "comments": []
            }
          ]
        }
        """
        html = """
        <script>
        commentsSectionAnchor-urn:li:activity:1001
        commentsSectionAnchor-urn:li:activity:1001
        commentsSectionAnchor-urn:li:activity:1002
        </script>
        """
        snapshot = parse_browser_payload(payload, "Example Company", html)
        self.assertEqual(snapshot.posts[0].post_id, "urn:li:activity:1001")
        self.assertEqual(snapshot.posts[0].post_url, "https://www.linkedin.com/feed/update/urn:li:activity:1001")
        self.assertEqual(snapshot.posts[1].post_id, "urn:li:activity:1002")

    def test_parse_browser_payload_ignores_internal_actor_state_blob(self) -> None:
        payload = """
        {
          "actor_name": "identitySwitcherActorContext-urn:li:activity:12345 proto.sdui.State commentBoxText-abc",
          "actor_verified": true,
          "search_shape_ok": true,
          "search_markers": ["keyword:opportunities", "content-view", "latest-sort", "photo-filter", "org-filter"],
          "challenge_signals": [],
          "posts": []
        }
        """
        html = """
        <div>acting as Example Company</div>
        <div>opportunities posts latest photo organization filter</div>
        """
        snapshot = parse_browser_payload(payload, "Example Company", html)
        self.assertTrue(snapshot.actor_verified)
        self.assertEqual(snapshot.actor_name, "Example Company")


if __name__ == "__main__":
    unittest.main()
