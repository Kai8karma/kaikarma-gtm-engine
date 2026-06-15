"""Typed ICP primitives.

The ICP is a data structure you can version, diff, and test — not a 100-point
table you eyeball. An ICPProfile is the definition of "who we sell to"; an
Account is a candidate; a ScoredAccount is the verdict plus its rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Default dimension weights (must sum to 100). Signals are weighted heavily and
# kept separate from static firmographic fit — "right account" and "right
# moment" are different questions and should score independently.
DEFAULT_WEIGHTS: dict[str, int] = {
    "firmographic": 40,
    "technographic": 20,
    "signal": 30,
    "fit": 10,
}

# Buying-signal hierarchy, ranked by observed reply-rate impact. Values are the
# fraction of the signal dimension a single signal earns; multiple signals stack
# but the dimension is capped at 1.0 (see icp_scorer).
SIGNAL_VALUE: dict[str, float] = {
    "job_change": 1.0,
    "hiring": 0.8,
    "website_visit": 0.7,
    "funding": 0.6,
    "tech_change": 0.5,
}


@dataclass(frozen=True)
class ICPProfile:
    """The definition of an ideal customer for one engagement."""

    name: str
    target_industries: frozenset[str]
    employee_min: int
    employee_max: int
    target_tech: frozenset[str] = frozenset()
    weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if total != 100:
            raise ValueError(f"weights must sum to 100, got {total}")
        if self.employee_min > self.employee_max:
            raise ValueError("employee_min cannot exceed employee_max")


@dataclass(frozen=True)
class Account:
    """A candidate account to score against an ICPProfile."""

    name: str
    industry: str
    employees: int
    tech_stack: frozenset[str] = frozenset()
    signals: frozenset[str] = frozenset()
    fit: float = 0.0  # 0..1 manual/psychographic fit (review notes, mission match)


@dataclass(frozen=True)
class ScoredAccount:
    """The verdict: a 0-100 score, an A/B/C/D tier, and a transparent breakdown."""

    name: str
    score: float
    tier: str
    breakdown: dict[str, float]  # per-dimension points contributed
    top_signal: str | None
