from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from automation_analytics import (
    action_events_from_report,
    linkedin_company_profile_engagement_metrics,
    linkedin_sales_community_metrics,
    normalize_report_payload,
)
from automation_catalog import (
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT,
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT,
    automation_label,
    automation_platform,
    automation_surface,
    canonical_automation_name,
)


BUNDLE_SCHEMA_VERSION = "phantomclaw.run-bundle.v1"
SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "phantomclaw.run-bundle.v1.schema.json"


def _report_to_dict(report: Any) -> dict[str, Any]:
    if is_dataclass(report):
        return asdict(report)
    if isinstance(report, dict):
        return report
    raise TypeError(f"Unsupported report type: {type(report)!r}")


def metrics_for_automation(automation_name: str, report: Any) -> dict[str, Any]:
    canonical = canonical_automation_name(automation_name)
    if canonical == LINKEDIN_COMPANY_PROFILE_ENGAGEMENT:
        return linkedin_company_profile_engagement_metrics(report)
    if canonical == LINKEDIN_SALES_COMMUNITY_ENGAGEMENT:
        return linkedin_sales_community_metrics(report)
    raise ValueError(f"No metrics adapter registered for automation: {automation_name}")


def build_run_bundle(
    *,
    automation_name: str,
    report: Any,
    platform: str | None = None,
    artifact_path: str | None = None,
    search_url: str | None = None,
) -> dict[str, Any]:
    canonical = canonical_automation_name(automation_name)
    report_dict = _report_to_dict(report)
    report_dict = normalize_report_payload(report_dict)
    metrics = metrics_for_automation(canonical, report_dict)
    resolved_platform = platform or automation_platform(canonical)
    if not resolved_platform:
        raise ValueError(f"No platform registered for automation: {automation_name}")

    bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {
            "project": "phantomclaw",
            "channel": "oss-core",
            "artifact_path": str(Path(artifact_path)) if artifact_path else None,
            "search_url": search_url,
        },
        "automation": {
            "name": canonical,
            "label": automation_label(canonical),
            "platform": resolved_platform,
            "surface": automation_surface(canonical),
        },
        "run": {
            "run_id": report_dict["run_id"],
            "started_at": report_dict["started_at"],
            "finished_at": report_dict.get("finished_at"),
            "status": report_dict["status"],
            "stop_reason": report_dict.get("stop_reason"),
            "profile_name": report_dict.get("profile_name") or report_dict.get("actor_name"),
            "action_events": action_events_from_report(report_dict),
            "screenshot_path": report_dict.get("screenshot_path"),
        },
        "metrics": metrics,
        "report": report_dict,
    }
    validate_run_bundle(bundle)
    return bundle


def build_run_bundle_from_path(
    *,
    automation_name: str,
    report_path: Path,
    platform: str | None = None,
    search_url: str | None = None,
) -> dict[str, Any]:
    report = json.loads(report_path.read_text())
    return build_run_bundle(
        automation_name=automation_name,
        report=report,
        platform=platform,
        artifact_path=str(report_path),
        search_url=search_url,
    )


def run_bundle_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def validate_run_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {bundle.get('schema_version')!r}")

    required_top_level = ("schema_version", "generated_at", "source", "automation", "run", "metrics", "report")
    for key in required_top_level:
        if key not in bundle:
            raise ValueError(f"Missing required top-level bundle field: {key}")

    for section_name, required_fields in (
        ("source", ("project", "channel")),
        ("automation", ("name", "label", "platform", "surface")),
        ("run", ("run_id", "started_at", "status")),
        (
            "metrics",
            (
                "items_scanned",
                "items_considered",
                "actions_total",
                "likes_count",
                "reposts_count",
                "comments_liked_count",
                "follows_count",
                "metrics_json",
            ),
        ),
    ):
        section = bundle.get(section_name)
        if not isinstance(section, dict):
            raise ValueError(f"Bundle section must be an object: {section_name}")
        for field_name in required_fields:
            if field_name not in section:
                raise ValueError(f"Missing required field {section_name}.{field_name}")

    if not isinstance(bundle["report"], dict):
        raise ValueError("Bundle report must be an object")

    run_id = bundle["run"]["run_id"]
    report_run_id = bundle["report"].get("run_id")
    if report_run_id != run_id:
        raise ValueError(f"Run id mismatch between run and report sections: {run_id!r} != {report_run_id!r}")

    for field_name in (
        "items_scanned",
        "items_considered",
        "actions_total",
        "likes_count",
        "reposts_count",
        "comments_liked_count",
        "follows_count",
    ):
        value = bundle["metrics"][field_name]
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"Bundle metric must be a non-negative integer: metrics.{field_name}")

    if not isinstance(bundle["metrics"]["metrics_json"], dict):
        raise ValueError("metrics.metrics_json must be an object")

    profile_name = bundle["run"].get("profile_name")
    if profile_name is not None and not isinstance(profile_name, str):
        raise ValueError("run.profile_name must be a string or null")

    action_events = bundle["run"].get("action_events")
    if action_events is not None:
        if not isinstance(action_events, list):
            raise ValueError("run.action_events must be an array or null")
        for action_event in action_events:
            if not isinstance(action_event, dict):
                raise ValueError("run.action_events items must be objects")

    for field_name, raw in (
        ("generated_at", bundle["generated_at"]),
        ("run.started_at", bundle["run"]["started_at"]),
        ("run.finished_at", bundle["run"].get("finished_at")),
    ):
        if raw is None:
            continue
        try:
            datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid ISO datetime for {field_name}: {raw!r}") from exc
