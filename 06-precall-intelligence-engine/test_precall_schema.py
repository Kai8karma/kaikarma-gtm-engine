"""Tests for pre-call intelligence schema validation.

    python3 06-precall-intelligence-engine/test_precall_schema.py
"""

from __future__ import annotations

import unittest

from precall_schema import (
    Attendee,
    BriefingSections,
    CalendarEvent,
    CompanyProfile,
    DedupFlags,
    RecapSummary,
)


class TestCalendarEvent(unittest.TestCase):

    def test_valid_event_constructs(self):
        evt = CalendarEvent(
            event_id="e1",
            title="Demo",
            description="",
            start_iso="2026-07-03T15:00:00+00:00",
            booked_at_iso="2026-06-20T09:00:00+00:00",
            attendees=(Attendee("rep@aerchain.io", "Rep", True),),
            flags=DedupFlags(),
        )
        self.assertEqual(evt.event_id, "e1")

    def test_blank_event_id_raises(self):
        with self.assertRaises(ValueError):
            CalendarEvent(
                event_id="",
                title="Demo",
                description="",
                start_iso="2026-07-03T15:00:00+00:00",
                booked_at_iso="2026-06-20T09:00:00+00:00",
                attendees=(Attendee("rep@aerchain.io", "Rep", True),),
                flags=DedupFlags(),
            )

    def test_no_attendees_raises(self):
        with self.assertRaises(ValueError):
            CalendarEvent(
                event_id="e1",
                title="Demo",
                description="",
                start_iso="2026-07-03T15:00:00+00:00",
                booked_at_iso="2026-06-20T09:00:00+00:00",
                attendees=(),
                flags=DedupFlags(),
            )


class TestCompanyProfile(unittest.TestCase):

    def test_valid_industry_source_crm(self):
        c = CompanyProfile(
            company_id="1", name="Acme", industry="software", industry_source="crm",
            domain="acme.com", employee_count=100, revenue="", hq="",
        )
        self.assertEqual(c.industry_source, "crm")

    def test_valid_industry_source_fallback(self):
        c = CompanyProfile(
            company_id="1", name="Acme", industry="", industry_source="web_search_fallback",
            domain="acme.com", employee_count=100, revenue="", hq="",
        )
        self.assertEqual(c.industry_source, "web_search_fallback")

    def test_invalid_industry_source_raises(self):
        with self.assertRaises(ValueError):
            CompanyProfile(
                company_id="1", name="Acme", industry="software", industry_source="guessed",
                domain="acme.com", employee_count=100, revenue="", hq="",
            )


class TestBriefingSections(unittest.TestCase):

    def _valid_kwargs(self, **overrides):
        kwargs = dict(
            contact_profile="profile text",
            company_deep_dive="deep dive text",
            industry_customers="customers text",
            relevant_agents="agents text",
            discovery_questions=tuple(f"Q{i}?" for i in range(6)),
        )
        kwargs.update(overrides)
        return kwargs

    def test_valid_sections_construct(self):
        s = BriefingSections(**self._valid_kwargs())
        self.assertEqual(len(s.discovery_questions), 6)

    def test_eight_questions_ok(self):
        s = BriefingSections(**self._valid_kwargs(discovery_questions=tuple(f"Q{i}?" for i in range(8))))
        self.assertEqual(len(s.discovery_questions), 8)

    def test_blank_section_raises(self):
        with self.assertRaises(ValueError):
            BriefingSections(**self._valid_kwargs(contact_profile="   "))

    def test_too_few_questions_raises(self):
        with self.assertRaises(ValueError):
            BriefingSections(**self._valid_kwargs(discovery_questions=("Q1?", "Q2?")))

    def test_too_many_questions_raises(self):
        with self.assertRaises(ValueError):
            BriefingSections(
                **self._valid_kwargs(discovery_questions=tuple(f"Q{i}?" for i in range(9)))
            )


class TestRecapSummary(unittest.TestCase):

    def _valid_kwargs(self, **overrides):
        kwargs = dict(
            why_it_matters="matters",
            top_contact_fact="fact",
            top_company_fact="fact",
            talking_points=("a", "b", "c"),
            references=("ref1",),
            opening_questions=("q1", "q2", "q3"),
        )
        kwargs.update(overrides)
        return kwargs

    def test_valid_recap_constructs(self):
        r = RecapSummary(**self._valid_kwargs())
        self.assertEqual(len(r.talking_points), 3)

    def test_two_references_ok(self):
        r = RecapSummary(**self._valid_kwargs(references=("ref1", "ref2")))
        self.assertEqual(len(r.references), 2)

    def test_wrong_talking_points_count_raises(self):
        with self.assertRaises(ValueError):
            RecapSummary(**self._valid_kwargs(talking_points=("a", "b")))

    def test_zero_references_raises(self):
        with self.assertRaises(ValueError):
            RecapSummary(**self._valid_kwargs(references=()))

    def test_three_references_raises(self):
        with self.assertRaises(ValueError):
            RecapSummary(**self._valid_kwargs(references=("a", "b", "c")))

    def test_wrong_opening_questions_count_raises(self):
        with self.assertRaises(ValueError):
            RecapSummary(**self._valid_kwargs(opening_questions=("q1", "q2")))


if __name__ == "__main__":
    unittest.main()
