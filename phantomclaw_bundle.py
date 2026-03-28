from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from automation_analytics import linkedin_company_profile_engagement_metrics, linkedin_sales_community_metrics
from automation_catalog import (
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT,
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT,
    automation_label,
    automation_platform,
    automation_surface,
    canonical_automation_name,
)


BUNDLE_SCHEMA_VERSION = "phantomclaw.run-bundle.v1"


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
    metrics = metrics_for_automation(canonical, report_dict)
    resolved_platform = platform or automation_platform(canonical)
    if not resolved_platform:
        raise ValueError(f"No platform registered for automation: {automation_name}")

    return {
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
            "screenshot_path": report_dict.get("screenshot_path"),
        },
        "metrics": metrics,
        "report": report_dict,
    }


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
