"""pitch.py — the single-command live demo. One run tells the whole story.

    python3 examples/pitch.py        (or:  make pitch)

Air-gapped, deterministic, zero setup, zero network. Safe to run on anyone's
laptop mid-call — it can't break on their wifi and nothing leaves the machine.
Runs the engine end to end: score accounts → control paid spend under caps →
learn from outcomes → re-score, showing the pipeline re-rank itself.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("01-list-engine", "03-abm-paid-engine", "05-brain-integration"):
    sys.path.insert(0, os.path.join(BASE, _d))

from brain_schema import Outcome           # noqa: E402
from icp_schema import Account, ICPProfile  # noqa: E402
from icp_scorer import rank                 # noqa: E402
from perf_controller import run as control  # noqa: E402
from perf_schema import Campaign, PerfPolicy  # noqa: E402
from policy_tuner import tune               # noqa: E402


def rule(title: str) -> None:
    print("\n" + "─" * 66)
    print(f"  {title}")
    print("─" * 66)


PROFILE = ICPProfile(
    name="B2B SaaS · RevOps buyer",
    target_industries=frozenset({"software", "saas", "fintech"}),
    employee_min=50, employee_max=1000,
    target_tech=frozenset({"hubspot", "salesforce", "clay"}),
)

ACCOUNTS = [
    Account("SignalFirst Corp", "software", 320, frozenset({"hubspot", "clay"}),
            frozenset({"job_change", "hiring"}), fit=0.9),
    Account("FirmMatch Ltd", "fintech", 140, frozenset({"salesforce"}), frozenset(), fit=0.5),
    Account("TechBlind Inc", "saas", 600, frozenset(), frozenset({"funding"}), fit=0.4),
    Account("OutOfBand LLC", "retail", 12, frozenset(), frozenset(), fit=0.1),
]

CAMPAIGNS = [
    Campaign("LI-ABM-tier1", spend=1200, conversions=40, daily_budget=100),
    Campaign("Google-brand", spend=2000, conversions=40, daily_budget=100),
    Campaign("Meta-broad", spend=3200, conversions=40, daily_budget=100),
    Campaign("Meta-retarget", spend=120, conversions=0, daily_budget=40),
]


def main() -> None:
    print("\n  kaikarma-gtm-engine — live, offline, tested. One command.")

    rule("1 · SCORE — who to chase, as a tested function (not a 100-point table)")
    ranked = rank(ACCOUNTS, PROFILE)
    for s in ranked:
        sig = f" [{s.top_signal}]" if s.top_signal else ""
        print(f"   {s.tier}  {s.score:5.1f}  {s.name}{sig}")

    rule("2 · CONTROL — paid spend, classified against target CPA, under hard caps")
    policy = PerfPolicy(target_cpa=50.0, account_daily_cap=400.0)
    for a in control(CAMPAIGNS, policy):
        cpa = "∞" if a.actual_cpa == float("inf") else f"${a.actual_cpa:.0f}"
        print(f"   {a.verdict:8s} {a.campaign:14s} ${a.old_budget:5.0f} → ${a.new_budget:5.0f}  ({cpa})")

    rule("3 · LEARN — closed-won/lost outcomes tune the weights")
    outcomes = [
        Outcome("icp_dimension", "signal", "win", confidence=0.9),
        Outcome("icp_dimension", "fit", "win"),
        Outcome("icp_dimension", "firmographic", "loss"),
    ]
    tuned = tune(PROFILE.weights, outcomes)
    print(f"   before: {PROFILE.weights}")
    print(f"   after : { {k: round(v) for k, v in tuned.items()} }")

    rule("4 · RE-SCORE — the pipeline re-ranks itself")
    new_profile = replace(PROFILE, weights={k: round(v) for k, v in tuned.items()})
    before = {s.name: (s.tier, s.score) for s in ranked}
    for s in rank(ACCOUNTS, new_profile):
        bt, bs = before[s.name]
        move = "" if bt == s.tier else f"   {bt}→{s.tier}"
        delta = s.score - bs
        print(f"   {s.tier}  {s.score:5.1f}  {s.name:18s} ({delta:+.1f}){move}")

    print("\n  Signal-driven accounts rose; pure-firmographic fell. The engine learned.")
    print("  All offline. All tested. The whole motion, one command.\n")


if __name__ == "__main__":
    main()
