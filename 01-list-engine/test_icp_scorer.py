"""Tests for the ICP scorer. The framework is only real if it's falsifiable.

Stdlib `unittest` — no install needed (runs air-gapped). pytest discovers these
too if you have it:
    python3 01-list-engine/test_icp_scorer.py    # stdlib
    python3 -m pytest 01-list-engine             # if pytest installed
"""

import unittest

from icp_schema import Account, ICPProfile
from icp_scorer import rank, score_account

PROFILE = ICPProfile(
    name="test ICP",
    target_industries=frozenset({"software", "saas", "fintech"}),
    employee_min=50,
    employee_max=1000,
    target_tech=frozenset({"hubspot", "salesforce", "clay"}),
)

STRONG = Account("Strong", "software", 320,
                 frozenset({"hubspot", "clay"}),
                 frozenset({"job_change", "hiring"}), fit=0.9)
WEAK = Account("Weak", "food", 8, frozenset(), frozenset(), fit=0.1)


class TestIcpScorer(unittest.TestCase):

    def test_strong_account_is_tier_a(self):
        s = score_account(STRONG, PROFILE)
        self.assertEqual(s.tier, "A")
        self.assertGreater(s.score, 90)

    def test_weak_account_is_tier_d(self):
        s = score_account(WEAK, PROFILE)
        self.assertEqual(s.tier, "D")
        self.assertLess(s.score, 10)

    def test_signal_dimension_is_capped_at_weight(self):
        one = Account("One", "software", 100, frozenset(), frozenset({"job_change"}))
        many = Account("Many", "software", 100, frozenset(),
                       frozenset({"job_change", "hiring", "website_visit",
                                  "funding", "tech_change"}))
        # job_change alone saturates the dimension; five signals can't exceed it.
        self.assertEqual(score_account(one, PROFILE).breakdown["signal"], 30.0)
        self.assertEqual(score_account(many, PROFILE).breakdown["signal"], 30.0)

    def test_top_signal_is_the_strongest_present(self):
        a = Account("A", "saas", 100, frozenset(), frozenset({"funding", "job_change"}))
        self.assertEqual(score_account(a, PROFILE).top_signal, "job_change")

    def test_adjacent_employee_band_scores_half(self):
        # 1500 is outside [50,1000] but within 2x → half credit on the band.
        a = Account("Big", "software", 1500, frozenset(), frozenset())
        # firmographic = 0.6*industry(1) + 0.4*band(0.5) = 0.8 → 0.8 * 40 = 32.0
        self.assertEqual(score_account(a, PROFILE).breakdown["firmographic"], 32.0)

    def test_neutral_technographic_when_no_target_tech(self):
        p = ICPProfile("no-tech", frozenset({"software"}), 50, 1000, frozenset())
        a = Account("A", "software", 100, frozenset({"anything"}), frozenset())
        self.assertEqual(score_account(a, p).breakdown["technographic"], 10.0)

    def test_weights_must_sum_to_100(self):
        with self.assertRaises(ValueError):
            ICPProfile("bad", frozenset({"x"}), 1, 10,
                       weights={"firmographic": 50, "technographic": 20,
                                "signal": 20, "fit": 5})  # sums to 95

    def test_employee_min_max_validated(self):
        with self.assertRaises(ValueError):
            ICPProfile("bad", frozenset({"x"}), 1000, 50)

    def test_rank_orders_best_first(self):
        ranked = rank([WEAK, STRONG], PROFILE)
        self.assertEqual([r.name for r in ranked], ["Strong", "Weak"])

    def test_scoring_is_deterministic(self):
        self.assertEqual(score_account(STRONG, PROFILE), score_account(STRONG, PROFILE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
