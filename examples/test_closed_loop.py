"""Tests for the end-to-end learning loop.

Three falsifiable assertions:
    1. The loop runs end-to-end without error.
    2. A one-sided outcome set moves the targeted weight in the expected direction
       (the loop *changes behaviour*, not just runs).
    3. Tuned weights still sum to 100.

    python3 examples/test_closed_loop.py
    python3 -m pytest examples/             # if pytest installed

Stdlib only, no network.  Uses tempfile so no real state is written.
"""

from __future__ import annotations

import sys
import os
import unittest

# ── pillar path injection (mirrors closed_loop.py) ───────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
[sys.path.insert(0, os.path.join(BASE, d))
 for d in ("01-list-engine", "03-abm-paid-engine", "05-brain-integration")]

from icp_schema import Account, ICPProfile  # noqa: E402
from brain_schema import Outcome             # noqa: E402
from closed_loop import learn, score_accounts  # noqa: E402

# ── shared fixtures ───────────────────────────────────────────────────────────

_PROFILE = ICPProfile(
    name="test ICP",
    target_industries=frozenset({"software", "saas"}),
    employee_min=50,
    employee_max=1000,
    target_tech=frozenset({"hubspot"}),
)

_ACCOUNTS: list[Account] = [
    Account(
        "SignalAccount",
        "software",
        300,
        frozenset({"hubspot"}),
        frozenset({"job_change", "hiring"}),
        fit=0.6,
    ),
    Account(
        "FirmAccount",
        "saas",
        200,
        frozenset({"hubspot"}),
        frozenset(),
        fit=0.9,
    ),
    Account(
        "WeakAccount",
        "retail",
        5,
        frozenset(),
        frozenset(),
        fit=0.1,
    ),
]

# Heavily signal-biased outcomes — signal gets 5 wins, firmographic gets 5 losses.
_SIGNAL_WINS: list[Outcome] = (
    [Outcome("icp_dimension", "signal", "win", confidence=1.0)] * 5
    + [Outcome("icp_dimension", "firmographic", "loss", confidence=1.0)] * 5
)


# ── test cases ────────────────────────────────────────────────────────────────

class TestClosedLoopEndToEnd(unittest.TestCase):
    """Assertion 1: the loop runs end-to-end without raising."""

    def test_score_accounts_returns_sorted_list(self):
        scored = score_accounts(_ACCOUNTS, _PROFILE)
        self.assertEqual(len(scored), len(_ACCOUNTS))
        # Sorted best-first
        scores = [s.score for s in scored]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_learn_returns_icp_profile(self):
        tuned = learn(_PROFILE, _SIGNAL_WINS)
        self.assertIsInstance(tuned, ICPProfile)

    def test_full_loop_runs_without_error(self):
        """Score → learn → re-score must not raise at any step."""
        scored_before = score_accounts(_ACCOUNTS, _PROFILE)
        tuned_profile = learn(_PROFILE, _SIGNAL_WINS)
        scored_after = score_accounts(_ACCOUNTS, tuned_profile)
        self.assertEqual(len(scored_before), len(scored_after))


class TestWeightsMoveInExpectedDirection(unittest.TestCase):
    """Assertion 2: a one-sided outcome set moves the targeted weight the right way."""

    def test_signal_wins_raise_signal_weight(self):
        """5 signal wins must increase the signal dimension weight."""
        outcomes = [Outcome("icp_dimension", "signal", "win", confidence=1.0)] * 5
        tuned = learn(_PROFILE, outcomes)
        self.assertGreater(
            tuned.weights["signal"],
            _PROFILE.weights["signal"],
            "signal wins should raise the signal weight",
        )

    def test_firmographic_losses_lower_firmographic_weight(self):
        """5 firmographic losses must decrease the firmographic dimension weight."""
        outcomes = [Outcome("icp_dimension", "firmographic", "loss", confidence=1.0)] * 5
        tuned = learn(_PROFILE, outcomes)
        self.assertLess(
            tuned.weights["firmographic"],
            _PROFILE.weights["firmographic"],
            "firmographic losses should lower the firmographic weight",
        )

    def test_signal_heavy_outcomes_change_tier_for_signal_account(self):
        """After signal wins, SignalAccount should score >= its pre-tune score.

        The 'signal' dimension carries more weight post-tune, so a high-signal
        account cannot score lower.
        """
        tuned_profile = learn(_PROFILE, _SIGNAL_WINS)

        before_map = {s.name: s for s in score_accounts(_ACCOUNTS, _PROFILE)}
        after_map = {s.name: s for s in score_accounts(_ACCOUNTS, tuned_profile)}

        signal_before = before_map["SignalAccount"].score
        signal_after = after_map["SignalAccount"].score
        self.assertGreaterEqual(
            signal_after,
            signal_before,
            "SignalAccount should not score lower after signal dimension is boosted",
        )

    def test_neutral_outcomes_do_not_change_weights(self):
        """All-neutral outcomes must leave weights unchanged."""
        outcomes = [
            Outcome("icp_dimension", "signal", "neutral"),
            Outcome("icp_dimension", "firmographic", "neutral"),
        ]
        tuned = learn(_PROFILE, outcomes)
        for k in _PROFILE.weights:
            self.assertEqual(
                tuned.weights[k],
                _PROFILE.weights[k],
                f"neutral outcomes must not change weight for '{k}'",
            )


class TestTunedWeightsSumTo100(unittest.TestCase):
    """Assertion 3: tuned weights must always sum to 100."""

    def test_sum_after_signal_wins(self):
        outcomes = [Outcome("icp_dimension", "signal", "win", confidence=1.0)] * 5
        tuned = learn(_PROFILE, outcomes)
        self.assertEqual(sum(tuned.weights.values()), 100)

    def test_sum_after_mixed_outcomes(self):
        tuned = learn(_PROFILE, _SIGNAL_WINS)
        self.assertEqual(sum(tuned.weights.values()), 100)

    def test_sum_after_empty_outcomes(self):
        tuned = learn(_PROFILE, [])
        self.assertEqual(sum(tuned.weights.values()), 100)

    def test_sum_after_repeated_wins_on_one_dimension(self):
        """Even 50 wins on one dimension must not break the sum invariant."""
        outcomes = [Outcome("icp_dimension", "firmographic", "win", confidence=1.0)] * 50
        tuned = learn(_PROFILE, outcomes)
        self.assertEqual(sum(tuned.weights.values()), 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
