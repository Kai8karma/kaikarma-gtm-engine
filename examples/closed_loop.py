"""End-to-end learning loop — the moat made real.

Ties together all three pillars:
    01-list-engine   → score accounts against an ICP
    05-brain-integration → log outcomes, tune weights, re-score

Exposes three reusable functions:
    score_accounts(accounts, profile)  → ranked list[ScoredAccount]
    learn(profile, outcomes)           → new ICPProfile with tuned weights
    main()                             → full narrative demo (no real state written)

    python3 examples/closed_loop.py   # demo

Stdlib only, no network, no external DB.  Safe to run air-gapped.
"""

from __future__ import annotations

import dataclasses
import sys
import os
import tempfile
from pathlib import Path

# ── pillar path injection ────────────────────────────────────────────────────
# Pillars are plain directories (not packages), so we add each to sys.path so
# their modules are importable by name.
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
[sys.path.insert(0, os.path.join(BASE, d))
 for d in ("01-list-engine", "03-abm-paid-engine", "05-brain-integration")]

# ── pillar imports (after path injection) ────────────────────────────────────
from icp_schema import Account, ICPProfile  # noqa: E402
from icp_scorer import rank                                   # noqa: E402
from brain_schema import Outcome                              # noqa: E402
from outcome_store import log_outcome                         # noqa: E402
from policy_tuner import tune                                 # noqa: E402

# Re-export so callers don't have to import the pillar modules directly.
ScoredAccount = __import__("icp_schema", fromlist=["ScoredAccount"]).ScoredAccount


# ── public API ───────────────────────────────────────────────────────────────

def score_accounts(
    accounts: list[Account],
    profile: ICPProfile,
) -> list[ScoredAccount]:
    """Score and rank *accounts* against *profile*. Best score first.

    Thin wrapper over icp_scorer.rank — exists so callers import one module.
    """
    return rank(accounts, profile)


def learn(
    profile: ICPProfile,
    outcomes: list[Outcome],
) -> ICPProfile:
    """Return a new ICPProfile whose weights have been tuned by *outcomes*.

    policy_tuner.tune() returns float weights; ICPProfile expects int weights
    (enforced by sum-to-100 check).  We round-then-redistribute any rounding
    error to the largest dimension so the invariant is always satisfied.

    Args:
        profile:   the current ICP to improve.
        outcomes:  closed feedback signals (win/loss/neutral per dimension).

    Returns:
        A new, frozen ICPProfile identical to *profile* except for its weights.
    """
    tuned_floats = tune(profile.weights, outcomes)

    # Convert floats → ints while preserving sum == original total.
    total = sum(profile.weights.values())  # typically 100
    int_weights: dict[str, int] = {k: int(v) for k, v in tuned_floats.items()}
    remainder = total - sum(int_weights.values())

    if remainder != 0:
        # Distribute rounding residual to the dimension with the largest
        # fractional part (greedy; deterministic given dict insertion order).
        fractional = {k: tuned_floats[k] - int_weights[k] for k in tuned_floats}
        for key in sorted(fractional, key=fractional.__getitem__, reverse=True):
            if remainder == 0:
                break
            step = 1 if remainder > 0 else -1
            int_weights[key] += step
            remainder -= step

    return dataclasses.replace(profile, weights=int_weights)


# ── demo ─────────────────────────────────────────────────────────────────────

_DEMO_PROFILE = ICPProfile(
    name="B2B SaaS, mid-market, RevOps buyer",
    target_industries=frozenset({"software", "saas", "fintech"}),
    employee_min=50,
    employee_max=1000,
    target_tech=frozenset({"hubspot", "salesforce", "clay"}),
)

_DEMO_ACCOUNTS: list[Account] = [
    Account(
        "SignalFirst Corp",
        "software",
        400,
        frozenset({"hubspot"}),
        frozenset({"job_change", "hiring"}),
        fit=0.6,
    ),
    Account(
        "FirmMatch Ltd",
        "saas",
        250,
        frozenset({"salesforce", "clay"}),
        frozenset(),
        fit=0.8,
    ),
    Account(
        "TechBlind Inc",
        "fintech",
        150,
        frozenset(),
        frozenset({"funding"}),
        fit=0.5,
    ),
    Account(
        "OutOfBand LLC",
        "manufacturing",
        12,
        frozenset(),
        frozenset(),
        fit=0.2,
    ),
]

# Outcomes reflecting that signal-driven accounts actually closed while
# pure-firmographic matches stalled.
_DEMO_OUTCOMES: list[Outcome] = [
    Outcome(
        "icp_dimension",
        "signal",
        "win",
        confidence=0.9,
        note="job_change + hiring correlates strongly with close",
    ),
    Outcome(
        "icp_dimension",
        "signal",
        "win",
        confidence=0.8,
        note="funding signal — second data point",
    ),
    Outcome(
        "icp_dimension",
        "firmographic",
        "loss",
        confidence=0.7,
        note="pure industry/size match didn't predict close rate",
    ),
    Outcome(
        "icp_dimension",
        "technographic",
        "loss",
        confidence=0.6,
        note="tech-stack overlap insufficient predictor this cohort",
    ),
]


def main() -> None:
    """Run the full closed-loop narrative and print results."""

    profile = _DEMO_PROFILE

    # ── PHASE 1: initial scoring ──────────────────────────────────────────────
    print("=" * 60)
    print("PHASE 1 — Score accounts with DEFAULT weights")
    print(f"  weights: {profile.weights}")
    print("=" * 60)
    before = score_accounts(_DEMO_ACCOUNTS, profile)
    for sa in before:
        sig = f" [{sa.top_signal}]" if sa.top_signal else ""
        print(f"  {sa.tier}  {sa.score:5.1f}  {sa.name}{sig}")
        print(f"         {sa.breakdown}")
    print()

    # ── PHASE 2: log outcomes to a throw-away temp store ─────────────────────
    print("PHASE 2 — Log outcomes (tempfile — no real state written)")
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "outcomes.json"
        for o in _DEMO_OUTCOMES:
            log_outcome(o, store)
            print(f"  logged [{o.verdict:7s}] {o.key}  conf={o.confidence}")
        print()

        # ── PHASE 3: learn — produce a tuned profile ──────────────────────────
        print("PHASE 3 — Tune weights from outcomes")
        tuned_profile = learn(profile, _DEMO_OUTCOMES)
        print(f"  before: {profile.weights}")
        print(f"  after:  {tuned_profile.weights}")
        print(f"  sum check: {sum(tuned_profile.weights.values())} (must be 100)")
        print()

        # ── PHASE 4: re-score with tuned profile ─────────────────────────────
        print("PHASE 4 — Re-score accounts with TUNED weights")
        after = score_accounts(_DEMO_ACCOUNTS, tuned_profile)
        print("  name                tier  before → after  Δscore")
        print("  " + "-" * 50)
        before_map = {sa.name: sa for sa in before}
        for sa in after:
            old = before_map[sa.name]
            delta = sa.score - old.score
            tier_change = (
                f"{old.tier}→{sa.tier}" if old.tier != sa.tier else f"{sa.tier}  "
            )
            print(
                f"  {sa.name:<20s} {tier_change}  "
                f"{old.score:5.1f} → {sa.score:5.1f}  ({delta:+.1f})"
            )

    print()
    print("Loop complete. Signal-driven accounts should score higher after tuning.")
    print("=" * 60)


if __name__ == "__main__":
    main()
