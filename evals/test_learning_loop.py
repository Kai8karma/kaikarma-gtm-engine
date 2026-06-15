"""Regression guard for the learning-loop backtest (see DEC-learning-loop.md).

Locks in the pre-registered finding: the loop must keep beating the
no-learning baseline and drifting weights toward the true drivers. If a change
breaks that, the "measured learning loop" claim has regressed and CI fails.
Deterministic (fixed seeds).

    python3 evals/test_learning_loop.py
"""

import unittest

from learning_loop_eval import DEFAULT_WEIGHTS, DIMS, SEEDS, run_trial


class TestLearningLoop(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.t = [run_trial(s) for s in SEEDS]
        n = len(cls.t)
        cls.baseline = sum(x["baseline"] for x in cls.t) / n
        cls.tuned = sum(x["tuned"] for x in cls.t) / n
        cls.oracle = sum(x["oracle"] for x in cls.t) / n
        cls.w = {d: sum(x["tuned_weights"][d] for x in cls.t) / n for d in DIMS}

    def test_tuned_beats_baseline(self):
        # The loop must help at all — this is the KILL boundary from the DEC.
        self.assertGreater(self.tuned, self.baseline)

    def test_lift_is_at_least_directional(self):
        # Locks in the measured magnitude (≈+0.032) with margin.
        self.assertGreaterEqual(self.tuned - self.baseline, 0.02)

    def test_oracle_is_the_upper_bound(self):
        self.assertGreaterEqual(self.oracle + 1e-9, self.tuned)

    def test_weights_drift_toward_truth(self):
        # firmographic was over-weighted → must fall; fit under-weighted → must rise.
        self.assertLess(self.w["firmographic"], DEFAULT_WEIGHTS["firmographic"])
        self.assertGreater(self.w["fit"], DEFAULT_WEIGHTS["fit"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
