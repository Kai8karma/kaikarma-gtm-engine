"""Tests for the HubSpot pre-call adapter — contact/company lookup, briefing writeback.

    python3 06-precall-intelligence-engine/test_hubspot_precall.py
"""

from __future__ import annotations

import unittest

from hubspot_precall import (
    BRIEFING_DATE_PROPERTY,
    BRIEFING_PROPERTY,
    FakeHubSpotPrecallClient,
    build_briefing_writeback,
    company_to_profile,
    contact_to_profile,
    fetch_company,
    fetch_contact_by_email,
    read_stored_briefing,
    update_contact_briefing,
)

CONTACT_PROPS = {
    "firstname": "Jane",
    "lastname": "Buyer",
    "jobtitle": "VP Procurement",
    "email": "buyer@acmecloud.com",
    "hs_linkedin_url": "linkedin.com/in/janebuyer",
    "associatedcompanyid": "1001",
}

COMPANY_PROPS_WITH_INDUSTRY = {
    "name": "Acme Cloud Inc",
    "industry": "COMPUTER_SOFTWARE",
    "domain": "acmecloud.com",
    "numberofemployees": "480",
    "annualrevenue": "50000000",
    "city": "Austin",
}

COMPANY_PROPS_BLANK_INDUSTRY = {**COMPANY_PROPS_WITH_INDUSTRY, "industry": ""}


class TestContactToProfile(unittest.TestCase):

    def test_maps_all_fields(self):
        p = contact_to_profile("501", CONTACT_PROPS)
        self.assertEqual(p.contact_id, "501")
        self.assertEqual(p.first_name, "Jane")
        self.assertEqual(p.email, "buyer@acmecloud.com")
        self.assertEqual(p.company_id, "1001")

    def test_missing_company_id_is_none(self):
        p = contact_to_profile("501", {k: v for k, v in CONTACT_PROPS.items() if k != "associatedcompanyid"})
        self.assertIsNone(p.company_id)


class TestCompanyToProfile(unittest.TestCase):

    def test_crm_industry_used_when_present(self):
        c = company_to_profile("1001", COMPANY_PROPS_WITH_INDUSTRY)
        self.assertEqual(c.industry, "COMPUTER_SOFTWARE")
        self.assertEqual(c.industry_source, "crm")

    def test_blank_industry_falls_back_to_web_search(self):
        c = company_to_profile("1001", COMPANY_PROPS_BLANK_INDUSTRY, web_search_industry="Cloud Infra")
        self.assertEqual(c.industry, "Cloud Infra")
        self.assertEqual(c.industry_source, "web_search_fallback")

    def test_blank_industry_no_web_search_stays_blank(self):
        c = company_to_profile("1001", COMPANY_PROPS_BLANK_INDUSTRY)
        self.assertEqual(c.industry, "")
        self.assertEqual(c.industry_source, "web_search_fallback")

    def test_employee_count_parsed(self):
        c = company_to_profile("1001", COMPANY_PROPS_WITH_INDUSTRY)
        self.assertEqual(c.employee_count, 480)

    def test_malformed_employee_count_defaults_zero(self):
        c = company_to_profile("1001", {**COMPANY_PROPS_WITH_INDUSTRY, "numberofemployees": "n/a"})
        self.assertEqual(c.employee_count, 0)


class TestBriefingWriteback(unittest.TestCase):

    def test_payload_shape(self):
        payload = build_briefing_writeback("<html/>", "2026-07-01T08:00:00Z")
        self.assertEqual(payload["properties"][BRIEFING_PROPERTY], "<html/>")
        self.assertEqual(payload["properties"][BRIEFING_DATE_PROPERTY], "2026-07-01T08:00:00Z")


class TestFakeClientRoundTrip(unittest.TestCase):

    def setUp(self):
        self.client = FakeHubSpotPrecallClient(
            contacts_by_email={"buyer@acmecloud.com": {"id": "501", "properties": CONTACT_PROPS}},
            companies_by_id={"1001": {"properties": COMPANY_PROPS_BLANK_INDUSTRY}},
            stored_briefings={"501": "<html>stored briefing</html>"},
        )

    def test_fetch_contact_found(self):
        c = fetch_contact_by_email(self.client, "buyer@acmecloud.com")
        self.assertEqual(c.contact_id, "501")

    def test_fetch_contact_not_found_returns_none(self):
        c = fetch_contact_by_email(self.client, "unknown@nowhere.com")
        self.assertIsNone(c)

    def test_fetch_company_found_with_fallback(self):
        c = fetch_company(self.client, "1001", web_search_industry="Cloud Infra")
        self.assertEqual(c.industry_source, "web_search_fallback")

    def test_fetch_company_not_found_returns_none(self):
        c = fetch_company(self.client, "nonexistent")
        self.assertIsNone(c)

    def test_read_stored_briefing_found(self):
        html = read_stored_briefing(self.client, "501")
        self.assertEqual(html, "<html>stored briefing</html>")

    def test_read_stored_briefing_missing_returns_none(self):
        html = read_stored_briefing(self.client, "999")
        self.assertIsNone(html)

    def test_update_contact_briefing_writes_payload(self):
        result = update_contact_briefing(self.client, "501", "<html/>", "2026-07-01T08:00:00Z")
        self.assertTrue(result["ok"])
        self.assertEqual(self.client.patch_calls[0][0], "501")


if __name__ == "__main__":
    unittest.main()
