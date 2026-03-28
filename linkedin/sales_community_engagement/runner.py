from __future__ import annotations

import json
import os
import random
import re
import traceback
import uuid
from pathlib import Path

from automation_catalog import LINKEDIN_PLATFORM, LINKEDIN_SALES_COMMUNITY_ENGAGEMENT, LINKEDIN_SALES_COMMUNITY_SURFACE

if __package__ in {None, ""}:
    import sys

    PACKAGE_ROOT = Path(__file__).resolve().parents[2]
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))

    from automation_analytics import linkedin_sales_community_metrics, upsert_automation_run
    from linkedin.sales_community_engagement.browser_use_client import BrowserUseClient
    from linkedin.sales_community_engagement.models import CommunityItem, CommunityRunReport, CommunitySnapshot, utc_now
    from linkedin.sales_community_engagement.state import StateStore
else:
    from automation_analytics import linkedin_sales_community_metrics, upsert_automation_run
    from .browser_use_client import BrowserUseClient
    from .models import CommunityItem, CommunityRunReport, CommunitySnapshot, utc_now
    from .state import StateStore

ENV_PREFIX = "LINKEDIN_SALES_COMMUNITY_ENGAGEMENT"
LEGACY_ENV_PREFIX = "LINKEDIN_SALES_COMMUNITY"
DEFAULT_URL = "https://scommunity.linkedin.com/"
DEFAULT_SESSION = "linkedin-sales-community-engagement"
DEFAULT_ARTIFACT_DIR = Path("artifacts/linkedin-sales-community-engagement")
DEFAULT_DB_PATH = DEFAULT_ARTIFACT_DIR / "state.sqlite3"


def add_event(report: CommunityRunReport, event_type: str, **fields: object) -> None:
    report.events.append({"ts": utc_now().isoformat(), "type": event_type, **fields})


def env_value(name: str, default: str | None = None) -> str | None:
    return os.getenv(f"{ENV_PREFIX}_{name}") or os.getenv(f"{LEGACY_ENV_PREFIX}_{name}", default)


def resolve_state_index(state_text: str, label: str) -> int | None:
    pattern = re.compile(r"^\[(\d+)\].*$", re.MULTILINE)
    lines = state_text.splitlines()
    for i, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        index = int(match.group(1))
        text = line[match.end(1) + 2 :].strip()
        if label.lower() in text.lower():
            return index
        if i + 1 < len(lines) and label.lower() in lines[i + 1].strip().lower():
            return index
    return None


def parse_args(argv: list[str] | None = None):
    import argparse

    parser = argparse.ArgumentParser(description="LinkedIn Sales Community runner")
    parser.add_argument("--url", default=env_value("URL", DEFAULT_URL))
    parser.add_argument("--chrome-profile", default=env_value("PROFILE"))
    parser.add_argument("--session-name", default=env_value("SESSION", DEFAULT_SESSION))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--like-cap", type=int, default=int(env_value("LIKE_CAP", "1") or "1"))
    parser.add_argument(
        "--analytics-database-url",
        default=env_value("ANALYTICS_DATABASE_URL") or os.getenv("AUTOMATION_ANALYTICS_DATABASE_URL"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run and not args.chrome_profile:
        raise SystemExit(f"Missing required configuration: {ENV_PREFIX}_PROFILE")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = StateStore(args.db_path)
    run_id = uuid.uuid4().hex
    report = CommunityRunReport(run_id=run_id, started_at=utc_now().isoformat())
    store.start_run(run_id, report.started_at)
    browser = None if args.dry_run else BrowserUseClient(session_name=args.session_name, chrome_profile=args.chrome_profile)
    try:
        if browser is None:
            raise SystemExit("--dry-run is not supported without a fixture yet")
        browser.open(args.url)
        browser.sleep(1.2)
        payload = json.loads(browser.collect_payload())
        snapshot = CommunitySnapshot(
            page_title=payload.get("page_title"),
            logged_in=bool(payload.get("logged_in")),
            page_shape_ok=bool(payload.get("page_shape_ok")),
            challenge_signals=list(payload.get("challenge_signals", [])),
            items=[
                CommunityItem(
                    item_id=str(item["item_id"]),
                    title=str(item["title"]),
                    subtitle=item.get("subtitle"),
                    detail=item.get("detail"),
                    action_label=item.get("action_label"),
                    action_selector=item.get("action_selector"),
                    high_signal=bool(item.get("high_signal")),
                )
                for item in payload.get("items", [])
            ],
        )
        report.page_shape_ok = snapshot.page_shape_ok
        store.record_snapshot(run_id, 0, snapshot)
        if snapshot.challenge_signals:
            report.status = "stopped"
            report.stop_reason = "challenge_signals"
            add_event(report, "run_stopped", reason="challenge_signals", signals=snapshot.challenge_signals)
            return finalize(store, report, args.artifact_dir, args.url, args.analytics_database_url)
        if not snapshot.logged_in or not snapshot.page_shape_ok:
            report.status = "stopped"
            report.stop_reason = "page_shape_changed"
            add_event(report, "run_stopped", reason="page_shape_changed", page_title=snapshot.page_title)
            return finalize(store, report, args.artifact_dir, args.url, args.analytics_database_url)

        for item in snapshot.items:
            report.items_scanned += 1
            if not item.high_signal:
                report.skips.append({"item_id": item.item_id, "reason": "low_signal"})
                continue
            report.items_considered += 1
            if report.items_liked >= args.like_cap:
                continue
            if not item.action_label:
                report.skips.append({"item_id": item.item_id, "reason": "missing_action_selector"})
                continue
            try:
                state_text = browser.state()
                element_index = resolve_state_index(state_text, item.action_label or item.title)
                if element_index is None:
                    report.skips.append({"item_id": item.item_id, "reason": "missing_action_index"})
                    continue
                browser.click_index(element_index)
                browser.sleep(random.uniform(0.5, 1.2))
                report.items_liked += 1
                add_event(report, "item_action_taken", item_id=item.item_id, label=item.action_label, element_index=element_index)
            except Exception as exc:
                report.skips.append({"item_id": item.item_id, "reason": "action_failed", "message": str(exc)})
                report.status = "stopped"
                report.stop_reason = "action_failed"
                break

        if report.status == "started":
            report.status = "ok"
        add_event(report, "run_completed", items_scanned=report.items_scanned, items_considered=report.items_considered, items_liked=report.items_liked)
        return finalize(store, report, args.artifact_dir, args.url, args.analytics_database_url)
    except Exception as exc:
        report.status = "failed"
        report.stop_reason = type(exc).__name__
        report.skips.append({"reason": "exception", "message": str(exc)})
        add_event(report, "run_failed", error=type(exc).__name__, message=str(exc))
        try:
            if browser is not None:
                shot = args.artifact_dir / f"{run_id}-failure.png"
                browser.screenshot(shot)
                report.screenshot_path = str(shot)
        except Exception:
            report.skips.append({"reason": "screenshot_failed", "trace": traceback.format_exc(limit=1)})
        return finalize(store, report, args.artifact_dir, args.url, args.analytics_database_url)
    finally:
        if browser is not None:
            browser.close()


def finalize(store: StateStore, report: CommunityRunReport, artifact_dir: Path, search_url: str, analytics_database_url: str | None) -> int:
    report.finished_at = utc_now().isoformat()
    store.finish_run(
        report.run_id,
        finished_at=report.finished_at,
        status=report.status,
        page_shape_ok=report.page_shape_ok,
        items_scanned=report.items_scanned,
        items_considered=report.items_considered,
        items_liked=report.items_liked,
        stop_reason=report.stop_reason,
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report_path = artifact_dir / f"{report.run_id}.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2))
    store.record_run_report(report.run_id, search_url, str(report_path), report)
    upsert_automation_run(
        database_url=analytics_database_url,
        automation_name=LINKEDIN_SALES_COMMUNITY_ENGAGEMENT,
        platform=LINKEDIN_PLATFORM,
        surface=LINKEDIN_SALES_COMMUNITY_SURFACE,
        search_url=search_url,
        artifact_path=str(report_path),
        report=report,
        metrics=linkedin_sales_community_metrics(report),
    )
    store.close()
    return 0 if report.status in {"ok", "stopped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
