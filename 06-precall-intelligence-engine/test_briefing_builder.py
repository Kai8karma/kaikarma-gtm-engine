"""Tests for the briefing/recap prompt builder and HTML assembler.

    python3 06-precall-intelligence-engine/test_briefing_builder.py
"""

from __future__ import annotations

import unittest

from briefing_builder import (
    assemble_briefing_html,
    assemble_recap_html,
    build_t1_prompt,
    build_t2_prompt,
)
from precall_schema import (
    Attendee,
    BriefingSections,
    CalendarEvent,
    CompanyProfile,
    ContactProfile,
    DedupFlags,
    RecapSummary,
)

CONTACT = ContactProfile(
    contact_id="501", first_name="Jane", last_name="Buyer", title="VP Procurement",
    email="buyer@acmecloud.com", linkedin_url="linkedin.com/in/janebuyer", company_id="1001",
)
EVENT = CalendarEvent(
    event_id="evt-1001", title="Aerchain demo — Acme Cloud", description="",
    start_iso="2026-07-03T15:00:00+00:00", booked_at_iso="2026-06-20T09:00:00+00:00",
    attendees=(Attendee("rep@aerchain.io", "Rep", True),), flags=DedupFlags(),
)
SECTIONS = BriefingSections(
    contact_profile="profile", company_deep_dive="deep dive",
    industry_customers="customers", relevant_agents="agents",
    discovery_questions=tuple(f"Q{i}?" for i in range(6)),
)
RECAP = RecapSummary(
    why_it_matters="matters", top_contact_fact="fact1", top_company_fact="fact2",
    talking_points=("a", "b", "c"), references=("ref1",),
    opening_questions=("q1", "q2", "q3"),
)


class TestT2Prompt(unittest.TestCase):

    def test_prompt_includes_five_sections(self):
        company = CompanyProfile(
            company_id="1001", name="Acme Cloud", industry="Cloud Infra", industry_source="crm",
            domain="acmecloud.com", employee_count=480, revenue="", hq="Austin",
        )
        prompt = build_t2_prompt(CONTACT, company, EVENT)
        for marker in ("Contact profile", "Company deep-dive", "Aerchain customers", "agents/use-cases", "discovery questions"):
            self.assertIn(marker, prompt)

    def test_prompt_flags_industry_fallback(self):
        company = CompanyProfile(
            company_id="1001", name="Acme Cloud", industry="", industry_source="web_search_fallback",
            domain="acmecloud.com", employee_count=480, revenue="", hq="Austin",
        )
        prompt = build_t2_prompt(CONTACT, company, EVENT)
        self.assertIn("blank", prompt.lower())
        self.assertIn("classify the company's industry", prompt)

    def test_prompt_uses_crm_industry_when_present(self):
        company = CompanyProfile(
            company_id="1001", name="Acme Cloud", industry="Cloud Infra", industry_source="crm",
            domain="acmecloud.com", employee_count=480, revenue="", hq="Austin",
        )
        prompt = build_t2_prompt(CONTACT, company, EVENT)
        self.assertIn("CRM industry: Cloud Infra", prompt)


class TestT1Prompt(unittest.TestCase):

    def test_prompt_wraps_stored_briefing(self):
        prompt = build_t1_prompt("<html>the briefing</html>")
        self.assertIn("<html>the briefing</html>", prompt)

    def test_blank_stored_briefing_raises(self):
        with self.assertRaises(ValueError):
            build_t1_prompt("")

    def test_whitespace_only_stored_briefing_raises(self):
        with self.assertRaises(ValueError):
            build_t1_prompt("   ")


class TestAssembleHtml(unittest.TestCase):

    def test_briefing_html_includes_all_sections(self):
        company = CompanyProfile(
            company_id="1001", name="Acme Cloud", industry="Cloud Infra", industry_source="crm",
            domain="acmecloud.com", employee_count=480, revenue="", hq="Austin",
        )
        html = assemble_briefing_html(SECTIONS, CONTACT, company)
        self.assertIn("profile", html)
        self.assertIn("deep dive", html)
        self.assertIn("<li>Q0?</li>", html)
        self.assertEqual(html.count("<li>"), 6)

    def test_recap_html_includes_all_fields(self):
        company = CompanyProfile(
            company_id="1001", name="Acme Cloud", industry="Cloud Infra", industry_source="crm",
            domain="acmecloud.com", employee_count=480, revenue="", hq="Austin",
        )
        html = assemble_recap_html(RECAP, CONTACT, company)
        self.assertIn("matters", html)
        self.assertIn("ref1", html)
        self.assertIn("<li>a</li>", html)
        self.assertIn("<li>q1</li>", html)


if __name__ == "__main__":
    unittest.main()
