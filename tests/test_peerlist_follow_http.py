import argparse
import unittest

from scripts.run_peerlist_follow_http import (
    filter_candidates,
    normalize_relationship,
    relation_me_follows_target,
    relation_target_follows_me,
    relation_verified_as_followed,
    relation_verified_as_unfollowed,
)


class PeerlistFollowHTTPTests(unittest.TestCase):
    def test_peerlist_relationship_direction_helpers(self) -> None:
        self.assertTrue(relation_me_follows_target({"follower": True, "following": False, "peer": False}))
        self.assertTrue(relation_me_follows_target({"follower": {"lists": []}, "following": False, "peer": False}))
        self.assertFalse(relation_me_follows_target({"follower": False, "following": True, "peer": False}))
        self.assertTrue(relation_target_follows_me({"follower": False, "following": True, "peer": False}))
        self.assertFalse(relation_target_follows_me({"follower": True, "following": False, "peer": False}))
        self.assertTrue(relation_verified_as_followed({"follower": True, "following": False, "peer": False}))
        self.assertTrue(relation_verified_as_unfollowed({"follower": False, "following": True, "peer": False}))
        self.assertFalse(relation_verified_as_unfollowed({"follower": True, "following": False, "peer": False}))
        self.assertEqual(
            normalize_relationship({"follower": {"lists": []}, "following": False, "isPeers": False}),
            {"follower": True, "following": False, "peer": False},
        )

    def test_filter_skips_existing_following_using_peerlist_follower_field(self) -> None:
        args = argparse.Namespace(
            profile_blacklist=[],
            profile_whitelist=[],
            require_verified_profile=False,
            skip_peers=True,
            skip_existing_following=True,
            skip_existing_followers=False,
        )
        candidates = [
            {
                "target_handle": "alreadyfollowed",
                "verified_profile": False,
                "relationship": {"follower": True, "following": False, "peer": False},
            },
            {
                "target_handle": "followsme",
                "verified_profile": False,
                "relationship": {"follower": False, "following": True, "peer": False},
            },
        ]

        accepted, skipped = filter_candidates(candidates, args=args, self_handle="danielsinewe")

        self.assertEqual([item["target_handle"] for item in accepted], ["followsme"])
        self.assertEqual(skipped[0]["reason"], "already_following")


if __name__ == "__main__":
    unittest.main()
