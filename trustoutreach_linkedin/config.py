from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DB_PATH = Path("artifacts/trustoutreach-linkedin/state.sqlite3")
DEFAULT_ARTIFACT_DIR = Path("artifacts/trustoutreach-linkedin")
DEFAULT_SESSION = "trustoutreach-linkedin"
DEFAULT_POST_CAP = 3
DEFAULT_REPOST_CAP = 1
DEFAULT_COMMENT_CAP = 12
DEFAULT_ACTOR_NAME = "TrustOutreach"
DEFAULT_MAX_PASSES = 6
DEFAULT_FOLLOW_ADMIN_URL = "https://www.linkedin.com/company/109821516/admin/dashboard/?manageFollowing=true"
DEFAULT_FOLLOW_CAP = 25


@dataclass(slots=True)
class RunnerConfig:
    search_url: str
    chrome_profile: str
    actor_name: str
    session_name: str
    post_cap: int
    repost_cap: int
    comment_cap: int
    max_passes: int
    follow_admin_url: str
    follow_cap: int
    dry_run: bool
    fixture_path: Path | None
    database_url: str | None
    analytics_database_url: str | None
    db_path: Path
    artifact_dir: Path
    success_screenshot: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TrustOutreach LinkedIn runner")
    parser.add_argument("--search-url", default=os.getenv("TRUSTOUTREACH_LINKEDIN_SEARCH_URL"))
    parser.add_argument("--chrome-profile", default=os.getenv("TRUSTOUTREACH_LINKEDIN_PROFILE"))
    parser.add_argument("--actor-name", default=os.getenv("TRUSTOUTREACH_LINKEDIN_ACTOR", DEFAULT_ACTOR_NAME))
    parser.add_argument("--session-name", default=os.getenv("TRUSTOUTREACH_LINKEDIN_SESSION", DEFAULT_SESSION))
    parser.add_argument("--post-cap", type=int, default=int(os.getenv("TRUSTOUTREACH_LINKEDIN_POST_CAP", DEFAULT_POST_CAP)))
    parser.add_argument(
        "--repost-cap",
        type=int,
        default=int(os.getenv("TRUSTOUTREACH_LINKEDIN_REPOST_CAP", DEFAULT_REPOST_CAP)),
    )
    parser.add_argument(
        "--comment-cap",
        type=int,
        default=int(os.getenv("TRUSTOUTREACH_LINKEDIN_COMMENT_CAP", DEFAULT_COMMENT_CAP)),
    )
    parser.add_argument(
        "--max-passes",
        type=int,
        default=int(os.getenv("TRUSTOUTREACH_LINKEDIN_MAX_PASSES", DEFAULT_MAX_PASSES)),
    )
    parser.add_argument(
        "--follow-admin-url",
        default=os.getenv("TRUSTOUTREACH_LINKEDIN_FOLLOW_ADMIN_URL", DEFAULT_FOLLOW_ADMIN_URL),
    )
    parser.add_argument(
        "--follow-cap",
        type=int,
        default=int(os.getenv("TRUSTOUTREACH_LINKEDIN_FOLLOW_CAP", DEFAULT_FOLLOW_CAP)),
    )
    parser.add_argument("--dry-run", action="store_true", default=os.getenv("TRUSTOUTREACH_LINKEDIN_DRY_RUN") == "1")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--database-url", default=os.getenv("TRUSTOUTREACH_LINKEDIN_DATABASE_URL"))
    parser.add_argument("--analytics-database-url", default=os.getenv("AUTOMATION_ANALYTICS_DATABASE_URL"))
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--success-screenshot", action="store_true")
    return parser


def parse_config(argv: list[str] | None = None) -> RunnerConfig:
    args = build_parser().parse_args(argv)
    if not args.dry_run:
        missing = []
        if not args.search_url:
            missing.append("TRUSTOUTREACH_LINKEDIN_SEARCH_URL")
        if not args.chrome_profile:
            missing.append("TRUSTOUTREACH_LINKEDIN_PROFILE")
        if missing:
            names = ", ".join(missing)
            raise SystemExit(f"Missing required configuration: {names}")
    if args.dry_run and not args.fixture:
        raise SystemExit("--dry-run requires --fixture")
    db_path = args.db_path
    if db_path == DEFAULT_DB_PATH and args.artifact_dir != DEFAULT_ARTIFACT_DIR:
        db_path = args.artifact_dir / "state.sqlite3"
    return RunnerConfig(
        search_url=args.search_url or "about:blank",
        chrome_profile=args.chrome_profile or "unset",
        actor_name=args.actor_name,
        session_name=args.session_name,
        post_cap=args.post_cap,
        repost_cap=args.repost_cap,
        comment_cap=args.comment_cap,
        max_passes=args.max_passes,
        follow_admin_url=args.follow_admin_url,
        follow_cap=args.follow_cap,
        dry_run=args.dry_run,
        fixture_path=args.fixture,
        database_url=args.database_url,
        analytics_database_url=args.analytics_database_url or args.database_url,
        db_path=db_path,
        artifact_dir=args.artifact_dir,
        success_screenshot=args.success_screenshot,
    )
