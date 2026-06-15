"""Tests for persistent_loop — warm-start from accumulated outcomes.

Three falsifiable assertions:
    1. Empty/missing store → base_profile returned unchanged.
    2. Seeded store → warmed weights sum to 100.
    3. Missing file is handled gracefully (no crash, base returned).

    python3 examples/test_persistent_loop.py
    python3 -m pytest examples/             # if pytest installed

Stdlib only, no network.  Uses tempfile so no real state is written.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# ── pillar path injection (mirrors persistent_loop.py) ──────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
[sys.path.insert(0, os.path.join(BASE, d))
 for d in ("01-list-engine", "05-brain-integration")]

from brain_schema import Outcome                                    # noqa: E402
from icp_schema import ICPProfile                                   # noqa: E402
from outcome_store import log_outcome                               # noqa: E402
from persistent_loop import load_and_tune, warm_start_summary      # noqa: E402

# ── shared fixtures ───────────────────────────────────────────────────────────

_PROFILE = ICPProfile(
    name="test ICP",
    target_industries=frozenset({"software", "saas"}),
    employee_min=50,
    employee_max=1000,
    target_tech=frozenset({"hubspot"}),
)

_ICP_OUTCOMES: list[Outcome] = [
    Outcome("icp_dimension", "signal", "win", confidence=0.9),
    Outcome("icp_dimension", "firmographic", "loss", confidence=0.7),
    # perf_threshold outcomes must be ignored by load_and_tune
    Outcome("perf_threshold", "scale_when_ratio_below", "win"),
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _seeded_store(outcomes: list[Outcome], tmp_dir: str) -> Path:
    """Write *outcomes* to a temp JSON store and return its path."""
    store = Path(tmp_dir) / "outcomes.json"
    for o in outcomes:
        log_outcome(o, store)
    return store


# ── test cases ────────────────────────────────────────────────────────────────

class TestEmptyOrMissingStore(unittest.TestCase):
    """Assertion 1 + 3: empty / missing store returns base_profile unchanged."""

    def test_missing_file_returns_base_unchanged(self):
        """A path that doesn't exist must not raise and must return base_profile."""
        missing = Path("/tmp/nonexistent_kaikarma_test_store.json")
        result = load_and_tune(_PROFILE, missing)
        self.assertEqual(result.weights, _PROFILE.weights)

    def test_empty_store_returns_base_unchanged(self):
        """An empty JSON store must return base_profile unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "outcomes.json"
            store.write_text("[]", encoding="utf-8")
            result = load_and_tune(_PROFILE, store)
            self.assertEqual(result.weights, _PROFILE.weights)

    def test_store_with_only_perf_outcomes_returns_base_unchanged(self):
        """Outcomes with entity_type != 'icp_dimension' must be ignored."""
        with tempfile.TemporaryDirectory() as tmp:
            store = _seeded_store(
                [Outcome("perf_threshold", "scale_when_ratio_below", "win")],
                tmp,
            )
            result = load_and_tune(_PROFILE, store)
            self.assertEqual(result.weights, _PROFILE.weights)

    def test_missing_file_warm_summary_does_not_crash(self):
        """warm_start_summary on a missing path must return a string, not raise."""
        missing = Path("/tmp/nonexistent_kaikarma_summary_store.json")
        summary = warm_start_summary(_PROFILE, missing)
        self.assertIsInstance(summary, str)
        self.assertIn("no icp_dimension outcomes found", summary)


class TestSeededStoreWarmStart(unittest.TestCase):
    """Assertion 2: seeded store → warmed weights sum to 100."""

    def test_warmed_weights_sum_to_100(self):
        """After replaying icp_dimension outcomes, weights must sum to 100."""
        with tempfile.TemporaryDirectory() as tmp:
            store = _seeded_store(_ICP_OUTCOMES, tmp)
            warmed = load_and_tune(_PROFILE, store)
            self.assertEqual(sum(warmed.weights.values()), 100)

    def test_warmed_returns_icp_profile_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _seeded_store(_ICP_OUTCOMES, tmp)
            result = load_and_tune(_PROFILE, store)
            self.assertIsInstance(result, ICPProfile)

    def test_signal_wins_raise_signal_weight(self):
        """Multiple signal wins must increase the signal dimension weight."""
        outcomes = [Outcome("icp_dimension", "signal", "win", confidence=1.0)] * 5
        with tempfile.TemporaryDirectory() as tmp:
            store = _seeded_store(outcomes, tmp)
            warmed = load_and_tune(_PROFILE, store)
            self.assertGreater(warmed.weights["signal"], _PROFILE.weights["signal"])

    def test_firmographic_losses_lower_weight(self):
        """Multiple firmographic losses must decrease the firmographic weight."""
        outcomes = [Outcome("icp_dimension", "firmographic", "loss", confidence=1.0)] * 5
        with tempfile.TemporaryDirectory() as tmp:
            store = _seeded_store(outcomes, tmp)
            warmed = load_and_tune(_PROFILE, store)
            self.assertLess(warmed.weights["firmographic"], _PROFILE.weights["firmographic"])

    def test_perf_outcomes_filtered_out(self):
        """perf_threshold outcomes mixed in must not affect icp weights."""
        icp_only = [Outcome("icp_dimension", "signal", "win", confidence=1.0)]
        mixed = icp_only + [Outcome("perf_threshold", "scale_when_ratio_below", "win")]
        with tempfile.TemporaryDirectory() as tmp_a:
            with tempfile.TemporaryDirectory() as tmp_b:
                store_icp = _seeded_store(icp_only, tmp_a)
                store_mixed = _seeded_store(mixed, tmp_b)
                warmed_icp = load_and_tune(_PROFILE, store_icp)
                warmed_mixed = load_and_tune(_PROFILE, store_mixed)
        self.assertEqual(warmed_icp.weights, warmed_mixed.weights)

    def test_neutral_outcomes_leave_weights_unchanged(self):
        """All-neutral icp_dimension outcomes must not change weights."""
        outcomes = [
            Outcome("icp_dimension", "signal", "neutral"),
            Outcome("icp_dimension", "firmographic", "neutral"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            store = _seeded_store(outcomes, tmp)
            result = load_and_tune(_PROFILE, store)
            self.assertEqual(result.weights, _PROFILE.weights)

    def test_warm_summary_reports_replay_count(self):
        """warm_start_summary must mention how many outcomes were replayed."""
        with tempfile.TemporaryDirectory() as tmp:
            store = _seeded_store(_ICP_OUTCOMES, tmp)
            summary = warm_start_summary(_PROFILE, store)
        # Two of the three test outcomes have entity_type == 'icp_dimension'
        self.assertIn("2", summary)
        self.assertIn("100", summary)


if __name__ == "__main__":
    unittest.main(verbosity=2)
