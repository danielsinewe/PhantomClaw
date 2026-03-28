from __future__ import annotations


LINKEDIN_PLATFORM = "linkedin"
LINKEDIN_CORE_SURFACE = "core"
LINKEDIN_SALES_COMMUNITY_SURFACE = "sales-community"
LINKEDIN_SALES_NAVIGATOR_SURFACE = "sales-navigator"

LINKEDIN_COMPANY_PROFILE_ENGAGEMENT = "linkedin-company-profile-engagement"
LINKEDIN_SALES_COMMUNITY_ENGAGEMENT = "linkedin-sales-community-engagement"

LEGACY_AUTOMATION_NAMES = {
    "trustoutreach-linkedin": LINKEDIN_COMPANY_PROFILE_ENGAGEMENT,
    "linkedin-sales-community": LINKEDIN_SALES_COMMUNITY_ENGAGEMENT,
}

AUTOMATION_LABELS = {
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT: "LinkedIn Company Profile Engagement",
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT: "LinkedIn Sales Community Engagement",
}

AUTOMATION_PLATFORMS = {
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT: LINKEDIN_PLATFORM,
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT: LINKEDIN_PLATFORM,
}

AUTOMATION_SURFACES = {
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT: LINKEDIN_CORE_SURFACE,
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT: LINKEDIN_SALES_COMMUNITY_SURFACE,
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
