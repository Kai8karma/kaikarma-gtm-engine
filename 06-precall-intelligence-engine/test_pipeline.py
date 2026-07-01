"""Tests for the pre-call intelligence batch orchestrator.

    python3 06-precall-intelligence-engine/test_pipeline.py
"""

from __future__ import annotations

import unittest
from datetime import date

from pipeline import RunAction, actionable, plan_run
from precall_schema import Attendee, CalendarEvent, DedupFlags


def _event(event_id, start_iso, booked_at_iso, attendees, **flag_kwargs):
    return CalendarEvent(
        event_id=event_id, title="Demo", description="",
        start_iso=start_iso, booked_at_iso=booked_at_iso,
        attendees=attendees, flags=DedupFlags(**flag_kwargs),
    )


class TestPlanRun(unittest.TestCase):

    def test_batches_multiple_events(self):
        events = [
            _event(
                "e1", "2026-07-03T15:00:00+00:00", "2026-06-20T09:00:00+00:00",
                (Attendee("rep@aerchain.io", "Rep", True), Attendee("buyer@acme.com", "Buyer", False)),
            ),
            _event(
                "e2", "2026-07-02T15:00:00+00:00", "2026-06-20T09:00:00+00:00",
                (Attendee("rep@aerchain.io", "Rep", True),), briefing_sent=True,
            ),
        ]
        actions = plan_run(events, today=date(2026, 7, 1))
        self.assertEqual(actions[0], RunAction("e1", "send_briefing", "buyer@acme.com"))
        self.assertEqual(actions[1], RunAction("e2", "send_recap", None))

    def test_internal_only_event_has_no_prospect_email(self):
        events = [
            _event("e1", "2026-07-03T15:00:00+00:00", "2026-06-20T09:00:00+00:00",
                   (Attendee("rep@aerchain.io", "Rep", True),)),
        ]
        actions = plan_run(events, today=date(2026, 7, 1))
        self.assertIsNone(actions[0].prospect_email)
        self.assertEqual(actions[0].action, "send_briefing")

    def test_daily_sweep_mode_passed_through(self):
        events = [
            _event("e1", "2026-07-02T10:00:00+00:00", "2026-07-01T08:00:00+00:00",
                   (Attendee("rep@aerchain.io", "Rep", True),)),
        ]
        hybrid = plan_run(events, today=date(2026, 7, 1), trigger_mode="hybrid")
        sweep = plan_run(events, today=date(2026, 7, 1), trigger_mode="daily_sweep")
        self.assertEqual(hybrid[0].action, "send_catchup_briefing")
        self.assertEqual(sweep[0].action, "send_recap")


class TestActionable(unittest.TestCase):

    def test_filters_out_skips(self):
        actions = [
            RunAction("e1", "send_briefing", "a@b.com"),
            RunAction("e2", "skip", None),
            RunAction("e3", "send_recap", None),
        ]
        result = actionable(actions)
        self.assertEqual([a.event_id for a in result], ["e1", "e3"])

    def test_empty_list_returns_empty(self):
        self.assertEqual(actionable([]), [])


if __name__ == "__main__":
    unittest.main()
