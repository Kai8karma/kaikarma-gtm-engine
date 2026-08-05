"""Tests for the MRR bridge, ARR, and churn-rate math.

    python3 07-revenue-engine/test_mrr_calculator.py
"""

from __future__ import annotations

import unittest

from mrr_calculator import arr, churn_rate, compute_mrr_bridge
from revenue_schema import Subscription


class TestComputeMrrBridge(unittest.TestCase):

    def test_new_subscription_counted_as_new(self):
        prev = []
        curr = [Subscription("s1", "a1", mrr=1000.0, status="active")]
        bridge = compute_mrr_bridge(prev, curr)
        self.assertEqual(bridge.new_mrr, 1000.0)
        self.assertEqual(bridge.expansion_mrr, 0.0)

    def test_expansion_when_mrr_increases(self):
        prev = [Subscription("s1", "a1", mrr=1000.0, status="active")]
        curr = [Subscription("s1", "a1", mrr=1500.0, status="active")]
        bridge = compute_mrr_bridge(prev, curr)
        self.assertEqual(bridge.expansion_mrr, 500.0)
        self.assertEqual(bridge.new_mrr, 0.0)

    def test_contraction_when_mrr_decreases(self):
        prev = [Subscription("s1", "a1", mrr=1000.0, status="active")]
        curr = [Subscription("s1", "a1", mrr=600.0, status="active")]
        bridge = compute_mrr_bridge(prev, curr)
        self.assertEqual(bridge.contraction_mrr, 400.0)

    def test_explicit_cancellation_is_churn(self):
        prev = [Subscription("s1", "a1", mrr=1000.0, status="active")]
        curr = [Subscription("s1", "a1", mrr=1000.0, status="canceled")]
        bridge = compute_mrr_bridge(prev, curr)
        self.assertEqual(bridge.churned_mrr, 1000.0)

    def test_disappearing_subscription_is_churn(self):
        prev = [Subscription("s1", "a1", mrr=800.0, status="active")]
        curr = []
        bridge = compute_mrr_bridge(prev, curr)
        self.assertEqual(bridge.churned_mrr, 800.0)

    def test_inactive_prev_promoted_to_active_is_new_not_expansion(self):
        prev = [Subscription("s1", "a1", mrr=0.0, status="trialing")]
        curr = [Subscription("s1", "a1", mrr=500.0, status="active")]
        bridge = compute_mrr_bridge(prev, curr)
        self.assertEqual(bridge.new_mrr, 500.0)
        self.assertEqual(bridge.expansion_mrr, 0.0)

    def test_no_change_yields_zero_bridge(self):
        prev = [Subscription("s1", "a1", mrr=1000.0, status="active")]
        curr = [Subscription("s1", "a1", mrr=1000.0, status="active")]
        bridge = compute_mrr_bridge(prev, curr)
        self.assertEqual(bridge.net_new_mrr, 0.0)

    def test_mixed_batch(self):
        prev = [
            Subscription("s1", "acme", mrr=2000.0, status="active"),
            Subscription("s2", "midfin", mrr=1500.0, status="active"),
            Subscription("s3", "scaleup", mrr=800.0, status="active"),
        ]
        curr = [
            Subscription("s1", "acme", mrr=2500.0, status="active"),
            Subscription("s2", "midfin", mrr=1500.0, status="canceled"),
            Subscription("s4", "newco", mrr=1200.0, status="active"),
        ]
        bridge = compute_mrr_bridge(prev, curr)
        self.assertEqual(bridge.new_mrr, 1200.0)
        self.assertEqual(bridge.expansion_mrr, 500.0)
        self.assertEqual(bridge.contraction_mrr, 0.0)
        self.assertEqual(bridge.churned_mrr, 1500.0 + 800.0)
        self.assertEqual(bridge.net_new_mrr, 1200.0 + 500.0 - 0.0 - 2300.0)


class TestArr(unittest.TestCase):

    def test_annualizes_mrr(self):
        self.assertEqual(arr(1000.0), 12000.0)

    def test_negative_mrr_raises(self):
        with self.assertRaises(ValueError):
            arr(-1.0)


class TestChurnRate(unittest.TestCase):

    def test_computes_ratio(self):
        self.assertAlmostEqual(churn_rate(200.0, 1000.0), 0.2)

    def test_zero_starting_mrr_returns_zero(self):
        self.assertEqual(churn_rate(0.0, 0.0), 0.0)

    def test_negative_churned_raises(self):
        with self.assertRaises(ValueError):
            churn_rate(-1.0, 100.0)

    def test_negative_starting_raises(self):
        with self.assertRaises(ValueError):
            churn_rate(10.0, -100.0)


if __name__ == "__main__":
    unittest.main()
