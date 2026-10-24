"""Cross-channel budget allocation — the same engine, one level up.

perf_controller.decide()/run() already generalize to any named row with
spend/conversions/budget — a channel (google/meta/linkedin) is just a
different granularity of row than a campaign. So cross-channel allocation
isn't new decision logic: it's rolling per-campaign metrics up into one row
per channel, letting perf_controller.run() decide the channel-level budget
shift under the total ad-spend cap (reusing the exact same hard-cap pacing),
then cascading that verdict back down to child campaigns.

    python3 03-abm-paid-engine/channel_allocator.py        # demo
    python3 03-abm-paid-engine/test_channel_allocator.py   # tests

Stdlib only, no network.
"""

from __future__ import annotations

from perf_controller import run
from perf_schema import Action, Campaign, PerfPolicy


def rollup_by_channel(
    campaigns: list[Campaign],
    channel_of: dict[str, str],
) -> list[Campaign]:
    """Aggregate per-campaign metrics into one Campaign row per channel.

    `channel_of` maps each campaign's name to its channel, e.g.
    {"LI-ABM-tier1": "linkedin", "Google-brand": "google"}.

    Raises:
        KeyError: if a campaign's name isn't in `channel_of` — an unmapped
            campaign silently dropped from the rollup would understate that
            channel's real spend, corrupting every downstream allocation.
    """
    totals: dict[str, dict[str, float]] = {}
    for c in campaigns:
        channel = channel_of[c.name]
        bucket = totals.setdefault(
            channel, {"spend": 0.0, "conversions": 0.0, "daily_budget": 0.0, "revenue": 0.0}
        )
        bucket["spend"] += c.spend
        bucket["conversions"] += c.conversions
        bucket["daily_budget"] += c.daily_budget
        bucket["revenue"] += c.revenue

    return [
        Campaign(
            name=channel,
            spend=b["spend"],
            conversions=int(b["conversions"]),
            daily_budget=b["daily_budget"],
            revenue=b["revenue"],
        )
        for channel, b in totals.items()
    ]


def allocate_channel_budgets(
    campaigns: list[Campaign],
    channel_of: dict[str, str],
    policy: PerfPolicy,
) -> list[Action]:
    """Decide each channel's new daily budget under the total ad-spend cap.

    `policy.account_daily_cap` is the TOTAL budget across every channel —
    reuses perf_controller.run()'s pacing (SCALE headroom clawed back first,
    then proportional trim) so the total never breaches the cap, exactly as
    it already guarantees at the single-platform campaign level.
    """
    return run(rollup_by_channel(campaigns, channel_of), policy)


def cascade_to_campaigns(
    campaigns: list[Campaign],
    channel_of: dict[str, str],
    channel_actions: list[Action],
) -> list[Campaign]:
    """Push each channel's new budget back down to its child campaigns.

    Split proportionally to each campaign's current share of that channel's
    spend — a campaign that proved it can spend efficiently earns a bigger
    share of the channel's increase, same reasoning perf_controller already
    applies per-campaign. A channel whose campaigns have zero total spend
    (e.g. everything still in learning) splits the budget evenly instead, so
    a brand-new campaign isn't starved by a divide-by-zero.

    Raises:
        KeyError: if a channel produced by rollup_by_channel has no matching
            Action — callers must pass the exact `channel_actions` returned
            by allocate_channel_budgets for the same campaign set.
    """
    action_by_channel = {a.campaign: a for a in channel_actions}
    by_channel: dict[str, list[Campaign]] = {}
    for c in campaigns:
        by_channel.setdefault(channel_of[c.name], []).append(c)

    updated: list[Campaign] = []
    for channel, members in by_channel.items():
        action = action_by_channel[channel]
        total_spend = sum(m.spend for m in members)
        for m in members:
            share = (m.spend / total_spend) if total_spend > 0 else (1.0 / len(members))
            updated.append(
                Campaign(
                    name=m.name,
                    spend=m.spend,
                    conversions=m.conversions,
                    daily_budget=round(action.new_budget * share, 2),
                    revenue=m.revenue,
                )
            )
    return updated


if __name__ == "__main__":
    policy = PerfPolicy(target_cpa=50.0, account_daily_cap=600.0)

    campaigns = [
        Campaign("LI-ABM-tier1", spend=1200, conversions=40, daily_budget=150),   # linkedin, cpa 30
        Campaign("LI-newtest", spend=200, conversions=8, daily_budget=30),        # linkedin, learning
        Campaign("Google-brand", spend=2000, conversions=40, daily_budget=200),   # google, cpa 50
        Campaign("Meta-broad", spend=3200, conversions=40, daily_budget=200),     # meta, cpa 80
        Campaign("Meta-retarget", spend=120, conversions=0, daily_budget=20),     # meta, runaway
    ]
    channel_of = {
        "LI-ABM-tier1": "linkedin", "LI-newtest": "linkedin",
        "Google-brand": "google",
        "Meta-broad": "meta", "Meta-retarget": "meta",
    }

    print(f"total ad-spend cap: ${policy.account_daily_cap:.0f}/day across 3 channels\n")

    channel_actions = allocate_channel_budgets(campaigns, channel_of, policy)
    print("--- channel-level allocation ---")
    for a in channel_actions:
        cpa = "∞" if a.actual_cpa == float("inf") else f"${a.actual_cpa:.0f}"
        print(f"  {a.verdict:8s} {a.campaign:10s} ${a.old_budget:6.0f} → ${a.new_budget:6.0f}  ({cpa})  {a.reason}")

    cascaded = cascade_to_campaigns(campaigns, channel_of, channel_actions)
    print("\n--- cascaded back to individual campaigns ---")
    for c in cascaded:
        print(f"  {channel_of[c.name]:10s} {c.name:16s} ${c.daily_budget:.2f}/day")

    print(f"\n  total after cascade: ${sum(c.daily_budget for c in cascaded):.2f} (cap: ${policy.account_daily_cap:.0f})")
