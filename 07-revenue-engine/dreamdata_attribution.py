"""Dreamdata adapter — deal + touchpoint read side for attribution modeling.

Parses Dreamdata-shaped deal/event rows into Deal (with its Touchpoint
history attached) so attribution.py can run any of the five models over it.

EGRESS POLICY (mirrors 04-revops-engine/hubspot_crm.py): no network I/O at
import time; the client is injected, never imported at module top-level.

DREAMDATA API SHAPE (illustrative — Dreamdata's public docs use a similar
deal + touchpoint-event model):
  GET /deals/{deal_id}
  Response: {"id": ..., "amount": ..., "stage": ..., "close_date": ...}

  GET /deals/{deal_id}/touchpoints
  Response: {"events": [{"channel": ..., "campaign": ..., "timestamp": ...}, ...]}

  The injected client must expose:
      client.get_deal(deal_id: str) -> dict
      client.get_touchpoints(deal_id: str) -> list[dict]
"""

from __future__ import annotations

from typing import Any

from revenue_schema import Deal, Touchpoint

_WON_STAGES: frozenset[str] = frozenset({"closed_won", "won"})


def row_to_touchpoint(row: dict[str, Any]) -> Touchpoint:
    """Map one Dreamdata touchpoint-event row to a Touchpoint. PURE — no network."""
    return Touchpoint(
        channel=(row.get("channel") or "").strip().lower(),
        campaign=(row.get("campaign") or "").strip(),
        timestamp_iso=row.get("timestamp") or "",
    )


def parse_touchpoints(rows: list[dict[str, Any]]) -> tuple[Touchpoint, ...]:
    """Convert a batch of Dreamdata touchpoint-event rows into Touchpoints,
    sorted chronologically so attribution models can rely on ordering."""
    touchpoints = [row_to_touchpoint(r) for r in rows]
    return tuple(sorted(touchpoints, key=lambda tp: tp.timestamp_iso))


def row_to_deal(deal_row: dict[str, Any], touchpoint_rows: list[dict[str, Any]]) -> Deal:
    """Map a Dreamdata deal row + its touchpoint-event rows to a Deal.

    PURE — no network.

    Raises:
        ValueError: if `id` is missing — a deal without an id can't be
            attributed or logged as a revenue outcome.
    """
    deal_id = str(deal_row.get("id") or "")
    if not deal_id:
        raise ValueError(f"Dreamdata deal row missing 'id': {deal_row!r}")

    stage = (deal_row.get("stage") or "").strip().lower()
    return Deal(
        deal_id=deal_id,
        amount=float(deal_row.get("amount", 0)),
        closed_won=stage in _WON_STAGES,
        close_date_iso=deal_row.get("close_date") or "",
        touchpoints=parse_touchpoints(touchpoint_rows),
    )


def fetch_deal(client: Any, deal_id: str) -> Deal:
    """Fetch one deal + its touchpoint history via the injected client.

    FAIL LOUD: read failures raise RuntimeError — attribution run against a
    silently-empty deal would misreport revenue as unattributed.
    """
    try:
        deal_row: dict[str, Any] = client.get_deal(deal_id=deal_id)
        touchpoint_rows: list[dict[str, Any]] = list(client.get_touchpoints(deal_id=deal_id))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Dreamdata fetch_deal failed [deal_id={deal_id}]: {exc}") from exc
    return row_to_deal(deal_row, touchpoint_rows)


class FakeDreamdataClient:
    """Returns canned deal/touchpoint rows instead of calling the real Dreamdata API."""

    def __init__(
        self,
        deals_by_id: dict[str, dict[str, Any]] | None = None,
        touchpoints_by_deal_id: dict[str, list[dict[str, Any]]] | None = None,
        raise_on_get: bool = False,
    ) -> None:
        self._deals_by_id = deals_by_id or {}
        self._touchpoints_by_deal_id = touchpoints_by_deal_id or {}
        self._raise_get = raise_on_get
        self.get_deal_calls: list[str] = []

    def get_deal(self, deal_id: str) -> dict[str, Any]:
        self.get_deal_calls.append(deal_id)
        if self._raise_get:
            raise RuntimeError("Simulated Dreamdata deal API error")
        return self._deals_by_id.get(deal_id, {})

    def get_touchpoints(self, deal_id: str) -> list[dict[str, Any]]:
        if self._raise_get:
            raise RuntimeError("Simulated Dreamdata touchpoints API error")
        return list(self._touchpoints_by_deal_id.get(deal_id, []))


if __name__ == "__main__":
    client = FakeDreamdataClient(
        deals_by_id={
            "deal-1001": {
                "id": "deal-1001", "amount": 48000, "stage": "closed_won",
                "close_date": "2026-07-01T00:00:00+00:00",
            },
        },
        touchpoints_by_deal_id={
            "deal-1001": [
                {"channel": "webinar", "campaign": "q2-procurement-series", "timestamp": "2026-06-15T00:00:00+00:00"},
                {"channel": "linkedin_ads", "campaign": "abm-tier1", "timestamp": "2026-06-01T00:00:00+00:00"},
            ],
        },
    )

    print("dreamdata_attribution demo (FakeDreamdataClient — zero egress):\n")
    deal = fetch_deal(client, "deal-1001")
    print(f"  Deal: {deal.deal_id}, ${deal.amount:,.2f}, closed_won={deal.closed_won}")
    print("  Touchpoints (sorted chronologically):")
    for tp in deal.touchpoints:
        print(f"    {tp.timestamp_iso}  {tp.channel:14s}  {tp.campaign}")

    print(f"\n  get_deal called {len(client.get_deal_calls)} time(s).")
    print("  No network I/O occurred.")
