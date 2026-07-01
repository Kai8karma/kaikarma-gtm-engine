"""Trigger logic for pre-call intelligence — decides when a call gets a briefing.

Encodes SOW Section 4/6's decision as pure, tested functions rather than a
diagram: the daily sweep classifies a call as exactly 2 days out (T-2) or 1
day out (T-1) by calendar date. A call booked inside the 48h lead-time window
never gets a clean T-2 slot — the catch-up rule (the hybrid trigger's reason
to exist) fires an immediate briefing for those instead of waiting on the
sweep. This module is what an n8n IF/Switch node encodes operationally; here
it is a function you can unit test against every boundary.

Pure — no network, no wall-clock reads. Callers pass `today` / `now` in.
"""

from __future__ import annotations

from datetime import date, datetime

from precall_schema import CalendarEvent, VALID_TRIGGER_MODES

CATCHUP_LEAD_HOURS = 48  # SOW Section 4: booked inside 48h misses its T-2 slot.


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def lead_time_hours(event: CalendarEvent) -> float:
    """Hours between when the call was booked and when it happens."""
    booked_at = _parse(event.booked_at_iso)
    call_start = _parse(event.start_iso)
    return (call_start - booked_at).total_seconds() / 3600


def needs_catchup(event: CalendarEvent, threshold_hours: float = CATCHUP_LEAD_HOURS) -> bool:
    """True if the call was booked with less than `threshold_hours` lead time.

    A call booked this close to its start time will never land cleanly in the
    T-2 daily-sweep bucket — by the time the sweep next runs, the call may
    already be inside the window. This is precisely the case Section 6's
    hybrid webhook trigger exists to catch in real time.
    """
    return 0 <= lead_time_hours(event) < threshold_hours


def classify_window(call_start_date: date, today: date) -> str:
    """Classify a call by calendar-day distance from today.

    Returns 't2' (exactly 2 days out), 't1' (exactly 1 day out), or 'none'.
    Matches SOW Section 4's own wording: "finds every call that is exactly
    2 days (and 1 day) out" — date-only comparison, not hour-precision, since
    the daily sweep runs once per day regardless of the call's time-of-day.
    """
    delta_days = (call_start_date - today).days
    if delta_days == 2:
        return "t2"
    if delta_days == 1:
        return "t1"
    return "none"


def plan_action(
    event: CalendarEvent,
    today: date,
    trigger_mode: str = "hybrid",
) -> str:
    """Decide what (if anything) to do for one calendar event today.

    Returns one of:
        'send_briefing'          — T-2 daily-sweep briefing is due
        'send_recap'             — T-1 recap is due
        'send_catchup_briefing'  — booked inside 48h; hybrid mode briefs now
        'skip'                   — nothing to do (already sent, or not due yet)

    Raises:
        ValueError: if trigger_mode is not 'daily_sweep' or 'hybrid'.
    """
    if trigger_mode not in VALID_TRIGGER_MODES:
        raise ValueError(
            f"trigger_mode must be one of {sorted(VALID_TRIGGER_MODES)}, got {trigger_mode!r}"
        )

    if event.flags.summary_sent:
        return "skip"

    if (
        trigger_mode == "hybrid"
        and not event.flags.briefing_sent
        and needs_catchup(event)
    ):
        return "send_catchup_briefing"

    call_start_date = _parse(event.start_iso).date()
    window = classify_window(call_start_date, today)

    if window == "t2" and not event.flags.briefing_sent:
        return "send_briefing"
    if window == "t1" and not event.flags.summary_sent:
        return "send_recap"
    return "skip"


if __name__ == "__main__":
    from precall_schema import Attendee, DedupFlags

    today = date(2026, 7, 1)

    demo_events = [
        CalendarEvent(
            event_id="evt-t2",
            title="Aerchain demo — Acme Cloud",
            description="Discovery call",
            start_iso="2026-07-03T15:00:00+00:00",
            booked_at_iso="2026-06-20T09:00:00+00:00",
            attendees=(Attendee("rep@aerchain.io", "Rep", True),),
            flags=DedupFlags(),
        ),
        CalendarEvent(
            event_id="evt-t1",
            title="Aerchain demo — MidFin Corp",
            description="Demo call",
            start_iso="2026-07-02T15:00:00+00:00",
            booked_at_iso="2026-06-20T09:00:00+00:00",
            attendees=(Attendee("rep@aerchain.io", "Rep", True),),
            flags=DedupFlags(briefing_sent=True),
        ),
        CalendarEvent(
            event_id="evt-catchup",
            title="Aerchain demo — ScaleUp Biotech",
            description="Booked last-minute",
            start_iso="2026-07-02T10:00:00+00:00",
            booked_at_iso="2026-07-01T08:00:00+00:00",  # 26h lead time
            attendees=(Attendee("rep@aerchain.io", "Rep", True),),
            flags=DedupFlags(),
        ),
        CalendarEvent(
            event_id="evt-done",
            title="Aerchain demo — Closed Co",
            description="Already fully briefed",
            start_iso="2026-07-02T15:00:00+00:00",
            booked_at_iso="2026-06-20T09:00:00+00:00",
            attendees=(Attendee("rep@aerchain.io", "Rep", True),),
            flags=DedupFlags(briefing_sent=True, summary_sent=True),
        ),
    ]

    print(f"Trigger scheduler demo — today = {today}\n")
    for evt in demo_events:
        action = plan_action(evt, today, trigger_mode="hybrid")
        print(f"  [{evt.event_id:14s}] lead_time={lead_time_hours(evt):6.1f}h  -> {action}")

    print("\nNo network I/O occurred.")
