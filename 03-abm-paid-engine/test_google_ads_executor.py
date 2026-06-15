"""Unit tests for google_ads_executor.py.

Stdlib unittest only — zero third-party packages required.
All tests run air-gapped; FakeGoogleClient records calls without any network I/O.
"""

from __future__ import annotations

import unittest

from executor import ExecResult, PaidOp, SET_BUDGET, PAUSE, NO_OP
from google_ads_executor import (
    FakeGoogleClient,
    GoogleAdsExecutor,
    MICROS_PER_UNIT,
    _PAUSED_STATUS,
    build_budget_payload,
    build_pause_payload,
    dollars_to_micros,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

CUSTOMER_ID = "123-456-7890"
REGISTRY = {
    "LI-ABM":        ("budgets/101", "campaigns/201"),
    "Meta-broad":    ("budgets/102", "campaigns/202"),
    "Meta-retarget": ("budgets/103", "campaigns/203"),
}


def _executor(raise_on: str = "") -> tuple[GoogleAdsExecutor, FakeGoogleClient]:
    client = FakeGoogleClient(raise_on_campaign=raise_on)
    ex = GoogleAdsExecutor(
        client=client,
        customer_id=CUSTOMER_ID,
        campaign_registry=REGISTRY,
    )
    return ex, client


def _op(kind: str, campaign: str = "LI-ABM", value: float | None = None) -> PaidOp:
    return PaidOp(kind=kind, campaign=campaign, value=value, reason="test")


# ---------------------------------------------------------------------------
# Pure helper tests — no executor needed.
# ---------------------------------------------------------------------------


class TestDollarsToMicros(unittest.TestCase):
    def test_one_dollar(self) -> None:
        self.assertEqual(dollars_to_micros(1.0), MICROS_PER_UNIT)

    def test_zero(self) -> None:
        self.assertEqual(dollars_to_micros(0.0), 0)

    def test_fractional(self) -> None:
        # $0.50 → 500_000
        self.assertEqual(dollars_to_micros(0.50), 500_000)

    def test_rounds_to_nearest(self) -> None:
        # $0.0000001 is sub-micro; should round to 0
        self.assertEqual(dollars_to_micros(0.0000001), 0)

    def test_negative_raises(self) -> None:
        with self.assertRaises(ValueError):
            dollars_to_micros(-1.0)

    def test_large_budget(self) -> None:
        self.assertEqual(dollars_to_micros(1000.0), 1_000_000_000)


class TestBuildBudgetPayload(unittest.TestCase):
    def test_shape(self) -> None:
        p = build_budget_payload("my-campaign", 5_000_000)
        self.assertEqual(p["campaign_id"], "my-campaign")
        self.assertEqual(p["budget_micros"], 5_000_000)

    def test_zero_micros_allowed(self) -> None:
        p = build_budget_payload("camp", 0)
        self.assertEqual(p["budget_micros"], 0)

    def test_negative_micros_raise(self) -> None:
        with self.assertRaises(ValueError):
            build_budget_payload("camp", -1)


class TestBuildPausePayload(unittest.TestCase):
    def test_shape(self) -> None:
        p = build_pause_payload("camp-123")
        self.assertEqual(p["campaign_id"], "camp-123")
        self.assertEqual(p["status"], _PAUSED_STATUS)

    def test_status_string(self) -> None:
        self.assertEqual(build_pause_payload("x")["status"], "PAUSED")


# ---------------------------------------------------------------------------
# GoogleAdsExecutor — NO_OP
# ---------------------------------------------------------------------------


class TestNoOp(unittest.TestCase):
    def test_no_op_returns_ok_no_calls(self) -> None:
        ex, client = _executor()
        op = _op(NO_OP, "LI-ABM", value=None)
        res = ex.apply(op)

        self.assertTrue(res.ok)
        self.assertIn("no-op", res.message)
        self.assertEqual(client.budget_calls, [])
        self.assertEqual(client.status_calls, [])

    def test_no_op_unregistered_campaign_still_ok(self) -> None:
        # NO_OP never touches the registry — it should succeed even for unknown campaigns.
        ex, client = _executor()
        op = _op(NO_OP, "Ghost-Campaign")
        res = ex.apply(op)
        self.assertTrue(res.ok)


# ---------------------------------------------------------------------------
# GoogleAdsExecutor — SET_BUDGET
# ---------------------------------------------------------------------------


class TestSetBudget(unittest.TestCase):
    def test_calls_mutate_budget(self) -> None:
        ex, client = _executor()
        op = _op(SET_BUDGET, "LI-ABM", value=125.0)
        res = ex.apply(op)

        self.assertTrue(res.ok)
        self.assertEqual(len(client.budget_calls), 1)
        cid, budget_rid, micros = client.budget_calls[0]
        self.assertEqual(cid, CUSTOMER_ID)
        self.assertEqual(budget_rid, "budgets/101")
        self.assertEqual(micros, dollars_to_micros(125.0))

    def test_message_contains_dollars_and_micros(self) -> None:
        ex, _ = _executor()
        res = ex.apply(_op(SET_BUDGET, "Meta-broad", value=80.0))
        self.assertIn("$80.00", res.message)
        self.assertIn("micros", res.message)

    def test_set_budget_none_value_returns_error(self) -> None:
        ex, client = _executor()
        op = PaidOp(SET_BUDGET, "LI-ABM", None, "test")
        res = ex.apply(op)
        self.assertFalse(res.ok)
        self.assertEqual(client.budget_calls, [])

    def test_unknown_campaign_returns_error(self) -> None:
        ex, client = _executor()
        op = _op(SET_BUDGET, "Unknown-Camp", value=50.0)
        res = ex.apply(op)
        self.assertFalse(res.ok)
        self.assertIn("not in registry", res.message)
        self.assertEqual(client.budget_calls, [])

    def test_api_error_caught_returns_error_result(self) -> None:
        ex, client = _executor(raise_on="budgets/101")
        op = _op(SET_BUDGET, "LI-ABM", value=50.0)
        res = ex.apply(op)
        self.assertFalse(res.ok)
        self.assertIn("mutate_campaign_budget error", res.message)

    def test_all_registered_campaigns_set_budget(self) -> None:
        ex, client = _executor()
        for name in REGISTRY:
            ex.apply(_op(SET_BUDGET, name, value=100.0))
        self.assertEqual(len(client.budget_calls), 3)


# ---------------------------------------------------------------------------
# GoogleAdsExecutor — PAUSE
# ---------------------------------------------------------------------------


class TestPause(unittest.TestCase):
    def test_calls_mutate_status(self) -> None:
        ex, client = _executor()
        op = _op(PAUSE, "Meta-retarget")
        res = ex.apply(op)

        self.assertTrue(res.ok)
        self.assertEqual(len(client.status_calls), 1)
        cid, camp_rid, status = client.status_calls[0]
        self.assertEqual(cid, CUSTOMER_ID)
        self.assertEqual(camp_rid, "campaigns/203")
        self.assertEqual(status, "PAUSED")

    def test_message_contains_paused(self) -> None:
        ex, _ = _executor()
        res = ex.apply(_op(PAUSE, "LI-ABM"))
        self.assertIn("PAUSED", res.message)

    def test_pause_unknown_campaign_returns_error(self) -> None:
        ex, client = _executor()
        res = ex.apply(_op(PAUSE, "Ghost"))
        self.assertFalse(res.ok)
        self.assertEqual(client.status_calls, [])

    def test_api_error_caught_returns_error_result(self) -> None:
        ex, client = _executor(raise_on="campaigns/203")
        op = _op(PAUSE, "Meta-retarget")
        res = ex.apply(op)
        self.assertFalse(res.ok)
        self.assertIn("mutate_campaign_status error", res.message)

    def test_no_budget_call_on_pause(self) -> None:
        ex, client = _executor()
        ex.apply(_op(PAUSE, "LI-ABM"))
        self.assertEqual(client.budget_calls, [])


# ---------------------------------------------------------------------------
# GoogleAdsExecutor — unknown op kind
# ---------------------------------------------------------------------------


class TestUnknownKind(unittest.TestCase):
    def test_unknown_kind_returns_error_no_calls(self) -> None:
        ex, client = _executor()
        op = PaidOp("TURBO_BOOST", "LI-ABM", 99.0, "test")
        res = ex.apply(op)
        self.assertFalse(res.ok)
        self.assertIn("unknown op kind", res.message)
        self.assertEqual(client.budget_calls, [])
        self.assertEqual(client.status_calls, [])


# ---------------------------------------------------------------------------
# ExecResult contract
# ---------------------------------------------------------------------------


class TestExecResultContract(unittest.TestCase):
    def test_result_carries_op(self) -> None:
        ex, _ = _executor()
        op = _op(NO_OP)
        res = ex.apply(op)
        self.assertIs(res.op, op)

    def test_result_is_execresult(self) -> None:
        ex, _ = _executor()
        res = ex.apply(_op(PAUSE, "LI-ABM"))
        self.assertIsInstance(res, ExecResult)


# ---------------------------------------------------------------------------
# FakeGoogleClient isolation tests
# ---------------------------------------------------------------------------


class TestFakeGoogleClient(unittest.TestCase):
    def test_budget_call_recorded(self) -> None:
        c = FakeGoogleClient()
        c.mutate_campaign_budget("cid", "brid", 1_000_000)
        self.assertEqual(c.budget_calls, [("cid", "brid", 1_000_000)])

    def test_status_call_recorded(self) -> None:
        c = FakeGoogleClient()
        c.mutate_campaign_status("cid", "campid", "PAUSED")
        self.assertEqual(c.status_calls, [("cid", "campid", "PAUSED")])

    def test_raise_on_campaign_budget(self) -> None:
        c = FakeGoogleClient(raise_on_campaign="budgets/101")
        with self.assertRaises(RuntimeError):
            c.mutate_campaign_budget("cid", "budgets/101", 500)

    def test_raise_on_campaign_status(self) -> None:
        c = FakeGoogleClient(raise_on_campaign="campaigns/201")
        with self.assertRaises(RuntimeError):
            c.mutate_campaign_status("cid", "campaigns/201", "PAUSED")

    def test_no_raise_on_different_campaign(self) -> None:
        c = FakeGoogleClient(raise_on_campaign="budgets/999")
        # Should not raise for a different budget_resource_id
        c.mutate_campaign_budget("cid", "budgets/101", 500)
        self.assertEqual(len(c.budget_calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
