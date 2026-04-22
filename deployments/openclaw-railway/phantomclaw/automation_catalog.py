from __future__ import annotations


LINKEDIN_PLATFORM = "linkedin"
LINKEDIN_CORE_SURFACE = "core"
LINKEDIN_SALES_COMMUNITY_SURFACE = "sales-community"
LINKEDIN_SALES_NAVIGATOR_SURFACE = "sales-navigator"
PEERLIST_PLATFORM = "peerlist"
PEERLIST_SCROLL_SURFACE = "scroll"
PEERLIST_NETWORK_SURFACE = "network"

LINKEDIN_COMPANY_PROFILE_ENGAGEMENT = "linkedin-company-profile-engagement"
LINKEDIN_SALES_COMMUNITY_ENGAGEMENT = "linkedin-sales-community-engagement"
PEERLIST_SCROLL_ENGAGEMENT = "peerlist-scroll-engagement"
PEERLIST_FOLLOW_WORKFLOW = "peerlist-follow-workflow"

AUTOMATION_KIND_ENGAGEMENT = "engagement"
AUTOMATION_KIND_WORKFLOW = "workflow"
PEERLIST_PROFILE_FOLLOWERS_METRIC = "peerlist_profile_followers"

LEGACY_AUTOMATION_NAMES = {
    "trustoutreach-linkedin": LINKEDIN_COMPANY_PROFILE_ENGAGEMENT,
    "company-profile-engagement": LINKEDIN_COMPANY_PROFILE_ENGAGEMENT,
    "linkedin-sales-community": LINKEDIN_SALES_COMMUNITY_ENGAGEMENT,
}

AUTOMATION_LABELS = {
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT: "LinkedIn Company Profile Engagement",
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT: "LinkedIn Sales Community Engagement",
    PEERLIST_SCROLL_ENGAGEMENT: "Peerlist Scroll Engagement",
    PEERLIST_FOLLOW_WORKFLOW: "Peerlist Follow Workflow",
}

AUTOMATION_PLATFORMS = {
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT: LINKEDIN_PLATFORM,
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT: LINKEDIN_PLATFORM,
    PEERLIST_SCROLL_ENGAGEMENT: PEERLIST_PLATFORM,
    PEERLIST_FOLLOW_WORKFLOW: PEERLIST_PLATFORM,
}

AUTOMATION_SURFACES = {
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT: LINKEDIN_CORE_SURFACE,
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT: LINKEDIN_SALES_COMMUNITY_SURFACE,
    PEERLIST_SCROLL_ENGAGEMENT: PEERLIST_SCROLL_SURFACE,
    PEERLIST_FOLLOW_WORKFLOW: PEERLIST_NETWORK_SURFACE,
}

AUTOMATION_KINDS = {
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT: AUTOMATION_KIND_ENGAGEMENT,
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT: AUTOMATION_KIND_ENGAGEMENT,
    PEERLIST_SCROLL_ENGAGEMENT: AUTOMATION_KIND_ENGAGEMENT,
    PEERLIST_FOLLOW_WORKFLOW: AUTOMATION_KIND_WORKFLOW,
}

AUTOMATION_NORTH_STAR_METRICS = {
    PEERLIST_FOLLOW_WORKFLOW: PEERLIST_PROFILE_FOLLOWERS_METRIC,
}

AUTOMATION_DEFAULT_PARAMETERS = {
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT: {},
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT: {},
    PEERLIST_SCROLL_ENGAGEMENT: {
        "max_upvotes": 1,
        "enable_comments": False,
        "click_streak": False,
    },
    PEERLIST_FOLLOW_WORKFLOW: {
        "type": "follow",
        "follows_per_day": 3,
        "max_follows_per_run": 1,
        "unfollows_per_day": 1000,
        "max_unfollows_per_run": 1,
        "unfollow_after_days": 14,
        "do_not_unfollow_peers": True,
        "active_window_start": "09:00",
        "active_window_end": "21:00",
        "min_delay_seconds": 45,
        "max_delay_seconds": 180,
        "error_backoff_seconds": 900,
        "candidate_pool_limit": 50,
        "require_verified_profile": False,
        "skip_existing_following": True,
        "skip_existing_followers": False,
        "skip_peers": True,
        "profile_blacklist": [],
        "profile_whitelist": [],
    },
}


def canonical_automation_name(name: str) -> str:
    return LEGACY_AUTOMATION_NAMES.get(name, name)


def automation_label(name: str) -> str:
    canonical = canonical_automation_name(name)
    return AUTOMATION_LABELS.get(canonical, canonical)


def automation_platform(name: str) -> str | None:
    canonical = canonical_automation_name(name)
    return AUTOMATION_PLATFORMS.get(canonical)


def automation_surface(name: str) -> str | None:
    canonical = canonical_automation_name(name)
    return AUTOMATION_SURFACES.get(canonical)


def automation_kind(name: str) -> str:
    canonical = canonical_automation_name(name)
    return AUTOMATION_KINDS.get(canonical, AUTOMATION_KIND_ENGAGEMENT)


def automation_north_star_metric(name: str) -> str | None:
    canonical = canonical_automation_name(name)
    return AUTOMATION_NORTH_STAR_METRICS.get(canonical)


def automation_default_parameters(name: str) -> dict:
    canonical = canonical_automation_name(name)
    return dict(AUTOMATION_DEFAULT_PARAMETERS.get(canonical, {}))
