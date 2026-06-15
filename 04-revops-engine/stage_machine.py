"""Lifecycle state machine for the RevOps engine.

Stages: subscriber → lead → mql → sql → opportunity → customer
Sink:   disqualified  (any stage can fall into it; no exit)

    python3 04-revops-engine/stage_machine.py        # demo
    python3 04-revops-engine/test_revops_extended.py # tests

Stdlib only, no network, no state. Air-gapped safe.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Stage constants — use these instead of raw strings in callers.
# ---------------------------------------------------------------------------
SUBSCRIBER = "subscriber"
LEAD = "lead"
MQL = "mql"
SQL = "sql"
OPPORTUNITY = "opportunity"
CUSTOMER = "customer"
DISQUALIFIED = "disqualified"

# Canonical stage order (excluding the sink).
LIFECYCLE_STAGES: tuple[str, ...] = (
    SUBSCRIBER, LEAD, MQL, SQL, OPPORTUNITY, CUSTOMER,
)

# ---------------------------------------------------------------------------
# Transition table — {current_stage: {event: next_stage}}
# Only legal transitions are listed; any unlisted (stage, event) pair raises.
# ---------------------------------------------------------------------------
TRANSITIONS: dict[str, dict[str, str]] = {
    SUBSCRIBER: {
        "activate":     LEAD,
        "disqualify":   DISQUALIFIED,
    },
    LEAD: {
        "qualify_marketing": MQL,
        "disqualify":        DISQUALIFIED,
    },
    MQL: {
        "accept_sales": SQL,
        "recycle":      LEAD,
        "disqualify":   DISQUALIFIED,
    },
    SQL: {
        "create_opportunity": OPPORTUNITY,
        "recycle":            MQL,
        "disqualify":         DISQUALIFIED,
    },
    OPPORTUNITY: {
        "close_won":    CUSTOMER,
        "close_lost":   DISQUALIFIED,
        "disqualify":   DISQUALIFIED,
    },
    CUSTOMER: {
        "churn":        DISQUALIFIED,
        # customers stay customers — no forward advance defined here
    },
    DISQUALIFIED: {
        # sink — no exits
    },
}


class IllegalTransitionError(ValueError):
    """Raised when an event is not legal from the current stage."""


def advance(current: str, event: str) -> str:
    """Return the next stage for *current* + *event*, or raise.

    Raises:
        ValueError   — if *current* is not a recognised stage.
        IllegalTransitionError — if *event* is not legal from *current*.
    """
    if current not in TRANSITIONS:
        raise ValueError(
            f"Unknown stage {current!r}. Valid stages: {sorted(TRANSITIONS)}"
        )
    events = TRANSITIONS[current]
    if event not in events:
        raise IllegalTransitionError(
            f"Event {event!r} is not legal from stage {current!r}. "
            f"Legal events: {sorted(events) or '(none)'}"
        )
    return events[event]


@dataclass(frozen=True)
class StageInfo:
    """Metadata about one stage — useful for inspection and reporting."""

    name: str
    is_sink: bool
    legal_events: tuple[str, ...]


def stage_info(stage: str) -> StageInfo:
    """Return metadata for *stage*. Raises ValueError for unknown stages."""
    if stage not in TRANSITIONS:
        raise ValueError(f"Unknown stage {stage!r}")
    events = TRANSITIONS[stage]
    sink = stage == DISQUALIFIED
    return StageInfo(
        name=stage,
        is_sink=sink,
        legal_events=tuple(sorted(events)),
    )


if __name__ == "__main__":
    print("Lifecycle stage machine demo\n")
    print(f"  Stages:  {' → '.join(LIFECYCLE_STAGES)}  →  [{DISQUALIFIED}]\n")

    # Walk the happy path.
    happy_path = [
        (SUBSCRIBER,   "activate"),
        (LEAD,         "qualify_marketing"),
        (MQL,          "accept_sales"),
        (SQL,          "create_opportunity"),
        (OPPORTUNITY,  "close_won"),
    ]
    current = SUBSCRIBER
    print("  Happy path:")
    for stage, event in happy_path:
        nxt = advance(stage, event)
        print(f"    {stage:16s} --[{event}]--> {nxt}")
        current = nxt

    print()

    # Demonstrate an illegal transition.
    print("  Illegal transition (subscriber → accept_sales):")
    try:
        advance(SUBSCRIBER, "accept_sales")
    except IllegalTransitionError as exc:
        print(f"    IllegalTransitionError: {exc}")

    print()

    # Print the full transition table.
    print("  Full transition table:")
    for src, events in TRANSITIONS.items():
        for event, dst in events.items():
            print(f"    {src:16s} + {event:22s} → {dst}")
