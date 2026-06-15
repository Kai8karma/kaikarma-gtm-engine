"""Persistent warm-start — load accumulated outcomes and tune an ICPProfile.

    python3 examples/persistent_loop.py    # demo (writes to TEMPFILE only)

The real cross-session store lives at:
    05-brain-integration/_state/outcomes.json

A fresh session calls load_and_tune(profile) and immediately gets an ICPProfile
already warmed by every outcome ever logged — no manual replay, no stale state.

Stdlib only, no network, no external DB.  Safe to run air-gapped.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from pathlib import Path

# ── pillar path injection ────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
[sys.path.insert(0, os.path.join(BASE, d))
 for d in ("01-list-engine", "05-brain-integration")]

# ── pillar imports (after path injection) ────────────────────────────────────
from brain_schema import Outcome          # noqa: E402
from icp_schema import ICPProfile         # noqa: E402
from outcome_store import load_outcomes   # noqa: E402
from policy_tuner import tune             # noqa: E402

# ── default persistent store (real cross-session state) ─────────────────────
DEFAULT_STATE: Path = (
    Path(__file__).parent.parent
    / "05-brain-integration"
    / "_state"
    / "outcomes.json"
)


# ── public API ───────────────────────────────────────────────────────────────

def load_and_tune(
    base_profile: ICPProfile,
    store_path: Path = DEFAULT_STATE,
) -> ICPProfile:
    """Return a new ICPProfile warmed by every icp_dimension outcome on disk.

    Reads the persistent outcomes JSON at *store_path*, filters to outcomes
    with entity_type == 'icp_dimension', replays them through policy_tuner.tune,
    and returns a new frozen ICPProfile via dataclasses.replace.

    If the file is missing or empty, returns *base_profile* unchanged.
    An ICPProfile requires integer weights summing to 100; this function
    handles the float→int conversion with greedy rounding so the invariant
    is always satisfied.

    Args:
        base_profile:  the starting ICPProfile to warm.
        store_path:    path to the outcomes JSON (default: real cross-session
                       store at 05-brain-integration/_state/outcomes.json).

    Returns:
        A new, frozen ICPProfile identical to *base_profile* except for its
        weights (which incorporate every logged icp_dimension outcome).
    """
    all_outcomes = load_outcomes(Path(store_path))
    icp_outcomes = [o for o in all_outcomes if o.entity_type == "icp_dimension"]

    if not icp_outcomes:
        return base_profile

    tuned_floats = tune(base_profile.weights, icp_outcomes)

    # Convert float weights → int while preserving sum == original total.
    total = sum(base_profile.weights.values())  # typically 100
    int_weights: dict[str, int] = {k: int(v) for k, v in tuned_floats.items()}
    remainder = total - sum(int_weights.values())

    if remainder != 0:
        fractional = {k: tuned_floats[k] - int_weights[k] for k in tuned_floats}
        for key in sorted(fractional, key=fractional.__getitem__, reverse=True):
            if remainder == 0:
                break
            step = 1 if remainder > 0 else -1
            int_weights[key] += step
            remainder -= step

    return dataclasses.replace(base_profile, weights=int_weights)


def warm_start_summary(
    base_profile: ICPProfile,
    store_path: Path = DEFAULT_STATE,
) -> str:
    """Return a human-readable summary of the warm-start replay.

    Reports how many outcomes were replayed and the net weight shift for each
    dimension.  If the store is missing or empty, reports that no outcomes
    were found and weights are unchanged.

    Args:
        base_profile:  the ICPProfile whose weights will be compared.
        store_path:    path to the outcomes JSON.

    Returns:
        A multi-line string ready to print.
    """
    all_outcomes = load_outcomes(Path(store_path))
    icp_outcomes = [o for o in all_outcomes if o.entity_type == "icp_dimension"]

    lines: list[str] = ["── warm-start summary ──────────────────────────────"]

    if not icp_outcomes:
        lines.append("  no icp_dimension outcomes found — weights unchanged")
        return "\n".join(lines)

    lines.append(f"  outcomes replayed : {len(icp_outcomes)}")
    lines.append(f"  total in store    : {len(all_outcomes)}")

    warmed = load_and_tune(base_profile, store_path)
    lines.append("  dimension weight shifts:")
    for dim in base_profile.weights:
        before = base_profile.weights[dim]
        after = warmed.weights[dim]
        delta = after - before
        lines.append(f"    {dim:<16s}  {before:3d} → {after:3d}  ({delta:+d})")

    lines.append(f"  sum check         : {sum(warmed.weights.values())} (must be 100)")
    return "\n".join(lines)


# ── demo ─────────────────────────────────────────────────────────────────────

_DEMO_PROFILE = ICPProfile(
    name="B2B SaaS, mid-market, RevOps buyer",
    target_industries=frozenset({"software", "saas", "fintech"}),
    employee_min=50,
    employee_max=1000,
    target_tech=frozenset({"hubspot", "salesforce", "clay"}),
)

_DEMO_OUTCOMES: list[Outcome] = [
    Outcome(
        "icp_dimension",
        "signal",
        "win",
        confidence=0.9,
        note="job_change + hiring signal closed 4/5 accounts",
    ),
    Outcome(
        "icp_dimension",
        "signal",
        "win",
        confidence=0.8,
        note="funding signal — second data point confirms",
    ),
    Outcome(
        "icp_dimension",
        "firmographic",
        "loss",
        confidence=0.7,
        note="industry/size match alone didn't predict close rate",
    ),
    Outcome(
        "icp_dimension",
        "technographic",
        "loss",
        confidence=0.6,
        note="tech-stack overlap insufficient predictor this cohort",
    ),
    Outcome(
        "perf_threshold",
        "scale_when_ratio_below",
        "win",
        note="perf outcome — filtered out by icp_dimension gate",
    ),
]

if __name__ == "__main__":
    from outcome_store import log_outcome  # noqa: E402

    print("=" * 60)
    print("persistent_loop.py — warm-start demo")
    print("(writes to TEMPFILE only — never touches the real _state)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "outcomes.json"

        # Seed the temp store with demo outcomes.
        for o in _DEMO_OUTCOMES:
            log_outcome(o, store)
        print(f"\nSeeded temp store with {len(_DEMO_OUTCOMES)} outcomes.")

        # Show before weights.
        print(f"\nBase weights:   {_DEMO_PROFILE.weights}")
        print(f"  sum = {sum(_DEMO_PROFILE.weights.values())}")

        # Warm start.
        warmed = load_and_tune(_DEMO_PROFILE, store)
        print(f"\nWarmed weights: {warmed.weights}")
        print(f"  sum = {sum(warmed.weights.values())} (must be 100)")

        # Summary.
        print()
        print(warm_start_summary(_DEMO_PROFILE, store))

    print("\nDemo complete — no real state was modified.")
    print("=" * 60)
