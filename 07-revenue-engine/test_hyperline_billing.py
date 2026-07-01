"""Tests for the Hyperline billing adapter.

    python3 07-revenue-engine/test_hyperline_billing.py
"""

from __future__ import annotations

import unittest

from hyperline_billing import FakeHyperlineClient, fetch_subscriptions, parse_subscriptions, row_to_subscription

ROW = {"id": "sub-1", "customer_id": "acct-acme", "mrr_cents": 200000, "status": "active"}


class TestRowToSubscription(unittest.TestCase):

    def test_maps_fields_and_converts_cents(self):
        s = row_to_subscription(ROW)
        self.assertEqual(s.subscription_id, "sub-1")
        self.assertEqual(s.account_id, "acct-acme")
        self.assertEqual(s.mrr, 2000.0)
        self.assertEqual(s.status, "active")

    def test_trial_normalizes_to_trialing(self):
        s = row_to_subscription({**ROW, "status": "trial"})
        self.assertEqual(s.status, "trialing")

    def test_cancelled_british_spelling_normalizes(self):
        s = row_to_subscription({**ROW, "status": "cancelled"})
        self.assertEqual(s.status, "canceled")

    def test_unknown_status_defaults_to_active(self):
        s = row_to_subscription({**ROW, "status": "weird_status"})
        self.assertEqual(s.status, "active")

    def test_missing_mrr_cents_defaults_zero(self):
        s = row_to_subscription({k: v for k, v in ROW.items() if k != "mrr_cents"})
        self.assertEqual(s.mrr, 0.0)


class TestParseSubscriptions(unittest.TestCase):

    def test_parses_batch_preserving_order(self):
        rows = [ROW, {**ROW, "id": "sub-2"}]
        subs = parse_subscriptions(rows)
        self.assertEqual([s.subscription_id for s in subs], ["sub-1", "sub-2"])


class TestFakeClientRoundTrip(unittest.TestCase):

    def test_fetch_subscriptions_returns_parsed(self):
        client = FakeHyperlineClient(rows_by_period={"2026-07": [ROW]})
        subs = fetch_subscriptions(client, "2026-07")
        self.assertEqual(len(subs), 1)
        self.assertEqual(client.get_calls, ["2026-07"])

    def test_missing_period_returns_empty_list(self):
        client = FakeHyperlineClient(rows_by_period={})
        subs = fetch_subscriptions(client, "2099-01")
        self.assertEqual(subs, [])

    def test_fetch_raises_on_client_error(self):
        client = FakeHyperlineClient(rows_by_period={"2026-07": [ROW]}, raise_on_get=True)
        with self.assertRaises(RuntimeError):
            fetch_subscriptions(client, "2026-07")


if __name__ == "__main__":
    unittest.main()
