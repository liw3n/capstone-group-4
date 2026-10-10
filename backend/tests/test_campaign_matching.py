"""Standard-library tests also collected by pytest; no services required."""
from dataclasses import replace
from datetime import date
import unittest
from unittest.mock import patch

from app.campaigns.matching import age_from_dob, explain_match, recommend_clients_for_campaign
from app.campaigns.repository import (
    CampaignInactive, CampaignUnavailable, Criteria,
    DEMO_FA, RequestScope, get_campaign, list_clients_for_fa,
)

from campaign_fixtures import CAMPAIGNS, CLIENTS, fixture_repository


class CampaignMatchingTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(fixture_repository())
        self.scope = RequestScope(DEMO_FA)
        self.client = CLIENTS[0]

    def test_seed_campaign_matches_and_accounting(self):
        expected = {
            "camp-1": (["client-001", "client-002", "client-003", "client-012"], 6),
            "camp-2": (["client-006", "client-007", "client-008"], 7),
        }
        for campaign_id, (ids, excluded) in expected.items():
            with self.subTest(campaign_id=campaign_id):
                result = recommend_clients_for_campaign(campaign_id, self.scope)
                self.assertEqual([c["contact_id"] for c in result["clients"]], ids)
                self.assertEqual(result["evaluated_count"], 12)
                self.assertEqual(result["excluded_count"], excluded)
                self.assertEqual(result["incomplete_count"], 2)
                self.assertEqual(result["matched_count"] + result["incomplete_count"]
                                 + result["excluded_count"], result["evaluated_count"])
                self.assertTrue(all(len(c["reasons"]) == 2 for c in result["clients"]))
                self.assertEqual(result["data_source"], "synthetic")
                self.assertFalse(result["truncated"])

    def test_exact_age_boundaries_and_birthday(self):
        for age, group in ((34, "under35"), (35, "35to44"), (44, "35to44"),
                           (45, "45to54"), (54, "45to54"), (55, "55to64"),
                           (64, "55to64"), (65, "65plus")):
            with self.subTest(age=age):
                client = replace(self.client, dob=f"{2026-age}-08-26")
                self.assertEqual(explain_match(client, Criteria(age_groups=(group,)))["status"], "matched")
        self.assertEqual(age_from_dob("1971-08-27"), 54)
        self.assertEqual(age_from_dob("1971-08-26"), 55)

    def test_exact_cash_boundaries(self):
        for cash, band in ((0, "under50k"), (49_999, "under50k"), (50_000, "50kTo250k"),
                           (249_999, "50kTo250k"), (250_000, "250kTo1m"),
                           (999_999, "250kTo1m"), (1_000_000, "above1m")):
            with self.subTest(cash=cash):
                client = replace(self.client, available_cash=cash)
                self.assertEqual(explain_match(client, Criteria(cash_bands=(band,)))["status"], "matched")

    def test_or_within_dimension_and_across_dimensions(self):
        criteria = Criteria(age_groups=("under35", "55to64"),
                            cash_bands=("under50k", "250kTo1m"))
        self.assertEqual(explain_match(self.client, criteria)["status"], "matched")
        self.assertEqual(explain_match(replace(self.client, available_cash=50_000), criteria)["status"], "excluded")
        criteria = replace(criteria, genders=("male", "female"))
        self.assertEqual(explain_match(self.client, criteria)["status"], "matched")
        self.assertEqual(explain_match(self.client, replace(criteria, genders=("male",)))["status"], "excluded")

    def test_custom_ranges_are_inclusive_and_or_with_bands(self):
        criteria = Criteria(age_groups=("under35",), age_min=58, age_max=58,
                            cash_bands=("under50k",), cash_min=300_000, cash_max=300_000)
        self.assertEqual(explain_match(self.client, criteria)["status"], "matched")
        self.assertEqual(explain_match(self.client, replace(criteria, age_max=57))["status"], "excluded")
        self.assertEqual(explain_match(self.client, Criteria(cash_min=300_000))["status"], "matched")
        self.assertEqual(explain_match(self.client, Criteria(cash_max=300_000))["status"], "matched")

    def test_missing_invalid_and_unfiltered_fields(self):
        criteria = CAMPAIGNS[0].criteria
        for dob in (None, "bad-date", "2026-02-30", "2027-01-01", "1896-08-26"):
            with self.subTest(dob=dob):
                self.assertEqual(explain_match(replace(self.client, dob=dob), criteria)["missing_fields"],
                                 ["date_of_birth"])
        for cash in (None, -1, float("nan"), float("inf"), True):
            with self.subTest(cash=cash):
                self.assertEqual(explain_match(replace(self.client, available_cash=cash), criteria)["missing_fields"],
                                 ["available_cash"])
        client = replace(self.client, dob=None, available_cash=None, gender=None)
        self.assertEqual(explain_match(client, Criteria())["status"], "matched")
        self.assertEqual(explain_match(client, Criteria(genders=("female",)))["missing_fields"], ["gender"])
        # Match targeting.ts: missing selected cash is incomplete even when age fails.
        client = replace(client, dob="1996-08-26")
        self.assertEqual(explain_match(client, criteria)["status"], "incomplete")

    def test_repository_excludes_other_adviser_and_tenant(self):
        self.assertEqual(len(list_clients_for_fa(self.scope)), 12)
        self.assertEqual(len(list_clients_for_fa(RequestScope("adv-other-demo"))), 1)
        self.assertEqual(len(list_clients_for_fa(RequestScope(DEMO_FA, "other-demo-tenant"))), 1)
        with self.assertRaises(CampaignUnavailable):
            get_campaign("camp-1", RequestScope("adv-other-demo"))
        with self.assertRaises(CampaignUnavailable):
            get_campaign("camp-1", RequestScope(DEMO_FA, "other-demo-tenant"))

    def test_invalid_unknown_and_inaccessible_campaigns_do_not_read_clients(self):
        with patch("app.campaigns.matching.list_clients_for_fa") as read:
            for campaign_id in ("", "not-a-campaign", "camp-missing", "camp-" + "x" * 65):
                with self.subTest(campaign_id=campaign_id), self.assertRaises(CampaignUnavailable):
                    recommend_clients_for_campaign(campaign_id, self.scope)
            with self.assertRaises(CampaignUnavailable):
                recommend_clients_for_campaign("camp-1", RequestScope("adv-other-demo"))
            read.assert_not_called()

    def test_inactive_and_outside_date_window_do_not_read_clients(self):
        for campaign in (replace(CAMPAIGNS[0], status="draft"),
                         replace(CAMPAIGNS[0], status="completed"),
                         replace(CAMPAIGNS[0], start_date=date(2027, 1, 1)),
                         replace(CAMPAIGNS[0], end_date=date(2026, 8, 25))):
            with patch("app.campaigns.matching.get_campaign", return_value=campaign), \
                 patch("app.campaigns.matching.list_clients_for_fa") as read:
                with self.assertRaises(CampaignInactive):
                    recommend_clients_for_campaign("camp-1", self.scope)
                read.assert_not_called()

    def test_no_matches_and_empty_book(self):
        for clients in ((CLIENTS[5],), ()):
            with patch("app.campaigns.matching.list_clients_for_fa", return_value=clients):
                result = recommend_clients_for_campaign("camp-1", self.scope)
                self.assertEqual(result["matched_count"], 0)
                self.assertEqual(result["clients"], [])

    def test_limit_preserves_total_counts_and_marks_truncation(self):
        result = recommend_clients_for_campaign("camp-1", self.scope, limit=1)
        self.assertEqual(result["matched_count"], 4)
        self.assertEqual(result["returned_count"], 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["incomplete_count"], 2)
        self.assertTrue(result["incomplete_truncated"])
        for limit in (0, -1, 101, 1.5, True, "2"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                recommend_clients_for_campaign("camp-1", self.scope, limit)

    def test_scope_is_required_and_minimal_output(self):
        with self.assertRaises(ValueError):
            RequestScope("")
        result = recommend_clients_for_campaign("camp-1", self.scope)
        self.assertEqual(set(result["clients"][0]), {"contact_id", "name", "reasons"})
        self.assertNotIn("dob", str(result["clients"]))


if __name__ == "__main__":
    unittest.main()
