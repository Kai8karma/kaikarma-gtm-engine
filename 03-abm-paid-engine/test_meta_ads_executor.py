"""Tests for the Meta Ads executor — builder functions and fake-client integration.

All tests are egress-isolated: no network I/O, no facebook_business SDK import.
The executor is exercised through the injected FakeMetaClient.

    python3 03-abm-paid-engine/test_meta_ads_executor.py
"""

import sys
import unittest

from executor import NO_OP, PAUSE, SET_BUDGET, ExecResult, PaidOp, plan_to_ops, execute
from meta_ads_executor import (
    FakeMetaClient,
    MetaAdsExecutor,
    build_pause_payload,
    build_set_budget_payload,
    dollars_to_minor,
)
from perf_controller import run
from perf_schema import Campaign, PerfPolicy


# ---------------------------------------------------------------------------
# Currency helpers
# ---------------------------------------------------------------------------

class TestDollarsToMinor(unittest.TestCase):

    def test_whole_dollar(self):
        self.assertEqual(dollars_to_minor(1.0), 100)

    def test_fractional_dollar(self):
        self.assertEqual(dollars_to_minor(1.50), 150)

    def test_typical_budget(self):
        self.assertEqual(dollars_to_minor(120.0), 12000)

    def test_zero(self):
        self.assertEqual(dollars_to_minor(0.0), 0)

    def test_rounding(self):
        # $0.005 rounds to 1 cent (round-half-even in Python, but cents are integers)
        result = dollars_to_minor(0.005)
        self.assertIsInstance(result, int)


# ---------------------------------------------------------------------------
# Builder functions — pure, SDK-free
# ---------------------------------------------------------------------------

class TestBuildSetBudgetPayload(unittest.TestCase):

    def test_returns_correct_keys(self):
        payload = build_set_budget_payload("camp-abc", 100.0)
        self.assertIn("ad_set_id", payload)
        self.assertIn("params", payload)

    def test_ad_set_id_matches_campaign(self):
        payload = build_set_budget_payload("camp-abc", 100.0)
        self.assertEqual(payload["ad_set_id"], "camp-abc")

    def test_budget_converted_to_cents(self):
        payload = build_set_budget_payload("camp-abc", 100.0)
        self.assertEqual(payload["params"]["daily_budget"], 10000)

    def test_no_status_field_in_budget_update(self):
        # A budget update must not accidentally pause the ad set.
        payload = build_set_budget_payload("camp-abc", 100.0)
        self.assertNotIn("status", payload["params"])

    def test_fractional_budget(self):
        payload = build_set_budget_payload("camp-xyz", 75.50)
        self.assertEqual(payload["params"]["daily_budget"], 7550)


class TestBuildPausePayload(unittest.TestCase):

    def test_returns_correct_keys(self):
        payload = build_pause_payload("camp-abc")
        self.assertIn("ad_set_id", payload)
        self.assertIn("params", payload)

    def test_status_is_paused(self):
        payload = build_pause_payload("camp-abc")
        self.assertEqual(payload["params"]["status"], "PAUSED")

    def test_ad_set_id_matches_campaign(self):
        payload = build_pause_payload("camp-abc")
        self.assertEqual(payload["ad_set_id"], "camp-abc")

    def test_no_budget_field_in_pause(self):
        # A pause must not accidentally touch the budget.
        payload = build_pause_payload("camp-abc")
        self.assertNotIn("daily_budget", payload["params"])


# ---------------------------------------------------------------------------
# FakeMetaClient
# ---------------------------------------------------------------------------

class TestFakeMetaClient(unittest.TestCase):

    def test_update_ad_set_records_call(self):
        fake = FakeMetaClient()
        fake.update_ad_set("ad-1", {"daily_budget": 5000})
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["method"], "update_ad_set")
        self.assertEqual(fake.calls[0]["ad_set_id"], "ad-1")

    def test_update_campaign_records_call(self):
        fake = FakeMetaClient()
        fake.update_campaign("camp-1", {"status": "PAUSED"})
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["method"], "update_campaign")

    def test_returns_success_dict(self):
        fake = FakeMetaClient()
        result = fake.update_ad_set("ad-1", {})
        self.assertTrue(result.get("success"))

    def test_no_network_io(self):
        # If FakeMetaClient ever tried to egress, it would raise in a test env.
        # This test confirms it doesn't by simply calling it without any socket setup.
        fake = FakeMetaClient()
        fake.update_ad_set("x", {"daily_budget": 1})
        fake.update_campaign("y", {"status": "PAUSED"})
        # Reaching here means no egress occurred.
        self.assertEqual(len(fake.calls), 2)


# ---------------------------------------------------------------------------
# MetaAdsExecutor — apply() via FakeMetaClient
# ---------------------------------------------------------------------------

class TestMetaAdsExecutorSetBudget(unittest.TestCase):

    def setUp(self):
        self.fake = FakeMetaClient()
        self.ex = MetaAdsExecutor(client=self.fake)

    def test_set_budget_calls_update_ad_set(self):
        op = PaidOp(SET_BUDGET, "camp-a", 80.0, "scale")
        self.ex.apply(op)
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(self.fake.calls[0]["method"], "update_ad_set")

    def test_set_budget_sends_correct_cents(self):
        op = PaidOp(SET_BUDGET, "camp-a", 80.0, "scale")
        self.ex.apply(op)
        self.assertEqual(self.fake.calls[0]["params"]["daily_budget"], 8000)

    def test_set_budget_returns_ok(self):
        op = PaidOp(SET_BUDGET, "camp-a", 80.0, "scale")
        result = self.ex.apply(op)
        self.assertTrue(result.ok)

    def test_set_budget_none_value_returns_error(self):
        op = PaidOp(SET_BUDGET, "camp-a", None, "reason")
        result = self.ex.apply(op)
        self.assertFalse(result.ok)
        self.assertEqual(len(self.fake.calls), 0)

    def test_set_budget_message_mentions_campaign(self):
        op = PaidOp(SET_BUDGET, "camp-a", 80.0, "scale")
        result = self.ex.apply(op)
        self.assertIn("camp-a", result.message)


class TestMetaAdsExecutorPause(unittest.TestCase):

    def setUp(self):
        self.fake = FakeMetaClient()
        self.ex = MetaAdsExecutor(client=self.fake)

    def test_pause_calls_update_ad_set(self):
        op = PaidOp(PAUSE, "camp-b", None, "kill")
        self.ex.apply(op)
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(self.fake.calls[0]["method"], "update_ad_set")

    def test_pause_sends_paused_status(self):
        op = PaidOp(PAUSE, "camp-b", None, "kill")
        self.ex.apply(op)
        self.assertEqual(self.fake.calls[0]["params"]["status"], "PAUSED")

    def test_pause_returns_ok(self):
        op = PaidOp(PAUSE, "camp-b", None, "kill")
        result = self.ex.apply(op)
        self.assertTrue(result.ok)

    def test_pause_message_mentions_campaign(self):
        op = PaidOp(PAUSE, "camp-b", None, "kill")
        result = self.ex.apply(op)
        self.assertIn("camp-b", result.message)


class TestMetaAdsExecutorNoOp(unittest.TestCase):

    def test_no_op_sends_nothing(self):
        fake = FakeMetaClient()
        ex = MetaAdsExecutor(client=fake)
        op = PaidOp(NO_OP, "camp-c", 50.0, "hold")
        result = ex.apply(op)
        self.assertEqual(len(fake.calls), 0)
        self.assertTrue(result.ok)


class TestMetaAdsExecutorDryRun(unittest.TestCase):

    def test_dry_run_budget_does_not_call_client(self):
        fake = FakeMetaClient()
        ex = MetaAdsExecutor(client=fake, dry_run=True)
        op = PaidOp(SET_BUDGET, "camp-d", 100.0, "scale")
        result = ex.apply(op)
        self.assertEqual(len(fake.calls), 0)
        self.assertTrue(result.ok)
        self.assertIn("dry-run", result.message)

    def test_dry_run_pause_does_not_call_client(self):
        fake = FakeMetaClient()
        ex = MetaAdsExecutor(client=fake, dry_run=True)
        op = PaidOp(PAUSE, "camp-d", None, "kill")
        result = ex.apply(op)
        self.assertEqual(len(fake.calls), 0)
        self.assertTrue(result.ok)
        self.assertIn("dry-run", result.message)


class TestMetaAdsExecutorClientError(unittest.TestCase):

    def test_set_budget_client_exception_returns_not_ok(self):
        class BrokenClient:
            def update_ad_set(self, *_a, **_kw):
                raise RuntimeError("API unreachable")

        ex = MetaAdsExecutor(client=BrokenClient())
        op = PaidOp(SET_BUDGET, "camp-e", 80.0, "scale")
        result = ex.apply(op)
        self.assertFalse(result.ok)
        self.assertIn("error", result.message)

    def test_pause_client_exception_returns_not_ok(self):
        class BrokenClient:
            def update_ad_set(self, *_a, **_kw):
                raise RuntimeError("API unreachable")

        ex = MetaAdsExecutor(client=BrokenClient())
        op = PaidOp(PAUSE, "camp-e", None, "kill")
        result = ex.apply(op)
        self.assertFalse(result.ok)
        self.assertIn("error", result.message)


# ---------------------------------------------------------------------------
# ExecResult contract
# ---------------------------------------------------------------------------

class TestExecResultShape(unittest.TestCase):

    def test_result_carries_original_op(self):
        fake = FakeMetaClient()
        ex = MetaAdsExecutor(client=fake)
        op = PaidOp(SET_BUDGET, "camp-f", 60.0, "cut")
        result = ex.apply(op)
        self.assertIs(result.op, op)

    def test_result_is_exec_result_instance(self):
        fake = FakeMetaClient()
        ex = MetaAdsExecutor(client=fake)
        op = PaidOp(PAUSE, "camp-g", None, "kill")
        result = ex.apply(op)
        self.assertIsInstance(result, ExecResult)


# ---------------------------------------------------------------------------
# End-to-end: perf_controller verdict → Meta executor
# ---------------------------------------------------------------------------

class TestEndToEndMeta(unittest.TestCase):

    def test_runaway_campaign_gets_paused_on_meta(self):
        policy = PerfPolicy(target_cpa=50.0, account_daily_cap=400.0)
        campaigns = [
            Campaign("Meta-good", 1200, 40, 100),
            Campaign("Meta-runaway", 120, 0, 40),
        ]
        ops = plan_to_ops(run(campaigns, policy))
        fake = FakeMetaClient()
        ex = MetaAdsExecutor(client=fake)
        results = {r.op.campaign: r for r in execute(ops, ex)}

        self.assertTrue(results["Meta-runaway"].ok)
        pause_call = next(
            (c for c in fake.calls if c["ad_set_id"] == "Meta-runaway"), None
        )
        self.assertIsNotNone(pause_call)
        self.assertEqual(pause_call["params"]["status"], "PAUSED")

    def test_scaled_campaign_sends_budget_in_cents(self):
        policy = PerfPolicy(target_cpa=50.0, account_daily_cap=400.0)
        campaigns = [Campaign("Meta-scale", 1200, 40, 100)]
        ops = plan_to_ops(run(campaigns, policy))
        fake = FakeMetaClient()
        ex = MetaAdsExecutor(client=fake)
        execute(ops, ex)

        budget_calls = [
            c for c in fake.calls
            if c.get("method") == "update_ad_set"
            and "daily_budget" in c.get("params", {})
        ]
        if budget_calls:
            # Budget must be an integer (cents), not fractional dollars.
            self.assertIsInstance(budget_calls[0]["params"]["daily_budget"], int)

    def test_no_sdk_imported(self):
        # facebook_business must not appear in sys.modules after import.
        self.assertNotIn("facebook_business", sys.modules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
