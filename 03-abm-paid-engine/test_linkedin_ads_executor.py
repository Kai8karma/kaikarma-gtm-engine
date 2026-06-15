"""Tests for the LinkedIn Ads executor — zero network, stdlib unittest only.

All tests use ``FakeLinkedInClient`` which records calls and returns canned
HTTP 200 responses.  No third-party packages are imported; no network is
touched.

    python3 03-abm-paid-engine/test_linkedin_ads_executor.py
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any

from executor import NO_OP, PAUSE, SET_BUDGET, ExecResult, PaidOp
from linkedin_ads_executor import (
    LinkedInAdsExecutor,
    _STATUS_PAUSED,
    _urn_encode,
    build_budget_payload,
    build_pause_payload,
    build_request_headers,
    campaign_url,
)


# ---------------------------------------------------------------------------
# Shared fake client — records calls, always 200 unless told otherwise
# ---------------------------------------------------------------------------


@dataclass
class _FakeResponse:
    status_code: int = 200
    _body: dict[str, Any] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return self._body


@dataclass
class FakeLinkedInClient:
    """Records every call; configurable response status for error-path tests."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    next_status: int = 200

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return _FakeResponse(status_code=self.next_status)

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return _FakeResponse(status_code=self.next_status)

    def reset(self) -> None:
        self.calls.clear()
        self.next_status = 200


def _make_executor(client: FakeLinkedInClient | None = None) -> LinkedInAdsExecutor:
    return LinkedInAdsExecutor(
        client=client or FakeLinkedInClient(),
        account_id="urn:li:sponsoredAccount:999",
        currency_code="USD",
        access_token="tok-test",
    )


# ---------------------------------------------------------------------------
# Pure builder function tests — no client, no network at all
# ---------------------------------------------------------------------------


class TestBuildBudgetPayload(unittest.TestCase):

    def test_amount_is_string(self) -> None:
        payload = build_budget_payload("urn:li:sponsoredCampaign:1", 120.0, "USD")
        amount = payload["patch"]["$set"]["dailyBudget"]["amount"]
        self.assertIsInstance(amount, str)

    def test_amount_value_matches(self) -> None:
        payload = build_budget_payload("urn:li:sponsoredCampaign:1", 99.50, "USD")
        self.assertEqual(payload["patch"]["$set"]["dailyBudget"]["amount"], "99.5")

    def test_currency_code_preserved(self) -> None:
        payload = build_budget_payload("urn:li:sponsoredCampaign:1", 50.0, "GBP")
        self.assertEqual(payload["patch"]["$set"]["dailyBudget"]["currencyCode"], "GBP")

    def test_rounding_to_two_decimal_places(self) -> None:
        payload = build_budget_payload("urn:li:sponsoredCampaign:1", 100.1234567, "USD")
        self.assertEqual(payload["patch"]["$set"]["dailyBudget"]["amount"], "100.12")

    def test_payload_structure_has_patch_set(self) -> None:
        payload = build_budget_payload("urn:li:sponsoredCampaign:1", 80.0, "EUR")
        self.assertIn("patch", payload)
        self.assertIn("$set", payload["patch"])
        self.assertIn("dailyBudget", payload["patch"]["$set"])


class TestBuildPausePayload(unittest.TestCase):

    def test_sets_status_to_paused(self) -> None:
        payload = build_pause_payload()
        self.assertEqual(payload["patch"]["$set"]["status"], _STATUS_PAUSED)

    def test_payload_has_patch_set(self) -> None:
        payload = build_pause_payload()
        self.assertIn("patch", payload)
        self.assertIn("$set", payload["patch"])


class TestBuildRequestHeaders(unittest.TestCase):

    def test_authorization_bearer_prefix(self) -> None:
        headers = build_request_headers("my-token")
        self.assertTrue(headers["Authorization"].startswith("Bearer "))

    def test_authorization_includes_token(self) -> None:
        headers = build_request_headers("my-token")
        self.assertIn("my-token", headers["Authorization"])

    def test_linkedin_version_header_present(self) -> None:
        headers = build_request_headers("tok")
        self.assertIn("LinkedIn-Version", headers)

    def test_content_type_is_json(self) -> None:
        headers = build_request_headers("tok")
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_restli_method_header_present(self) -> None:
        headers = build_request_headers("tok")
        self.assertIn("X-Restli-Method", headers)


class TestCampaignUrl(unittest.TestCase):

    def test_url_starts_with_api_base(self) -> None:
        url = campaign_url("urn:li:sponsoredCampaign:9876")
        self.assertTrue(url.startswith("https://api.linkedin.com/rest/adCampaigns/"))

    def test_colons_are_percent_encoded_in_url(self) -> None:
        url = campaign_url("urn:li:sponsoredCampaign:9876")
        self.assertNotIn("urn:li", url)
        self.assertIn("%3A", url)

    def test_campaign_id_present_in_url(self) -> None:
        url = campaign_url("urn:li:sponsoredCampaign:9876")
        self.assertIn("9876", url)


class TestUrnEncode(unittest.TestCase):

    def test_colons_encoded(self) -> None:
        self.assertEqual(_urn_encode("urn:li:x:1"), "urn%3Ali%3Ax%3A1")

    def test_no_colons_unchanged(self) -> None:
        self.assertEqual(_urn_encode("simple"), "simple")


# ---------------------------------------------------------------------------
# Executor behaviour tests — use FakeLinkedInClient, zero network
# ---------------------------------------------------------------------------


class TestLinkedInAdsExecutorNoOp(unittest.TestCase):

    def test_no_op_returns_ok_without_calling_client(self) -> None:
        client = FakeLinkedInClient()
        ex = _make_executor(client)
        op = PaidOp(NO_OP, "urn:li:sponsoredCampaign:1", None, "hold")
        result = ex.apply(op)
        self.assertTrue(result.ok)
        self.assertEqual(len(client.calls), 0)

    def test_no_op_message_contains_campaign(self) -> None:
        ex = _make_executor()
        op = PaidOp(NO_OP, "urn:li:sponsoredCampaign:42", None, "hold")
        result = ex.apply(op)
        self.assertIn("urn:li:sponsoredCampaign:42", result.message)


class TestLinkedInAdsExecutorSetBudget(unittest.TestCase):

    def test_set_budget_makes_one_http_call(self) -> None:
        client = FakeLinkedInClient()
        ex = _make_executor(client)
        op = PaidOp(SET_BUDGET, "urn:li:sponsoredCampaign:1", 150.0, "scale")
        ex.apply(op)
        self.assertEqual(len(client.calls), 1)

    def test_set_budget_posts_to_campaign_url(self) -> None:
        client = FakeLinkedInClient()
        ex = _make_executor(client)
        op = PaidOp(SET_BUDGET, "urn:li:sponsoredCampaign:77", 100.0, "cut")
        ex.apply(op)
        self.assertIn("77", client.calls[0]["url"])

    def test_set_budget_payload_has_correct_amount(self) -> None:
        client = FakeLinkedInClient()
        ex = _make_executor(client)
        op = PaidOp(SET_BUDGET, "urn:li:sponsoredCampaign:1", 200.0, "scale")
        ex.apply(op)
        body = client.calls[0]["json"]
        amount = body["patch"]["$set"]["dailyBudget"]["amount"]
        self.assertEqual(amount, "200.0")

    def test_set_budget_result_is_ok(self) -> None:
        ex = _make_executor()
        op = PaidOp(SET_BUDGET, "urn:li:sponsoredCampaign:1", 80.0, "cut")
        result = ex.apply(op)
        self.assertTrue(result.ok)

    def test_set_budget_message_contains_new_value(self) -> None:
        ex = _make_executor()
        op = PaidOp(SET_BUDGET, "urn:li:sponsoredCampaign:1", 175.0, "scale")
        result = ex.apply(op)
        self.assertIn("175.0", result.message)

    def test_set_budget_none_value_returns_not_ok(self) -> None:
        ex = _make_executor()
        op = PaidOp(SET_BUDGET, "urn:li:sponsoredCampaign:1", None, "bad")
        result = ex.apply(op)
        self.assertFalse(result.ok)
        self.assertIn("value", result.message)

    def test_set_budget_headers_sent(self) -> None:
        client = FakeLinkedInClient()
        ex = _make_executor(client)
        op = PaidOp(SET_BUDGET, "urn:li:sponsoredCampaign:1", 120.0, "scale")
        ex.apply(op)
        headers = client.calls[0]["headers"]
        self.assertIn("Authorization", headers)
        self.assertIn("LinkedIn-Version", headers)


class TestLinkedInAdsExecutorPause(unittest.TestCase):

    def test_pause_makes_one_http_call(self) -> None:
        client = FakeLinkedInClient()
        ex = _make_executor(client)
        op = PaidOp(PAUSE, "urn:li:sponsoredCampaign:5", None, "kill")
        ex.apply(op)
        self.assertEqual(len(client.calls), 1)

    def test_pause_payload_sets_status_paused(self) -> None:
        client = FakeLinkedInClient()
        ex = _make_executor(client)
        op = PaidOp(PAUSE, "urn:li:sponsoredCampaign:5", None, "kill")
        ex.apply(op)
        body = client.calls[0]["json"]
        self.assertEqual(body["patch"]["$set"]["status"], _STATUS_PAUSED)

    def test_pause_result_is_ok(self) -> None:
        ex = _make_executor()
        op = PaidOp(PAUSE, "urn:li:sponsoredCampaign:5", None, "kill")
        result = ex.apply(op)
        self.assertTrue(result.ok)

    def test_pause_message_contains_campaign_urn(self) -> None:
        ex = _make_executor()
        op = PaidOp(PAUSE, "urn:li:sponsoredCampaign:5", None, "kill")
        result = ex.apply(op)
        self.assertIn("urn:li:sponsoredCampaign:5", result.message)

    def test_pause_result_op_echoed_back(self) -> None:
        ex = _make_executor()
        op = PaidOp(PAUSE, "urn:li:sponsoredCampaign:5", None, "kill")
        result = ex.apply(op)
        self.assertIs(result.op, op)


class TestLinkedInAdsExecutorErrorHandling(unittest.TestCase):

    def test_api_4xx_returns_not_ok(self) -> None:
        client = FakeLinkedInClient()
        client.next_status = 403
        ex = _make_executor(client)
        op = PaidOp(SET_BUDGET, "urn:li:sponsoredCampaign:1", 100.0, "scale")
        result = ex.apply(op)
        self.assertFalse(result.ok)
        self.assertIn("403", result.message)

    def test_api_5xx_returns_not_ok(self) -> None:
        client = FakeLinkedInClient()
        client.next_status = 500
        ex = _make_executor(client)
        op = PaidOp(PAUSE, "urn:li:sponsoredCampaign:1", None, "kill")
        result = ex.apply(op)
        self.assertFalse(result.ok)
        self.assertIn("500", result.message)

    def test_unknown_op_kind_returns_not_ok(self) -> None:
        ex = _make_executor()
        op = PaidOp("BOOST", "urn:li:sponsoredCampaign:1", 50.0, "??")
        result = ex.apply(op)
        self.assertFalse(result.ok)
        self.assertIn("unknown", result.message.lower())


class TestLinkedInAdsExecutorReturnType(unittest.TestCase):

    def test_apply_returns_exec_result(self) -> None:
        ex = _make_executor()
        op = PaidOp(NO_OP, "urn:li:sponsoredCampaign:1", None, "hold")
        result = ex.apply(op)
        self.assertIsInstance(result, ExecResult)


class TestLinkedInAdsExecutorCurrency(unittest.TestCase):

    def test_currency_code_propagated_to_budget_payload(self) -> None:
        client = FakeLinkedInClient()
        ex = LinkedInAdsExecutor(
            client=client,
            account_id="urn:li:sponsoredAccount:1",
            currency_code="EUR",
            access_token="tok",
        )
        op = PaidOp(SET_BUDGET, "urn:li:sponsoredCampaign:1", 90.0, "scale")
        ex.apply(op)
        body = client.calls[0]["json"]
        self.assertEqual(body["patch"]["$set"]["dailyBudget"]["currencyCode"], "EUR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
