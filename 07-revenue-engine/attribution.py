"""Multi-touch revenue attribution — the Dreamdata-shaped decision layer.

Five standard models over a Deal's touchpoint history, each a pure function
returning per-channel dollar credit that sums to the deal amount:

  first_touch — 100% to the first touch (channel that created awareness)
  last_touch  — 100% to the last touch before close (channel that converted)
  linear      — equal credit across every touchpoint
  u_shaped    — 40% first / 40% last / 20% split across the middle
                (falls back to 50/50 for exactly 2 touches, 100% for 1)
  time_decay  — exponential recency weighting (half-life in days, default 7)

A deal with zero touchpoints (direct/referral, no tracked marketing touch)
attributes its full amount to the 'unattributed' channel rather than raising
— that is a real, common case, not an error.

Pure — no network.
"""

from __future__ import annotations

from datetime import datetime

from revenue_schema import AttributionResult, Deal, Touchpoint, VALID_ATTRIBUTION_MODELS

UNATTRIBUTED = "unattributed"
DEFAULT_TIME_DECAY_HALF_LIFE_DAYS = 7.0


def _credit_by_channel(weighted: list[tuple[Touchpoint, float]], amount: float) -> dict[str, float]:
    """Aggregate (touchpoint, weight) pairs into per-channel dollar credit."""
    credit: dict[str, float] = {}
    for tp, weight in weighted:
        credit[tp.channel] = credit.get(tp.channel, 0.0) + weight * amount
    return credit


def first_touch(deal: Deal) -> dict[str, float]:
    if not deal.touchpoints:
        return {UNATTRIBUTED: deal.amount}
    return {deal.touchpoints[0].channel: deal.amount}


def last_touch(deal: Deal) -> dict[str, float]:
    if not deal.touchpoints:
        return {UNATTRIBUTED: deal.amount}
    return {deal.touchpoints[-1].channel: deal.amount}


def linear(deal: Deal) -> dict[str, float]:
    if not deal.touchpoints:
        return {UNATTRIBUTED: deal.amount}
    weight = 1.0 / len(deal.touchpoints)
    return _credit_by_channel([(tp, weight) for tp in deal.touchpoints], deal.amount)


def u_shaped(deal: Deal) -> dict[str, float]:
    n = len(deal.touchpoints)
    if n == 0:
        return {UNATTRIBUTED: deal.amount}
    if n == 1:
        return {deal.touchpoints[0].channel: deal.amount}
    if n == 2:
        return _credit_by_channel([(tp, 0.5) for tp in deal.touchpoints], deal.amount)

    middle = deal.touchpoints[1:-1]
    middle_weight = 0.2 / len(middle)
    weighted = (
        [(deal.touchpoints[0], 0.4)]
        + [(tp, middle_weight) for tp in middle]
        + [(deal.touchpoints[-1], 0.4)]
    )
    return _credit_by_channel(weighted, deal.amount)


def time_decay(deal: Deal, half_life_days: float = DEFAULT_TIME_DECAY_HALF_LIFE_DAYS) -> dict[str, float]:
    if not deal.touchpoints:
        return {UNATTRIBUTED: deal.amount}
    if half_life_days <= 0:
        raise ValueError(f"half_life_days must be positive, got {half_life_days}")

    close = datetime.fromisoformat(deal.close_date_iso)
    raw_weights = []
    for tp in deal.touchpoints:
        touch = datetime.fromisoformat(tp.timestamp_iso)
        days_before_close = max((close - touch).total_seconds() / 86400, 0.0)
        raw_weights.append(2.0 ** (-days_before_close / half_life_days))

    total = sum(raw_weights)
    normalized = [w / total for w in raw_weights]
    return _credit_by_channel(list(zip(deal.touchpoints, normalized)), deal.amount)


_MODEL_FUNCS = {
    "first_touch": first_touch,
    "last_touch": last_touch,
    "linear": linear,
    "u_shaped": u_shaped,
}


def attribute(deal: Deal, model: str = "linear") -> AttributionResult:
    """Run one attribution model over a deal's touchpoints.

    Raises:
        ValueError: if `model` isn't one of the five supported models.
    """
    if model not in VALID_ATTRIBUTION_MODELS:
        raise ValueError(
            f"model must be one of {sorted(VALID_ATTRIBUTION_MODELS)}, got {model!r}"
        )
    if model == "time_decay":
        credit = time_decay(deal)
    else:
        credit = _MODEL_FUNCS[model](deal)
    return AttributionResult(deal_id=deal.deal_id, model=model, channel_credit=credit)


if __name__ == "__main__":
    deal = Deal(
        deal_id="deal-1001",
        amount=48000.0,
        closed_won=True,
        close_date_iso="2026-07-01T00:00:00+00:00",
        touchpoints=(
            Touchpoint("linkedin_ads", "abm-tier1", "2026-06-01T00:00:00+00:00"),
            Touchpoint("webinar", "q2-procurement-series", "2026-06-15T00:00:00+00:00"),
            Touchpoint("outbound_email", "sdr-sequence-3", "2026-06-25T00:00:00+00:00"),
            Touchpoint("demo_call", "aerchain-precall", "2026-06-30T00:00:00+00:00"),
        ),
    )

    print("attribution demo — $48,000 deal, 4 touchpoints\n")
    for model in ("first_touch", "last_touch", "linear", "u_shaped", "time_decay"):
        result = attribute(deal, model)
        print(f"  {model:12s}: {result.channel_credit}")

    print("\nNo network I/O occurred.")
