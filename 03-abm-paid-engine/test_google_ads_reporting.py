"""Unit tests for google_ads_reporting.

stdlib unittest only — zero third-party packages required.
Reuses conftest.py (presence puts 03-abm-paid-engine/ on sys.path).

Coverage:
  1.  micros → dollars conversion is correct for spend (cost_micros).
  2.  micros → dollars conversion is correct for budget (campaign_budget.amount_micros).
  3.  Fractional conversions are rounded to int.
  4.  conversions_value maps to revenue.
  5.  Missing top-level key raises ValueError naming the field.
  6.  Missing nested key raises ValueError naming the full dotted path.
  7.  fetch_campaigns with a fake client returns correct Campaign objects.
  8.  Empty rows list returns empty list (no crash, no ValueError).
  9.  parse_campaigns is deterministic: same input, same output, same order.
  10. fetch_campaigns raises RuntimeError (not []) when the client errors.
  11. fetch_campaigns records the customer_id on the fake client.
  12. revenue=0.0 default when conversions_value is 0.
"""

from __future__ import annotations

import unittest
from typing import Any

from google_ads_reporting import (
    MICROS_PER_UNIT,
    FakeGoogleReportingClient,
    fetch_campaigns,
    parse_campaigns,
)
from perf_schema import Campaign


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_row(
    name: str = "TestCampaign",
    cost_micros: int = 10_000_000,
    conversions: float = 5.0,
    conversions_value: float = 300.0,
    budget_micros: int = 40_000_000,
) -> dict[str, Any]:
    """Return a minimal valid GAQL-shaped row."""
    return {
        "campaign": {"name": name},
        "metrics": {
            "cost_micros": cost_micros,
            "conversions": conversions,
            "conversions_value": conversions_value,
        },
        "campaign_budget": {"amount_micros": budget_micros},
    }


# ---------------------------------------------------------------------------
# parse_campaigns tests
# ---------------------------------------------------------------------------

class TestMicrosConversionSpend(unittest.TestCase):
    """cost_micros is divided by 1_000_000 to produce spend in dollars."""

    def test_whole_dollar_spend(self) -> None:
        row = _make_row(cost_micros=50_000_000)
        (c,) = parse_campaigns([row])
        self.assertAlmostEqual(c.spend, 50.0, places=6)

    def test_fractional_dollar_spend(self) -> None:
        # $12.34 = 12_340_000 micros
        row = _make_row(cost_micros=12_340_000)
        (c,) = parse_campaigns([row])
        self.assertAlmostEqual(c.spend, 12.34, places=6)

    def test_zero_spend(self) -> None:
        row = _make_row(cost_micros=0)
        (c,) = parse_campaigns([row])
        self.assertEqual(c.spend, 0.0)

    def test_micros_per_unit_constant(self) -> None:
        """Sanity: the module constant matches the expected denominator."""
        self.assertEqual(MICROS_PER_UNIT, 1_000_000)


class TestMicrosConversionBudget(unittest.TestCase):
    """campaign_budget.amount_micros is divided by 1_000_000 → daily_budget."""

    def test_whole_dollar_budget(self) -> None:
        row = _make_row(budget_micros=100_000_000)
        (c,) = parse_campaigns([row])
        self.assertAlmostEqual(c.daily_budget, 100.0, places=6)

    def test_fractional_dollar_budget(self) -> None:
        # $75.50 = 75_500_000 micros
        row = _make_row(budget_micros=75_500_000)
        (c,) = parse_campaigns([row])
        self.assertAlmostEqual(c.daily_budget, 75.5, places=6)

    def test_zero_budget(self) -> None:
        row = _make_row(budget_micros=0)
        (c,) = parse_campaigns([row])
        self.assertEqual(c.daily_budget, 0.0)


class TestFractionalConversions(unittest.TestCase):
    """Google may return fractional conversions; they must be rounded to int."""

    def test_half_rounds_to_nearest(self) -> None:
        # Python's round() uses banker's rounding; 5.5 → 6
        row = _make_row(conversions=5.5)
        (c,) = parse_campaigns([row])
        self.assertIsInstance(c.conversions, int)
        self.assertEqual(c.conversions, round(5.5))

    def test_point_four_rounds_down(self) -> None:
        row = _make_row(conversions=3.4)
        (c,) = parse_campaigns([row])
        self.assertEqual(c.conversions, 3)

    def test_point_six_rounds_up(self) -> None:
        row = _make_row(conversions=3.6)
        (c,) = parse_campaigns([row])
        self.assertEqual(c.conversions, 4)

    def test_exact_integer_conversions(self) -> None:
        row = _make_row(conversions=12.0)
        (c,) = parse_campaigns([row])
        self.assertEqual(c.conversions, 12)
        self.assertIsInstance(c.conversions, int)

    def test_zero_conversions(self) -> None:
        row = _make_row(conversions=0.0)
        (c,) = parse_campaigns([row])
        self.assertEqual(c.conversions, 0)


class TestConversionsValueToRevenue(unittest.TestCase):
    """conversions_value from the metrics block maps to Campaign.revenue."""

    def test_revenue_populated(self) -> None:
        row = _make_row(conversions_value=480.0)
        (c,) = parse_campaigns([row])
        self.assertAlmostEqual(c.revenue, 480.0)

    def test_zero_revenue_default(self) -> None:
        row = _make_row(conversions_value=0.0)
        (c,) = parse_campaigns([row])
        self.assertEqual(c.revenue, 0.0)


class TestMissingFieldRaisesValueError(unittest.TestCase):
    """Missing required fields raise ValueError naming the field — never silently dropped."""

    def test_missing_campaign_block(self) -> None:
        row = _make_row()
        del row["campaign"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("campaign", str(ctx.exception))

    def test_missing_campaign_name(self) -> None:
        row = _make_row()
        del row["campaign"]["name"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("name", str(ctx.exception))

    def test_missing_metrics_block(self) -> None:
        row = _make_row()
        del row["metrics"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("metrics", str(ctx.exception))

    def test_missing_cost_micros(self) -> None:
        row = _make_row()
        del row["metrics"]["cost_micros"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("cost_micros", str(ctx.exception))

    def test_missing_conversions(self) -> None:
        row = _make_row()
        del row["metrics"]["conversions"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("conversions", str(ctx.exception))

    def test_missing_conversions_value(self) -> None:
        row = _make_row()
        del row["metrics"]["conversions_value"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("conversions_value", str(ctx.exception))

    def test_missing_campaign_budget_block(self) -> None:
        row = _make_row()
        del row["campaign_budget"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("campaign_budget", str(ctx.exception))

    def test_missing_budget_amount_micros(self) -> None:
        row = _make_row()
        del row["campaign_budget"]["amount_micros"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([row])
        self.assertIn("amount_micros", str(ctx.exception))


class TestEmptyRows(unittest.TestCase):
    """Empty row list returns an empty Campaign list without raising."""

    def test_empty_list(self) -> None:
        result = parse_campaigns([])
        self.assertEqual(result, [])
        self.assertIsInstance(result, list)


class TestDeterminism(unittest.TestCase):
    """Same input → same output in the same order, every time."""

    def test_order_preserved(self) -> None:
        rows = [_make_row(name=f"Camp-{i}", cost_micros=i * 1_000_000) for i in range(5)]
        first = parse_campaigns(rows)
        second = parse_campaigns(rows)
        self.assertEqual(len(first), len(second))
        for a, b in zip(first, second):
            self.assertEqual(a.name, b.name)
            self.assertAlmostEqual(a.spend, b.spend)

    def test_names_match_input_order(self) -> None:
        names = ["Alpha", "Beta", "Gamma"]
        rows = [_make_row(name=n) for n in names]
        result = parse_campaigns(rows)
        self.assertEqual([c.name for c in result], names)


# ---------------------------------------------------------------------------
# fetch_campaigns tests
# ---------------------------------------------------------------------------

class TestFetchCampaignsHappyPath(unittest.TestCase):
    """fetch_campaigns returns correct Campaign objects via a fake client."""

    def setUp(self) -> None:
        self.row = _make_row(
            name="LI-ABM",
            cost_micros=48_000_000,    # $48.00
            conversions=8.0,
            conversions_value=480.0,
            budget_micros=60_000_000,  # $60.00
        )
        self.client = FakeGoogleReportingClient(rows=[self.row])

    def test_returns_campaign_list(self) -> None:
        result = fetch_campaigns(self.client, customer_id="123-456-7890")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Campaign)

    def test_spend_converted_from_micros(self) -> None:
        (c,) = fetch_campaigns(self.client, customer_id="123-456-7890")
        self.assertAlmostEqual(c.spend, 48.0, places=6)

    def test_budget_converted_from_micros(self) -> None:
        (c,) = fetch_campaigns(self.client, customer_id="123-456-7890")
        self.assertAlmostEqual(c.daily_budget, 60.0, places=6)

    def test_conversions_correct(self) -> None:
        (c,) = fetch_campaigns(self.client, customer_id="123-456-7890")
        self.assertEqual(c.conversions, 8)

    def test_revenue_correct(self) -> None:
        (c,) = fetch_campaigns(self.client, customer_id="123-456-7890")
        self.assertAlmostEqual(c.revenue, 480.0)

    def test_customer_id_forwarded_to_client(self) -> None:
        fetch_campaigns(self.client, customer_id="111-222-3333")
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.client.calls[0][0], "111-222-3333")


class TestFetchCampaignsEmptyResponse(unittest.TestCase):
    """fetch_campaigns returns [] when the client returns no rows."""

    def test_empty_response(self) -> None:
        client = FakeGoogleReportingClient(rows=[])
        result = fetch_campaigns(client, customer_id="000-000-0000")
        self.assertEqual(result, [])


class TestFetchCampaignsClientError(unittest.TestCase):
    """When the client raises, fetch_campaigns raises RuntimeError (not []).

    Silently returning [] would make the controller act on phantom data.
    """

    def test_raises_runtime_error_not_empty_list(self) -> None:
        bad_client = FakeGoogleReportingClient(rows=[], raise_on_search=True)
        with self.assertRaises(RuntimeError) as ctx:
            fetch_campaigns(bad_client, customer_id="000-000-0000")
        # Error message must contain enough context to diagnose the failure.
        self.assertIn("000-000-0000", str(ctx.exception))

    def test_error_message_contains_query_prefix(self) -> None:
        bad_client = FakeGoogleReportingClient(rows=[], raise_on_search=True)
        with self.assertRaises(RuntimeError) as ctx:
            fetch_campaigns(bad_client, customer_id="cust-99")
        # The error wraps rather than swallows the original exception text.
        self.assertIn("fetch failed", str(ctx.exception).lower().replace("_", " ") or str(ctx.exception))


class TestFetchCampaignsCustomQuery(unittest.TestCase):
    """A custom query string is passed through to the client unchanged."""

    def test_custom_query_forwarded(self) -> None:
        client = FakeGoogleReportingClient(rows=[])
        custom_q = "SELECT campaign.name FROM campaign WHERE campaign.id = 42"
        fetch_campaigns(client, customer_id="x", query=custom_q)
        self.assertEqual(client.calls[0][1], custom_q)


# ---------------------------------------------------------------------------
# Multi-row integration test
# ---------------------------------------------------------------------------

class TestMultiRowParsing(unittest.TestCase):
    """Realistic multi-row scenario exercising all fields together."""

    def test_three_campaigns(self) -> None:
        rows = [
            _make_row("Alpha", cost_micros=20_000_000, conversions=4.0,
                      conversions_value=200.0, budget_micros=30_000_000),
            _make_row("Beta",  cost_micros=35_750_000, conversions=7.5,
                      conversions_value=450.0, budget_micros=50_000_000),
            _make_row("Gamma", cost_micros=0,          conversions=0.0,
                      conversions_value=0.0,   budget_micros=10_000_000),
        ]
        result = parse_campaigns(rows)
        self.assertEqual(len(result), 3)

        alpha, beta, gamma = result
        self.assertAlmostEqual(alpha.spend, 20.0)
        self.assertAlmostEqual(alpha.daily_budget, 30.0)
        self.assertEqual(alpha.conversions, 4)

        self.assertAlmostEqual(beta.spend, 35.75)
        self.assertAlmostEqual(beta.daily_budget, 50.0)
        self.assertEqual(beta.conversions, round(7.5))
        self.assertAlmostEqual(beta.revenue, 450.0)

        self.assertEqual(gamma.conversions, 0)
        self.assertEqual(gamma.revenue, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
