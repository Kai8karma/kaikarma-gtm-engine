"""Google Calendar adapter — read confirmed calls, write dedup flags.

Parses raw Calendar API event dicts into CalendarEvent (splitting attendees
into internal reps vs. the prospect by domain), and builds the PATCH payloads
that mark briefingSent / summarySent on the event's extended properties so
the daily sweep never re-sends.

EGRESS POLICY (mirrors 04-revops-engine/hubspot_crm.py):
  - No network I/O at import time or in any pure helper.
  - The Calendar SDK / requests session is a RUNTIME dependency, injected via
    the `client` parameter — never imported at module top-level.

GOOGLE CALENDAR EVENTS API SHAPE (v3):
  GET /calendars/{calendarId}/events
  Response: {"items": [{...event...}, ...]}

  Event fields used:
    id                                — event id
    summary                           — title
    description                       — booking notes
    created                           — RFC3339 timestamp; used as booked_at
    start.dateTime                    — RFC3339 timestamp; used as call start
    attendees: [{"email": ..., "displayName": ...}, ...]
    extendedProperties.private.briefingSent / .summarySent — "true"/"false"

  The injected client must expose:
      client.get_events(time_min: str, time_max: str) -> list[dict]
      client.patch_event(event_id: str, patch: dict) -> dict
"""

from __future__ import annotations

from typing import Any

from precall_schema import Attendee, CalendarEvent, DedupFlags

_TRUE_STRINGS: frozenset[str] = frozenset({"true", "True", "TRUE", "1"})


def parse_attendees(
    raw_attendees: list[dict[str, Any]],
    internal_domains: frozenset[str],
) -> tuple[Attendee, ...]:
    """Split raw Calendar attendees into internal-vs-prospect by email domain.

    PURE — no network. `internal_domains` should be lower-cased (e.g.
    frozenset({"aerchain.io"})); comparison is case-insensitive.
    """
    attendees: list[Attendee] = []
    for raw in raw_attendees:
        email = (raw.get("email") or "").strip().lower()
        name = (raw.get("displayName") or "").strip()
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        attendees.append(Attendee(email=email, name=name, is_internal=domain in internal_domains))
    return tuple(attendees)


def prospect_attendee(event: CalendarEvent) -> Attendee | None:
    """First non-internal attendee, or None if every attendee is internal."""
    for a in event.attendees:
        if not a.is_internal:
            return a
    return None


def internal_attendees(event: CalendarEvent) -> tuple[Attendee, ...]:
    """All internal attendees (the reps who receive the briefing/recap)."""
    return tuple(a for a in event.attendees if a.is_internal)


def parse_event(raw_event: dict[str, Any], internal_domains: frozenset[str]) -> CalendarEvent:
    """Convert one raw Google Calendar API event dict into a CalendarEvent.

    PURE — no network, no SDK.

    Raises:
        ValueError: if id, start.dateTime, or created is missing — an event
            without these cannot be scheduled or deduped.
    """
    event_id = raw_event.get("id") or ""
    if not event_id:
        raise ValueError(f"Calendar event missing 'id': {raw_event!r}")

    start_iso = (raw_event.get("start") or {}).get("dateTime") or ""
    if not start_iso:
        raise ValueError(f"Calendar event {event_id!r} missing start.dateTime")

    booked_at_iso = raw_event.get("created") or ""
    if not booked_at_iso:
        raise ValueError(f"Calendar event {event_id!r} missing 'created'")

    private_props: dict[str, Any] = (
        (raw_event.get("extendedProperties") or {}).get("private") or {}
    )
    flags = DedupFlags(
        briefing_sent=str(private_props.get("briefingSent", "")) in _TRUE_STRINGS,
        summary_sent=str(private_props.get("summarySent", "")) in _TRUE_STRINGS,
    )

    return CalendarEvent(
        event_id=event_id,
        title=(raw_event.get("summary") or "").strip(),
        description=(raw_event.get("description") or "").strip(),
        start_iso=start_iso,
        booked_at_iso=booked_at_iso,
        attendees=parse_attendees(raw_event.get("attendees") or [], internal_domains),
        flags=flags,
    )


def parse_events(
    raw_events: list[dict[str, Any]],
    internal_domains: frozenset[str],
) -> list[CalendarEvent]:
    """Convert a batch of raw Calendar API events into CalendarEvent objects."""
    return [parse_event(e, internal_domains) for e in raw_events]


def build_briefing_sent_patch(sent_iso: str) -> dict[str, Any]:
    """PATCH payload marking briefingSent=true with a timestamp for audit."""
    return {
        "extendedProperties": {
            "private": {"briefingSent": "true", "briefingSentAt": sent_iso}
        }
    }


def build_summary_sent_patch(sent_iso: str) -> dict[str, Any]:
    """PATCH payload marking summarySent=true with a timestamp for audit."""
    return {
        "extendedProperties": {
            "private": {"summarySent": "true", "summarySentAt": sent_iso}
        }
    }


def fetch_events(
    client: Any,
    time_min: str,
    time_max: str,
) -> list[CalendarEvent]:
    """Fetch calendar events in [time_min, time_max) via the injected client.

    FAIL LOUD: read failures raise RuntimeError — a silent empty list here
    would make the daily sweep believe there is nothing to brief.
    """
    try:
        raw_events: list[dict[str, Any]] = list(
            client.get_events(time_min=time_min, time_max=time_max)
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Calendar fetch_events failed [{time_min}..{time_max}]: {exc}"
        ) from exc
    return parse_events(raw_events, client.internal_domains)


def patch_event(client: Any, event_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Write a dedup-flag PATCH to one event. Does not raise on failure.

    Matches the executor contract used across the engine (see hubspot_crm.py
    update_contact): individual write failures are logged/retried by the
    caller, not allowed to crash the whole sweep.
    """
    try:
        return client.patch_event(event_id=event_id, patch=patch)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "event_id": event_id, "error": str(exc)}


class FakeCalendarClient:
    """Returns canned events instead of calling the real Calendar API.

    Zero network I/O — suitable for unit tests and zero-egress demos.
    """

    def __init__(
        self,
        events: list[dict[str, Any]] | None = None,
        internal_domains: frozenset[str] = frozenset({"aerchain.io"}),
        raise_on_get: bool = False,
        raise_on_patch: bool = False,
    ) -> None:
        self._events = events or []
        self.internal_domains = internal_domains
        self._raise_get = raise_on_get
        self._raise_patch = raise_on_patch
        self.get_calls: list[tuple[str, str]] = []
        self.patch_calls: list[tuple[str, dict[str, Any]]] = []

    def get_events(self, time_min: str, time_max: str) -> list[dict[str, Any]]:
        self.get_calls.append((time_min, time_max))
        if self._raise_get:
            raise RuntimeError("Simulated Calendar events API error")
        return list(self._events)

    def patch_event(self, event_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self.patch_calls.append((event_id, patch))
        if self._raise_patch:
            raise RuntimeError("Simulated Calendar PATCH error")
        return {"id": event_id, "ok": True, **patch}


if __name__ == "__main__":
    CANNED_EVENTS: list[dict[str, Any]] = [
        {
            "id": "evt-1001",
            "summary": "Aerchain demo — Acme Cloud",
            "description": "Discovery call re: procurement automation",
            "created": "2026-06-20T09:00:00Z",
            "start": {"dateTime": "2026-07-03T15:00:00Z"},
            "attendees": [
                {"email": "rep@aerchain.io", "displayName": "Rep One"},
                {"email": "buyer@acmecloud.com", "displayName": "Buyer Jane"},
            ],
            "extendedProperties": {"private": {"briefingSent": "false", "summarySent": "false"}},
        },
    ]

    client = FakeCalendarClient(events=CANNED_EVENTS)
    print("calendar_parser demo (FakeCalendarClient — zero egress):\n")

    events = fetch_events(client, time_min="2026-07-01T00:00:00Z", time_max="2026-07-10T00:00:00Z")
    for evt in events:
        prospect = prospect_attendee(evt)
        reps = internal_attendees(evt)
        print(f"  [{evt.event_id}] {evt.title}")
        print(f"    prospect : {prospect.email if prospect else '(none found)'}")
        print(f"    reps     : {[r.email for r in reps]}")
        print(f"    flags    : {evt.flags}")

        patch = build_briefing_sent_patch(sent_iso="2026-07-01T08:00:00Z")
        result = patch_event(client, evt.event_id, patch)
        print(f"    patch    : {result}")

    print(f"\n  {len(events)} event(s) parsed. patch_event called {len(client.patch_calls)} time(s).")
    print("  No network I/O occurred.")
