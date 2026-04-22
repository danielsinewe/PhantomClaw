import json
from pathlib import Path
import unittest

from automation_catalog import (
    PEERLIST_FOLLOW_WORKFLOW,
    PEERLIST_NETWORK_SURFACE,
    PEERLIST_PLATFORM,
    PEERLIST_PROFILE_FOLLOWERS_METRIC,
    automation_default_parameters,
    automation_kind,
    automation_north_star_metric,
    automation_surface,
)


BUNDLE_DIR = Path("bundles/peerlist-follow-workflow")


class PeerlistBundleManifestTests(unittest.TestCase):
    def load_manifest(self) -> dict:
        return json.loads((BUNDLE_DIR / "bundle.json").read_text())

    def load_schema(self) -> dict:
        return json.loads((BUNDLE_DIR / "schema.json").read_text())

    def test_manifest_matches_catalog_identity(self) -> None:
        manifest = self.load_manifest()

        self.assertEqual(manifest["name"], PEERLIST_FOLLOW_WORKFLOW)
        self.assertEqual(manifest["platform"], PEERLIST_PLATFORM)
        self.assertEqual(manifest["surface"], PEERLIST_NETWORK_SURFACE)
        self.assertEqual(manifest["kind"], automation_kind(PEERLIST_FOLLOW_WORKFLOW))
        self.assertEqual(manifest["surface"], automation_surface(PEERLIST_FOLLOW_WORKFLOW))
        self.assertEqual(manifest["north_star_metric"], PEERLIST_PROFILE_FOLLOWERS_METRIC)
        self.assertEqual(manifest["north_star_metric"], automation_north_star_metric(PEERLIST_FOLLOW_WORKFLOW))

    def test_manifest_defaults_match_catalog_defaults(self) -> None:
        manifest = self.load_manifest()
        defaults = automation_default_parameters(PEERLIST_FOLLOW_WORKFLOW)

        self.assertEqual(manifest["parameters"], defaults)
        self.assertEqual(defaults["follows_per_day"], 3)
        self.assertEqual(defaults["max_follows_per_run"], 1)
        self.assertTrue(defaults["do_not_unfollow_peers"])
        self.assertTrue(defaults["skip_peers"])

    def test_manifest_declares_required_safety_and_outputs(self) -> None:
        manifest = self.load_manifest()

        self.assertEqual(manifest["default_mode"], "dry-run")
        self.assertEqual(manifest["runner"]["entrypoint"], "/usr/local/bin/run-peerlist-follow-workflow.sh")
        self.assertEqual(manifest["runner"]["default_backend"], "peerlist-http")
        self.assertIn("openclaw-railway", manifest["runtimes"])
        self.assertIn("PEERLIST_COOKIES_JSON", manifest["secrets"])
        self.assertEqual(manifest["safety"]["explicit_live_flag"], "PEERLIST_FOLLOW_LIVE=1")
        self.assertEqual(manifest["safety"]["daily_cap_source"], "automation_action_events_v1")
        self.assertEqual(manifest["safety"]["per_run_cap_parameter"], "max_follows_per_run")
        self.assertEqual(manifest["outputs"]["run_bundle_schema"], "phantomclaw.run-bundle.v1")
        self.assertEqual(manifest["outputs"]["daily_metrics"], "automation_daily_metrics_v1")

    def test_schema_requires_core_bundle_sections(self) -> None:
        schema = self.load_schema()

        required = set(schema["required"])
        self.assertIn("name", required)
        self.assertIn("north_star_metric", required)
        self.assertIn("parameters", required)
        self.assertIn("safety", required)
        self.assertEqual(schema["properties"]["name"]["const"], PEERLIST_FOLLOW_WORKFLOW)
        self.assertEqual(schema["properties"]["north_star_metric"]["const"], PEERLIST_PROFILE_FOLLOWERS_METRIC)

    def test_bundle_docs_and_examples_exist(self) -> None:
        for relative in [
            "README.md",
            "SKILL.md",
            "CHANGELOG.md",
            "examples/dry-run.sh",
            "examples/live-capped.sh",
            "fixtures/verified-follow-report.json",
            "fixtures/daily-cap-report.json",
        ]:
            self.assertTrue((BUNDLE_DIR / relative).is_file(), relative)

    def test_fixture_reports_match_expected_bundle_outcomes(self) -> None:
        verified = json.loads((BUNDLE_DIR / "fixtures/verified-follow-report.json").read_text())
        capped = json.loads((BUNDLE_DIR / "fixtures/daily-cap-report.json").read_text())

        self.assertEqual(verified["status"], "ok")
        self.assertEqual(verified["follows_count"], 1)
        self.assertEqual(verified["events"][0]["type"], "peerlist_profile_followed")
        self.assertTrue(verified["events"][0]["verified"])
        self.assertEqual(capped["status"], "no_action")
        self.assertEqual(capped["daily_follows_remaining"], 0)
        self.assertEqual(capped["skipped"][0]["type"], "daily_follow_cap_reached")


if __name__ == "__main__":
    unittest.main()
