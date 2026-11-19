"""Tests for revenue_outcomes.py — brain-integration bridge for attribution.

    python3 07-revenue-engine/test_revenue_outcomes.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Cross-pillar sys.path bridge.
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("07-revenue-engine", "05-brain-integration"):
    _p = os.path.join(_BASE, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from outcome_store import load_outcomes  # noqa: E402
from revenue_outcomes import (  # noqa: E402
    build_revenue_outcomes,
    record_revenue_outcomes,
    record_revenue_outcomes_batch,
)
from revenue_schema import AttributionResult  # noqa: E402

TWO_CHANNEL_RESULT = AttributionResult(
    deal_id="d1", model="u_shaped", channel_credit={"linkedin_ads": 400.0, "webinar": 600.0}
)


class TestBuildRevenueOutcomes(unittest.TestCase):

    def test_one_outcome_per_channel(self):
        outcomes = build_revenue_outcomes(TWO_CHANNEL_RESULT, closed_won=True)
        self.assertEqual(len(outcomes), 2)
        self.assertEqual({o.key for o in outcomes}, {"linkedin_ads", "webinar"})

    def test_entity_type_is_revenue_channel(self):
        outcomes = build_revenue_outcomes(TWO_CHANNEL_RESULT, closed_won=True)
        for o in outcomes:
            self.assertEqual(o.entity_type, "revenue_channel")

    def test_won_deal_yields_win_verdict(self):
        outcomes = build_revenue_outcomes(TWO_CHANNEL_RESULT, closed_won=True)
        for o in outcomes:
            self.assertEqual(o.verdict, "win")

    def test_lost_deal_yields_loss_verdict(self):
        outcomes = build_revenue_outcomes(TWO_CHANNEL_RESULT, closed_won=False)
        for o in outcomes:
            self.assertEqual(o.verdict, "loss")

    def test_confidence_is_share_of_total_credit(self):
        outcomes = build_revenue_outcomes(TWO_CHANNEL_RESULT, closed_won=True)
        by_key = {o.key: o for o in outcomes}
        self.assertAlmostEqual(by_key["linkedin_ads"].confidence, 0.4)
        self.assertAlmostEqual(by_key["webinar"].confidence, 0.6)

    def test_zero_total_credit_yields_zero_confidence(self):
        result = AttributionResult(deal_id="d2", model="linear", channel_credit={"unattributed": 0.0})
        outcomes = build_revenue_outcomes(result, closed_won=True)
        self.assertEqual(outcomes[0].confidence, 0.0)


class TestRecordRevenueOutcomes(unittest.TestCase):

    def test_logs_and_returns_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "outcomes.json"
            outcomes = record_revenue_outcomes(TWO_CHANNEL_RESULT, closed_won=True, store_path=store)
            self.assertEqual(len(outcomes), 2)
            loaded = load_outcomes(store)
            self.assertEqual(len(loaded), 2)

    def test_batch_logs_all_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "outcomes.json"
            other_result = AttributionResult(deal_id="d3", model="linear", channel_credit={"seo": 100.0})
            batch = [(TWO_CHANNEL_RESULT, True), (other_result, False)]
            outcomes = record_revenue_outcomes_batch(batch, store)
            self.assertEqual(len(outcomes), 3)
            self.assertEqual(len(load_outcomes(store)), 3)

    def test_empty_batch_logs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "outcomes.json"
            outcomes = record_revenue_outcomes_batch([], store)
            self.assertEqual(outcomes, [])


if __name__ == "__main__":
    unittest.main()
