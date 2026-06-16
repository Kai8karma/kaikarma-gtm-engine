"""Ad campaign-creation and audience-upload builders for the kaikarma paid engine.

ORIGINAL WORK — every line written from scratch using the public API documentation
for Google Ads, Meta Marketing API, and LinkedIn Marketing API.  No code was
copied, cloned, fetched, or adapted from any third-party repository (including
ivangfalco/ads-skills or any unlicensed repo).

HONEST SCOPE:
  - Builder functions are pure-dict factories; they produce the payload shape the
    platforms expect but do NOT validate it against a live API.
  - All campaigns are created PAUSED by default — matching the executors' safety
    stance: humans review before enabling spend.
  - Audience upload hashes emails with SHA-256 (lowercase+strip first) per each
    platform's Customer Match / Custom Audience privacy requirement.  The raw email
    never leaves this process.

EGRESS POLICY:
  - No network I/O at import time or in any pure helper.
  - The SDK / HTTP client is ALWAYS injected by the caller.  Tests run with a
    FakeAdsClient — zero egress, zero credentials, stdlib-only.

Platform API references (public docs, no third-party code used):
  - Google Ads: https://developers.google.com/google-ads/api/docs/campaigns/overview
                https://developers.google.com/google-ads/api/docs/remarketing/audience-types/customer-match
  - Meta:       https://developers.facebook.com/docs/marketing-api/campaigns
                https://developers.facebook.com/docs/marketing-api/audiences/guides/custom-audiences
  - LinkedIn:   https://learn.microsoft.com/en-us/linkedin/marketing/integrations/ads/account-structure/create-and-manage-campaigns
                https://learn.microsoft.com/en-us/linkedin/marketing/integrations/matched-audiences/matched-audiences

Usage (demo — zero egress):
    python3 03-abm-paid-engine/ads_campaigns.py
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from executor import ExecResult, PaidOp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Google Ads stores budget amounts in micros (1 USD = 1_000_000 micros).
_GOOGLE_MICROS_PER_DOLLAR: int = 1_000_000

# Meta Marketing API stores daily budgets in the account's minor currency unit
# (cents for USD accounts: $1.00 = 100 cents).
_META_CENTS_PER_DOLLAR: int = 100

# All platforms use the string "PAUSED" to denote a paused / inactive campaign.
_STATUS_PAUSED = "PAUSED"


# ---------------------------------------------------------------------------
# Platform-specific campaign payload builders — pure functions, no SDK needed
# ---------------------------------------------------------------------------


def build_google_campaign_payload(
    name: str,
    daily_budget_dollars: float,
    *,
    advertising_channel_type: str = "SEARCH",
    bidding_strategy_type: str = "MANUAL_CPC",
) -> dict[str, Any]:
    """Return a plain-dict Google Ads campaign-creation payload.

    Google Ads API shape (google-ads v14+):
      POST /customers/{customer_id}/campaigns:mutate
      The CampaignBudget is a separate resource; the caller must create/link it.
      Budget is in MICROS (USD × 1_000_000).

    Args:
        name:                    Human-readable campaign name.
        daily_budget_dollars:    Daily budget in USD.  Converted to micros internally.
        advertising_channel_type: e.g. "SEARCH", "DISPLAY", "VIDEO".  Defaults to "SEARCH".
        bidding_strategy_type:   e.g. "MANUAL_CPC", "TARGET_CPA".  Defaults to "MANUAL_CPC".

    Returns:
        Dict representing the campaign resource fields for the mutate request.
        status is always "PAUSED" — humans enable spend deliberately.
    """
    if daily_budget_dollars < 0:
        raise ValueError(f"daily_budget_dollars must be >= 0, got {daily_budget_dollars}")
    return {
        "name": name,
        "status": _STATUS_PAUSED,
        "advertising_channel_type": advertising_channel_type,
        "campaign_budget": {
            "amount_micros": round(daily_budget_dollars * _GOOGLE_MICROS_PER_DOLLAR),
            "delivery_method": "STANDARD",
        },
        "bidding_strategy_type": bidding_strategy_type,
    }


def build_meta_campaign_payload(
    name: str,
    daily_budget_dollars: float,
    objective: str,
    *,
    special_ad_categories: list[str] | None = None,
    buying_type: str = "AUCTION",
) -> dict[str, Any]:
    """Return a plain-dict Meta Marketing API campaign-creation payload.

    Meta Marketing API v20+ shape:
      POST /{ad_account_id}/campaigns
      daily_budget is in minor currency units (cents for USD: $1.00 = 100).
      Campaign is created at campaign level; AdSet inherits budget unless overridden.

    Args:
        name:                  Campaign name.
        daily_budget_dollars:  Daily budget in USD.  Converted to cents internally.
        objective:             Meta campaign objective, e.g. "OUTCOME_LEADS",
                               "OUTCOME_TRAFFIC", "OUTCOME_AWARENESS".
        special_ad_categories: Required list for regulated verticals; defaults to [].
        buying_type:           "AUCTION" (default) or "RESERVED".

    Returns:
        Dict suitable for the Meta API campaigns endpoint body.
        status is always "PAUSED".
    """
    if daily_budget_dollars < 0:
        raise ValueError(f"daily_budget_dollars must be >= 0, got {daily_budget_dollars}")
    return {
        "name": name,
        "objective": objective,
        "status": _STATUS_PAUSED,
        "buying_type": buying_type,
        "daily_budget": round(daily_budget_dollars * _META_CENTS_PER_DOLLAR),
        "special_ad_categories": special_ad_categories if special_ad_categories is not None else [],
    }


def build_linkedin_campaign_payload(
    name: str,
    daily_budget_dollars: float,
    *,
    account_urn: str,
    currency_code: str = "USD",
    campaign_group_urn: str = "",
    objective_type: str = "LEAD_GENERATION",
    audience_expansion_enabled: bool = False,
) -> dict[str, Any]:
    """Return a plain-dict LinkedIn Marketing API campaign-creation payload.

    LinkedIn Marketing API v2 shape (REST, versioned endpoints):
      POST /rest/adCampaigns
      dailyBudget.amount is a string (the API requires string, not float).
      Campaign is created PAUSED; the caller activates deliberately.

    Args:
        name:                       Campaign name.
        daily_budget_dollars:       Daily budget in the account currency.
        account_urn:                Sponsored-account URN, e.g.
                                    "urn:li:sponsoredAccount:123456".
        currency_code:              ISO-4217 code matching the account, e.g. "USD".
        campaign_group_urn:         Parent campaign group URN.  Optional — LinkedIn
                                    assigns a default group if omitted.
        objective_type:             e.g. "LEAD_GENERATION", "WEBSITE_CONVERSIONS",
                                    "BRAND_AWARENESS".  Defaults to "LEAD_GENERATION".
        audience_expansion_enabled: Whether LinkedIn may expand the target audience.

    Returns:
        Dict body for the adCampaigns POST endpoint.
        status is always "PAUSED".
    """
    if daily_budget_dollars < 0:
        raise ValueError(f"daily_budget_dollars must be >= 0, got {daily_budget_dollars}")
    payload: dict[str, Any] = {
        "name": name,
        "account": account_urn,
        "status": _STATUS_PAUSED,
        "type": "SPONSORED_UPDATES",
        "objectiveType": objective_type,
        "dailyBudget": {
            "amount": str(round(daily_budget_dollars, 2)),
            "currencyCode": currency_code,
        },
        "audienceExpansionEnabled": audience_expansion_enabled,
    }
    if campaign_group_urn:
        payload["campaignGroup"] = campaign_group_urn
    return payload


# ---------------------------------------------------------------------------
# Customer Match / Custom Audience upload builder
# ---------------------------------------------------------------------------


def _normalize_email(email: str) -> str:
    """Lowercase and strip whitespace from an email address."""
    return email.strip().lower()


def _sha256_hex(value: str) -> str:
    """Return the lowercase hex SHA-256 digest of a UTF-8 string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_customer_match_audience(
    name: str,
    emails: list[str],
) -> dict[str, Any]:
    """Return a platform-agnostic customer-match audience payload.

    Privacy requirement: raw emails MUST NOT leave this process.  We
    normalise (lowercase + strip) then SHA-256 hash each email before
    including it in the payload — matching the requirement shared by the
    Google Ads Customer Match, Meta Custom Audiences, and LinkedIn Matched
    Audiences APIs.

    Args:
        name:   Audience name shown in the ad platform UI.
        emails: List of raw email strings.  May contain leading/trailing
                whitespace and mixed case — normalised before hashing.

    Returns:
        Dict with:
          - "name":            the audience name
          - "hashed_emails":   list of lowercase-hex SHA-256 digests
          - "member_count":    count of hashed members
          - "hash_algorithm":  "sha256" (for the caller's audit trail)
        Raw emails are never present in the returned dict.
    """
    hashed = [_sha256_hex(_normalize_email(e)) for e in emails]
    return {
        "name": name,
        "hashed_emails": hashed,
        "member_count": len(hashed),
        "hash_algorithm": "sha256",
    }


# ---------------------------------------------------------------------------
# Platform constants used by create_campaign / upload_audience
# ---------------------------------------------------------------------------

_SUPPORTED_PLATFORMS = {"google", "meta", "linkedin"}


# ---------------------------------------------------------------------------
# Injected-client API surface: create_campaign / upload_audience
# ---------------------------------------------------------------------------


def create_campaign(
    client: Any,
    platform: str,
    payload: dict[str, Any],
) -> ExecResult:
    """Submit a campaign-creation payload via the injected client.

    The client is called lazily — it is never touched at import time.
    Any exception from the client is caught and returned as ok=False,
    matching the executor error contract (never raise to the caller).

    Args:
        client:   Duck-typed client.  Must expose:
                    client.create_campaign(platform: str, payload: dict) -> dict
                  The FakeAdsClient in __main__ satisfies this interface.
        platform: One of "google", "meta", "linkedin".  Case-sensitive.
        payload:  The dict produced by one of the build_*_campaign_payload helpers.

    Returns:
        ExecResult with ok=True on success, ok=False on error or unknown platform.
    """
    _sentinel_op = PaidOp(kind="create_campaign", campaign=payload.get("name", ""), value=None, reason="")

    if platform not in _SUPPORTED_PLATFORMS:
        return ExecResult(
            op=_sentinel_op,
            ok=False,
            message=f"create_campaign: unknown platform {platform!r}; supported: {sorted(_SUPPORTED_PLATFORMS)}",
        )
    try:
        result = client.create_campaign(platform, payload)
        return ExecResult(
            op=_sentinel_op,
            ok=True,
            message=f"create_campaign[{platform}]: {payload.get('name', '?')} → {result}",
        )
    except Exception as exc:  # noqa: BLE001
        return ExecResult(
            op=_sentinel_op,
            ok=False,
            message=f"create_campaign[{platform}] error: {exc}",
        )


def upload_audience(
    client: Any,
    platform: str,
    payload: dict[str, Any],
) -> ExecResult:
    """Submit an audience payload via the injected client.

    The payload must have been produced by build_customer_match_audience —
    raw emails must not be present; only hashed_emails.

    Args:
        client:   Duck-typed client.  Must expose:
                    client.upload_audience(platform: str, payload: dict) -> dict
        platform: One of "google", "meta", "linkedin".  Case-sensitive.
        payload:  The dict produced by build_customer_match_audience.

    Returns:
        ExecResult with ok=True on success, ok=False on error or unknown platform.
    """
    _sentinel_op = PaidOp(kind="upload_audience", campaign=payload.get("name", ""), value=None, reason="")

    if platform not in _SUPPORTED_PLATFORMS:
        return ExecResult(
            op=_sentinel_op,
            ok=False,
            message=f"upload_audience: unknown platform {platform!r}; supported: {sorted(_SUPPORTED_PLATFORMS)}",
        )
    try:
        result = client.upload_audience(platform, payload)
        return ExecResult(
            op=_sentinel_op,
            ok=False if not result else True,
            message=f"upload_audience[{platform}]: {payload.get('name', '?')} ({payload.get('member_count', '?')} members) → {result}",
        )
    except Exception as exc:  # noqa: BLE001
        return ExecResult(
            op=_sentinel_op,
            ok=False,
            message=f"upload_audience[{platform}] error: {exc}",
        )


# ---------------------------------------------------------------------------
# FakeAdsClient — records calls, zero egress (used in tests + __main__ demo)
# ---------------------------------------------------------------------------


@dataclass
class FakeAdsClient:
    """Records campaign-creation and audience-upload calls without any network I/O.

    Used in tests and the __main__ demo.  Satisfies the duck-typed client
    interface expected by create_campaign() and upload_audience().

    Set raise_on to a platform name to simulate a client error for that platform.
    """

    campaign_calls: list[dict[str, Any]] = field(default_factory=list)
    audience_calls: list[dict[str, Any]] = field(default_factory=list)
    raise_on: str = ""  # if set, raise RuntimeError when this platform is called

    def create_campaign(self, platform: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.raise_on and self.raise_on == platform:
            raise RuntimeError(f"Simulated client error for platform {platform!r}")
        entry = {"platform": platform, "payload": payload}
        self.campaign_calls.append(entry)
        return {"id": f"fake-campaign-{len(self.campaign_calls)}", "status": "PAUSED"}

    def upload_audience(self, platform: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.raise_on and self.raise_on == platform:
            raise RuntimeError(f"Simulated client error for platform {platform!r}")
        entry = {"platform": platform, "payload": payload}
        self.audience_calls.append(entry)
        return {"id": f"fake-audience-{len(self.audience_calls)}", "member_count": payload.get("member_count", 0)}


# ---------------------------------------------------------------------------
# Demo — zero egress, FakeAdsClient
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== ads_campaigns.py demo (FakeAdsClient — zero egress) ===\n")

    fake = FakeAdsClient()

    # --- Campaign creation ---
    google_payload = build_google_campaign_payload("GTM-Google-ABM", daily_budget_dollars=150.0)
    meta_payload = build_meta_campaign_payload(
        "GTM-Meta-ABM",
        daily_budget_dollars=200.0,
        objective="OUTCOME_LEADS",
    )
    linkedin_payload = build_linkedin_campaign_payload(
        "GTM-LinkedIn-ABM",
        daily_budget_dollars=100.0,
        account_urn="urn:li:sponsoredAccount:999000",
    )

    print("Campaign creation results:")
    for platform, payload in [
        ("google", google_payload),
        ("meta", meta_payload),
        ("linkedin", linkedin_payload),
    ]:
        res = create_campaign(fake, platform, payload)
        status = "OK " if res.ok else "ERR"
        print(f"  [{status}] {res.message}")

    print(f"\n  Campaigns recorded by fake client: {len(fake.campaign_calls)}")
    for c in fake.campaign_calls:
        camp = c["payload"]
        print(f"    {c['platform']:10s}  name={camp['name']}  status={camp['status']}")

    # --- Audience upload ---
    raw_emails = ["  Alice@Example.com ", "BOB@example.COM", "charlie@example.com"]
    audience_payload = build_customer_match_audience("GTM-Q3-Warm-List", raw_emails)

    print("\nAudience upload results:")
    for platform in ("google", "meta", "linkedin"):
        res = upload_audience(fake, platform, audience_payload)
        status = "OK " if res.ok else "ERR"
        print(f"  [{status}] {res.message}")

    print(f"\n  Audience uploads recorded: {len(fake.audience_calls)}")
    print(f"  Hashed email count (raw emails never stored): {audience_payload['member_count']}")
    print(f"  Hash algorithm: {audience_payload['hash_algorithm']}")
    print(f"  Sample hash:    {audience_payload['hashed_emails'][0][:32]}...")

    # --- Unknown platform guard ---
    print("\nUnknown platform guard:")
    res = create_campaign(fake, "tiktok", google_payload)
    print(f"  [{'ERR' if not res.ok else 'OK '}] {res.message}")

    print("\n  No network I/O occurred.  Swap FakeAdsClient for a real client to go live.")
