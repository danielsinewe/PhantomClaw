import os
import unittest
from unittest.mock import patch

from linkedin.company_profile_engagement.config import parse_config


class LinkedInCompanyProfileConfigTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_SEARCH_URL": "https://www.linkedin.com/search/results/content/",
            "LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_PROFILE": "work-profile",
            "LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_ACTOR": "Example Company",
            "LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_DATABASE_URL": "postgresql://self-hosted-state",
        },
        clear=True,
    )
    def test_analytics_database_does_not_implicitly_follow_state_database(self) -> None:
        config = parse_config([])
        self.assertEqual(config.database_url, "postgresql://self-hosted-state")
        self.assertIsNone(config.analytics_database_url)

    @patch.dict(
        os.environ,
        {
            "LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_SEARCH_URL": "https://www.linkedin.com/search/results/content/",
            "LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_PROFILE": "work-profile",
            "LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_ACTOR": "Example Company",
            "LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_ANALYTICS_DATABASE_URL": "postgresql://self-hosted-analytics",
        },
        clear=True,
    )
    def test_analytics_database_can_be_set_explicitly_per_automation(self) -> None:
        config = parse_config([])
        self.assertEqual(config.analytics_database_url, "postgresql://self-hosted-analytics")


if __name__ == "__main__":
    unittest.main()
