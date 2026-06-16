"""Tests for meta_ads_reporting — parse layer and fetch wrapper.

All tests are egress-isolated: no network I/O, no facebook_business SDK import.
parse_campaigns() is exercised with raw dicts; fetch_campaigns() is exercised
through FakeMetaReportingClient.

    python3 03-abm-paid-engine/test_meta_ads_reporting.py
"""

from __future__ import annotations

import sys
import unittest

from meta_ads_reporting import (
    FakeMetaReportingClient,
    fetch_campaigns,
    parse_campaigns,
)
from perf_schema import Campaign


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(
    *,
    campaign_name: str = "Test Campaign",
    spend: str = "100.00",
    daily_budget: str = "5000",
    actions: list | None = None,
    action_values: list | None = None,
) -> dict:
    """Build a minimal valid Insights row. Omit optional lists when None."""
    row: dict = {
        "campaign_name": campaign_name,
        "spend": spend,
        "daily_budget": daily_budget,
    }
    if actions is not None:
        row["actions"] = actions
    if action_values is not None:
        row["action_values"] = action_values
    return row


# ---------------------------------------------------------------------------
# parse_campaigns — spend string → float
# ---------------------------------------------------------------------------

class TestParseSpend(unittest.TestCase):

    def test_spend_string_to_float(self):
        rows = [_row(spend="1234.56")]
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].spend, 1234.56)

    def test_spend_whole_dollars(self):
        rows = [_row(spend="500")]
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].spend, 500.0)

    def test_spend_zero(self):
        rows = [_row(spend="0.00")]
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].spend, 0.0)

    def test_spend_returns_float_type(self):
        rows = [_row(spend="99.99")]
        campaigns = parse_campaigns(rows)
        self.assertIsInstance(campaigns[0].spend, float)


# ---------------------------------------------------------------------------
# parse_campaigns — actions → conversions
# ---------------------------------------------------------------------------

class TestParseConversions(unittest.TestCase):

    def test_lead_action_counted(self):
        rows = [_row(actions=[{"action_type": "lead", "value": "40"}])]
        campaigns = parse_campaigns(rows)
        self.assertEqual(campaigns[0].conversions, 40)

    def test_fb_pixel_purchase_counted(self):
        rows = [_row(actions=[
            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "15"}
        ])]
        campaigns = parse_campaigns(rows)
        self.assertEqual(campaigns[0].conversions, 15)

    def test_fb_pixel_lead_counted(self):
        rows = [_row(actions=[
            {"action_type": "offsite_conversion.fb_pixel_lead", "value": "22"}
        ])]
        campaigns = parse_campaigns(rows)
        self.assertEqual(campaigns[0].conversions, 22)

    def test_multiple_conversion_types_summed(self):
        rows = [_row(actions=[
            {"action_type": "lead", "value": "10"},
            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "5"},
        ])]
        campaigns = parse_campaigns(rows)
        self.assertEqual(campaigns[0].conversions, 15)

    def test_non_conversion_action_ignored(self):
        rows = [_row(actions=[
            {"action_type": "link_click", "value": "200"},
            {"action_type": "post_engagement", "value": "80"},
            {"action_type": "lead", "value": "7"},
        ])]
        campaigns = parse_campaigns(rows)
        self.assertEqual(campaigns[0].conversions, 7)

    def test_no_actions_key_gives_zero_conversions(self):
        rows = [_row()]  # actions omitted
        campaigns = parse_campaigns(rows)
        self.assertEqual(campaigns[0].conversions, 0)

    def test_empty_actions_list_gives_zero_conversions(self):
        rows = [_row(actions=[])]
        campaigns = parse_campaigns(rows)
        self.assertEqual(campaigns[0].conversions, 0)

    def test_conversions_is_int(self):
        rows = [_row(actions=[{"action_type": "lead", "value": "3"}])]
        campaigns = parse_campaigns(rows)
        self.assertIsInstance(campaigns[0].conversions, int)

    def test_fractional_action_value_truncated_to_int(self):
        # Meta occasionally returns "3.0" as a string value
        rows = [_row(actions=[{"action_type": "lead", "value": "3.0"}])]
        campaigns = parse_campaigns(rows)
        self.assertEqual(campaigns[0].conversions, 3)


# ---------------------------------------------------------------------------
# parse_campaigns — action_values → revenue
# ---------------------------------------------------------------------------

class TestParseRevenue(unittest.TestCase):

    def test_lead_revenue_summed(self):
        rows = [_row(action_values=[{"action_type": "lead", "value": "2000.00"}])]
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].revenue, 2000.0)

    def test_purchase_revenue_summed(self):
        rows = [_row(action_values=[
            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "750.50"}
        ])]
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].revenue, 750.5)

    def test_multiple_revenue_entries_summed(self):
        rows = [_row(action_values=[
            {"action_type": "lead", "value": "100.00"},
            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "50.00"},
        ])]
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].revenue, 150.0)

    def test_no_action_values_key_gives_zero_revenue(self):
        rows = [_row()]  # action_values omitted
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].revenue, 0.0)

    def test_empty_action_values_gives_zero_revenue(self):
        rows = [_row(action_values=[])]
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].revenue, 0.0)

    def test_non_conversion_action_value_ignored(self):
        rows = [_row(action_values=[
            {"action_type": "link_click", "value": "999.99"},
            {"action_type": "lead", "value": "200.00"},
        ])]
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].revenue, 200.0)

    def test_revenue_is_float(self):
        rows = [_row(action_values=[{"action_type": "lead", "value": "1.0"}])]
        campaigns = parse_campaigns(rows)
        self.assertIsInstance(campaigns[0].revenue, float)


# ---------------------------------------------------------------------------
# parse_campaigns — daily_budget cents → dollars
# ---------------------------------------------------------------------------

class TestParseDailyBudget(unittest.TestCase):

    def test_cents_converted_to_dollars(self):
        rows = [_row(daily_budget="10000")]   # 10000 cents = $100.00
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].daily_budget, 100.0)

    def test_small_budget(self):
        rows = [_row(daily_budget="1000")]    # $10.00
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].daily_budget, 10.0)

    def test_budget_is_float(self):
        rows = [_row(daily_budget="5000")]
        campaigns = parse_campaigns(rows)
        self.assertIsInstance(campaigns[0].daily_budget, float)

    def test_odd_cent_value(self):
        rows = [_row(daily_budget="4567")]    # $45.67
        campaigns = parse_campaigns(rows)
        self.assertAlmostEqual(campaigns[0].daily_budget, 45.67)


# ---------------------------------------------------------------------------
# parse_campaigns — missing required fields raise ValueError
# ---------------------------------------------------------------------------

class TestMissingFields(unittest.TestCase):

    def test_missing_campaign_name_raises(self):
        row = {"spend": "100.00", "daily_budget": "5000"}
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("campaign_name", str(ctx.exception))

    def test_missing_spend_raises(self):
        row = {"campaign_name": "Camp", "daily_budget": "5000"}
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("spend", str(ctx.exception))

    def test_missing_daily_budget_raises(self):
        row = {"campaign_name": "Camp", "spend": "100.00"}
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("daily_budget", str(ctx.exception))

    def test_unparseable_spend_raises(self):
        row = {"campaign_name": "Camp", "spend": "not-a-number", "daily_budget": "5000"}
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("spend", str(ctx.exception))

    def test_unparseable_budget_raises(self):
        row = {"campaign_name": "Camp", "spend": "100.00", "daily_budget": "N/A"}
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("daily_budget", str(ctx.exception))

    def test_error_names_campaign_when_available(self):
        row = {"campaign_name": "MyCamp", "spend": "100.00"}  # missing daily_budget
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("MyCamp", str(ctx.exception))


# ---------------------------------------------------------------------------
# parse_campaigns — empty input
# ---------------------------------------------------------------------------

class TestEmptyRows(unittest.TestCase):

    def test_empty_list_returns_empty_list(self):
        self.assertEqual(parse_campaigns([]), [])

    def test_empty_list_returns_list_type(self):
        result = parse_campaigns([])
        self.assertIsInstance(result, list)


# ---------------------------------------------------------------------------
# parse_campaigns — output type and determinism
# ---------------------------------------------------------------------------

class TestOutputShape(unittest.TestCase):

    def test_returns_campaign_instances(self):
        rows = [_row()]
        campaigns = parse_campaigns(rows)
        self.assertIsInstance(campaigns[0], Campaign)

    def test_campaign_name_preserved(self):
        rows = [_row(campaign_name="Precise Campaign Name")]
        campaigns = parse_campaigns(rows)
        self.assertEqual(campaigns[0].name, "Precise Campaign Name")

    def test_order_preserved(self):
        rows = [_row(campaign_name="A"), _row(campaign_name="B"), _row(campaign_name="C")]
        campaigns = parse_campaigns(rows)
        self.assertEqual([c.name for c in campaigns], ["A", "B", "C"])

    def test_deterministic_same_input_same_output(self):
        rows = [
            _row(campaign_name="X", spend="500.00", daily_budget="3000",
                 actions=[{"action_type": "lead", "value": "10"}])
        ]
        first = parse_campaigns(rows)
        second = parse_campaigns(rows)
        self.assertEqual(first[0].spend, second[0].spend)
        self.assertEqual(first[0].conversions, second[0].conversions)
        self.assertEqual(first[0].daily_budget, second[0].daily_budget)

    def test_multiple_rows_parsed(self):
        rows = [_row(campaign_name="A"), _row(campaign_name="B")]
        campaigns = parse_campaigns(rows)
        self.assertEqual(len(campaigns), 2)


# ---------------------------------------------------------------------------
# fetch_campaigns — via FakeMetaReportingClient
# ---------------------------------------------------------------------------

class TestFetchCampaigns(unittest.TestCase):

    def _make_client(self, rows: list[dict]) -> FakeMetaReportingClient:
        return FakeMetaReportingClient(canned_rows=rows)

    def test_returns_campaign_list(self):
        client = self._make_client([_row(campaign_name="Fetched")])
        result = fetch_campaigns(client, "act_123", "last_7d")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_correct_campaigns_returned(self):
        rows = [
            _row(campaign_name="Alpha", spend="200.00", daily_budget="5000"),
            _row(campaign_name="Beta", spend="400.00", daily_budget="8000"),
        ]
        client = self._make_client(rows)
        result = fetch_campaigns(client, "act_123", "last_7d")
        names = [c.name for c in result]
        self.assertIn("Alpha", names)
        self.assertIn("Beta", names)

    def test_client_called_with_account_id(self):
        client = self._make_client([_row()])
        fetch_campaigns(client, "act_987654", "last_7d")
        self.assertEqual(client.calls[0]["account_id"], "act_987654")

    def test_client_called_with_date_preset(self):
        client = self._make_client([_row()])
        fetch_campaigns(client, "act_123", "last_30d")
        self.assertEqual(client.calls[0]["date_preset"], "last_30d")

    def test_default_date_preset_is_last_7d(self):
        client = self._make_client([_row()])
        fetch_campaigns(client, "act_123")
        self.assertEqual(client.calls[0]["date_preset"], "last_7d")

    def test_client_receives_expected_fields(self):
        client = self._make_client([_row()])
        fetch_campaigns(client, "act_123")
        fields = client.calls[0]["fields"]
        self.assertIn("campaign_name", fields)
        self.assertIn("spend", fields)
        self.assertIn("daily_budget", fields)

    def test_empty_rows_returns_empty_list(self):
        client = self._make_client([])
        result = fetch_campaigns(client, "act_123")
        self.assertEqual(result, [])

    def test_client_error_raises_runtime_error(self):
        class BrokenClient:
            def get_insights(self, **_kw):
                raise ConnectionError("socket timeout")

        with self.assertRaises(RuntimeError) as ctx:
            fetch_campaigns(BrokenClient(), "act_err")
        self.assertIn("act_err", str(ctx.exception))

    def test_client_error_does_not_swallow_context(self):
        class BrokenClient:
            def get_insights(self, **_kw):
                raise ValueError("bad request")

        with self.assertRaises(RuntimeError) as ctx:
            fetch_campaigns(BrokenClient(), "act_err")
        # The RuntimeError must surface enough context to diagnose the call.
        self.assertIn("get_insights", str(ctx.exception))

    def test_no_sdk_imported(self):
        # facebook_business must not appear in sys.modules after import.
        self.assertNotIn("facebook_business", sys.modules)


# ---------------------------------------------------------------------------
# Full realistic scenario
# ---------------------------------------------------------------------------

class TestRealisticScenario(unittest.TestCase):

    def test_abm_warm_campaign_parsed_correctly(self):
        rows = [
            {
                "campaign_name": "Meta-ABM-warm",
                "spend": "1800.00",
                "daily_budget": "10000",
                "actions": [
                    {"action_type": "lead", "value": "38"},
                    {"action_type": "link_click", "value": "204"},
                ],
                "action_values": [
                    {"action_type": "lead", "value": "3800.00"},
                ],
            }
        ]
        client = FakeMetaReportingClient(canned_rows=rows)
        campaigns = fetch_campaigns(client, "act_demo")

        c = campaigns[0]
        self.assertEqual(c.name, "Meta-ABM-warm")
        self.assertAlmostEqual(c.spend, 1800.0)
        self.assertEqual(c.conversions, 38)
        self.assertAlmostEqual(c.daily_budget, 100.0)
        self.assertAlmostEqual(c.revenue, 3800.0)

    def test_retarget_zero_conversions_flagged(self):
        rows = [
            {
                "campaign_name": "Meta-retarget",
                "spend": "80.00",
                "daily_budget": "4000",
                # no actions — zero conversions expected
            }
        ]
        client = FakeMetaReportingClient(canned_rows=rows)
        campaigns = fetch_campaigns(client, "act_demo")

        c = campaigns[0]
        self.assertEqual(c.conversions, 0)
        self.assertAlmostEqual(c.revenue, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
