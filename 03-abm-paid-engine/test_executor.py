"""Tests for the execution boundary — mapping + dry-run, provably zero-egress.

    python3 03-abm-paid-engine/test_executor.py
"""

import unittest

from executor import (
    NO_OP,
    PAUSE,
    SET_BUDGET,
    DryRunExecutor,
    GoogleAdsExecutor,
    PaidOp,
    execute,
    plan_to_ops,
)
from perf_controller import run
from perf_schema import CUT, HOLD, KILL, LEARNING, SCALE, Action, Campaign, PerfPolicy


def _action(verdict: str, new_budget: float = 80.0) -> Action:
    return Action("camp", verdict, 100.0, new_budget, 50.0, "reason")


class TestMapping(unittest.TestCase):

    def test_kill_maps_to_pause(self):
        op = plan_to_ops([_action(KILL, 0.0)])[0]
        self.assertEqual(op.kind, PAUSE)
        self.assertIsNone(op.value)

    def test_scale_maps_to_set_budget_with_new_value(self):
        op = plan_to_ops([_action(SCALE, 125.0)])[0]
        self.assertEqual(op.kind, SET_BUDGET)
        self.assertEqual(op.value, 125.0)

    def test_cut_maps_to_set_budget(self):
        self.assertEqual(plan_to_ops([_action(CUT, 75.0)])[0].kind, SET_BUDGET)

    def test_hold_and_learning_are_no_ops(self):
        self.assertEqual(plan_to_ops([_action(HOLD, 100.0)])[0].kind, NO_OP)
        self.assertEqual(plan_to_ops([_action(LEARNING, 30.0)])[0].kind, NO_OP)


class TestDryRun(unittest.TestCase):

    def test_records_all_ops_and_succeeds(self):
        ops = [PaidOp(SET_BUDGET, "a", 120.0, "r"), PaidOp(PAUSE, "b", None, "r")]
        ex = DryRunExecutor()
        results = execute(ops, ex)
        self.assertEqual(len(ex.log), 2)
        self.assertTrue(all(r.ok for r in results))

    def test_message_includes_value_for_set_budget(self):
        ex = DryRunExecutor()
        r = ex.apply(PaidOp(SET_BUDGET, "a", 120.0, "r"))
        self.assertIn("120", r.message)


class TestLiveStub(unittest.TestCase):

    def test_live_executor_refuses_until_implemented(self):
        # An honest stub must NOT silently pretend to work.
        with self.assertRaises(NotImplementedError):
            GoogleAdsExecutor().apply(PaidOp(PAUSE, "a", None, "r"))


class TestEndToEnd(unittest.TestCase):

    def test_runaway_campaign_becomes_a_pause(self):
        policy = PerfPolicy(target_cpa=50.0, account_daily_cap=400.0)
        campaigns = [Campaign("good", 1200, 40, 100), Campaign("runaway", 120, 0, 40)]
        ops = {o.campaign: o for o in plan_to_ops(run(campaigns, policy))}
        self.assertEqual(ops["runaway"].kind, PAUSE)
        self.assertEqual(ops["good"].kind, SET_BUDGET)


if __name__ == "__main__":
    unittest.main(verbosity=2)
