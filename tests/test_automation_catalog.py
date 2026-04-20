import unittest

from automation_catalog import (
    AUTOMATION_KIND_ENGAGEMENT,
    AUTOMATION_KIND_WORKFLOW,
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT,
    LINKEDIN_CORE_SURFACE,
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT,
    LINKEDIN_SALES_COMMUNITY_SURFACE,
    PEERLIST_FOLLOW_WORKFLOW,
    PEERLIST_PROFILE_FOLLOWERS_METRIC,
    automation_default_parameters,
    automation_kind,
    automation_label,
    automation_north_star_metric,
    automation_surface,
    canonical_automation_name,
)


class AutomationCatalogTests(unittest.TestCase):
    def test_company_profile_alias_maps_to_canonical(self) -> None:
        self.assertEqual(canonical_automation_name("company-profile-engagement"), LINKEDIN_COMPANY_PROFILE_ENGAGEMENT)

    def test_legacy_sales_community_name_maps_to_canonical(self) -> None:
        self.assertEqual(canonical_automation_name("linkedin-sales-community"), LINKEDIN_SALES_COMMUNITY_ENGAGEMENT)

    def test_company_profile_label_is_human_readable(self) -> None:
        self.assertEqual(automation_label("company-profile-engagement"), "LinkedIn Company Profile Engagement")

    def test_company_profile_surface_maps_to_core(self) -> None:
        self.assertEqual(automation_surface("company-profile-engagement"), LINKEDIN_CORE_SURFACE)

    def test_sales_community_surface_maps_correctly(self) -> None:
        self.assertEqual(automation_surface("linkedin-sales-community"), LINKEDIN_SALES_COMMUNITY_SURFACE)

    def test_peerlist_follow_workflow_has_standard_metadata(self) -> None:
        self.assertEqual(automation_kind(PEERLIST_FOLLOW_WORKFLOW), AUTOMATION_KIND_WORKFLOW)
        self.assertEqual(automation_kind(LINKEDIN_COMPANY_PROFILE_ENGAGEMENT), AUTOMATION_KIND_ENGAGEMENT)
        self.assertEqual(automation_north_star_metric(PEERLIST_FOLLOW_WORKFLOW), PEERLIST_PROFILE_FOLLOWERS_METRIC)
        self.assertTrue(automation_default_parameters(PEERLIST_FOLLOW_WORKFLOW)["do_not_unfollow_peers"])


if __name__ == "__main__":
    unittest.main()
