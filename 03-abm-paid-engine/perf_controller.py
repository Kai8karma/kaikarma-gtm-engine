"""Autonomous paid-marketing controller — the loop Ivan's repo lacks.

Per campaign: classify actual CPA against target → emit an action (scale / hold /
cut / kill) → enforce hard caps (max single-step move, account daily ceiling).
Deterministic and explainable: every action carries its reason. The learning
phase is protected — campaigns without enough data are held, not optimized.

    python3 03-abm-paid-engine/perf_controller.py        # demo
    python3 03-abm-paid-engine/test_perf_controller.py   # tests

Stdlib only, no network. The next step (05-brain-integration) logs each action's
outcome so the policy thresholds tune to what actually worked.
"""

from __future__ import annotations


from perf_schema import (
    CUT,
    HOLD,
    KILL,
    LEARNING,
    SCALE,
    Action,
    Campaign,
    PerfPolicy,
)


def actual_cpa(c: Campaign) -> float:
    """Cost per conversion; infinite when nothing converted."""
    return c.spend / c.conversions if c.conversions > 0 else float("inf")


def _scaled(budget: float, pct: float, up: bool, floor: float) -> float:
    factor = (1 + pct) if up else (1 - pct)
    return round(max(floor, budget * factor), 2)


def decide(c: Campaign, p: PerfPolicy) -> Action:
    """Verdict for a single campaign (before account-cap pacing)."""
    cpa = actual_cpa(c)
    exited_learning = c.conversions >= p.min_conversions_to_exit_learning

    # Runaway non-performer: burning past the kill threshold with zero
    # conversions. Fires even during learning — you don't protect a money pit.
    if cpa == float("inf") and c.spend >= p.kill_when_ratio_above * p.target_cpa:
        return Action(c.name, KILL, c.daily_budget, 0.0, cpa,
                      f"non-performer: {c.spend:.0f} spent, 0 conversions")

    if not exited_learning:
        return Action(c.name, LEARNING, c.daily_budget, c.daily_budget, cpa,
                      f"in learning ({c.conversions}/{p.min_conversions_to_exit_learning} conv) — hold")

    ratio = cpa / p.target_cpa
    if ratio < p.scale_when_ratio_below:
        nb = _scaled(c.daily_budget, p.max_budget_change_pct, True, p.min_daily_budget)
        return Action(c.name, SCALE, c.daily_budget, nb, cpa,
                      f"CPA {cpa:.0f} = {ratio:.0%} of target — scale")
    if ratio >= p.kill_when_ratio_above:
        return Action(c.name, KILL, c.daily_budget, 0.0, cpa,
                      f"CPA {cpa:.0f} = {ratio:.0%} of target — kill")
    if ratio >= p.cut_when_ratio_above:
        nb = _scaled(c.daily_budget, p.max_budget_change_pct, False, p.min_daily_budget)
        return Action(c.name, CUT, c.daily_budget, nb, cpa,
                      f"CPA {cpa:.0f} = {ratio:.0%} of target — cut")
    return Action(c.name, HOLD, c.daily_budget, c.daily_budget, cpa,
                  f"CPA {cpa:.0f} = {ratio:.0%} of target — on target")


def run(campaigns: list[Campaign], p: PerfPolicy) -> list[Action]:
    """Decide every campaign, then enforce the account daily cap.

    Pacing protects baseline performers: speculative SCALE increases are clawed
    back first; only if that's not enough is everything trimmed proportionally.
    """
    actions = [decide(c, p) for c in campaigns]
    total = sum(a.new_budget for a in actions)
    overflow = total - p.account_daily_cap
    if overflow <= 0:
        return actions

    # Step 1 — claw back SCALE headroom (the optional growth) first.
    for a in actions:
        if overflow <= 0:
            break
        if a.verdict == SCALE:
            headroom = a.new_budget - a.old_budget
            take = min(headroom, overflow)
            a.new_budget = round(a.new_budget - take, 2)
            a.reason += "; paced to cap"
            overflow -= take

    # Step 2 — still over? trim all live budgets proportionally.
    if overflow > 1e-9:
        live_total = sum(a.new_budget for a in actions)
        factor = p.account_daily_cap / live_total if live_total else 0.0
        for a in actions:
            if a.new_budget > 0:
                a.new_budget = round(a.new_budget * factor, 2)
                a.reason += "; trimmed to cap"
    return actions


def blended(campaigns: list[Campaign]) -> dict[str, float]:
    """Portfolio summary — blended CPA and ROAS across the account."""
    spend = sum(c.spend for c in campaigns)
    conv = sum(c.conversions for c in campaigns)
    rev = sum(c.revenue for c in campaigns)
    return {
        "spend": round(spend, 2),
        "conversions": conv,
        "blended_cpa": round(spend / conv, 2) if conv else float("inf"),
        "roas": round(rev / spend, 2) if spend else 0.0,
    }


if __name__ == "__main__":
    policy = PerfPolicy(target_cpa=50.0, account_daily_cap=400.0)
    campaigns = [
        Campaign("LI-ABM-tier1", spend=1200, conversions=40, daily_budget=100),   # cpa 30 → scale
        Campaign("Google-brand", spend=2000, conversions=40, daily_budget=100),   # cpa 50 → hold
        Campaign("Meta-broad", spend=3200, conversions=40, daily_budget=100),     # cpa 80 → cut
        Campaign("Meta-retarget", spend=120, conversions=0, daily_budget=40),     # runaway → kill
        Campaign("LI-newtest", spend=200, conversions=8, daily_budget=30),        # learning → hold
    ]
    print(f"target CPA ${policy.target_cpa:.0f} · account cap ${policy.account_daily_cap:.0f}/day\n")
    for a in run(campaigns, policy):
        cpa = "∞" if a.actual_cpa == float("inf") else f"${a.actual_cpa:.0f}"
        print(f"  {a.verdict:8s} {a.campaign:16s} ${a.old_budget:6.0f} → ${a.new_budget:6.0f}  ({cpa})  {a.reason}")
    s = blended(campaigns)
    print(f"\n  blended: ${s['spend']:.0f} spend · {s['conversions']} conv · ${s['blended_cpa']:.0f} CPA")
