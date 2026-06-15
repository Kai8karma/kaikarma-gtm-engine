"""Policy tuner — nudge ICP / perf weights from observed Outcomes.

    python3 05-brain-integration/policy_tuner.py         # demo

A 'win' on a dimension nudges that dimension's weight up; a 'loss' nudges it
down.  After every nudge the weights are RENORMALIZED so they sum to the same
total they started with (mirroring the ICP 4-dimension sum-to-100 rule).

Bounds are enforced per dimension BEFORE renormalization so no single dimension
can ever monopolise or disappear:
    MIN_WEIGHT / MAX_WEIGHT = 5 / 80  (as a fraction of the original sum)

'neutral' outcomes are recorded but skipped by the tuner.
Confidence gates the step size: a low-confidence outcome moves the needle less.

Stdlib only, no network, no external DB.  Deterministic given the same inputs.

Can later sync to an external brain DB (e.g. kai-brain.db) but does not
require one — the pillar runs fully air-gapped.
"""

from __future__ import annotations

from brain_schema import Outcome

# Nudge magnitude per win/loss signal at confidence=1.0 (fraction of the
# original sum).  At confidence=0.7 the step is 0.7× smaller.
_BASE_STEP_PCT = 0.05   # 5 % of the total weight pool per signal

# Hard bounds as a fraction of the original total.  These prevent any single
# dimension from vanishing or taking over regardless of accumulated wins.
_MIN_FRAC = 0.05   # 5 % of total — a dimension can never fall below this
_MAX_FRAC = 0.80   # 80 % of total — a dimension can never exceed this


def tune(base_weights: dict[str, float | int], outcomes: list[Outcome]) -> dict[str, float]:
    """Return a new weight dict tuned by the outcomes.

    Rules:
    1.  Only outcomes whose key exists in base_weights are applied.
    2.  Each win/loss nudges by BASE_STEP_PCT × confidence × total.
    3.  After all nudges, bounds are clamped, then weights are renormalized
        so the sum equals the original total.
    4.  'neutral' outcomes are skipped entirely.
    5.  Deterministic: outcomes applied in list order.

    Args:
        base_weights:  dict of dimension → numeric weight.  Must not be empty.
                       Typically sums to 100 (ICP convention) but any positive
                       total is accepted.
        outcomes:      list of Outcome records to replay.  May be empty — in
                       that case base_weights are returned unchanged (as floats).

    Returns:
        New dict with the same keys, adjusted and renormalized, values rounded
        to 2 decimal places.
    """
    if not base_weights:
        raise ValueError("base_weights must not be empty")

    total = sum(float(v) for v in base_weights.values())
    if total <= 0:
        raise ValueError(f"base_weights must sum to a positive value, got {total}")

    # Work in floats throughout.
    weights: dict[str, float] = {k: float(v) for k, v in base_weights.items()}

    step_pool = _BASE_STEP_PCT * total  # absolute units per signal at conf=1

    for o in outcomes:
        if o.verdict == "neutral":
            continue
        if o.key not in weights:
            continue  # unknown key — skip silently (future dimension, schema mismatch)

        delta = step_pool * o.confidence
        if o.verdict == "win":
            weights[o.key] += delta
        else:  # 'loss'
            weights[o.key] -= delta

    # Clamp each dimension to [min_frac×total, max_frac×total].
    lo = _MIN_FRAC * total
    hi = _MAX_FRAC * total
    for k in weights:
        weights[k] = max(lo, min(hi, weights[k]))

    # Renormalize so the sum is preserved exactly.
    current_sum = sum(weights.values())
    if current_sum > 0:
        factor = total / current_sum
        weights = {k: v * factor for k, v in weights.items()}

    return {k: round(v, 2) for k, v in weights.items()}


# ── demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Mirror the ICP 4-dimension default — defined inline so the demo runs
    # standalone without needing 01-list-engine on sys.path.
    base: dict[str, float] = {
        "firmographic": 40.0,
        "technographic": 20.0,
        "signal": 30.0,
        "fit": 10.0,
    }
    print("Base weights (must sum to 100):")
    print(f"  {base}  →  sum={sum(base.values())}\n")

    outcomes = [
        Outcome("icp_dimension", "firmographic", "win",
                note="industry match closed 4/5 deals"),
        Outcome("icp_dimension", "signal", "win", confidence=0.9,
                note="job_change signal strongly correlated"),
        Outcome("icp_dimension", "technographic", "loss", confidence=0.6,
                note="tech stack overlap didn't predict close"),
    ]

    tuned = tune(base, outcomes)
    print("Tuned weights after 3 outcomes:")
    print(f"  {tuned}  →  sum={sum(tuned.values()):.2f}")
    for k in base:
        delta = tuned[k] - base[k]
        print(f"    {k:15s}  {base[k]:5.1f} → {tuned[k]:5.2f}  ({delta:+.2f})")
