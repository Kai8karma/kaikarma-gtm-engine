"""Tests for the brain learning loop — store + tuner.

    python3 05-brain-integration/test_brain.py

Stdlib only.  Uses tempfile so no real _state/ is touched.
"""

import tempfile
import unittest
from pathlib import Path

from brain_schema import Outcome
from outcome_store import load_outcomes, log_outcome
from policy_tuner import tune

# ── helpers ──────────────────────────────────────────────────────────────────

_BASE: dict[str, float] = {
    "firmographic": 40.0,
    "technographic": 20.0,
    "signal": 30.0,
    "fit": 10.0,
}
_TOTAL = sum(_BASE.values())  # 100.0


def _store(tmp: str) -> Path:
    return Path(tmp) / "outcomes.json"


# ── schema tests ─────────────────────────────────────────────────────────────

class TestOutcomeSchema(unittest.TestCase):

    def test_valid_outcome_constructs(self):
        o = Outcome("icp_dimension", "firmographic", "win")
        self.assertEqual(o.entity_type, "icp_dimension")
        self.assertEqual(o.verdict, "win")
        self.assertEqual(o.confidence, 0.7)

    def test_confidence_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            Outcome("icp_dimension", "firmographic", "win", confidence=1.5)

    def test_empty_key_raises(self):
        with self.assertRaises(ValueError):
            Outcome("icp_dimension", "   ", "win")

    def test_confidence_lower_bound(self):
        with self.assertRaises(ValueError):
            Outcome("icp_dimension", "firmographic", "win", confidence=-0.1)


# ── store tests ──────────────────────────────────────────────────────────────

class TestOutcomeStore(unittest.TestCase):

    def test_log_and_load_roundtrip(self):
        """log_outcome then load_outcomes must return the same record."""
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            o = Outcome("icp_dimension", "signal", "loss",
                        confidence=0.8, note="bad signal")
            log_outcome(o, store)
            loaded = load_outcomes(store)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].entity_type, "icp_dimension")
            self.assertEqual(loaded[0].key, "signal")
            self.assertEqual(loaded[0].verdict, "loss")
            self.assertAlmostEqual(loaded[0].confidence, 0.8)
            self.assertEqual(loaded[0].note, "bad signal")

    def test_multiple_outcomes_preserved_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            verdicts = ["win", "loss", "neutral"]
            for v in verdicts:
                log_outcome(Outcome("icp_dimension", "firmographic", v), store)  # type: ignore[arg-type]
            loaded = load_outcomes(store)
            self.assertEqual([o.verdict for o in loaded], verdicts)

    def test_load_from_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            loaded = load_outcomes(_store(tmp))
            self.assertEqual(loaded, [])

    def test_store_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "nested" / "dir" / "outcomes.json"
            log_outcome(Outcome("perf_threshold", "scale_when_ratio_below", "win"), store)
            self.assertTrue(store.exists())

    def test_perf_threshold_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            o = Outcome("perf_threshold", "kill_when_ratio_above", "neutral")
            log_outcome(o, store)
            loaded = load_outcomes(store)
            self.assertEqual(loaded[0].entity_type, "perf_threshold")


# ── tuner tests ──────────────────────────────────────────────────────────────

class TestPolicyTuner(unittest.TestCase):

    def test_win_raises_weight(self):
        """A win on 'firmographic' must increase its weight."""
        outcomes = [Outcome("icp_dimension", "firmographic", "win")]
        tuned = tune(_BASE, outcomes)
        self.assertGreater(tuned["firmographic"], _BASE["firmographic"])

    def test_loss_lowers_weight(self):
        """A loss on 'firmographic' must decrease its weight."""
        outcomes = [Outcome("icp_dimension", "firmographic", "loss")]
        tuned = tune(_BASE, outcomes)
        self.assertLess(tuned["firmographic"], _BASE["firmographic"])

    def test_renormalization_preserves_sum(self):
        """After any combination of wins/losses the sum must equal the original total."""
        outcomes = [
            Outcome("icp_dimension", "firmographic", "win"),
            Outcome("icp_dimension", "signal", "win", confidence=0.9),
            Outcome("icp_dimension", "technographic", "loss", confidence=0.6),
        ]
        tuned = tune(_BASE, outcomes)
        self.assertAlmostEqual(sum(tuned.values()), _TOTAL, places=1)

    def test_neutral_outcome_has_no_effect(self):
        """Neutral outcomes must leave weights unchanged."""
        outcomes = [Outcome("icp_dimension", "firmographic", "neutral")]
        tuned = tune(_BASE, outcomes)
        for k in _BASE:
            self.assertAlmostEqual(tuned[k], _BASE[k], places=2)

    def test_unknown_key_is_silently_skipped(self):
        """An outcome key not in base_weights must not raise, just be skipped."""
        outcomes = [Outcome("icp_dimension", "nonexistent_dim", "win")]
        tuned = tune(_BASE, outcomes)
        self.assertAlmostEqual(sum(tuned.values()), _TOTAL, places=1)

    def test_min_bound_respected(self):
        """Repeated losses must not drive a weight below MIN_FRAC * total."""
        # 50 losses — enough to push 'fit' (weight 10) well below the floor.
        outcomes = [Outcome("icp_dimension", "fit", "loss")] * 50
        tuned = tune(_BASE, outcomes)
        min_allowed = 0.05 * _TOTAL   # 5.0 for a 100-total base
        self.assertGreaterEqual(tuned["fit"], min_allowed - 1e-6)

    def test_max_bound_respected(self):
        """Repeated wins must not drive a weight above MAX_FRAC * total."""
        outcomes = [Outcome("icp_dimension", "firmographic", "win")] * 50
        tuned = tune(_BASE, outcomes)
        max_allowed = 0.80 * _TOTAL   # 80.0 for a 100-total base
        self.assertLessEqual(tuned["firmographic"], max_allowed + 1e-6)

    def test_empty_outcomes_returns_base_unchanged(self):
        tuned = tune(_BASE, [])
        for k in _BASE:
            self.assertAlmostEqual(tuned[k], _BASE[k], places=2)

    def test_deterministic(self):
        """Same inputs must produce identical outputs every time."""
        outcomes = [
            Outcome("icp_dimension", "firmographic", "win"),
            Outcome("icp_dimension", "signal", "loss", confidence=0.8),
        ]
        self.assertEqual(tune(_BASE, outcomes), tune(_BASE, outcomes))

    def test_confidence_gates_step_size(self):
        """High-confidence win should move the weight more than low-confidence win."""
        high = tune(_BASE, [Outcome("icp_dimension", "firmographic", "win", confidence=1.0)])
        low  = tune(_BASE, [Outcome("icp_dimension", "firmographic", "win", confidence=0.1)])
        self.assertGreater(high["firmographic"], low["firmographic"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
