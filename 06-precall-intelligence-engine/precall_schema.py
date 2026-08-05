"""Typed primitives for pre-call intelligence — briefings and recaps for demo calls.

A CalendarEvent arrives from Google Calendar with attendees split into internal
reps vs. the prospect, plus dedup flags (briefingSent / summarySent) so nothing
sends twice. A ContactProfile + CompanyProfile come from HubSpot enrichment. A
BriefingSections holds the five T-2 sections; a RecapSummary holds the T-1
one-screen refresher. All frozen, all validated at construction — a malformed
briefing must fail loud, not ship half-written to a rep's inbox.

Pure data — no network, no state.
"""

from __future__ import annotations

from dataclasses import dataclass

VALID_INDUSTRY_SOURCES: frozenset[str] = frozenset({"crm", "web_search_fallback"})
VALID_TRIGGER_MODES: frozenset[str] = frozenset({"daily_sweep", "hybrid"})


@dataclass(frozen=True)
class Attendee:
    """One calendar-invite attendee."""

    email: str
    name: str
    is_internal: bool


@dataclass(frozen=True)
class DedupFlags:
    """Send-state for one calendar event — never re-send once True."""

    briefing_sent: bool = False
    summary_sent: bool = False


@dataclass(frozen=True)
class CalendarEvent:
    """A confirmed demo call read from Google Calendar.

    ``start_iso`` and ``booked_at_iso`` are ISO-8601 strings (UTC). Keeping
    them as strings at the schema boundary avoids importing datetime parsing
    rules into pure data; parsing happens once in calendar_parser.py.
    """

    event_id: str
    title: str
    description: str
    start_iso: str
    booked_at_iso: str
    attendees: tuple[Attendee, ...]
    flags: DedupFlags

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("CalendarEvent.event_id must not be blank")
        if not self.attendees:
            raise ValueError(f"CalendarEvent {self.event_id!r} has no attendees")


@dataclass(frozen=True)
class ContactProfile:
    """HubSpot contact record for the prospect."""

    contact_id: str
    first_name: str
    last_name: str
    title: str
    email: str
    linkedin_url: str
    company_id: str | None


@dataclass(frozen=True)
class CompanyProfile:
    """HubSpot company record for the prospect's employer."""

    company_id: str
    name: str
    industry: str
    industry_source: str  # 'crm' | 'web_search_fallback'
    domain: str
    employee_count: int
    revenue: str
    hq: str

    def __post_init__(self) -> None:
        if self.industry_source not in VALID_INDUSTRY_SOURCES:
            raise ValueError(
                f"industry_source must be one of {sorted(VALID_INDUSTRY_SOURCES)}, "
                f"got {self.industry_source!r}"
            )


@dataclass(frozen=True)
class BriefingSections:
    """The five T-2 briefing sections, already written."""

    contact_profile: str
    company_deep_dive: str
    industry_customers: str
    relevant_agents: str
    discovery_questions: tuple[str, ...]  # 6-8 suggested questions

    def __post_init__(self) -> None:
        blanks = [
            name
            for name, val in (
                ("contact_profile", self.contact_profile),
                ("company_deep_dive", self.company_deep_dive),
                ("industry_customers", self.industry_customers),
                ("relevant_agents", self.relevant_agents),
            )
            if not val.strip()
        ]
        if blanks:
            raise ValueError(f"BriefingSections has blank section(s): {blanks}")
        if not (6 <= len(self.discovery_questions) <= 8):
            raise ValueError(
                f"discovery_questions must have 6-8 items, got {len(self.discovery_questions)}"
            )


@dataclass(frozen=True)
class RecapSummary:
    """The T-1 one-screen refresher."""

    why_it_matters: str
    top_contact_fact: str
    top_company_fact: str
    talking_points: tuple[str, ...]     # exactly 3
    references: tuple[str, ...]         # 1-2
    opening_questions: tuple[str, ...]  # exactly 3

    def __post_init__(self) -> None:
        if len(self.talking_points) != 3:
            raise ValueError(
                f"talking_points must have exactly 3 items, got {len(self.talking_points)}"
            )
        if not (1 <= len(self.references) <= 2):
            raise ValueError(
                f"references must have 1-2 items, got {len(self.references)}"
            )
        if len(self.opening_questions) != 3:
            raise ValueError(
                f"opening_questions must have exactly 3 items, got {len(self.opening_questions)}"
            )
