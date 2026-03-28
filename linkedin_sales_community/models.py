from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class CommunityItem:
    item_id: str
    title: str
    subtitle: str | None
    detail: str | None
    action_label: str | None
    action_selector: str | None
    high_signal: bool = False


@dataclass(slots=True)
class CommunitySnapshot:
    page_title: str | None
    logged_in: bool
    page_shape_ok: bool
    challenge_signals: list[str]
    items: list[CommunityItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class CommunityRunReport:
    run_id: str
    started_at: str
    finished_at: str | None = None
    status: str = "started"
    page_shape_ok: bool = False
    items_scanned: int = 0
    items_considered: int = 0
    items_liked: int = 0
    skips: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    stop_reason: str | None = None
    screenshot_path: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
