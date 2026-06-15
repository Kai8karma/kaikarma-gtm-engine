"""Tests for routing_outcomes.py — brain-integration bridge for the lead router.

    python3 04-revops-engine/test_routing_outcomes.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Cross-pillar sys.path bridge.
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("04-revops-engine", "05-brain-integration"):
    _p = os.path.join(_BASE, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from outcome_store import load_outcomes  # noqa: E402
from revops_schema import Lead, Route  # noqa: E402
from routing_outcomes import (  # noqa: E402
    build_sla_outcome,
    build_tier_outcome,
    record_routing_outcome,
    record_routing_outcomes_batch,
)


def _lead(tier: str = "A", signal: str | None = "job_change") -> Lead:
    return Lead(name="TestCo", icp_tier=tier, signal=signal, region="AMER")


def _route(destination: str = "ae_queue", sla_minutes: int = 60) -> Route:
    return Route(
        lead_name="TestCo",
        destination=destination,
        sla_minutes=sla_minutes,
        reason="test",
    )


class TestBuildSlaOutcome(unittest.TestCase):

    def test_entity_type_is_routing_sla(self) -> None:
        o = build_sla_outcome(_lead(), _route(), converted=True)
        self.assertEqual(o.entity_type, "routing_sla")

    def test_key_is_destination(self) -> None:
        o = build_sla_outcome(_lead(), _route("instant_alert"), converted=True)
        self.assertEqual(o.key, "instant_alert")

    def test_win_when_converted(self) -> None:
        o = build_sla_outcome(_lead(), _route(), converted=True)
        self.assertEqual(o.verdict, "win")

    def test_loss_when_not_converted(self) -> None:
        o = build_sla_outcome(_lead(), _route(), converted=False)
        self.assertEqual(o.verdict, "loss")

    def test_note_contains_lead_name(self) -> None:
        lead = Lead("Specific Co", icp_tier="B", signal=None, region="EMEA")
        o = build_sla_outcome(lead, _route(), converted=True)
        self.assertIn("Specific Co", o.note)

    def test_note_contains_destination(self) -> None:
        o = build_sla_outcome(_lead(), _route("sdr_sequence"), converted=False)
        self.assertIn("sdr_sequence", o.note)

    def test_default_confidence(self) -> None:
        o = build_sla_outcome(_lead(), _route(), converted=True)
        self.assertEqual(o.confidence, 0.7)

    def test_sla_minutes_in_note(self) -> None:
        o = build_sla_outcome(_lead(), _route(sla_minutes=240), converted=True)
        self.assertIn("240", o.note)


class TestBuildTierOutcome(unittest.TestCase):

    def test_entity_type_is_routing_tier(self) -> None:
        o = build_tier_outcome(_lead("A"), _route(), converted=True)
        self.assertEqual(o.entity_type, "routing_tier")

    def test_key_is_icp_tier(self) -> None:
        for tier in ("A", "B", "C", "D"):
            lead = Lead("X", icp_tier=tier, signal=None, region="AMER")
            o = build_tier_outcome(lead, _route(), converted=True)
            self.assertEqual(o.key, tier)

    def test_win_when_converted(self) -> None:
        o = build_tier_outcome(_lead("B"), _route(), converted=True)
        self.assertEqual(o.verdict, "win")

    def test_loss_when_not_converted(self) -> None:
        o = build_tier_outcome(_lead("C"), _route(), converted=False)
        self.assertEqual(o.verdict, "loss")

    def test_note_contains_tier(self) -> None:
        o = build_tier_outcome(_lead("A"), _route(), converted=True)
        self.assertIn("A", o.note)

    def test_default_confidence(self) -> None:
        o = build_tier_outcome(_lead(), _route(), converted=True)
        self.assertEqual(o.confidence, 0.7)


class TestRecordRoutingOutcome(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name) / "outcomes.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_logs_two_outcomes_per_lead(self) -> None:
        record_routing_outcome(_lead(), _route(), converted=True, store_path=self.store)
        loaded = load_outcomes(self.store)
        self.assertEqual(len(loaded), 2)

    def test_first_outcome_is_sla(self) -> None:
        record_routing_outcome(_lead(), _route("ae_queue"), converted=True, store_path=self.store)
        loaded = load_outcomes(self.store)
        self.assertEqual(loaded[0].entity_type, "routing_sla")
        self.assertEqual(loaded[0].key, "ae_queue")

    def test_second_outcome_is_tier(self) -> None:
        record_routing_outcome(_lead("B"), _route(), converted=False, store_path=self.store)
        loaded = load_outcomes(self.store)
        self.assertEqual(loaded[1].entity_type, "routing_tier")
        self.assertEqual(loaded[1].key, "B")

    def test_returns_sla_and_tier_tuple(self) -> None:
        sla_o, tier_o = record_routing_outcome(
            _lead("A"), _route("instant_alert"), converted=True, store_path=self.store
        )
        self.assertEqual(sla_o.entity_type, "routing_sla")
        self.assertEqual(tier_o.entity_type, "routing_tier")

    def test_win_verdict_round_trip(self) -> None:
        record_routing_outcome(_lead(), _route(), converted=True, store_path=self.store)
        loaded = load_outcomes(self.store)
        for o in loaded:
            self.assertEqual(o.verdict, "win")

    def test_loss_verdict_round_trip(self) -> None:
        record_routing_outcome(_lead(), _route(), converted=False, store_path=self.store)
        loaded = load_outcomes(self.store)
        for o in loaded:
            self.assertEqual(o.verdict, "loss")

    def test_appends_multiple_leads(self) -> None:
        record_routing_outcome(_lead("A"), _route(), converted=True, store_path=self.store)
        record_routing_outcome(_lead("C"), _route("nurture"), converted=False, store_path=self.store)
        loaded = load_outcomes(self.store)
        self.assertEqual(len(loaded), 4)  # 2 per lead


class TestRecordRoutingOutcomesBatch(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name) / "outcomes.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_batch_returns_pairs_matching_input_length(self) -> None:
        triples = [
            (_lead("A"), _route("ae_queue"), True),
            (_lead("B"), _route("sdr_sequence"), False),
            (_lead("D"), _route("disqualified", 0), False),
        ]
        results = record_routing_outcomes_batch(triples, self.store)
        self.assertEqual(len(results), 3)

    def test_batch_stores_two_outcomes_per_triple(self) -> None:
        triples = [
            (_lead("A"), _route(), True),
            (_lead("C"), _route("nurture"), False),
        ]
        record_routing_outcomes_batch(triples, self.store)
        loaded = load_outcomes(self.store)
        self.assertEqual(len(loaded), 4)

    def test_empty_batch_writes_nothing(self) -> None:
        record_routing_outcomes_batch([], self.store)
        self.assertFalse(self.store.exists())

    def test_batch_order_preserved(self) -> None:
        triples = [
            (_lead("A"), _route("instant_alert"), True),
            (_lead("B"), _route("sdr_sequence"), False),
        ]
        record_routing_outcomes_batch(triples, self.store)
        loaded = load_outcomes(self.store)
        # First two: A lead (sla=instant_alert, tier=A both win)
        self.assertEqual(loaded[0].key, "instant_alert")
        self.assertEqual(loaded[1].key, "A")
        # Next two: B lead (sla=sdr_sequence, tier=B both loss)
        self.assertEqual(loaded[2].key, "sdr_sequence")
        self.assertEqual(loaded[3].key, "B")


if __name__ == "__main__":
    unittest.main(verbosity=2)
