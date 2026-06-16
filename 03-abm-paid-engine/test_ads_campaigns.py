"""Unit tests for ads_campaigns.py.

Stdlib unittest only — zero third-party packages required.
All tests run air-gapped; FakeAdsClient records calls without any network I/O.

Coverage:
  - Each platform builder: PAUSED status, correct budget unit, required fields
  - build_customer_match_audience: email normalisation, SHA-256 hash correctness,
    raw emails never present in output, determinism
  - create_campaign / upload_audience via FakeAdsClient: ok=True on success
  - Client error → ok=False (error contract)
  - Unknown platform → ok=False
  - Negative budget → ValueError
"""

from __future__ import annotations

import hashlib
import unittest

from ads_campaigns import (
    FakeAdsClient,
    _normalize_email,
    _sha256_hex,
    build_customer_match_audience,
    build_google_campaign_payload,
    build_linkedin_campaign_payload,
    build_meta_campaign_payload,
    create_campaign,
    upload_audience,
)
from executor import ExecResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LINKEDIN_ACCOUNT = "urn:li:sponsoredAccount:123456"


def _known_hash(raw: str) -> str:
    """Reference SHA-256 of a known normalised email — for correctness assertions."""
    normalised = raw.strip().lower()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# build_google_campaign_payload
# ---------------------------------------------------------------------------


class TestBuildGoogleCampaignPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = build_google_campaign_payload("Test-Google", daily_budget_dollars=120.0)

    def test_status_is_paused(self) -> None:
        self.assertEqual(self.payload["status"], "PAUSED")

    def test_budget_in_micros(self) -> None:
        # $120.00 → 120_000_000 micros
        self.assertEqual(self.payload["campaign_budget"]["amount_micros"], 120_000_000)

    def test_name_preserved(self) -> None:
        self.assertEqual(self.payload["name"], "Test-Google")

    def test_default_channel_type(self) -> None:
        self.assertEqual(self.payload["advertising_channel_type"], "SEARCH")

    def test_default_bidding_strategy(self) -> None:
        self.assertEqual(self.payload["bidding_strategy_type"], "MANUAL_CPC")

    def test_custom_channel_type(self) -> None:
        p = build_google_campaign_payload("x", 10.0, advertising_channel_type="DISPLAY")
        self.assertEqual(p["advertising_channel_type"], "DISPLAY")

    def test_zero_budget(self) -> None:
        p = build_google_campaign_payload("zero", 0.0)
        self.assertEqual(p["campaign_budget"]["amount_micros"], 0)

    def test_fractional_budget_rounds(self) -> None:
        # $1.50 → 1_500_000
        p = build_google_campaign_payload("frac", 1.50)
        self.assertEqual(p["campaign_budget"]["amount_micros"], 1_500_000)

    def test_negative_budget_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_google_campaign_payload("bad", -1.0)

    def test_delivery_method_present(self) -> None:
        self.assertIn("delivery_method", self.payload["campaign_budget"])


# ---------------------------------------------------------------------------
# build_meta_campaign_payload
# ---------------------------------------------------------------------------


class TestBuildMetaCampaignPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = build_meta_campaign_payload(
            "Test-Meta", daily_budget_dollars=200.0, objective="OUTCOME_LEADS"
        )

    def test_status_is_paused(self) -> None:
        self.assertEqual(self.payload["status"], "PAUSED")

    def test_budget_in_cents(self) -> None:
        # $200.00 → 20_000 cents
        self.assertEqual(self.payload["daily_budget"], 20_000)

    def test_name_preserved(self) -> None:
        self.assertEqual(self.payload["name"], "Test-Meta")

    def test_objective_preserved(self) -> None:
        self.assertEqual(self.payload["objective"], "OUTCOME_LEADS")

    def test_default_buying_type(self) -> None:
        self.assertEqual(self.payload["buying_type"], "AUCTION")

    def test_default_special_ad_categories_empty(self) -> None:
        self.assertEqual(self.payload["special_ad_categories"], [])

    def test_custom_special_ad_categories(self) -> None:
        p = build_meta_campaign_payload("x", 10.0, "OUTCOME_TRAFFIC", special_ad_categories=["CREDIT"])
        self.assertEqual(p["special_ad_categories"], ["CREDIT"])

    def test_zero_budget(self) -> None:
        p = build_meta_campaign_payload("zero", 0.0, "OUTCOME_AWARENESS")
        self.assertEqual(p["daily_budget"], 0)

    def test_fractional_budget_rounds(self) -> None:
        # $1.50 → 150 cents
        p = build_meta_campaign_payload("frac", 1.50, "OUTCOME_LEADS")
        self.assertEqual(p["daily_budget"], 150)

    def test_negative_budget_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_meta_campaign_payload("bad", -5.0, "OUTCOME_LEADS")


# ---------------------------------------------------------------------------
# build_linkedin_campaign_payload
# ---------------------------------------------------------------------------


class TestBuildLinkedInCampaignPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = build_linkedin_campaign_payload(
            "Test-LinkedIn",
            daily_budget_dollars=100.0,
            account_urn=_LINKEDIN_ACCOUNT,
        )

    def test_status_is_paused(self) -> None:
        self.assertEqual(self.payload["status"], "PAUSED")

    def test_budget_amount_is_string(self) -> None:
        # LinkedIn API requires amount as a string, not a float.
        self.assertIsInstance(self.payload["dailyBudget"]["amount"], str)

    def test_budget_value_correct(self) -> None:
        # str(round(100.0, 2)) produces "100.0" — the API accepts any decimal string.
        self.assertEqual(self.payload["dailyBudget"]["amount"], "100.0")

    def test_currency_code_default(self) -> None:
        self.assertEqual(self.payload["dailyBudget"]["currencyCode"], "USD")

    def test_custom_currency_code(self) -> None:
        p = build_linkedin_campaign_payload("x", 50.0, account_urn=_LINKEDIN_ACCOUNT, currency_code="EUR")
        self.assertEqual(p["dailyBudget"]["currencyCode"], "EUR")

    def test_account_urn_preserved(self) -> None:
        self.assertEqual(self.payload["account"], _LINKEDIN_ACCOUNT)

    def test_default_objective_type(self) -> None:
        self.assertEqual(self.payload["objectiveType"], "LEAD_GENERATION")

    def test_campaign_group_absent_when_empty(self) -> None:
        self.assertNotIn("campaignGroup", self.payload)

    def test_campaign_group_present_when_set(self) -> None:
        p = build_linkedin_campaign_payload(
            "x", 50.0, account_urn=_LINKEDIN_ACCOUNT, campaign_group_urn="urn:li:sponsoredCampaignGroup:999"
        )
        self.assertEqual(p["campaignGroup"], "urn:li:sponsoredCampaignGroup:999")

    def test_audience_expansion_default_false(self) -> None:
        self.assertFalse(self.payload["audienceExpansionEnabled"])

    def test_negative_budget_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_linkedin_campaign_payload("bad", -1.0, account_urn=_LINKEDIN_ACCOUNT)

    def test_fractional_budget_rounded_string(self) -> None:
        p = build_linkedin_campaign_payload("frac", 99.99, account_urn=_LINKEDIN_ACCOUNT)
        self.assertEqual(p["dailyBudget"]["amount"], "99.99")


# ---------------------------------------------------------------------------
# build_customer_match_audience
# ---------------------------------------------------------------------------


class TestBuildCustomerMatchAudience(unittest.TestCase):
    _RAW = ["  Alice@Example.com ", "BOB@example.COM", "charlie@example.com"]

    def setUp(self) -> None:
        self.payload = build_customer_match_audience("Test-Audience", self._RAW)

    def test_name_preserved(self) -> None:
        self.assertEqual(self.payload["name"], "Test-Audience")

    def test_member_count_matches_input(self) -> None:
        self.assertEqual(self.payload["member_count"], 3)

    def test_hash_algorithm_field(self) -> None:
        self.assertEqual(self.payload["hash_algorithm"], "sha256")

    def test_hashed_emails_count(self) -> None:
        self.assertEqual(len(self.payload["hashed_emails"]), 3)

    def test_raw_emails_not_present_in_payload(self) -> None:
        payload_str = str(self.payload)
        # Raw (un-normalised) email must not appear anywhere in the payload.
        for raw in self._RAW:
            self.assertNotIn(raw.strip(), payload_str)
        # Also verify the un-stripped, mixed-case originals are absent.
        self.assertNotIn("Alice@Example.com", payload_str)
        self.assertNotIn("BOB@example.COM", payload_str)

    def test_known_hash_of_alice(self) -> None:
        # "alice@example.com" after normalise → known SHA-256
        expected = _known_hash("  Alice@Example.com ")
        self.assertEqual(self.payload["hashed_emails"][0], expected)

    def test_known_hash_of_bob(self) -> None:
        expected = _known_hash("BOB@example.COM")
        self.assertEqual(self.payload["hashed_emails"][1], expected)

    def test_known_hash_of_charlie(self) -> None:
        expected = _known_hash("charlie@example.com")
        self.assertEqual(self.payload["hashed_emails"][2], expected)

    def test_hashes_are_hex_strings(self) -> None:
        for h in self.payload["hashed_emails"]:
            self.assertIsInstance(h, str)
            self.assertEqual(len(h), 64)  # SHA-256 → 64 hex chars
            int(h, 16)  # will raise ValueError if not valid hex

    def test_determinism(self) -> None:
        p2 = build_customer_match_audience("Test-Audience", self._RAW)
        self.assertEqual(self.payload["hashed_emails"], p2["hashed_emails"])

    def test_empty_list(self) -> None:
        p = build_customer_match_audience("empty", [])
        self.assertEqual(p["member_count"], 0)
        self.assertEqual(p["hashed_emails"], [])

    def test_normalise_helper(self) -> None:
        self.assertEqual(_normalize_email("  Alice@Example.COM  "), "alice@example.com")

    def test_sha256_helper_known_value(self) -> None:
        # Independent reference: echo -n "test@example.com" | sha256sum
        expected = hashlib.sha256(b"test@example.com").hexdigest()
        self.assertEqual(_sha256_hex("test@example.com"), expected)


# ---------------------------------------------------------------------------
# create_campaign — via FakeAdsClient
# ---------------------------------------------------------------------------


class TestCreateCampaign(unittest.TestCase):
    def _client(self, raise_on: str = "") -> FakeAdsClient:
        return FakeAdsClient(raise_on=raise_on)

    def test_google_returns_ok(self) -> None:
        client = self._client()
        payload = build_google_campaign_payload("G-test", 100.0)
        res = create_campaign(client, "google", payload)
        self.assertIsInstance(res, ExecResult)
        self.assertTrue(res.ok)
        self.assertEqual(len(client.campaign_calls), 1)

    def test_meta_returns_ok(self) -> None:
        client = self._client()
        payload = build_meta_campaign_payload("M-test", 50.0, "OUTCOME_LEADS")
        res = create_campaign(client, "meta", payload)
        self.assertTrue(res.ok)
        self.assertEqual(len(client.campaign_calls), 1)

    def test_linkedin_returns_ok(self) -> None:
        client = self._client()
        payload = build_linkedin_campaign_payload("L-test", 75.0, account_urn=_LINKEDIN_ACCOUNT)
        res = create_campaign(client, "linkedin", payload)
        self.assertTrue(res.ok)
        self.assertEqual(len(client.campaign_calls), 1)

    def test_unknown_platform_returns_ok_false(self) -> None:
        client = self._client()
        payload = build_google_campaign_payload("G-test", 10.0)
        res = create_campaign(client, "tiktok", payload)
        self.assertFalse(res.ok)
        self.assertIn("unknown platform", res.message)
        self.assertEqual(len(client.campaign_calls), 0)

    def test_client_error_returns_ok_false(self) -> None:
        client = self._client(raise_on="google")
        payload = build_google_campaign_payload("G-err", 10.0)
        res = create_campaign(client, "google", payload)
        self.assertFalse(res.ok)
        self.assertIn("error", res.message)

    def test_message_contains_campaign_name(self) -> None:
        client = self._client()
        payload = build_google_campaign_payload("My-Campaign", 10.0)
        res = create_campaign(client, "google", payload)
        self.assertIn("My-Campaign", res.message)

    def test_call_recorded_with_correct_platform(self) -> None:
        client = self._client()
        payload = build_meta_campaign_payload("M-rec", 10.0, "OUTCOME_TRAFFIC")
        create_campaign(client, "meta", payload)
        self.assertEqual(client.campaign_calls[0]["platform"], "meta")


# ---------------------------------------------------------------------------
# upload_audience — via FakeAdsClient
# ---------------------------------------------------------------------------


class TestUploadAudience(unittest.TestCase):
    def _client(self, raise_on: str = "") -> FakeAdsClient:
        return FakeAdsClient(raise_on=raise_on)

    def _audience(self) -> dict:
        return build_customer_match_audience("Warm-List", ["test@example.com", "user@example.com"])

    def test_google_returns_ok(self) -> None:
        client = self._client()
        res = upload_audience(client, "google", self._audience())
        self.assertIsInstance(res, ExecResult)
        self.assertTrue(res.ok)
        self.assertEqual(len(client.audience_calls), 1)

    def test_meta_returns_ok(self) -> None:
        client = self._client()
        res = upload_audience(client, "meta", self._audience())
        self.assertTrue(res.ok)

    def test_linkedin_returns_ok(self) -> None:
        client = self._client()
        res = upload_audience(client, "linkedin", self._audience())
        self.assertTrue(res.ok)

    def test_unknown_platform_returns_ok_false(self) -> None:
        client = self._client()
        res = upload_audience(client, "snapchat", self._audience())
        self.assertFalse(res.ok)
        self.assertIn("unknown platform", res.message)
        self.assertEqual(len(client.audience_calls), 0)

    def test_client_error_returns_ok_false(self) -> None:
        client = self._client(raise_on="linkedin")
        res = upload_audience(client, "linkedin", self._audience())
        self.assertFalse(res.ok)
        self.assertIn("error", res.message)

    def test_message_contains_audience_name(self) -> None:
        client = self._client()
        res = upload_audience(client, "google", self._audience())
        self.assertIn("Warm-List", res.message)

    def test_message_contains_member_count(self) -> None:
        client = self._client()
        res = upload_audience(client, "google", self._audience())
        self.assertIn("2", res.message)

    def test_hashed_emails_in_call_payload(self) -> None:
        client = self._client()
        audience = self._audience()
        upload_audience(client, "google", audience)
        recorded_payload = client.audience_calls[0]["payload"]
        self.assertIn("hashed_emails", recorded_payload)
        # Raw emails must NOT be present in what was sent to the client.
        self.assertNotIn("test@example.com", str(recorded_payload))

    def test_all_three_platforms(self) -> None:
        client = self._client()
        audience = self._audience()
        for platform in ("google", "meta", "linkedin"):
            res = upload_audience(client, platform, audience)
            self.assertTrue(res.ok, f"Expected ok for platform {platform!r}")
        self.assertEqual(len(client.audience_calls), 3)


# ---------------------------------------------------------------------------
# FakeAdsClient isolation tests
# ---------------------------------------------------------------------------


class TestFakeAdsClient(unittest.TestCase):
    def test_campaign_call_recorded(self) -> None:
        c = FakeAdsClient()
        payload = {"name": "test", "status": "PAUSED"}
        result = c.create_campaign("google", payload)
        self.assertEqual(len(c.campaign_calls), 1)
        self.assertEqual(c.campaign_calls[0]["platform"], "google")
        self.assertIn("id", result)

    def test_audience_call_recorded(self) -> None:
        c = FakeAdsClient()
        payload = {"name": "aud", "hashed_emails": [], "member_count": 0, "hash_algorithm": "sha256"}
        result = c.upload_audience("meta", payload)
        self.assertEqual(len(c.audience_calls), 1)
        self.assertIn("id", result)

    def test_raise_on_campaign(self) -> None:
        c = FakeAdsClient(raise_on="google")
        with self.assertRaises(RuntimeError):
            c.create_campaign("google", {})

    def test_raise_on_audience(self) -> None:
        c = FakeAdsClient(raise_on="meta")
        with self.assertRaises(RuntimeError):
            c.upload_audience("meta", {})

    def test_raise_on_does_not_affect_other_platforms(self) -> None:
        c = FakeAdsClient(raise_on="google")
        # linkedin should work fine even though google raises
        c.create_campaign("linkedin", {"name": "ok"})
        self.assertEqual(len(c.campaign_calls), 1)

    def test_no_raise_on_different_platform(self) -> None:
        c = FakeAdsClient(raise_on="meta")
        c.create_campaign("google", {})  # must not raise
        self.assertEqual(len(c.campaign_calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
