"""Bridge: scored accounts → rendered outbound copy.

Ties 01-list-engine (ICP scoring) to 02-send-engine (copy frameworks).

Public API
----------
build_sequences(scored_accounts, account_context) -> list[RenderedMessage]

    scored_accounts  : list[ScoredAccount] — output of icp_scorer.rank()
    account_context  : dict[account_name, dict[slot, value]] — per-account
                       slot values used to fill the chosen framework's template.

Tier → framework assignment
---------------------------
    A-tier → 'problem-first'  (signal detected) or 'do-the-math' (no signal)
    B-tier → 'upfront-value'
    C/D    → skipped

Missing-slot handling: if any required slot is absent the account is reported
(not raised) and excluded from the output so the rest of the batch still lands.

    python3 examples/list_to_sequences.py   # demo

Stdlib only, no network. Safe to run air-gapped.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass

# ── pillar path injection ────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
[sys.path.insert(0, os.path.join(BASE, d))
 for d in ("01-list-engine", "02-send-engine")]

from icp_schema import Account, ICPProfile, ScoredAccount  # noqa: E402
from icp_scorer import rank                                 # noqa: E402
from framework_registry import get_framework                # noqa: E402


# ── types ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RenderedMessage:
    """One rendered outbound message for a single account."""

    account_name: str
    tier: str
    framework_name: str
    body: str


@dataclass(frozen=True)
class SkippedAccount:
    """An account that was excluded from the batch, with a reason."""

    account_name: str
    tier: str
    reason: str


# ── tier → framework assignment ──────────────────────────────────────────────

def _pick_framework(sa: ScoredAccount) -> str | None:
    """Return the framework name for this tier, or None to skip."""
    if sa.tier == "A":
        # If a buying signal exists use 'problem-first'; otherwise fall back to
        # 'do-the-math' (attach a number to justify the reach-out).
        return "problem-first" if sa.top_signal else "do-the-math"
    if sa.tier == "B":
        return "upfront-value"
    return None  # C or D — skip


# ── public API ───────────────────────────────────────────────────────────────

def build_sequences(
    scored_accounts: list[ScoredAccount],
    account_context: dict[str, dict[str, str]],
) -> tuple[list[RenderedMessage], list[SkippedAccount]]:
    """Render outbound copy for every eligible scored account.

    Args:
        scored_accounts: ranked list from icp_scorer.rank().
        account_context: mapping of account name → slot dict.  Missing keys in
                         the outer dict mean no context at all for that account.

    Returns:
        (messages, skipped) — messages are the rendered copy; skipped records
        every account that was omitted and why.  Together they cover every
        input account so callers can audit the full batch.
    """
    messages: list[RenderedMessage] = []
    skipped: list[SkippedAccount] = []

    for sa in scored_accounts:
        fw_name = _pick_framework(sa)

        if fw_name is None:
            skipped.append(SkippedAccount(
                account_name=sa.name,
                tier=sa.tier,
                reason=f"tier {sa.tier} — below outbound threshold",
            ))
            continue

        slots = account_context.get(sa.name, {})
        fw = get_framework(fw_name)

        missing = [s for s in fw.required_slots if s not in slots]
        if missing:
            skipped.append(SkippedAccount(
                account_name=sa.name,
                tier=sa.tier,
                reason=f"missing slot(s) for '{fw_name}': {missing}",
            ))
            continue

        body = fw.render(slots)
        messages.append(RenderedMessage(
            account_name=sa.name,
            tier=sa.tier,
            framework_name=fw_name,
            body=body,
        ))

    return messages, skipped


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
        "Acme Cloud",
        "software",
        320,
        frozenset({"hubspot", "clay"}),
        frozenset({"job_change", "hiring"}),
        fit=0.9,
    ),
    Account(
        "MidFin Co",
        "fintech",
        140,
        frozenset({"salesforce"}),
        frozenset({"funding"}),
        fit=0.5,
    ),
    Account(
        "SteadySaaS Ltd",
        "saas",
        200,
        frozenset({"hubspot"}),
        frozenset(),
        fit=0.7,
    ),
    Account(
        "LocalBakery LLC",
        "food",
        8,
        frozenset(),
        frozenset(),
        fit=0.1,
    ),
    # B-tier but missing slots — tests graceful skip
    Account(
        "NoContextCo",
        "saas",
        300,
        frozenset({"hubspot"}),
        frozenset(),
        fit=0.6,
    ),
]

# Per-account context dicts — supply slot values for framework rendering.
# Acme Cloud → A-tier with signal → 'problem-first'
# MidFin Co  → B-tier            → 'upfront-value'
# SteadySaaS Ltd / NoContextCo → C-tier → skipped (tier gate)
# LocalBakery LLC → D-tier → skipped
# NoContextCo intentionally omitted → would be C-tier skip anyway, but
# demonstrates that the missing-slot path is also covered if tier were higher.
_DEMO_CONTEXT: dict[str, dict[str, str]] = {
    "Acme Cloud": {
        "first_name": "Sarah",
        "observed_signal": "saw you just posted 4 SDR roles on LinkedIn",
        "quantified_pain": "scaling teams lose ~8 h/rep/week to manual CRM entry",
        "one_liner_solution": "we auto-sync every call note to HubSpot in real-time",
        "soft_cta": "Worth 15 min this week to see if it fits?",
    },
    "MidFin Co": {
        # B-tier → 'upfront-value' framework
        "first_name": "Marcus",
        "value_artifact": "a 5-min teardown of your current RevOps stack",
        "key_finding": "found two manual handoff points that add ~6 h/rep/week",
        "why_it_matters": "plugging them typically saves $4-5 k/mo at your headcount",
        "soft_cta": "Want me to send it over — no strings?",
    },
    "LocalBakery LLC": {
        # context present but account will be skipped (D-tier)
        "first_name": "Bob",
    },
    # SteadySaaS Ltd / NoContextCo → C-tier skip; no context needed
}


def main() -> None:
    scored = rank(_DEMO_ACCOUNTS, _DEMO_PROFILE)

    print("=" * 60)
    print("STEP 1 — Scored accounts (best first)")
    print("=" * 60)
    for sa in scored:
        sig = f" [{sa.top_signal}]" if sa.top_signal else ""
        print(f"  {sa.tier}  {sa.score:5.1f}  {sa.name}{sig}")
    print()

    messages, skipped = build_sequences(scored, _DEMO_CONTEXT)

    print("=" * 60)
    print(f"STEP 2 — Rendered sequences ({len(messages)} messages, "
          f"{len(skipped)} skipped)")
    print("=" * 60)
    for msg in messages:
        print(f"\n[{msg.tier}] {msg.account_name}  —  framework: {msg.framework_name}")
        print("-" * 50)
        print(msg.body)

    if skipped:
        print("\n--- Skipped ---")
        for s in skipped:
            print(f"  [{s.tier}] {s.account_name}: {s.reason}")


if __name__ == "__main__":
    main()
