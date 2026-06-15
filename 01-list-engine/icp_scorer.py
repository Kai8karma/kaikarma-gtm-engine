"""ICP scorer — the reference "framework as code" module.

Run it:
    python 01-list-engine/icp_scorer.py        # demo
    python -m pytest 01-list-engine            # tests

Pure stdlib, no network, no state — safe to run air-gapped. Outcomes from real
campaigns should feed back into the weights via 05-brain-integration/ so the
profile sharpens over time instead of staying a static guess.
"""

from __future__ import annotations

from icp_schema import SIGNAL_VALUE, Account, ICPProfile, ScoredAccount

TIERS = (("A", 75.0), ("B", 55.0), ("C", 35.0))  # else "D"


def _firmographic(account: Account, profile: ICPProfile) -> float:
    """0..1 — industry match (60%) + employee-band fit (40%)."""
    industry = 1.0 if account.industry.lower() in {
        i.lower() for i in profile.target_industries
    } else 0.0

    lo, hi = profile.employee_min, profile.employee_max
    if lo <= account.employees <= hi:
        band = 1.0
    elif lo / 2 <= account.employees <= hi * 2:
        band = 0.5  # adjacent band — close enough to keep, not ideal
    else:
        band = 0.0
    return 0.6 * industry + 0.4 * band


def _technographic(account: Account, profile: ICPProfile) -> float:
    """0..1 — share of the target tech stack the account already runs."""
    if not profile.target_tech:
        return 0.5  # no signal either way → neutral
    have = {t.lower() for t in account.tech_stack}
    want = {t.lower() for t in profile.target_tech}
    return min(1.0, len(have & want) / len(want))


def _signal(account: Account) -> tuple[float, str | None]:
    """0..1 — stacked buying signals, capped. Returns (score, strongest signal)."""
    present = [(s, SIGNAL_VALUE[s]) for s in account.signals if s in SIGNAL_VALUE]
    if not present:
        return 0.0, None
    top = max(present, key=lambda kv: kv[1])[0]
    return min(1.0, sum(v for _, v in present)), top


def score_account(account: Account, profile: ICPProfile) -> ScoredAccount:
    """Score one account against an ICP. Deterministic and explainable."""
    w = profile.weights
    sig_score, top_signal = _signal(account)

    dims = {
        "firmographic": _firmographic(account, profile) * w["firmographic"],
        "technographic": _technographic(account, profile) * w["technographic"],
        "signal": sig_score * w["signal"],
        "fit": max(0.0, min(1.0, account.fit)) * w["fit"],
    }
    total = round(sum(dims.values()), 1)

    tier = "D"
    for label, cutoff in TIERS:
        if total >= cutoff:
            tier = label
            break

    return ScoredAccount(
        name=account.name,
        score=total,
        tier=tier,
        breakdown={k: round(v, 1) for k, v in dims.items()},
        top_signal=top_signal,
    )


def rank(accounts: list[Account], profile: ICPProfile) -> list[ScoredAccount]:
    """Score and sort a list, best first — the actual list-building output."""
    return sorted(
        (score_account(a, profile) for a in accounts),
        key=lambda s: s.score,
        reverse=True,
    )


if __name__ == "__main__":
    demo_profile = ICPProfile(
        name="B2B SaaS, mid-market, RevOps buyer",
        target_industries=frozenset({"software", "saas", "fintech"}),
        employee_min=50,
        employee_max=1000,
        target_tech=frozenset({"hubspot", "salesforce", "clay"}),
    )
    demo_accounts = [
        Account("Acme Cloud", "software", 320,
                frozenset({"hubspot", "clay"}),
                frozenset({"job_change", "hiring"}), fit=0.9),
        Account("LocalBakery LLC", "food", 8,
                frozenset(), frozenset(), fit=0.1),
        Account("MidFin Co", "fintech", 140,
                frozenset({"salesforce"}), frozenset({"funding"}), fit=0.5),
    ]
    print(f"ICP: {demo_profile.name}\n")
    for s in rank(demo_accounts, demo_profile):
        sig = f" [{s.top_signal}]" if s.top_signal else ""
        print(f"  {s.tier}  {s.score:5.1f}  {s.name}{sig}")
        print(f"        {s.breakdown}")
