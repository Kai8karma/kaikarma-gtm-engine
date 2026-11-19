"""Tests for multi-touch attribution models — every model must sum to the deal amount.

    python3 07-revenue-engine/test_attribution.py
"""

from __future__ import annotations

import unittest

from attribution import UNATTRIBUTED, attribute, first_touch, last_touch, linear, time_decay, u_shaped
from revenue_schema import Deal, Touchpoint

NO_TOUCH_DEAL = Deal(deal_id="d0", amount=500.0, closed_won=True, close_date_iso="2026-07-01T00:00:00+00:00")

ONE_TOUCH_DEAL = Deal(
    deal_id="d1", amount=1000.0, closed_won=True, close_date_iso="2026-07-01T00:00:00+00:00",
    touchpoints=(Touchpoint("seo", "organic", "2026-06-01T00:00:00+00:00"),),
)

TWO_TOUCH_DEAL = Deal(
    deal_id="d2", amount=1000.0, closed_won=True, close_date_iso="2026-07-01T00:00:00+00:00",
    touchpoints=(
        Touchpoint("linkedin_ads", "abm", "2026-06-01T00:00:00+00:00"),
        Touchpoint("demo_call", "precall", "2026-06-30T00:00:00+00:00"),
    ),
)

FOUR_TOUCH_DEAL = Deal(
    deal_id="d4", amount=1000.0, closed_won=True, close_date_iso="2026-07-01T00:00:00+00:00",
    touchpoints=(
        Touchpoint("linkedin_ads", "abm", "2026-06-01T00:00:00+00:00"),
        Touchpoint("webinar", "q2", "2026-06-10T00:00:00+00:00"),
        Touchpoint("outbound_email", "sdr", "2026-06-20T00:00:00+00:00"),
        Touchpoint("demo_call", "precall", "2026-06-30T00:00:00+00:00"),
    ),
)


class TestNoTouchpoints(unittest.TestCase):

    def test_all_models_fall_back_to_unattributed(self):
        for model in ("first_touch", "last_touch", "linear", "u_shaped", "time_decay"):
            with self.subTest(model=model):
                result = attribute(NO_TOUCH_DEAL, model)
                self.assertEqual(result.channel_credit, {UNATTRIBUTED: 500.0})


class TestFirstLastTouch(unittest.TestCase):

    def test_first_touch_credits_first_channel(self):
        self.assertEqual(first_touch(FOUR_TOUCH_DEAL), {"linkedin_ads": 1000.0})

    def test_last_touch_credits_last_channel(self):
        self.assertEqual(last_touch(FOUR_TOUCH_DEAL), {"demo_call": 1000.0})


class TestLinear(unittest.TestCase):

    def test_splits_evenly_across_touchpoints(self):
        credit = linear(FOUR_TOUCH_DEAL)
        self.assertEqual(len(credit), 4)
        for amount in credit.values():
            self.assertAlmostEqual(amount, 250.0)
        self.assertAlmostEqual(sum(credit.values()), 1000.0)

    def test_same_channel_touched_twice_aggregates(self):
        deal = Deal(
            deal_id="d", amount=400.0, closed_won=True, close_date_iso="2026-07-01T00:00:00+00:00",
            touchpoints=(
                Touchpoint("email", "c1", "2026-06-01T00:00:00+00:00"),
                Touchpoint("email", "c2", "2026-06-15T00:00:00+00:00"),
            ),
        )
        self.assertEqual(linear(deal), {"email": 400.0})


class TestUShaped(unittest.TestCase):

    def test_single_touchpoint_gets_all_credit(self):
        self.assertEqual(u_shaped(ONE_TOUCH_DEAL), {"seo": 1000.0})

    def test_two_touchpoints_split_50_50(self):
        credit = u_shaped(TWO_TOUCH_DEAL)
        self.assertAlmostEqual(credit["linkedin_ads"], 500.0)
        self.assertAlmostEqual(credit["demo_call"], 500.0)

    def test_four_touchpoints_40_20_40(self):
        credit = u_shaped(FOUR_TOUCH_DEAL)
        self.assertAlmostEqual(credit["linkedin_ads"], 400.0)
        self.assertAlmostEqual(credit["demo_call"], 400.0)
        self.assertAlmostEqual(credit["webinar"], 100.0)
        self.assertAlmostEqual(credit["outbound_email"], 100.0)
        self.assertAlmostEqual(sum(credit.values()), 1000.0)


class TestTimeDecay(unittest.TestCase):

    def test_more_recent_touch_gets_more_credit(self):
        deal = Deal(
            deal_id="d", amount=300.0, closed_won=True, close_date_iso="2026-07-01T00:00:00+00:00",
            touchpoints=(
                Touchpoint("first_channel", "c1", "2026-06-24T00:00:00+00:00"),  # 7 days before close
                Touchpoint("last_channel", "c2", "2026-07-01T00:00:00+00:00"),   # 0 days before close
            ),
        )
        credit = time_decay(deal, half_life_days=7.0)
        # weight(0d)=1.0, weight(7d)=0.5 -> normalized 2/3 and 1/3 of $300
        self.assertAlmostEqual(credit["last_channel"], 200.0, places=2)
        self.assertAlmostEqual(credit["first_channel"], 100.0, places=2)

    def test_credits_sum_to_deal_amount(self):
        credit = time_decay(FOUR_TOUCH_DEAL)
        self.assertAlmostEqual(sum(credit.values()), 1000.0)

    def test_non_positive_half_life_raises(self):
        with self.assertRaises(ValueError):
            time_decay(TWO_TOUCH_DEAL, half_life_days=0)


class TestAttributeDispatch(unittest.TestCase):

    def test_returns_attribution_result(self):
        result = attribute(FOUR_TOUCH_DEAL, "linear")
        self.assertEqual(result.deal_id, "d4")
        self.assertEqual(result.model, "linear")

    def test_invalid_model_raises(self):
        with self.assertRaises(ValueError):
            attribute(FOUR_TOUCH_DEAL, "magic")

    def test_all_five_models_are_dispatchable(self):
        for model in ("first_touch", "last_touch", "linear", "u_shaped", "time_decay"):
            with self.subTest(model=model):
                result = attribute(FOUR_TOUCH_DEAL, model)
                self.assertAlmostEqual(sum(result.channel_credit.values()), 1000.0)


if __name__ == "__main__":
    unittest.main()
