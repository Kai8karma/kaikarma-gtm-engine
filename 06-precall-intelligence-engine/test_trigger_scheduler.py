"""Tests for the pre-call trigger scheduler — every timing rule must be provably correct.

    python3 06-precall-intelligence-engine/test_trigger_scheduler.py
"""

from __future__ import annotations

import unittest
from datetime import date

from precall_schema import Attendee, CalendarEvent, DedupFlags
from trigger_scheduler import classify_window, lead_time_hours, needs_catchup, plan_action


def _event(start_iso, booked_at_iso, briefing_sent=False, summary_sent=False, event_id="e1"):
    return CalendarEvent(
        event_id=event_id,
        title="Demo",
        description="",
        start_iso=start_iso,
        booked_at_iso=booked_at_iso,
        attendees=(Attendee("rep@aerchain.io", "Rep", True),),
        flags=DedupFlags(briefing_sent=briefing_sent, summary_sent=summary_sent),
    )


class TestClassifyWindow(unittest.TestCase):

    def test_exactly_two_days_out_is_t2(self):
        self.assertEqual(classify_window(date(2026, 7, 3), date(2026, 7, 1)), "t2")

    def test_exactly_one_day_out_is_t1(self):
        self.assertEqual(classify_window(date(2026, 7, 2), date(2026, 7, 1)), "t1")

    def test_three_days_out_is_none(self):
        self.assertEqual(classify_window(date(2026, 7, 4), date(2026, 7, 1)), "none")

    def test_same_day_is_none(self):
        self.assertEqual(classify_window(date(2026, 7, 1), date(2026, 7, 1)), "none")

    def test_past_call_is_none(self):
        self.assertEqual(classify_window(date(2026, 6, 30), date(2026, 7, 1)), "none")


class TestLeadTime(unittest.TestCase):

    def test_lead_time_hours_computed_correctly(self):
        evt = _event("2026-07-03T15:00:00+00:00", "2026-06-20T09:00:00+00:00")
        self.assertAlmostEqual(lead_time_hours(evt), 13 * 24 + 6, places=1)

    def test_needs_catchup_true_under_threshold(self):
        evt = _event("2026-07-02T10:00:00+00:00", "2026-07-01T08:00:00+00:00")  # 26h
        self.assertTrue(needs_catchup(evt))

    def test_needs_catchup_false_over_threshold(self):
        evt = _event("2026-07-03T15:00:00+00:00", "2026-06-20T09:00:00+00:00")
        self.assertFalse(needs_catchup(evt))

    def test_needs_catchup_false_for_past_call(self):
        evt = _event("2026-06-25T15:00:00+00:00", "2026-06-30T09:00:00+00:00")
        self.assertFalse(needs_catchup(evt))


class TestPlanAction(unittest.TestCase):

    def test_t2_window_not_yet_sent_sends_briefing(self):
        evt = _event("2026-07-03T15:00:00+00:00", "2026-06-20T09:00:00+00:00")
        self.assertEqual(plan_action(evt, date(2026, 7, 1)), "send_briefing")

    def test_t2_window_already_sent_skips(self):
        evt = _event("2026-07-03T15:00:00+00:00", "2026-06-20T09:00:00+00:00", briefing_sent=True)
        self.assertEqual(plan_action(evt, date(2026, 7, 1)), "skip")

    def test_t1_window_sends_recap(self):
        evt = _event("2026-07-02T15:00:00+00:00", "2026-06-20T09:00:00+00:00", briefing_sent=True)
        self.assertEqual(plan_action(evt, date(2026, 7, 1)), "send_recap")

    def test_t1_window_already_summarized_skips(self):
        evt = _event(
            "2026-07-02T15:00:00+00:00", "2026-06-20T09:00:00+00:00",
            briefing_sent=True, summary_sent=True,
        )
        self.assertEqual(plan_action(evt, date(2026, 7, 1)), "skip")

    def test_no_window_skips(self):
        evt = _event("2026-07-10T15:00:00+00:00", "2026-06-20T09:00:00+00:00")
        self.assertEqual(plan_action(evt, date(2026, 7, 1)), "skip")

    def test_hybrid_catchup_fires_immediately(self):
        evt = _event("2026-07-02T10:00:00+00:00", "2026-07-01T08:00:00+00:00")  # 26h lead
        self.assertEqual(plan_action(evt, date(2026, 7, 1), trigger_mode="hybrid"), "send_catchup_briefing")

    def test_daily_sweep_mode_ignores_catchup_rule(self):
        """Without hybrid mode, a sub-48h booking has no real-time path — the
        sweep only acts if it happens to land in a T-2/T-1 date window."""
        evt = _event("2026-07-02T10:00:00+00:00", "2026-07-01T08:00:00+00:00")  # 26h lead, 1 day out
        self.assertEqual(plan_action(evt, date(2026, 7, 1), trigger_mode="daily_sweep"), "send_recap")

    def test_catchup_not_retriggered_once_briefed(self):
        evt = _event(
            "2026-07-02T10:00:00+00:00", "2026-07-01T08:00:00+00:00", briefing_sent=True,
        )
        self.assertNotEqual(plan_action(evt, date(2026, 7, 1), trigger_mode="hybrid"), "send_catchup_briefing")

    def test_invalid_trigger_mode_raises(self):
        evt = _event("2026-07-03T15:00:00+00:00", "2026-06-20T09:00:00+00:00")
        with self.assertRaises(ValueError):
            plan_action(evt, date(2026, 7, 1), trigger_mode="carrier_pigeon")


if __name__ == "__main__":
    unittest.main()
