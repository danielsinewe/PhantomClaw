from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class CommentSnapshot:
    comment_id: str
    parent_post_id: str
    parent_comment_id: str | None
    text: str
    liked: bool
    like_selector: str | None


@dataclass(slots=True)
class PostSnapshot:
    post_id: str
    post_url: str | None
    text: str
    sponsored: bool
    already_liked: bool
    already_reposted: bool
    interactable: bool
    like_selector: str | None
    repost_selector: str | None
    comments_expanded: bool
    comment_toggle_selector: str | None
    reply_toggle_selectors: list[str] = field(default_factory=list)
    comments: list[CommentSnapshot] = field(default_factory=list)


@dataclass(slots=True)
class FeedSnapshot:
    actor_name: str | None
    actor_verified: bool
    search_shape_ok: bool
    search_markers: list[str]
    challenge_signals: list[str]
    posts: list[PostSnapshot]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class CompanySnapshot:
    company_id: str
    company_url: str
    name: str
    subtitle: str | None
    followers_text: str | None
    already_following: bool
    follow_selector: str | None


@dataclass(slots=True)
class CompanyFeedSnapshot:
    page_shape_ok: bool
    challenge_signals: list[str]
    following_count: int | None
    active_tab: str | None
    companies: list[CompanySnapshot]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["agencies"] = data["companies"]
        return data

    @property
    def agencies(self) -> list[CompanySnapshot]:
        return self.companies

    @agencies.setter
    def agencies(self, value: list[CompanySnapshot]) -> None:
        self.companies = value


@dataclass(slots=True)
class RunReport:
    run_id: str
    started_at: str
    profile_name: str | None = None
    finished_at: str | None = None
    status: str = "started"
    actor_verified: bool = False
    search_shape_ok: bool = False
    posts_scanned: int = 0
    posts_liked: int = 0
    posts_reposted: int = 0
    comments_liked: int = 0
    companies_scanned: int = 0
    companies_followed: int = 0
    skips: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    stop_reason: str | None = None
    screenshot_path: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["agencies_scanned"] = data["companies_scanned"]
        data["agencies_followed"] = data["companies_followed"]
        return data

    @property
    def agencies_scanned(self) -> int:
        return self.companies_scanned

    @agencies_scanned.setter
    def agencies_scanned(self, value: int) -> None:
        self.companies_scanned = value

    @property
    def agencies_followed(self) -> int:
        return self.companies_followed

    @agencies_followed.setter
    def agencies_followed(self, value: int) -> None:
        self.companies_followed = value


AgencySnapshot = CompanySnapshot
AgencyFeedSnapshot = CompanyFeedSnapshot
