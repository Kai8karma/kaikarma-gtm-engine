"""Tests for the Google Calendar adapter.

    python3 06-precall-intelligence-engine/test_calendar_parser.py
"""

from __future__ import annotations

import unittest

from calendar_parser import (
    FakeCalendarClient,
    build_briefing_sent_patch,
    build_summary_sent_patch,
    fetch_events,
    internal_attendees,
    parse_attendees,
    parse_event,
    patch_event,
    prospect_attendee,
)

INTERNAL = frozenset({"aerchain.io"})

RAW_EVENT = {
    "id": "evt-1001",
    "summary": "Aerchain demo — Acme Cloud",
    "description": "Discovery call",
    "created": "2026-06-20T09:00:00Z",
    "start": {"dateTime": "2026-07-03T15:00:00Z"},
    "attendees": [
        {"email": "rep@aerchain.io", "displayName": "Rep One"},
        {"email": "buyer@acmecloud.com", "displayName": "Buyer Jane"},
    ],
    "extendedProperties": {"private": {"briefingSent": "false", "summarySent": "false"}},
}


class TestParseAttendees(unittest.TestCase):

    def test_splits_internal_vs_prospect(self):
        attendees = parse_attendees(RAW_EVENT["attendees"], INTERNAL)
        internal = [a for a in attendees if a.is_internal]
        external = [a for a in attendees if not a.is_internal]
        self.assertEqual(len(internal), 1)
        self.assertEqual(len(external), 1)
        self.assertEqual(external[0].email, "buyer@acmecloud.com")

    def test_email_domain_match_is_case_insensitive(self):
        attendees = parse_attendees([{"email": "Rep@AERCHAIN.IO", "displayName": "Rep"}], INTERNAL)
        self.assertTrue(attendees[0].is_internal)


class TestParseEvent(unittest.TestCase):

    def test_parses_full_event(self):
        evt = parse_event(RAW_EVENT, INTERNAL)
        self.assertEqual(evt.event_id, "evt-1001")
        self.assertEqual(evt.start_iso, "2026-07-03T15:00:00Z")
        self.assertEqual(evt.booked_at_iso, "2026-06-20T09:00:00Z")
        self.assertFalse(evt.flags.briefing_sent)
        self.assertFalse(evt.flags.summary_sent)

    def test_missing_id_raises(self):
        bad = {**RAW_EVENT, "id": ""}
        with self.assertRaises(ValueError):
            parse_event(bad, INTERNAL)

    def test_missing_start_raises(self):
        bad = {**RAW_EVENT, "start": {}}
        with self.assertRaises(ValueError):
            parse_event(bad, INTERNAL)

    def test_missing_created_raises(self):
        bad = {**RAW_EVENT, "created": ""}
        with self.assertRaises(ValueError):
            parse_event(bad, INTERNAL)

    def test_dedup_flags_parsed_true(self):
        flagged = {
            **RAW_EVENT,
            "extendedProperties": {"private": {"briefingSent": "true", "summarySent": "false"}},
        }
        evt = parse_event(flagged, INTERNAL)
        self.assertTrue(evt.flags.briefing_sent)
        self.assertFalse(evt.flags.summary_sent)

    def test_missing_extended_properties_defaults_false(self):
        bare = {k: v for k, v in RAW_EVENT.items() if k != "extendedProperties"}
        evt = parse_event(bare, INTERNAL)
        self.assertFalse(evt.flags.briefing_sent)
        self.assertFalse(evt.flags.summary_sent)


class TestAttendeeHelpers(unittest.TestCase):

    def test_prospect_attendee_found(self):
        evt = parse_event(RAW_EVENT, INTERNAL)
        prospect = prospect_attendee(evt)
        self.assertEqual(prospect.email, "buyer@acmecloud.com")

    def test_prospect_attendee_none_when_all_internal(self):
        internal_only = {**RAW_EVENT, "attendees": [{"email": "rep@aerchain.io", "displayName": "Rep"}]}
        evt = parse_event(internal_only, INTERNAL)
        self.assertIsNone(prospect_attendee(evt))

    def test_internal_attendees(self):
        evt = parse_event(RAW_EVENT, INTERNAL)
        reps = internal_attendees(evt)
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0].email, "rep@aerchain.io")


class TestPatchBuilders(unittest.TestCase):

    def test_briefing_sent_patch_shape(self):
        patch = build_briefing_sent_patch("2026-07-01T08:00:00Z")
        self.assertEqual(
            patch["extendedProperties"]["private"]["briefingSent"], "true"
        )
        self.assertEqual(
            patch["extendedProperties"]["private"]["briefingSentAt"], "2026-07-01T08:00:00Z"
        )

    def test_summary_sent_patch_shape(self):
        patch = build_summary_sent_patch("2026-07-02T08:00:00Z")
        self.assertEqual(patch["extendedProperties"]["private"]["summarySent"], "true")


class TestFakeClientRoundTrip(unittest.TestCase):

    def test_fetch_events_returns_parsed_events(self):
        client = FakeCalendarClient(events=[RAW_EVENT], internal_domains=INTERNAL)
        events = fetch_events(client, time_min="2026-07-01T00:00:00Z", time_max="2026-07-10T00:00:00Z")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, "evt-1001")
        self.assertEqual(client.get_calls, [("2026-07-01T00:00:00Z", "2026-07-10T00:00:00Z")])

    def test_fetch_events_raises_on_client_error(self):
        client = FakeCalendarClient(events=[RAW_EVENT], internal_domains=INTERNAL, raise_on_get=True)
        with self.assertRaises(RuntimeError):
            fetch_events(client, time_min="x", time_max="y")

    def test_patch_event_success(self):
        client = FakeCalendarClient(events=[], internal_domains=INTERNAL)
        result = patch_event(client, "evt-1001", build_briefing_sent_patch("2026-07-01T08:00:00Z"))
        self.assertTrue(result["ok"])
        self.assertEqual(client.patch_calls[0][0], "evt-1001")

    def test_patch_event_failure_does_not_raise(self):
        client = FakeCalendarClient(events=[], internal_domains=INTERNAL, raise_on_patch=True)
        result = patch_event(client, "evt-1001", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["event_id"], "evt-1001")


if __name__ == "__main__":
    unittest.main()
