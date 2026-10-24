"""Tests for pipeline velocity and cohort retention.

    python3 07-revenue-engine/test_pipeline_velocity.py
"""

from __future__ import annotations

import unittest

from pipeline_velocity import cohort_retention, velocity
from revenue_schema import PipelineVelocityInputs


class TestVelocity(unittest.TestCase):

    def test_formula(self):
        inputs = PipelineVelocityInputs(
            qualified_opps=40, win_rate=0.25, avg_deal_size=42000.0, avg_cycle_days=60.0
        )
        expected = (40 * 0.25 * 42000.0) / 60.0
        self.assertAlmostEqual(velocity(inputs), expected)

    def test_zero_opps_yields_zero_velocity(self):
        inputs = PipelineVelocityInputs(
            qualified_opps=0, win_rate=0.5, avg_deal_size=1000.0, avg_cycle_days=30.0
        )
        self.assertEqual(velocity(inputs), 0.0)

    def test_zero_win_rate_yields_zero_velocity(self):
        inputs = PipelineVelocityInputs(
            qualified_opps=100, win_rate=0.0, avg_deal_size=1000.0, avg_cycle_days=30.0
        )
        self.assertEqual(velocity(inputs), 0.0)


class TestCohortRetention(unittest.TestCase):

    def test_expansion_above_one(self):
        self.assertAlmostEqual(cohort_retention(50000.0, 58000.0), 1.16)

    def test_contraction_below_one(self):
        self.assertAlmostEqual(cohort_retention(50000.0, 31000.0), 0.62)

    def test_zero_start_returns_zero(self):
        self.assertEqual(cohort_retention(0.0, 0.0), 0.0)

    def test_negative_start_raises(self):
        with self.assertRaises(ValueError):
            cohort_retention(-1.0, 100.0)

    def test_negative_current_raises(self):
        with self.assertRaises(ValueError):
            cohort_retention(100.0, -1.0)


if __name__ == "__main__":
    unittest.main()
