"""Tests for list_to_sequences.py — the list-engine → send-engine bridge.

Four falsifiable assertions:
    1. A-tier account with full context produces a rendered message.
    2. D-tier account is excluded from the output.
    3. An account missing required slots is reported in skipped, not raised.
    4. Output count (messages + skipped) == total input accounts.

    python3 examples/test_list_to_sequences.py
    python3 -m pytest examples/test_list_to_sequences.py -v
"""

from __future__ import annotations

import sys
import os
import unittest

# ── pillar path injection ────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
[sys.path.insert(0, os.path.join(BASE, d))
 for d in ("01-list-engine", "02-send-engine")]

from icp_schema import Account, ICPProfile, ScoredAccount  # noqa: E402  # noqa: F401
from icp_scorer import rank                                 # noqa: E402
from list_to_sequences import build_sequences               # noqa: E402


# ── shared fixtures ───────────────────────────────────────────────────────────

_PROFILE = ICPProfile(
    name="test ICP",
    target_industries=frozenset({"software", "saas"}),
    employee_min=50,
    employee_max=1000,
    target_tech=frozenset({"hubspot"}),
)

# A-tier: high score, has a signal
_A_ACCOUNT = Account(
    "AlphaAccount",
    "software",
    300,
    frozenset({"hubspot"}),
    frozenset({"job_change", "hiring"}),
    fit=0.9,
)

# B-tier: decent score, no signal (upfront-value framework)
_B_ACCOUNT = Account(
    "BetaAccount",
    "saas",
    200,
    frozenset({"hubspot"}),
    frozenset(),
    fit=0.7,
)

# D-tier: clearly out of ICP
_D_ACCOUNT = Account(
    "DeltaAccount",
    "food",
    5,
    frozenset(),
    frozenset(),
    fit=0.0,
)

# Missing required slots for its framework
_NO_SLOTS_ACCOUNT = Account(
    "EmptyContextAccount",
    "software",
    150,
    frozenset({"hubspot"}),
    frozenset({"funding"}),  # signal → would pick problem-first
    fit=0.8,
)

_ALL_ACCOUNTS: list[Account] = [
    _A_ACCOUNT,
    _B_ACCOUNT,
    _D_ACCOUNT,
    _NO_SLOTS_ACCOUNT,
]

# Full context for A-tier (problem-first slots)
_A_CONTEXT: dict[str, str] = {
    "first_name": "Sarah",
    "observed_signal": "saw you just posted 4 SDR roles on LinkedIn",
    "quantified_pain": "scaling teams lose ~8 h/rep/week to manual CRM entry",
    "one_liner_solution": "we auto-sync every call note to HubSpot in real-time",
    "soft_cta": "Worth 15 min this week?",
}

# Full context for B-tier (upfront-value slots)
_B_CONTEXT: dict[str, str] = {
    "first_name": "Marcus",
    "value_artifact": "a teardown of your onboarding flow",
    "key_finding": "found 3 drop-off points in the first 48h",
    "why_it_matters": "fixing the first one alone could lift activation 15%",
    "soft_cta": "Want me to send it over?",
}

_FULL_CONTEXT: dict[str, dict[str, str]] = {
    _A_ACCOUNT.name: _A_CONTEXT,
    _B_ACCOUNT.name: _B_CONTEXT,
    # D account present with content — still should be skipped (tier gate)
    _D_ACCOUNT.name: {"first_name": "Bob"},
    # No entry for EmptyContextAccount → triggers missing-slot path
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _rank(accounts: list[Account]) -> list[ScoredAccount]:
    return rank(accounts, _PROFILE)


# ── test cases ────────────────────────────────────────────────────────────────

class TestATierProducesMessage(unittest.TestCase):
    """Assertion 1: A-tier account with full context yields a rendered message."""

    def test_a_tier_produces_rendered_message(self) -> None:
        scored = _rank([_A_ACCOUNT])
        self.assertEqual(scored[0].tier, "A", "fixture must score A-tier")

        messages, skipped = build_sequences(scored, {_A_ACCOUNT.name: _A_CONTEXT})

        self.assertEqual(len(messages), 1)
        self.assertEqual(len(skipped), 0)
        msg = messages[0]
        self.assertEqual(msg.account_name, _A_ACCOUNT.name)
        self.assertEqual(msg.tier, "A")
        # problem-first chosen because there is a signal
        self.assertEqual(msg.framework_name, "problem-first")
        self.assertIn("Sarah", msg.body)

    def test_a_tier_no_signal_picks_do_the_math(self) -> None:
        """A-tier account without a buying signal should use 'do-the-math'.

        Uses a profile with a low signal weight (10 pts) so A-tier (≥75) is
        reachable from firmographic + technographic + fit alone.
        """
        low_signal_profile = ICPProfile(
            name="low-signal test ICP",
            target_industries=frozenset({"software"}),
            employee_min=50,
            employee_max=1000,
            target_tech=frozenset({"hubspot"}),
            weights={"firmographic": 50, "technographic": 30, "signal": 10, "fit": 10},
        )
        no_signal = Account(
            "NoSignalA",
            "software",
            300,
            frozenset({"hubspot"}),
            frozenset(),   # no signals
            fit=1.0,
        )
        scored = rank([no_signal], low_signal_profile)
        self.assertEqual(scored[0].tier, "A", "fixture must score A-tier")
        self.assertIsNone(scored[0].top_signal, "fixture must have no signal")

        slots = {
            "first_name": "Lena",
            "observed_signal": "noticed your team doubled headcount",
            "cost_of_problem": "$5k/mo in wasted time",
            "what_we_do": "we cut that by 70%",
            "proof_point": "similar result at Acme in 3 weeks",
            "soft_cta": "Open to a quick call?",
        }
        messages, skipped = build_sequences(scored, {no_signal.name: slots})

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].framework_name, "do-the-math")


class TestDTierIsSkipped(unittest.TestCase):
    """Assertion 2: D-tier account must not appear in messages."""

    def test_d_tier_excluded(self) -> None:
        scored = _rank([_D_ACCOUNT])
        self.assertEqual(scored[0].tier, "D", "fixture must score D-tier")

        messages, skipped = build_sequences(scored, {_D_ACCOUNT.name: {"first_name": "X"}})

        self.assertEqual(len(messages), 0)
        self.assertEqual(len(skipped), 1)
        self.assertIn("D", skipped[0].tier)
        self.assertIn(_D_ACCOUNT.name, skipped[0].account_name)

    def test_c_tier_also_excluded(self) -> None:
        # Wrong industry, tiny headcount, no tech match, no signal → D-tier
        # (C-tier: 35–54.9; D-tier: <35).  Either way the account must be skipped.
        low_account = Account(
            "LowScoreAccount",
            "food",    # not in ICP industries
            10,        # below employee_min / 2 → band = 0
            frozenset(),
            frozenset(),
            fit=0.0,
        )
        scored = _rank([low_account])
        # Score is 0 — solidly D-tier
        self.assertIn(scored[0].tier, {"C", "D"})

        messages, skipped = build_sequences(scored, {})

        self.assertEqual(len(messages), 0)
        self.assertEqual(len(skipped), 1)


class TestMissingSlotReportedNotCrashed(unittest.TestCase):
    """Assertion 3: missing required slots → SkippedAccount entry, no exception."""

    def test_missing_slots_skipped_gracefully(self) -> None:
        # EmptyContextAccount has a signal → would pick problem-first
        scored = _rank([_NO_SLOTS_ACCOUNT])
        self.assertEqual(scored[0].tier, "A", "fixture must score A-tier")

        # Pass an empty context (all slots missing)
        messages, skipped = build_sequences(scored, {})

        self.assertEqual(len(messages), 0)
        self.assertEqual(len(skipped), 1)
        self.assertIn("missing", skipped[0].reason.lower())

    def test_partial_slots_also_skipped(self) -> None:
        scored = _rank([_NO_SLOTS_ACCOUNT])
        # Provide only some of the required slots
        partial = {"first_name": "Ali"}  # problem-first needs 5 slots
        messages, skipped = build_sequences(scored, {_NO_SLOTS_ACCOUNT.name: partial})

        self.assertEqual(len(messages), 0)
        self.assertEqual(len(skipped), 1)
        self.assertIn("missing", skipped[0].reason.lower())


class TestOutputCountMatchesInput(unittest.TestCase):
    """Assertion 4: messages + skipped == total input accounts."""

    def test_full_batch_coverage(self) -> None:
        scored = _rank(_ALL_ACCOUNTS)
        messages, skipped = build_sequences(scored, _FULL_CONTEXT)

        total_in = len(scored)
        total_out = len(messages) + len(skipped)
        self.assertEqual(
            total_out,
            total_in,
            f"messages ({len(messages)}) + skipped ({len(skipped)}) "
            f"must equal input count ({total_in})",
        )

    def test_eligible_accounts_in_messages(self) -> None:
        """The two accounts with full context should both render successfully."""
        scored = _rank([_A_ACCOUNT, _B_ACCOUNT])
        messages, skipped = build_sequences(
            scored,
            {_A_ACCOUNT.name: _A_CONTEXT, _B_ACCOUNT.name: _B_CONTEXT},
        )

        rendered_names = {m.account_name for m in messages}
        self.assertIn(_A_ACCOUNT.name, rendered_names)
        self.assertIn(_B_ACCOUNT.name, rendered_names)
        self.assertEqual(len(skipped), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
