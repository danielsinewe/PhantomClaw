import unittest

from automation_catalog import (
    LINKEDIN_COMPANY_PROFILE_ENGAGEMENT,
    LINKEDIN_CORE_SURFACE,
    LINKEDIN_SALES_COMMUNITY_ENGAGEMENT,
    LINKEDIN_SALES_COMMUNITY_SURFACE,
    automation_label,
    automation_surface,
    canonical_automation_name,
)


class AutomationCatalogTests(unittest.TestCase):
    def test_legacy_company_profile_name_maps_to_canonical(self) -> None:
        self.assertEqual(canonical_automation_name("trustoutreach-linkedin"), LINKEDIN_COMPANY_PROFILE_ENGAGEMENT)

    def test_legacy_sales_community_name_maps_to_canonical(self) -> None:
        self.assertEqual(canonical_automation_name("linkedin-sales-community"), LINKEDIN_SALES_COMMUNITY_ENGAGEMENT)

    def test_company_profile_label_is_human_readable(self) -> None:
        self.assertEqual(automation_label("trustoutreach-linkedin"), "LinkedIn Company Profile Engagement")

    def test_company_profile_surface_maps_to_core(self) -> None:
        self.assertEqual(automation_surface("trustoutreach-linkedin"), LINKEDIN_CORE_SURFACE)

    def test_sales_community_surface_maps_correctly(self) -> None:
        self.assertEqual(automation_surface("linkedin-sales-community"), LINKEDIN_SALES_COMMUNITY_SURFACE)


if __name__ == "__main__":
    unittest.main()
