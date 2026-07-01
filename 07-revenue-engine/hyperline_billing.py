"""Hyperline adapter — billing/subscription read side for MRR reporting.

Parses Hyperline-shaped subscription rows into Subscription so
mrr_calculator.compute_mrr_bridge can diff two snapshots.

EGRESS POLICY (mirrors 04-revops-engine/hubspot_crm.py): no network I/O at
import time; the client is injected, never imported at module top-level.

HYPERLINE API SHAPE (illustrative — Hyperline's public docs):
  GET /subscriptions
  Response: {"data": [{"id": ..., "customer_id": ..., "mrr_cents": ..., "status": ...}, ...]}

  Status values map 1:1 onto VALID_SUBSCRIPTION_STATUSES except Hyperline's
  'trial' which normalises to our 'trialing'.

  The injected client must expose:
      client.get_subscriptions(period: str) -> list[dict]
"""

from __future__ import annotations

from typing import Any

from revenue_schema import Subscription

_STATUS_MAP: dict[str, str] = {
    "active": "active",
    "canceled": "canceled",
    "cancelled": "canceled",
    "past_due": "past_due",
    "trial": "trialing",
    "trialing": "trialing",
}


def row_to_subscription(row: dict[str, Any]) -> Subscription:
    """Map one Hyperline subscription row to a Subscription.

    PURE — no network. `mrr_cents` is Hyperline's minor-unit convention;
    converted to a float dollar amount here so downstream math (ARR, churn
    rate) never has to remember the /100.
    """
    raw_status = (row.get("status") or "").strip().lower()
    status = _STATUS_MAP.get(raw_status, "active")
    return Subscription(
        subscription_id=str(row.get("id", "")),
        account_id=str(row.get("customer_id", "")),
        mrr=float(row.get("mrr_cents", 0)) / 100.0,
        status=status,
    )


def parse_subscriptions(rows: list[dict[str, Any]]) -> list[Subscription]:
    """Convert a batch of Hyperline subscription rows into Subscription objects."""
    return [row_to_subscription(r) for r in rows]


def fetch_subscriptions(client: Any, period: str) -> list[Subscription]:
    """Fetch a subscription snapshot for one billing period via the injected client.

    FAIL LOUD: a read failure raises RuntimeError — a silently empty snapshot
    would make every subscription look "new" or "churned" against the prior
    period, corrupting the MRR bridge.
    """
    try:
        rows: list[dict[str, Any]] = list(client.get_subscriptions(period=period))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Hyperline fetch_subscriptions failed [period={period}]: {exc}") from exc
    return parse_subscriptions(rows)


class FakeHyperlineClient:
    """Returns canned subscription rows instead of calling the real Hyperline API."""

    def __init__(
        self,
        rows_by_period: dict[str, list[dict[str, Any]]] | None = None,
        raise_on_get: bool = False,
    ) -> None:
        self._rows_by_period = rows_by_period or {}
        self._raise_get = raise_on_get
        self.get_calls: list[str] = []

    def get_subscriptions(self, period: str) -> list[dict[str, Any]]:
        self.get_calls.append(period)
        if self._raise_get:
            raise RuntimeError("Simulated Hyperline subscriptions API error")
        return list(self._rows_by_period.get(period, []))


if __name__ == "__main__":
    ROWS_BY_PERIOD = {
        "2026-06": [
            {"id": "sub-1", "customer_id": "acct-acme", "mrr_cents": 200000, "status": "active"},
            {"id": "sub-2", "customer_id": "acct-midfin", "mrr_cents": 150000, "status": "active"},
        ],
        "2026-07": [
            {"id": "sub-1", "customer_id": "acct-acme", "mrr_cents": 250000, "status": "active"},
            {"id": "sub-2", "customer_id": "acct-midfin", "mrr_cents": 150000, "status": "cancelled"},
            {"id": "sub-3", "customer_id": "acct-newco", "mrr_cents": 120000, "status": "trial"},
        ],
    }

    client = FakeHyperlineClient(rows_by_period=ROWS_BY_PERIOD)
    print("hyperline_billing demo (FakeHyperlineClient — zero egress):\n")

    prev = fetch_subscriptions(client, "2026-06")
    curr = fetch_subscriptions(client, "2026-07")
    print(f"  {len(prev)} subscription(s) in 2026-06, {len(curr)} in 2026-07")
    for s in curr:
        print(f"    {s}")

    print(f"\n  get_subscriptions called {len(client.get_calls)} time(s).")
    print("  No network I/O occurred.")
