"""Tests for the autonomous paid controller. Hard caps must be provably enforced.

    python3 03-abm-paid-engine/test_perf_controller.py
"""

import unittest

from perf_schema import CUT, HOLD, KILL, LEARNING, SCALE, Campaign, PerfPolicy
from perf_controller import actual_cpa, blended, decide, run

# High cap so per-campaign verdict tests aren't affected by pacing.
P = PerfPolicy(target_cpa=50.0, account_daily_cap=100_000.0)


class TestDecide(unittest.TestCase):

    def test_scale_when_beating_target(self):
        a = decide(Campaign("c", 1200, 40, 100), P)   # cpa 30 → 60% of target
        self.assertEqual(a.verdict, SCALE)
        self.assertEqual(a.new_budget, 125.0)         # +25% max step

    def test_scale_capped_at_max_step(self):
        a = decide(Campaign("c", 400, 40, 100), P)    # cpa 10 → crushing target
        self.assertEqual(a.verdict, SCALE)
        self.assertEqual(a.new_budget, 125.0)         # still only +25%, never more

    def test_hold_on_target(self):
        a = decide(Campaign("c", 2000, 40, 100), P)   # cpa 50 → exactly target
        self.assertEqual(a.verdict, HOLD)
        self.assertEqual(a.new_budget, 100.0)

    def test_cut_when_over_target(self):
        a = decide(Campaign("c", 3200, 40, 100), P)   # cpa 80 → 160% of target
        self.assertEqual(a.verdict, CUT)
        self.assertEqual(a.new_budget, 75.0)          # -25%

    def test_kill_when_far_over_target(self):
        a = decide(Campaign("c", 4400, 40, 100), P)   # cpa 110 → 220% of target
        self.assertEqual(a.verdict, KILL)
        self.assertEqual(a.new_budget, 0.0)

    def test_kill_runaway_zero_conversions(self):
        a = decide(Campaign("c", 120, 0, 40), P)      # 0 conv, spent > 2x target
        self.assertEqual(a.verdict, KILL)
        self.assertEqual(a.new_budget, 0.0)

    def test_learning_phase_is_held_not_optimized(self):
        a = decide(Campaign("c", 200, 8, 30), P)      # only 8 conv < 30
        self.assertEqual(a.verdict, LEARNING)
        self.assertEqual(a.new_budget, 30.0)          # untouched

    def test_zero_conv_low_spend_stays_in_learning(self):
        a = decide(Campaign("c", 40, 0, 20), P)       # 0 conv but spend < kill line
        self.assertEqual(a.verdict, LEARNING)         # given room, not killed
        self.assertEqual(a.new_budget, 20.0)

    def test_actual_cpa_is_inf_with_zero_conversions(self):
        self.assertEqual(actual_cpa(Campaign("c", 100, 0, 10)), float("inf"))


class TestHardCaps(unittest.TestCase):

    def test_account_cap_claws_back_scale_first(self):
        pol = PerfPolicy(target_cpa=50.0, account_daily_cap=200.0)
        cs = [Campaign("scaler", 1200, 40, 100),   # wants +25% → 125
              Campaign("holder", 2000, 40, 100)]   # holds at 100
        out = {a.campaign: a for a in run(cs, pol)}
        self.assertLessEqual(sum(a.new_budget for a in out.values()), 200.0)
        self.assertEqual(out["scaler"].new_budget, 100.0)  # scale clawed back
        self.assertEqual(out["holder"].new_budget, 100.0)  # baseline protected
        self.assertIn("paced to cap", out["scaler"].reason)

    def test_account_cap_trims_proportionally_when_needed(self):
        pol = PerfPolicy(target_cpa=50.0, account_daily_cap=150.0)
        cs = [Campaign("a", 2000, 40, 100),        # hold 100
              Campaign("b", 2000, 40, 100)]        # hold 100  → 200 > 150
        out = run(cs, pol)
        self.assertLessEqual(sum(a.new_budget for a in out), 150.0)
        for a in out:
            self.assertEqual(a.new_budget, 75.0)   # 0.75x proportional trim

    def test_policy_validates_threshold_order(self):
        with self.assertRaises(ValueError):
            PerfPolicy(target_cpa=50, account_daily_cap=100,
                       scale_when_ratio_below=1.6, cut_when_ratio_above=1.5)

    def test_policy_rejects_nonpositive_target(self):
        with self.assertRaises(ValueError):
            PerfPolicy(target_cpa=0, account_daily_cap=100)


class TestBlended(unittest.TestCase):

    def test_blended_cpa_and_roas(self):
        cs = [Campaign("a", 1000, 20, 50, revenue=4000),
              Campaign("b", 1000, 30, 50, revenue=2000)]
        s = blended(cs)
        self.assertEqual(s["blended_cpa"], 40.0)   # 2000 spend / 50 conv
        self.assertEqual(s["roas"], 3.0)           # 6000 rev / 2000 spend

    def test_determinism(self):
        c = Campaign("c", 1200, 40, 100)
        self.assertEqual(decide(c, P), decide(c, P))


if __name__ == "__main__":
    unittest.main(verbosity=2)
