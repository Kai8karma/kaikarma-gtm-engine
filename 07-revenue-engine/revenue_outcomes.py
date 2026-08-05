"""Brain-integration bridge: log attributed revenue as brain Outcomes.

Given an AttributionResult + whether the deal closed won, log one Outcome per
credited channel so the brain can eventually learn which channels' credit
actually predicts revenue — not just lead-stage conversion (04-revops-engine's
routing_outcomes.py) or CPA (03-abm-paid-engine's perf_outcomes.py).

entity_type = 'revenue_channel'
key         = the channel name credited (e.g. 'linkedin_ads', 'webinar')
verdict     = 'win' if the deal closed won, 'loss' otherwise
confidence  = the channel's share of the deal's total credit (0.0-1.0) —
              a channel credited for 10% of a deal is a weaker signal than
              one credited for 90% of it.

    python3 07-revenue-engine/revenue_outcomes.py        # demo (TEMPFILE store)
    python3 07-revenue-engine/test_revenue_outcomes.py   # tests

Stdlib only, no network. Feeds the brain air-gapped.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Cross-pillar sys.path bridge — pillar dirs are not packages.
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("07-revenue-engine", "05-brain-integration"):
    _p = os.path.join(_BASE, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from brain_schema import Outcome  # noqa: E402
from outcome_store import log_outcome  # noqa: E402
from revenue_schema import AttributionResult  # noqa: E402


def build_revenue_outcomes(result: AttributionResult, closed_won: bool) -> list[Outcome]:
    """Build one Outcome per channel credited in an AttributionResult.

    Confidence is the channel's share of the deal's total credited amount —
    a channel that captured most of the credit is a stronger signal than one
    that captured a sliver, regardless of win/loss.
    """
    total = sum(result.channel_credit.values())
    verdict = "win" if closed_won else "loss"

    outcomes: list[Outcome] = []
    for channel, credit in result.channel_credit.items():
        confidence = (credit / total) if total > 0 else 0.0
        outcomes.append(
            Outcome(
                entity_type="revenue_channel",
                key=channel,
                verdict=verdict,  # type: ignore[arg-type]
                confidence=confidence,
                note=f"deal={result.deal_id!r} model={result.model} credit=${credit:,.2f}",
            )
        )
    return outcomes


def record_revenue_outcomes(
    result: AttributionResult,
    closed_won: bool,
    store_path: Path,
) -> list[Outcome]:
    """Build and log Outcomes for one deal's attribution result.

    Returns the logged Outcomes for inspection / testing.
    """
    outcomes = build_revenue_outcomes(result, closed_won)
    for outcome in outcomes:
        log_outcome(outcome, store_path)
    return outcomes


def record_revenue_outcomes_batch(
    pairs: list[tuple[AttributionResult, bool]],
    store_path: Path,
) -> list[Outcome]:
    """Log Outcomes for a batch of (AttributionResult, closed_won) pairs."""
    logged: list[Outcome] = []
    for result, closed_won in pairs:
        logged.extend(record_revenue_outcomes(result, closed_won, store_path))
    return logged


# ── demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    from attribution import attribute
    from outcome_store import load_outcomes
    from revenue_schema import Deal, Touchpoint

    won_deal = Deal(
        deal_id="deal-1001",
        amount=48000.0,
        closed_won=True,
        close_date_iso="2026-07-01T00:00:00+00:00",
        touchpoints=(
            Touchpoint("linkedin_ads", "abm-tier1", "2026-06-01T00:00:00+00:00"),
            Touchpoint("webinar", "q2-procurement-series", "2026-06-15T00:00:00+00:00"),
        ),
    )
    lost_deal = Deal(
        deal_id="deal-1002",
        amount=20000.0,
        closed_won=False,
        close_date_iso="2026-06-20T00:00:00+00:00",
        touchpoints=(Touchpoint("outbound_email", "sdr-sequence-3", "2026-06-01T00:00:00+00:00"),),
    )

    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "outcomes.json"
        batch = [
            (attribute(won_deal, "u_shaped"), True),
            (attribute(lost_deal, "linear"), False),
        ]
        outcomes = record_revenue_outcomes_batch(batch, store)

        print(f"Logged {len(outcomes)} revenue Outcomes:\n")
        for o in load_outcomes(store):
            print(
                f"  [{o.verdict:4s}] revenue_channel.{o.key}"
                f"  conf={o.confidence:.2f}  note={o.note!r}"
            )
