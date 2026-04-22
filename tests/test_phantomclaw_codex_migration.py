from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phantomclaw_bundle import validate_run_bundle
from phantomclaw_codex_migration import (
    automation_from_registry,
    build_dispatch_bundle,
    build_registry,
    load_codex_automations,
    normalize_rrule,
    validate_registry,
    write_registry,
)


class PhantomClawCodexMigrationTests(unittest.TestCase):
    def test_normalize_rrule_removes_prefixes(self) -> None:
        self.assertEqual(normalize_rrule("RRULE:FREQ=HOURLY;INTERVAL=1"), "FREQ=HOURLY;INTERVAL=1")
        self.assertEqual(
            normalize_rrule("DTSTART:20260319T000000Z RRULE:FREQ=DAILY;BYHOUR=1"),
            "FREQ=DAILY;BYHOUR=1",
        )

    def test_imports_codex_automations_with_phantomclaw_policy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            automation_dir = root / "trustoutreach-linkedin"
            automation_dir.mkdir()
            (automation_dir / "automation.toml").write_text(
                "\n".join(
                    [
                        'name = "LinkedIn Company Profile Engagement"',
                        'status = "ACTIVE"',
                        'kind = "cron"',
                        'rrule = "RRULE:FREQ=HOURLY;INTERVAL=1"',
                        'cwds = ["/tmp/Automations"]',
                        'model = "gpt-5.4"',
                        'prompt = "Run LinkedIn engagement"',
                    ]
                )
            )
            (automation_dir / "memory.md").write_text("Use fail-closed gates.\n")

            automations = load_codex_automations(root)
            registry = build_registry(automations)
            validate_registry(registry)

            self.assertEqual(len(registry["automations"]), 1)
            migrated = registry["automations"][0]
            self.assertEqual(migrated["processing_system"], "phantomclaw")
            self.assertFalse(migrated["codex_processing_enabled"])
            self.assertEqual(migrated["runner"]["status"], "native")
            self.assertEqual(migrated["rrule"], "FREQ=HOURLY;INTERVAL=1")

    def test_write_registry_and_build_dispatch_bundle(self) -> None:
        with TemporaryDirectory() as tmpdir:
            registry = {
                "schema_version": "phantomclaw.automation-registry.v1",
                "generated_at": "2026-04-22T12:00:00+00:00",
                "source": {"system": "codex", "imported_count": 1},
                "policy": {"processing_system": "phantomclaw", "codex_processing_enabled": False},
                "automations": [
                    {
                        "id": "daily-x-reuse-queue",
                        "name": "Daily X Reuse Queue",
                        "status": "ACTIVE",
                        "source_status": "ACTIVE",
                        "kind": "cron",
                        "rrule": "FREQ=WEEKLY;BYHOUR=10;BYMINUTE=18",
                        "timezone": "Europe/Berlin",
                        "cwds": ["/tmp/Automations"],
                        "execution_environment": None,
                        "model": "gpt-5.3-codex",
                        "reasoning_effort": None,
                        "prompt": "Build a reuse queue",
                        "memory": None,
                        "platform": "x",
                        "surface": "timeline",
                        "runner": {
                            "status": "needs_native_runner",
                            "dispatch": "phantomclaw_bundle_only",
                            "command": None,
                            "codex_fallback_allowed": False,
                        },
                        "source": {"system": "codex", "path": "/tmp/codex/automation.toml"},
                        "processing_system": "phantomclaw",
                        "codex_processing_enabled": False,
                    }
                ],
            }
            output = write_registry(registry, Path(tmpdir) / "registry.json")
            loaded = json.loads(output.read_text())
            automation = automation_from_registry(loaded, "daily-x-reuse-queue")
            bundle = build_dispatch_bundle(automation, run_id="test-run")

            self.assertEqual(bundle["schema_version"], "phantomclaw.run-bundle.v1")
            self.assertEqual(bundle["report"]["processing_system"], "phantomclaw")
            self.assertFalse(bundle["report"]["codex_processing_enabled"])
            validate_run_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
