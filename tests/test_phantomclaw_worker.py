from __future__ import annotations

import json
import os
from argparse import Namespace
from datetime import datetime
from datetime import timedelta
import sys
from zoneinfo import ZoneInfo
import unittest
from unittest.mock import patch

from phantomclaw_worker import (
    DueAutomation,
    STALE_CLAIMED_MINUTES,
    claim_due_automation,
    dispatch_status_for_result,
    due_occurrence_key,
    execute_due_automation,
    load_due_automations,
    namespace_for_peerlist,
    native_command_for,
    native_status_from_stdout,
    recent_due_occurrences,
    recent_expected_occurrences,
    registry_entry_parameters,
)


class FakeCursor:
    def __init__(self, *, rowcount: int = 0, rows: list[tuple[object, ...]] | None = None) -> None:
        self.rowcount = rowcount
        self.rows = rows or []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> None:
        self.calls.append((query, params))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.fake_cursor = cursor
        self.committed = False

    def cursor(self) -> FakeCursor:
        return self.fake_cursor

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class PhantomClawWorkerTests(unittest.TestCase):
    def test_hourly_rrule_supports_byhour_without_redeploy_schedule(self) -> None:
        now = datetime(2026, 4, 23, 9, 7, tzinfo=ZoneInfo("Europe/Berlin"))

        self.assertEqual(
            due_occurrence_key(
                "peerlist-follow-workflow",
                "FREQ=HOURLY;INTERVAL=2;BYDAY=MO,TU,WE,TH,FR,SA,SU;BYHOUR=9,11,13,15,17,19,21;BYMINUTE=7",
                now,
            ),
            "peerlist-follow-workflow:2026-04-23T09:07",
        )
        self.assertIsNone(
            due_occurrence_key(
                "peerlist-follow-workflow",
                "FREQ=HOURLY;INTERVAL=2;BYDAY=MO,TU,WE,TH,FR,SA,SU;BYHOUR=9,11,13,15,17,19,21;BYMINUTE=7",
                datetime(2026, 4, 23, 10, 7, tzinfo=ZoneInfo("Europe/Berlin")),
            )
        )

    def test_recent_expected_occurrences_finds_missed_scheduler_slots(self) -> None:
        occurrences = recent_expected_occurrences(
            "peerlist-follow-workflow",
            "FREQ=HOURLY;INTERVAL=2;BYDAY=MO,TU,WE,TH,FR,SA,SU;BYHOUR=9,11,13;BYMINUTE=7",
            now=datetime(2026, 4, 23, 13, 30, tzinfo=ZoneInfo("Europe/Berlin")),
            timezone_name="Europe/Berlin",
            lookback_hours=5,
        )

        self.assertEqual(
            occurrences,
            [
                "peerlist-follow-workflow:2026-04-23T09:07",
                "peerlist-follow-workflow:2026-04-23T11:07",
                "peerlist-follow-workflow:2026-04-23T13:07",
            ],
        )

    def test_recent_due_occurrences_catches_worker_drift(self) -> None:
        occurrences = recent_due_occurrences(
            "trustoutreach-linkedin",
            "FREQ=HOURLY;INTERVAL=1;BYMINUTE=0;BYDAY=SU,MO,TU,WE,TH,FR,SA",
            now=datetime(2026, 5, 2, 8, 1, 1, tzinfo=ZoneInfo("Europe/Berlin")),
            catchup_minutes=3,
        )

        self.assertIn("trustoutreach-linkedin:2026-05-02T08:00", occurrences)

    def test_claim_due_automation_reclaims_stale_claimed_dispatch(self) -> None:
        due = DueAutomation(
            workspace_slug="daniel-sinewe",
            automation_id="trustoutreach-linkedin",
            automation_name="LinkedIn Company Profile Engagement",
            timezone="Europe/Berlin",
            rrule="FREQ=HOURLY;INTERVAL=1;BYMINUTE=0",
            platform="linkedin",
            surface="core",
            runner_status="native",
            runner_dispatch="phantomclaw_native",
            runner_command=["python3", "-m", "linkedin.company_profile_engagement.runner"],
            runner_dry_run_command=[],
            parameters={"live_enabled": True},
            metadata={},
            occurrence_key="trustoutreach-linkedin:2026-05-18T09:00",
        )
        cursor = FakeCursor(rowcount=1)
        connection = FakeConnection(cursor)

        with patch("phantomclaw_worker.connect", return_value=connection):
            claimed = claim_due_automation("postgresql://example", due)

        self.assertTrue(claimed)
        self.assertTrue(connection.committed)
        query, params = cursor.calls[0]
        self.assertIn("ON CONFLICT (workspace_slug, automation_id, occurrence_key) DO UPDATE", query)
        self.assertIn("reclaimed_from_stale", query)
        self.assertIn("phantomclaw_dispatches.status = 'claimed'", query)
        self.assertIn("phantomclaw_dispatches.finished_at IS NULL", query)
        self.assertEqual(
            params,
            (
                "daniel-sinewe",
                "trustoutreach-linkedin",
                "trustoutreach-linkedin:2026-05-18T09:00",
                STALE_CLAIMED_MINUTES,
            ),
        )

    def test_load_due_automations_returns_stale_claimed_occurrence_for_retry(self) -> None:
        now = datetime(2026, 5, 18, 9, 35, tzinfo=ZoneInfo("Europe/Berlin"))
        occurrence_key = "trustoutreach-linkedin:2026-05-18T09:00"
        active_rows = [
            (
                "daniel-sinewe",
                "trustoutreach-linkedin",
                "LinkedIn Company Profile Engagement",
                "Europe/Berlin",
                "FREQ=HOURLY;INTERVAL=1;BYMINUTE=0;BYDAY=SU,MO,TU,WE,TH,FR,SA",
                "linkedin",
                "core",
                "native",
                "phantomclaw_native",
                json.dumps(["python3", "-m", "linkedin.company_profile_engagement.runner"]),
                json.dumps([]),
                json.dumps({"live_enabled": True}),
                json.dumps({}),
            )
        ]
        dispatch_rows = [
            (
                occurrence_key,
                "claimed",
                now - timedelta(minutes=STALE_CLAIMED_MINUTES + 1),
                None,
            )
        ]
        cursors = [FakeCursor(rows=active_rows), FakeCursor(rows=dispatch_rows)]

        with patch("phantomclaw_worker.ensure_worker_schema"):
            with patch("phantomclaw_worker.connect", side_effect=[FakeConnection(cursors[0]), FakeConnection(cursors[1])]):
                due = load_due_automations(
                    "postgresql://example",
                    workspace_slug="daniel-sinewe",
                    now=now,
                    catchup_minutes=40,
                )

        self.assertEqual([item.occurrence_key for item in due], [occurrence_key])

    def test_load_due_automations_skips_fresh_claimed_occurrence(self) -> None:
        now = datetime(2026, 5, 18, 9, 5, tzinfo=ZoneInfo("Europe/Berlin"))
        occurrence_key = "trustoutreach-linkedin:2026-05-18T09:00"
        active_rows = [
            (
                "daniel-sinewe",
                "trustoutreach-linkedin",
                "LinkedIn Company Profile Engagement",
                "Europe/Berlin",
                "FREQ=HOURLY;INTERVAL=1;BYMINUTE=0;BYDAY=SU,MO,TU,WE,TH,FR,SA",
                "linkedin",
                "core",
                "native",
                "phantomclaw_native",
                json.dumps(["python3", "-m", "linkedin.company_profile_engagement.runner"]),
                json.dumps([]),
                json.dumps({"live_enabled": True}),
                json.dumps({}),
            )
        ]
        dispatch_rows = [(occurrence_key, "claimed", now - timedelta(minutes=2), None)]
        cursors = [FakeCursor(rows=active_rows), FakeCursor(rows=dispatch_rows)]

        with patch("phantomclaw_worker.ensure_worker_schema"):
            with patch("phantomclaw_worker.connect", side_effect=[FakeConnection(cursors[0]), FakeConnection(cursors[1])]):
                due = load_due_automations(
                    "postgresql://example",
                    workspace_slug="daniel-sinewe",
                    now=now,
                    catchup_minutes=10,
                )

        self.assertEqual(due, [])

    def test_registry_entry_parameters_merges_peerlist_defaults(self) -> None:
        params = registry_entry_parameters(
            {
                "id": "peerlist-follow-workflow",
                "parameters": {
                    "type": "unfollow",
                    "max_unfollows_per_run": 1000,
                },
            }
        )

        self.assertEqual(params["type"], "unfollow")
        self.assertEqual(params["follows_per_day"], 30)
        self.assertEqual(params["unfollows_per_day"], 1400)
        self.assertEqual(params["max_unfollows_per_run"], 1000)
        self.assertTrue(params["do_not_unfollow_peers"])
        self.assertTrue(params["do_not_unfollow_followers"])

    def test_peerlist_namespace_uses_neon_parameters(self) -> None:
        due = DueAutomation(
            workspace_slug="daniel-sinewe",
            automation_id="peerlist-follow-workflow",
            automation_name="Peerlist Follow Workflow",
            timezone="Europe/Berlin",
            rrule="FREQ=HOURLY;INTERVAL=2;BYMINUTE=7",
            platform="peerlist",
            surface="network",
            runner_status="native",
            runner_dispatch="openclaw_railway_host_command",
            runner_command=["/usr/local/bin/run-peerlist-follow-workflow.sh"],
            runner_dry_run_command=[],
            parameters={"type": "unfollow", "max_follows_per_run": 0, "max_unfollows_per_run": 1000},
            metadata={},
            occurrence_key="peerlist-follow-workflow:2026-04-23T09:07",
        )

        args = namespace_for_peerlist(
            due,
            live=True,
            database_url="postgresql://example",
            artifact_root=None,
        )

        self.assertIsInstance(args, Namespace)
        self.assertTrue(args.live)
        self.assertFalse(args.dry_run)
        self.assertEqual(args.workspace_slug, "daniel-sinewe")
        self.assertEqual(args.workflow_type, "unfollow")
        self.assertEqual(args.max_follows_per_run, 0)
        self.assertEqual(args.follows_per_day, 30)
        self.assertEqual(args.unfollows_per_day, 1400)
        self.assertEqual(args.max_unfollows_per_run, 1000)
        self.assertTrue(args.sync_blocked)

    def test_execute_generic_native_dry_run_command(self) -> None:
        due = DueAutomation(
            workspace_slug="daniel-sinewe",
            automation_id="linkedin-sales-community",
            automation_name="LinkedIn Sales Community Engagement",
            timezone="Europe/Berlin",
            rrule="FREQ=WEEKLY;BYDAY=TH;BYHOUR=9;BYMINUTE=20",
            platform="linkedin",
            surface="sales-community",
            runner_status="native",
            runner_dispatch="phantomclaw_native",
            runner_command=[sys.executable, "-c", "raise SystemExit(99)"],
            runner_dry_run_command=[sys.executable, "-c", "print('native dry run ok')"],
            parameters={},
            metadata={},
            occurrence_key="linkedin-sales-community:TH:2026-04-23:09:20",
        )

        result = execute_due_automation(
            due,
            live=False,
            database_url="postgresql://example",
            artifact_root=None,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mode"], "dry-run")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("native dry run ok", result["stdout"])

    def test_dry_run_only_prevents_live_native_command(self) -> None:
        due = DueAutomation(
            workspace_slug="daniel-sinewe",
            automation_id="linkedin-sales-community",
            automation_name="LinkedIn Sales Community Engagement",
            timezone="Europe/Berlin",
            rrule="FREQ=WEEKLY;BYDAY=TH;BYHOUR=9;BYMINUTE=20",
            platform="linkedin",
            surface="sales-community",
            runner_status="native",
            runner_dispatch="phantomclaw_native",
            runner_command=[sys.executable, "-c", "raise SystemExit(99)"],
            runner_dry_run_command=[sys.executable, "-c", "print('guarded dry run')"],
            parameters={"dry_run_only": True},
            metadata={},
            occurrence_key="linkedin-sales-community:TH:2026-04-23:09:20",
        )

        result = execute_due_automation(
            due,
            live=True,
            database_url="postgresql://example",
            artifact_root=None,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mode"], "dry-run")
        self.assertTrue(result["live_requested"])
        self.assertTrue(result["dry_run_only"])
        self.assertIn("guarded dry run", result["stdout"])

    def test_live_enabled_uses_live_native_command_without_global_live_flag(self) -> None:
        due = DueAutomation(
            workspace_slug="daniel-sinewe",
            automation_id="linkedin-sales-community",
            automation_name="LinkedIn Sales Community Engagement",
            timezone="Europe/Berlin",
            rrule="FREQ=WEEKLY;BYDAY=TH;BYHOUR=9;BYMINUTE=20",
            platform="linkedin",
            surface="sales-community",
            runner_status="native",
            runner_dispatch="phantomclaw_native",
            runner_command=[sys.executable, "-c", "print('live command')"],
            runner_dry_run_command=[sys.executable, "-c", "print('dry command')"],
            parameters={"live_enabled": True, "dry_run_only": False},
            metadata={},
            occurrence_key="linkedin-sales-community:TH:2026-04-23:09:20",
        )

        result = execute_due_automation(
            due,
            live=False,
            database_url="postgresql://example",
            artifact_root=None,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["mode"], "live")
        self.assertFalse(result["live_requested"])
        self.assertTrue(result["live_enabled"])
        self.assertIn("live command", result["stdout"])
        self.assertNotIn("dry command", result["stdout"])

    def test_python_native_command_uses_worker_interpreter(self) -> None:
        due = DueAutomation(
            workspace_slug="daniel-sinewe",
            automation_id="trustoutreach-linkedin",
            automation_name="LinkedIn Company Profile Engagement",
            timezone="Europe/Berlin",
            rrule="FREQ=HOURLY;INTERVAL=1;BYMINUTE=0",
            platform="linkedin",
            surface="core",
            runner_status="native",
            runner_dispatch="phantomclaw_native",
            runner_command=["python3", "-m", "linkedin.company_profile_engagement.runner"],
            runner_dry_run_command=[],
            parameters={"live_enabled": True},
            metadata={},
            occurrence_key="trustoutreach-linkedin:2026-05-06T15:00",
        )

        command = native_command_for(due, live=False)

        self.assertIsNotNone(command)
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1:], ["-m", "linkedin.company_profile_engagement.runner"])

    def test_blocked_result_sets_blocked_dispatch_status(self) -> None:
        self.assertEqual(dispatch_status_for_result({"status": "blocked", "exit_code": 0}), "blocked")
        self.assertEqual(dispatch_status_for_result({"status": "ok", "exit_code": 0}), "ok")
        self.assertEqual(dispatch_status_for_result({"status": "ok", "exit_code": 1}), "failed")

    def test_native_status_reads_blocked_json_stdout(self) -> None:
        self.assertEqual(native_status_from_stdout('{"status":"blocked"}', returncode=0), "blocked")
        self.assertEqual(native_status_from_stdout('plain output', returncode=0), "ok")
        self.assertEqual(native_status_from_stdout('{"status":"ok"}', returncode=1), "failed")

    def test_native_command_receives_due_automation_json(self) -> None:
        due = DueAutomation(
            workspace_slug="daniel-sinewe",
            automation_id="daily-x-reuse-queue",
            automation_name="Daily X Reuse Queue",
            timezone="Europe/Berlin",
            rrule="FREQ=WEEKLY;BYHOUR=10;BYMINUTE=18",
            platform="x",
            surface="timeline",
            runner_status="native_candidate",
            runner_dispatch="openclaw_railway_host_command",
            runner_command=[
                sys.executable,
                "-c",
                "import json, os; data=json.loads(os.environ['PHANTOMCLAW_AUTOMATION_JSON']); print(data['id'], data['platform'], data['parameters']['post_cap'])",
            ],
            runner_dry_run_command=[
                sys.executable,
                "-c",
                "import json, os; data=json.loads(os.environ['PHANTOMCLAW_AUTOMATION_JSON']); print(data['id'], data['platform'], data['parameters']['post_cap'])",
            ],
            parameters={"post_cap": 25},
            metadata={"cwds": [], "source": {"system": "codex"}},
            occurrence_key="daily-x-reuse-queue:2026-04-23:10:18",
        )

        result = execute_due_automation(
            due,
            live=False,
            database_url="postgresql://example",
            artifact_root=None,
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("daily-x-reuse-queue x 25", result["stdout"])

    def test_native_command_receives_linkedin_sales_community_env(self) -> None:
        due = DueAutomation(
            workspace_slug="daniel-sinewe",
            automation_id="linkedin-sales-community",
            automation_name="LinkedIn Sales Community Engagement",
            timezone="Europe/Berlin",
            rrule="FREQ=WEEKLY;BYDAY=TH;BYHOUR=9;BYMINUTE=20",
            platform="linkedin",
            surface="sales-community",
            runner_status="native",
            runner_dispatch="phantomclaw_native",
            runner_command=[
                sys.executable,
                "-c",
                (
                    "import json, os; keys=["
                    "'LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_URL',"
                    "'LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_PROFILE',"
                    "'LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_PROFILE_NAME',"
                    "'LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_LIKE_CAP',"
                    "'LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_REQUIRE_ACTION_VERIFICATION',"
                    "'LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_ANALYTICS_DATABASE_URL',"
                    "'AUTOMATION_ANALYTICS_DATABASE_URL'"
                    "]; print(json.dumps({key: os.environ.get(key) for key in keys}, sort_keys=True))"
                ),
            ],
            runner_dry_run_command=[sys.executable, "-c", "raise SystemExit(99)"],
            parameters={
                "live_enabled": True,
                "url": "https://scommunity.linkedin.com/",
                "chrome_profile": "danielsinewe.com",
                "profile_name": "Daniel",
                "like_cap": 3,
                "require_action_verification": True,
            },
            metadata={},
            occurrence_key="linkedin-sales-community:TH:2026-04-23:09:20",
        )

        with patch.dict(os.environ, {"PHANTOMCLAW_DATABASE_URL": "postgresql://example"}, clear=True):
            result = execute_due_automation(
                due,
                live=False,
                database_url="postgresql://example",
                artifact_root=None,
            )

        self.assertTrue(result["executed"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mode"], "live")
        payload = json.loads(result["stdout"])
        self.assertEqual(payload["LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_URL"], "https://scommunity.linkedin.com/")
        self.assertEqual(payload["LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_PROFILE"], "danielsinewe.com")
        self.assertEqual(payload["LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_PROFILE_NAME"], "Daniel")
        self.assertEqual(payload["LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_LIKE_CAP"], "3")
        self.assertEqual(payload["LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_REQUIRE_ACTION_VERIFICATION"], "1")
        self.assertEqual(payload["LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_ANALYTICS_DATABASE_URL"], "postgresql://example")
        self.assertEqual(payload["AUTOMATION_ANALYTICS_DATABASE_URL"], "postgresql://example")

    def test_native_command_receives_linkedin_company_defaults_env(self) -> None:
        due = DueAutomation(
            workspace_slug="daniel-sinewe",
            automation_id="trustoutreach-linkedin",
            automation_name="LinkedIn Company Profile Engagement",
            timezone="Europe/Berlin",
            rrule="FREQ=HOURLY;INTERVAL=1;BYMINUTE=0",
            platform="linkedin",
            surface="core",
            runner_status="native",
            runner_dispatch="phantomclaw_native",
            runner_command=[
                sys.executable,
                "-c",
                (
                    "import json, os; keys=["
                    "'LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_SEARCH_URL',"
                    "'LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_PROFILE',"
                    "'LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_ACTOR',"
                    "'LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_POST_CAP',"
                    "'LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_ANALYTICS_DATABASE_URL'"
                    "]; print(json.dumps({key: os.environ.get(key) for key in keys}, sort_keys=True))"
                ),
            ],
            runner_dry_run_command=[sys.executable, "-c", "raise SystemExit(99)"],
            parameters={"live_enabled": True, "post_cap": 9},
            metadata={},
            occurrence_key="trustoutreach-linkedin:2026-05-06T15:00",
        )

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True):
            result = execute_due_automation(
                due,
                live=False,
                database_url="postgresql://example",
                artifact_root=None,
            )

        self.assertTrue(result["executed"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mode"], "live")
        payload = json.loads(result["stdout"])
        self.assertIn("mentionsOrganization", payload["LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_SEARCH_URL"])
        self.assertEqual(payload["LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_PROFILE"], "danielsinewe.com")
        self.assertEqual(payload["LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_ACTOR"], "TrustOutreach")
        self.assertEqual(payload["LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_POST_CAP"], "9")
        self.assertEqual(payload["LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_ANALYTICS_DATABASE_URL"], "postgresql://example")

    def test_native_command_timeout_fails_cleanly(self) -> None:
        due = DueAutomation(
            workspace_slug="daniel-sinewe",
            automation_id="daily-x-reuse-queue",
            automation_name="Daily X Reuse Queue",
            timezone="Europe/Berlin",
            rrule="FREQ=WEEKLY;BYHOUR=10;BYMINUTE=18",
            platform="x",
            surface="timeline",
            runner_status="native_candidate",
            runner_dispatch="openclaw_railway_host_command",
            runner_command=[sys.executable, "-c", "import time; print('started', flush=True); time.sleep(5)"],
            runner_dry_run_command=[sys.executable, "-c", "import time; print('started', flush=True); time.sleep(5)"],
            parameters={},
            metadata={},
            occurrence_key="daily-x-reuse-queue:2026-04-23:10:18",
        )

        with patch.dict(os.environ, {"PHANTOMCLAW_NATIVE_TIMEOUT_SECONDS": "1"}, clear=True):
            result = execute_due_automation(
                due,
                live=False,
                database_url="postgresql://example",
                artifact_root=None,
            )

        self.assertTrue(result["executed"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "native_runner_timeout")
        self.assertEqual(result["exit_code"], 124)
        self.assertIn("started", result["stdout"])
        self.assertIn("timed out after 1s", result["stderr"])


if __name__ == "__main__":
    unittest.main()
