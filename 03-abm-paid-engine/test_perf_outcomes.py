"""Tests for perf_outcomes.py — brain-integration bridge for the paid controller.

    python3 03-abm-paid-engine/test_perf_outcomes.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Cross-pillar sys.path bridge.
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("03-abm-paid-engine", "05-brain-integration"):
    _p = os.path.join(_BASE, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from outcome_store import load_outcomes  # noqa: E402
from perf_schema import Action, CUT, HOLD, KILL, LEARNING, SCALE  # noqa: E402
from perf_outcomes import (  # noqa: E402
    _VERDICT_TO_KEY,
    build_perf_outcome,
    record_perf_outcome,
    record_perf_outcomes_batch,
)


def _action(verdict: str, campaign: str = "test-camp") -> Action:
    return Action(
        campaign=campaign,
        verdict=verdict,
        old_budget=100.0,
        new_budget=125.0 if verdict == SCALE else 100.0,
        actual_cpa=30.0,
        reason="test",
    )


class TestBuildPerfOutcome(unittest.TestCase):

    def test_scale_win_maps_to_correct_key(self) -> None:
        o = build_perf_outcome(_action(SCALE), kept_under_target=True)
        self.assertEqual(o.entity_type, "perf_threshold")
        self.assertEqual(o.key, "scale_when_ratio_below")
        self.assertEqual(o.verdict, "win")

    def test_scale_loss_when_not_kept_under_target(self) -> None:
        o = build_perf_outcome(_action(SCALE), kept_under_target=False)
        self.assertEqual(o.verdict, "loss")

    def test_cut_key(self) -> None:
        o = build_perf_outcome(_action(CUT), kept_under_target=True)
        self.assertEqual(o.key, "cut_when_ratio_above")

    def test_kill_key(self) -> None:
        o = build_perf_outcome(_action(KILL), kept_under_target=True)
        self.assertEqual(o.key, "kill_when_ratio_above")

    def test_hold_key(self) -> None:
        o = build_perf_outcome(_action(HOLD), kept_under_target=True)
        self.assertEqual(o.key, "scale_when_ratio_below")

    def test_learning_key(self) -> None:
        o = build_perf_outcome(_action(LEARNING), kept_under_target=True)
        self.assertEqual(o.key, "min_conversions_to_exit_learning")

    def test_note_contains_campaign_name(self) -> None:
        o = build_perf_outcome(_action(SCALE, "my-camp"), kept_under_target=True)
        self.assertIn("my-camp", o.note)

    def test_note_contains_verdict(self) -> None:
        o = build_perf_outcome(_action(CUT), kept_under_target=False)
        self.assertIn("CUT", o.note)

    def test_default_confidence(self) -> None:
        o = build_perf_outcome(_action(SCALE), kept_under_target=True)
        self.assertEqual(o.confidence, 0.7)

    def test_entity_type_is_perf_threshold(self) -> None:
        for verdict in (SCALE, HOLD, CUT, KILL, LEARNING):
            o = build_perf_outcome(_action(verdict), kept_under_target=True)
            self.assertEqual(o.entity_type, "perf_threshold")


class TestRecordPerfOutcome(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name) / "outcomes.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_round_trip_single(self) -> None:
        action = _action(SCALE)
        logged = record_perf_outcome(action, kept_under_target=True, store_path=self.store)
        loaded = load_outcomes(self.store)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].entity_type, "perf_threshold")
        self.assertEqual(loaded[0].key, "scale_when_ratio_below")
        self.assertEqual(loaded[0].verdict, "win")
        self.assertEqual(loaded[0], logged)

    def test_round_trip_loss(self) -> None:
        record_perf_outcome(_action(CUT), kept_under_target=False, store_path=self.store)
        loaded = load_outcomes(self.store)
        self.assertEqual(loaded[0].verdict, "loss")

    def test_returns_outcome(self) -> None:
        result = record_perf_outcome(_action(KILL), kept_under_target=True, store_path=self.store)
        self.assertEqual(result.key, "kill_when_ratio_above")

    def test_appends_multiple_calls(self) -> None:
        record_perf_outcome(_action(SCALE), kept_under_target=True, store_path=self.store)
        record_perf_outcome(_action(CUT), kept_under_target=False, store_path=self.store)
        loaded = load_outcomes(self.store)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].key, "scale_when_ratio_below")
        self.assertEqual(loaded[1].key, "cut_when_ratio_above")


class TestRecordPerfOutcomesBatch(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name) / "outcomes.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_batch_length_matches_input(self) -> None:
        pairs = [
            (_action(SCALE), True),
            (_action(CUT), False),
            (_action(KILL), True),
        ]
        results = record_perf_outcomes_batch(pairs, self.store)
        self.assertEqual(len(results), 3)

    def test_batch_round_trips_all(self) -> None:
        pairs = [
            (_action(SCALE), True),
            (_action(HOLD), True),
            (_action(LEARNING), False),
        ]
        record_perf_outcomes_batch(pairs, self.store)
        loaded = load_outcomes(self.store)
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0].verdict, "win")
        self.assertEqual(loaded[1].verdict, "win")
        self.assertEqual(loaded[2].verdict, "loss")

    def test_empty_batch_writes_nothing(self) -> None:
        record_perf_outcomes_batch([], self.store)
        self.assertFalse(self.store.exists())

    def test_all_verdict_keys_covered(self) -> None:
        """Every controller verdict should map to a threshold key."""
        for v in (SCALE, CUT, KILL, HOLD, LEARNING):
            self.assertIn(v, _VERDICT_TO_KEY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
