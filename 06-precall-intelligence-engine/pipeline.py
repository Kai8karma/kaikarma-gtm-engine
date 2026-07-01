"""Batch orchestrator — the daily sweep / webhook entrypoint's decision layer.

`plan_run` is what the n8n schedule-trigger node and the sub-48h webhook node
both call into: given the events currently on the calendar, decide per-event
what to do today. All strategic timing logic lives in trigger_scheduler.py;
this module just batches it and attaches the prospect email each action needs
downstream (HubSpot lookup, Claude call, Gmail send).

Pure — no network. Callers pass `today` in explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from calendar_parser import prospect_attendee
from precall_schema import CalendarEvent
from trigger_scheduler import plan_action

ACTIONS_REQUIRING_PROSPECT: frozenset[str] = frozenset(
    {"send_briefing", "send_catchup_briefing"}
)


@dataclass(frozen=True)
class RunAction:
    """One event's decision for today's run."""

    event_id: str
    action: str  # 'send_briefing' | 'send_recap' | 'send_catchup_briefing' | 'skip'
    prospect_email: str | None


def plan_run(
    events: list[CalendarEvent],
    today: date,
    trigger_mode: str = "hybrid",
) -> list[RunAction]:
    """Decide today's action for every event in one pass.

    Events with no prospect attendee (every attendee is internal, e.g. an
    internal-only test invite) still get an action verdict — the caller
    decides whether to skip send steps for those; this function only
    encodes the trigger doctrine, not the send logic.
    """
    actions: list[RunAction] = []
    for event in events:
        action = plan_action(event, today, trigger_mode)
        prospect = prospect_attendee(event)
        actions.append(
            RunAction(
                event_id=event.event_id,
                action=action,
                prospect_email=prospect.email if prospect else None,
            )
        )
    return actions


def actionable(actions: list[RunAction]) -> list[RunAction]:
    """Filter out 'skip' verdicts — what the sweep actually has to do today."""
    return [a for a in actions if a.action != "skip"]


if __name__ == "__main__":
    from precall_schema import Attendee, DedupFlags

    today = date(2026, 7, 1)
    demo_events = [
        CalendarEvent(
            event_id="evt-t2",
            title="Aerchain demo — Acme Cloud",
            description="",
            start_iso="2026-07-03T15:00:00+00:00",
            booked_at_iso="2026-06-20T09:00:00+00:00",
            attendees=(
                Attendee("rep@aerchain.io", "Rep", True),
                Attendee("buyer@acmecloud.com", "Buyer", False),
            ),
            flags=DedupFlags(),
        ),
        CalendarEvent(
            event_id="evt-internal-only",
            title="Internal test invite",
            description="",
            start_iso="2026-07-03T15:00:00+00:00",
            booked_at_iso="2026-06-20T09:00:00+00:00",
            attendees=(Attendee("rep@aerchain.io", "Rep", True),),
            flags=DedupFlags(),
        ),
    ]

    print(f"pipeline demo — today = {today}\n")
    all_actions = plan_run(demo_events, today, trigger_mode="hybrid")
    for a in all_actions:
        print(f"  {a}")

    print(f"\n  {len(actionable(all_actions))}/{len(all_actions)} event(s) need action today.")
    print("  No network I/O occurred.")
