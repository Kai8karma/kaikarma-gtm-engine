"""Tests for the Dreamdata deal/touchpoint adapter.

    python3 07-revenue-engine/test_dreamdata_attribution.py
"""

from __future__ import annotations

import unittest

from dreamdata_attribution import (
    FakeDreamdataClient,
    fetch_deal,
    parse_touchpoints,
    row_to_deal,
    row_to_touchpoint,
)

DEAL_ROW = {
    "id": "deal-1001", "amount": 48000, "stage": "closed_won",
    "close_date": "2026-07-01T00:00:00+00:00",
}
TOUCHPOINT_ROWS = [
    {"channel": "webinar", "campaign": "q2", "timestamp": "2026-06-15T00:00:00+00:00"},
    {"channel": "linkedin_ads", "campaign": "abm", "timestamp": "2026-06-01T00:00:00+00:00"},
]


class TestRowToTouchpoint(unittest.TestCase):

    def test_maps_fields_lowercased(self):
        tp = row_to_touchpoint({"channel": "LinkedIn_Ads", "campaign": "abm", "timestamp": "2026-06-01T00:00:00+00:00"})
        self.assertEqual(tp.channel, "linkedin_ads")


class TestParseTouchpoints(unittest.TestCase):

    def test_sorts_chronologically(self):
        touchpoints = parse_touchpoints(TOUCHPOINT_ROWS)
        self.assertEqual([tp.channel for tp in touchpoints], ["linkedin_ads", "webinar"])


class TestRowToDeal(unittest.TestCase):

    def test_maps_fields(self):
        deal = row_to_deal(DEAL_ROW, TOUCHPOINT_ROWS)
        self.assertEqual(deal.deal_id, "deal-1001")
        self.assertEqual(deal.amount, 48000.0)
        self.assertTrue(deal.closed_won)
        self.assertEqual(len(deal.touchpoints), 2)

    def test_open_stage_is_not_closed_won(self):
        deal = row_to_deal({**DEAL_ROW, "stage": "open"}, [])
        self.assertFalse(deal.closed_won)

    def test_won_stage_variant_recognized(self):
        deal = row_to_deal({**DEAL_ROW, "stage": "won"}, [])
        self.assertTrue(deal.closed_won)

    def test_missing_id_raises(self):
        with self.assertRaises(ValueError):
            row_to_deal({k: v for k, v in DEAL_ROW.items() if k != "id"}, [])


class TestFakeClientRoundTrip(unittest.TestCase):

    def test_fetch_deal_returns_parsed_deal_with_touchpoints(self):
        client = FakeDreamdataClient(
            deals_by_id={"deal-1001": DEAL_ROW},
            touchpoints_by_deal_id={"deal-1001": TOUCHPOINT_ROWS},
        )
        deal = fetch_deal(client, "deal-1001")
        self.assertEqual(deal.deal_id, "deal-1001")
        self.assertEqual(len(deal.touchpoints), 2)
        self.assertEqual(client.get_deal_calls, ["deal-1001"])

    def test_fetch_raises_on_client_error(self):
        client = FakeDreamdataClient(
            deals_by_id={"deal-1001": DEAL_ROW},
            touchpoints_by_deal_id={"deal-1001": TOUCHPOINT_ROWS},
            raise_on_get=True,
        )
        with self.assertRaises(RuntimeError):
            fetch_deal(client, "deal-1001")


if __name__ == "__main__":
    unittest.main()
