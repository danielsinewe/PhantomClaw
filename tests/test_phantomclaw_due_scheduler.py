from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from scripts.phantomclaw_run_due_automations import due_occurrence_key


class PhantomClawDueSchedulerTests(unittest.TestCase):
    def test_weekly_all_days_rule_is_due_at_matching_time(self) -> None:
        automation = {
            "id": "leetcode-daily",
            "rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR,SA,SU;BYHOUR=8;BYMINUTE=45",
        }
        now = datetime(2026, 4, 22, 8, 45, tzinfo=ZoneInfo("Europe/Berlin"))
        self.assertEqual(due_occurrence_key(automation, now), "leetcode-daily:WE:2026-04-22:08:45")

    def test_weekly_rule_is_not_due_on_wrong_day(self) -> None:
        automation = {
            "id": "weekly-seo-rollout-check",
            "rrule": "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=40",
        }
        now = datetime(2026, 4, 22, 9, 40, tzinfo=ZoneInfo("Europe/Berlin"))
        self.assertIsNone(due_occurrence_key(automation, now))

    def test_hourly_rule_respects_minute(self) -> None:
        automation = {
            "id": "daily-product-hunt-forums-check",
            "rrule": "FREQ=HOURLY;INTERVAL=1;BYMINUTE=0;BYDAY=SU,MO,TU,WE,TH,FR,SA",
        }
        due = datetime(2026, 4, 22, 14, 0, tzinfo=ZoneInfo("Europe/Berlin"))
        not_due = datetime(2026, 4, 22, 14, 5, tzinfo=ZoneInfo("Europe/Berlin"))
        self.assertEqual(due_occurrence_key(automation, due), "daily-product-hunt-forums-check:2026-04-22T14:00")
        self.assertIsNone(due_occurrence_key(automation, not_due))


if __name__ == "__main__":
    unittest.main()
