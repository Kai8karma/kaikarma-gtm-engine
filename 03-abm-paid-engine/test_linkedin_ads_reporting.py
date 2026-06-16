"""Tests for linkedin_ads_reporting — stdlib unittest, zero egress.

Covers:
  - cost object → float spend
  - plain string cost → float spend
  - externalWebsiteConversions → int conversions
  - conversionValueInLocalCurrency → float revenue
  - dailyBudget object → float daily_budget
  - optional revenue field absent → defaults to 0.0
  - missing campaign_name raises ValueError
  - missing costInLocalCurrency raises ValueError
  - missing externalWebsiteConversions raises ValueError
  - missing dailyBudget raises ValueError
  - fetch_campaigns with fake client returns correct Campaigns
  - non-2xx response raises RuntimeError
  - transport error raises RuntimeError
  - empty elements list → []
  - determinism: same input → same output (two calls, same result)
  - revenue zero-conversion campaign (cpa = inf guard in caller)
"""

from __future__ import annotations

import unittest
from typing import Any

from linkedin_ads_reporting import fetch_campaigns, parse_campaigns
from perf_schema import Campaign


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _element(
    *,
    campaign_name: str = "Test Campaign",
    cost: Any = {"amount": "500.00", "currencyCode": "USD"},
    conversions: Any = 20,
    conversion_value: Any = {"amount": "2000.00", "currencyCode": "USD"},
    daily_budget: Any = {"amount": "75.00", "currencyCode": "USD"},
) -> dict[str, Any]:
    """Build a minimal valid adAnalytics element with overridable fields."""
    el: dict[str, Any] = {
        "campaign_name": campaign_name,
        "costInLocalCurrency": cost,
        "externalWebsiteConversions": conversions,
        "conversionValueInLocalCurrency": conversion_value,
        "dailyBudget": daily_budget,
    }
    return el


class _FakeResponse:
    """Minimal response object returned by the fake client."""

    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body


class _FakeClient:
    """Zero-egress client that records calls and returns a configured response."""

    def __init__(self, status_code: int = 200, elements: list[dict[str, Any]] | None = None) -> None:
        self._status_code = status_code
        self._elements: list[dict[str, Any]] = elements or []
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return _FakeResponse(
            self._status_code,
            {"elements": self._elements} if self._status_code < 300 else {"error": "bad request"},
        )


class _TransportErrorClient:
    """Client that raises an exception on get() — simulates network failure."""

    def get(self, url: str, **kwargs: Any) -> Any:
        raise ConnectionError("simulated transport failure")


# ---------------------------------------------------------------------------
# parse_campaigns — pure unit tests (no network)
# ---------------------------------------------------------------------------


class TestParseCampaigns(unittest.TestCase):

    # --- happy-path field mapping ---

    def test_cost_object_to_float_spend(self) -> None:
        campaigns = parse_campaigns([_element(cost={"amount": "1234.56", "currencyCode": "USD"})])
        self.assertEqual(len(campaigns), 1)
        self.assertAlmostEqual(campaigns[0].spend, 1234.56)

    def test_cost_plain_string_to_float_spend(self) -> None:
        """LinkedIn occasionally returns plain strings for money fields."""
        campaigns = parse_campaigns([_element(cost="88.00")])
        self.assertAlmostEqual(campaigns[0].spend, 88.0)

    def test_cost_plain_float_to_float_spend(self) -> None:
        campaigns = parse_campaigns([_element(cost=99.5)])
        self.assertAlmostEqual(campaigns[0].spend, 99.5)

    def test_conversions_to_int(self) -> None:
        campaigns = parse_campaigns([_element(conversions=42)])
        self.assertEqual(campaigns[0].conversions, 42)

    def test_conversion_value_object_to_revenue(self) -> None:
        campaigns = parse_campaigns([_element(conversion_value={"amount": "8000.00", "currencyCode": "USD"})])
        self.assertAlmostEqual(campaigns[0].revenue, 8000.0)

    def test_daily_budget_object_to_daily_budget(self) -> None:
        campaigns = parse_campaigns([_element(daily_budget={"amount": "100.00", "currencyCode": "USD"})])
        self.assertAlmostEqual(campaigns[0].daily_budget, 100.0)

    def test_optional_revenue_absent_defaults_to_zero(self) -> None:
        el = _element()
        del el["conversionValueInLocalCurrency"]
        campaigns = parse_campaigns([el])
        self.assertAlmostEqual(campaigns[0].revenue, 0.0)

    def test_optional_revenue_none_defaults_to_zero(self) -> None:
        campaigns = parse_campaigns([_element(conversion_value=None)])
        self.assertAlmostEqual(campaigns[0].revenue, 0.0)

    def test_zero_conversions_allowed(self) -> None:
        """Zero conversions is valid data — don't treat it as missing."""
        campaigns = parse_campaigns([_element(conversions=0)])
        self.assertEqual(campaigns[0].conversions, 0)

    def test_campaign_name_preserved(self) -> None:
        campaigns = parse_campaigns([_element(campaign_name="ABM — APAC Q2")])
        self.assertEqual(campaigns[0].name, "ABM — APAC Q2")

    def test_multiple_elements_returns_all(self) -> None:
        els = [_element(campaign_name=f"Camp {i}", conversions=i) for i in range(5)]
        campaigns = parse_campaigns(els)
        self.assertEqual(len(campaigns), 5)
        for i, c in enumerate(campaigns):
            self.assertEqual(c.name, f"Camp {i}")
            self.assertEqual(c.conversions, i)

    def test_empty_elements_returns_empty_list(self) -> None:
        self.assertEqual(parse_campaigns([]), [])

    def test_returns_campaign_dataclass_instances(self) -> None:
        campaigns = parse_campaigns([_element()])
        self.assertIsInstance(campaigns[0], Campaign)

    # --- error cases ---

    def test_missing_campaign_name_raises_value_error(self) -> None:
        el = _element()
        del el["campaign_name"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([el])
        self.assertIn("campaign_name", str(ctx.exception))

    def test_empty_campaign_name_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([_element(campaign_name="")])
        self.assertIn("campaign_name", str(ctx.exception))

    def test_missing_cost_raises_value_error(self) -> None:
        el = _element()
        del el["costInLocalCurrency"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([el])
        self.assertIn("costInLocalCurrency", str(ctx.exception))

    def test_missing_conversions_raises_value_error(self) -> None:
        el = _element()
        del el["externalWebsiteConversions"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([el])
        self.assertIn("externalWebsiteConversions", str(ctx.exception))

    def test_missing_daily_budget_raises_value_error(self) -> None:
        el = _element()
        del el["dailyBudget"]
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([el])
        self.assertIn("dailyBudget", str(ctx.exception))

    def test_unparseable_cost_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([_element(cost="not-a-number")])
        self.assertIn("costInLocalCurrency", str(ctx.exception))

    def test_unparseable_conversions_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_campaigns([_element(conversions="forty-two")])
        self.assertIn("externalWebsiteConversions", str(ctx.exception))

    # --- determinism ---

    def test_determinism_same_input_same_output(self) -> None:
        els = [_element(campaign_name="Stable", conversions=10)]
        first = parse_campaigns(els)
        second = parse_campaigns(els)
        self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# fetch_campaigns — integration with fake client (still zero egress)
# ---------------------------------------------------------------------------


class TestFetchCampaigns(unittest.TestCase):

    def _two_element_client(self) -> _FakeClient:
        return _FakeClient(
            status_code=200,
            elements=[
                _element(campaign_name="Camp A", conversions=30, cost={"amount": "900.00", "currencyCode": "USD"}),
                _element(campaign_name="Camp B", conversions=5, cost={"amount": "250.00", "currencyCode": "USD"}),
            ],
        )

    def test_fetch_returns_correct_campaigns(self) -> None:
        client = self._two_element_client()
        campaigns = fetch_campaigns(client, "urn:li:sponsoredAccount:42")
        self.assertEqual(len(campaigns), 2)
        self.assertEqual(campaigns[0].name, "Camp A")
        self.assertEqual(campaigns[0].conversions, 30)
        self.assertAlmostEqual(campaigns[0].spend, 900.0)
        self.assertEqual(campaigns[1].name, "Camp B")

    def test_fetch_calls_get_exactly_once(self) -> None:
        client = self._two_element_client()
        fetch_campaigns(client, "urn:li:sponsoredAccount:42")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["method"], "GET")

    def test_fetch_passes_account_urn_in_params(self) -> None:
        client = self._two_element_client()
        fetch_campaigns(client, "urn:li:sponsoredAccount:99")
        params = client.calls[0].get("params", {})
        self.assertIn("urn:li:sponsoredAccount:99", params.get("accounts", ""))

    def test_empty_elements_from_api_returns_empty_list(self) -> None:
        client = _FakeClient(status_code=200, elements=[])
        campaigns = fetch_campaigns(client, "urn:li:sponsoredAccount:42")
        self.assertEqual(campaigns, [])

    def test_non_2xx_raises_runtime_error(self) -> None:
        client = _FakeClient(status_code=400, elements=[])
        with self.assertRaises(RuntimeError) as ctx:
            fetch_campaigns(client, "urn:li:sponsoredAccount:42")
        self.assertIn("400", str(ctx.exception))

    def test_404_raises_runtime_error(self) -> None:
        client = _FakeClient(status_code=404, elements=[])
        with self.assertRaises(RuntimeError) as ctx:
            fetch_campaigns(client, "urn:li:sponsoredAccount:42")
        self.assertIn("404", str(ctx.exception))

    def test_500_raises_runtime_error(self) -> None:
        client = _FakeClient(status_code=500, elements=[])
        with self.assertRaises(RuntimeError) as ctx:
            fetch_campaigns(client, "urn:li:sponsoredAccount:42")
        self.assertIn("500", str(ctx.exception))

    def test_transport_error_raises_runtime_error(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            fetch_campaigns(_TransportErrorClient(), "urn:li:sponsoredAccount:42")
        self.assertIn("transport error", str(ctx.exception))

    def test_determinism_fetch_same_output_two_calls(self) -> None:
        client_a = self._two_element_client()
        client_b = self._two_element_client()
        result_a = fetch_campaigns(client_a, "urn:li:sponsoredAccount:1")
        result_b = fetch_campaigns(client_b, "urn:li:sponsoredAccount:1")
        self.assertEqual(result_a, result_b)

    def test_revenue_flows_through_fetch(self) -> None:
        client = _FakeClient(
            status_code=200,
            elements=[_element(conversion_value={"amount": "5000.00", "currencyCode": "USD"})],
        )
        campaigns = fetch_campaigns(client, "urn:li:sponsoredAccount:1")
        self.assertAlmostEqual(campaigns[0].revenue, 5000.0)

    def test_error_message_includes_account_urn(self) -> None:
        client = _FakeClient(status_code=403, elements=[])
        with self.assertRaises(RuntimeError) as ctx:
            fetch_campaigns(client, "urn:li:sponsoredAccount:777")
        self.assertIn("urn:li:sponsoredAccount:777", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
