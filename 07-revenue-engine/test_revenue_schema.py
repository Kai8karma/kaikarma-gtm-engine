"""Tests for revenue-layer schema validation.

    python3 07-revenue-engine/test_revenue_schema.py
"""

from __future__ import annotations

import unittest

from revenue_schema import (
    AttributionResult,
    Deal,
    MRRBridge,
    PipelineVelocityInputs,
    Subscription,
)


class TestDeal(unittest.TestCase):

    def test_valid_deal_constructs(self):
        d = Deal(deal_id="d1", amount=1000.0, closed_won=True, close_date_iso="2026-07-01T00:00:00+00:00")
        self.assertEqual(d.touchpoints, ())

    def test_negative_amount_raises(self):
        with self.assertRaises(ValueError):
            Deal(deal_id="d1", amount=-1.0, closed_won=True, close_date_iso="2026-07-01T00:00:00+00:00")


class TestAttributionResult(unittest.TestCase):

    def test_valid_model_constructs(self):
        r = AttributionResult(deal_id="d1", model="linear", channel_credit={"webinar": 100.0})
        self.assertEqual(r.model, "linear")

    def test_invalid_model_raises(self):
        with self.assertRaises(ValueError):
            AttributionResult(deal_id="d1", model="magic", channel_credit={})


class TestSubscription(unittest.TestCase):

    def test_valid_status_constructs(self):
        s = Subscription(subscription_id="s1", account_id="a1", mrr=100.0, status="active")
        self.assertEqual(s.status, "active")

    def test_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            Subscription(subscription_id="s1", account_id="a1", mrr=100.0, status="lapsed")

    def test_negative_mrr_raises(self):
        with self.assertRaises(ValueError):
            Subscription(subscription_id="s1", account_id="a1", mrr=-5.0, status="active")


class TestMRRBridge(unittest.TestCase):

    def test_net_new_mrr_computed(self):
        bridge = MRRBridge(new_mrr=1000, expansion_mrr=500, contraction_mrr=200, churned_mrr=300)
        self.assertEqual(bridge.net_new_mrr, 1000)

    def test_net_new_mrr_can_be_negative(self):
        bridge = MRRBridge(new_mrr=0, expansion_mrr=0, contraction_mrr=100, churned_mrr=500)
        self.assertEqual(bridge.net_new_mrr, -600)


class TestPipelineVelocityInputs(unittest.TestCase):

    def _valid_kwargs(self, **overrides):
        kwargs = dict(qualified_opps=10, win_rate=0.3, avg_deal_size=1000.0, avg_cycle_days=30.0)
        kwargs.update(overrides)
        return kwargs

    def test_valid_inputs_construct(self):
        PipelineVelocityInputs(**self._valid_kwargs())

    def test_negative_opps_raises(self):
        with self.assertRaises(ValueError):
            PipelineVelocityInputs(**self._valid_kwargs(qualified_opps=-1))

    def test_win_rate_above_one_raises(self):
        with self.assertRaises(ValueError):
            PipelineVelocityInputs(**self._valid_kwargs(win_rate=1.1))

    def test_win_rate_below_zero_raises(self):
        with self.assertRaises(ValueError):
            PipelineVelocityInputs(**self._valid_kwargs(win_rate=-0.1))

    def test_negative_deal_size_raises(self):
        with self.assertRaises(ValueError):
            PipelineVelocityInputs(**self._valid_kwargs(avg_deal_size=-1.0))

    def test_zero_cycle_days_raises(self):
        with self.assertRaises(ValueError):
            PipelineVelocityInputs(**self._valid_kwargs(avg_cycle_days=0))

    def test_negative_cycle_days_raises(self):
        with self.assertRaises(ValueError):
            PipelineVelocityInputs(**self._valid_kwargs(avg_cycle_days=-5))


if __name__ == "__main__":
    unittest.main()
