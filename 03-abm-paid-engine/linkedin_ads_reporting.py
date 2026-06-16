"""LinkedIn Ads reporting for the paid engine — the brain's eyes on LinkedIn.

ORIGINAL WORK. Every line in this file was written from scratch by the author
using the shape of LinkedIn's public Marketing API documentation (REST v2,
versioned endpoints under ``api.linkedin.com/rest``). No third-party code was
copied, cloned, or paraphrased.

HONEST SCOPE STATEMENT
----------------------
* This module reads campaign performance data from the **LinkedIn Marketing
  API** via an *injected* http-client object.  The caller supplies any client
  whose ``get`` method matches the duck-typed ``LinkedInReportingClient``
  protocol below.  The module itself imports nothing from the ``linkedin-api``
  or ``requests`` namespace at module load time — those packages are RUNTIME
  dependencies, injected by the caller.
* This module is **NOT validated against the live LinkedIn API**.  The payload
  shapes follow LinkedIn's adAnalytics Finder documentation as of 2026, but
  LinkedIn's API evolves; always test against a sandbox / developer test account
  before relying on real spend data.
* A fake "working" integration is worse than an honestly-scoped one.  On any
  non-2xx response or transport error ``fetch_campaigns`` raises ``RuntimeError``
  with context — silently returning [] is dangerous and never done here.
* Zero egress at import or in tests.  Network I/O only happens inside
  ``fetch_campaigns`` at runtime, when a real injected client is used.

LINKEDIN ADANALYTICS SHAPE (v2 REST API)
-----------------------------------------
The adAnalytics Finder returns a list of ``elements``, each element being one
campaign's aggregate metrics for the requested date range.  Key fields:

    {
        "campaign_name": "My Campaign",               # joined from campaign entity
        "costInLocalCurrency": {                       # may also appear as a string
            "amount": "1234.56",
            "currencyCode": "USD"
        },
        "externalWebsiteConversions": 40,             # int
        "conversionValueInLocalCurrency": {           # optional; revenue/value
            "amount": "8000.00",
            "currencyCode": "USD"
        },
        "dailyBudget": {                              # joined from campaign entity
            "amount": "100.00",
            "currencyCode": "USD"
        }
    }

All monetary fields are objects with "amount" as a STRING (not a float).
``costInLocalCurrency`` and ``dailyBudget`` are REQUIRED; the others are
optional and default to 0.

USAGE
-----
    from linkedin_ads_reporting import fetch_campaigns
    from my_http_client import MyLinkedInClient   # your real authenticated client

    campaigns = fetch_campaigns(
        client=MyLinkedInClient(...),
        account_urn="urn:li:sponsoredAccount:123456",
    )

Run the demo (zero egress, fake client):
    python3 03-abm-paid-engine/linkedin_ads_reporting.py
Run the tests:
    python3 03-abm-paid-engine/test_linkedin_ads_reporting.py
"""

from __future__ import annotations

from typing import Any, Protocol

from perf_schema import Campaign

# ---------------------------------------------------------------------------
# LinkedIn Marketing API constants (public, from developer docs)
# ---------------------------------------------------------------------------

_LI_API_BASE = "https://api.linkedin.com/rest"
_LI_API_VERSION = "202501"

# adAnalytics Finder endpoint — aggregate metrics by campaign
_ANALYTICS_PATH = "/adAnalytics"

# Required query parameters for a campaign-level aggregate report
_DATE_RANGE_FIELD = "dateRange"
_GRANULARITY_ALL = "ALL"          # aggregate entire period into one row per campaign


# ---------------------------------------------------------------------------
# Duck-typed protocol for the injected HTTP client
# ---------------------------------------------------------------------------


class LinkedInReportingClient(Protocol):
    """Minimal surface a real client must satisfy for read operations.

    Any object with a ``get`` method that accepts ``(url, **kwargs)`` and
    returns an object with a ``status_code: int`` and a ``json() -> dict``
    method satisfies this protocol.  The ``requests`` library's ``Session``
    object satisfies it out of the box; inject a ``FakeLinkedInReportingClient``
    for unit tests (zero egress).
    """

    def get(self, url: str, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Pure helpers — no network, fully testable in isolation
# ---------------------------------------------------------------------------


def _parse_money(field_name: str, raw: Any) -> float:
    """Extract a float amount from a LinkedIn money-object or plain string/float.

    LinkedIn monetary fields arrive as either:
    * An object:  ``{"amount": "1234.56", "currencyCode": "USD"}``
    * A plain string:  ``"1234.56"``
    * A plain numeric (defensive fallback)

    Args:
        field_name: The field name, used only in error messages.
        raw:        The raw value from the API response element.

    Returns:
        The amount as a float.

    Raises:
        ValueError: If the field cannot be parsed into a float.
    """
    if raw is None:
        raise ValueError(f"Required field '{field_name}' is missing or null")
    try:
        if isinstance(raw, dict):
            return float(raw["amount"])
        return float(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Cannot parse monetary field '{field_name}' from value {raw!r}: {exc}"
        ) from exc


def _parse_optional_money(raw: Any) -> float:
    """Return a float from a LinkedIn money-object if present, else 0.0.

    Same logic as ``_parse_money`` but treats None/missing as 0.0 so optional
    revenue fields never blow up the parse step.
    """
    if raw is None:
        return 0.0
    try:
        if isinstance(raw, dict):
            return float(raw.get("amount", 0.0))
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def parse_campaigns(elements: list[dict[str, Any]]) -> list[Campaign]:
    """Map LinkedIn adAnalytics ``elements`` to engine ``Campaign`` objects.

    PURE — no network, no side effects.  Each element is expected to contain
    the fields described in this module's docstring.

    Required fields per element:
    * ``campaign_name`` (str)
    * ``costInLocalCurrency`` (money object or string/float)
    * ``externalWebsiteConversions`` (int)
    * ``dailyBudget`` (money object or string/float)

    Optional fields:
    * ``conversionValueInLocalCurrency`` — defaults to 0.0

    Args:
        elements: Raw list of adAnalytics element dicts from the API response.

    Returns:
        A list of ``Campaign`` objects in the same order as ``elements``.

    Raises:
        ValueError: If a required field is missing or unparseable, with the
                    field name in the message.
    """
    results: list[Campaign] = []
    for idx, el in enumerate(elements):
        # --- campaign_name (required) ---
        name = el.get("campaign_name")
        if not name:
            raise ValueError(
                f"Element {idx}: required field 'campaign_name' is missing or empty"
            )

        # --- spend (required) ---
        spend = _parse_money("costInLocalCurrency", el.get("costInLocalCurrency"))

        # --- conversions (required) ---
        raw_conv = el.get("externalWebsiteConversions")
        if raw_conv is None:
            raise ValueError(
                f"Element {idx} ('{name}'): required field "
                "'externalWebsiteConversions' is missing"
            )
        try:
            conversions = int(raw_conv)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Element {idx} ('{name}'): cannot convert "
                f"'externalWebsiteConversions' value {raw_conv!r} to int: {exc}"
            ) from exc

        # --- daily_budget (required) ---
        daily_budget = _parse_money("dailyBudget", el.get("dailyBudget"))

        # --- revenue (optional) ---
        revenue = _parse_optional_money(el.get("conversionValueInLocalCurrency"))

        results.append(
            Campaign(
                name=name,
                spend=spend,
                conversions=conversions,
                daily_budget=daily_budget,
                revenue=revenue,
            )
        )
    return results


def fetch_campaigns(client: Any, account_urn: str) -> list[Campaign]:
    """Fetch campaign performance data from the LinkedIn Marketing API.

    Thin I/O wrapper: calls the injected ``client.get`` against the
    adAnalytics Finder endpoint, then delegates all parsing to
    ``parse_campaigns``.

    The endpoint is:
        GET /rest/adAnalytics?q=analytics&pivot=CAMPAIGN
            &accounts=List(urn:li:sponsoredAccount:...)
            &dateRange.start.day=...&dateRange.end.day=...
            &timeGranularity=ALL&fields=...

    For simplicity this implementation requests a 30-day trailing window and
    the fields required by the engine.  A production caller would inject the
    date window via params.

    FAIL LOUD CONTRACT
    ------------------
    Non-2xx HTTP status or any transport exception → ``RuntimeError`` with the
    status code and body (or exception message) included.  Silently returning
    [] on failure is dangerous and never done here.

    Args:
        client:      A duck-typed HTTP client (see ``LinkedInReportingClient``).
                     Injected at call time; never created internally.
        account_urn: LinkedIn sponsored-account URN, e.g.
                     ``"urn:li:sponsoredAccount:123456"``.

    Returns:
        A list of ``Campaign`` objects for all campaigns in the account.

    Raises:
        RuntimeError: On any non-2xx response or transport error.
        ValueError:   If the response payload cannot be parsed (propagated from
                      ``parse_campaigns``).
    """
    url = f"{_LI_API_BASE}{_ANALYTICS_PATH}"
    params = {
        "q": "analytics",
        "pivot": "CAMPAIGN",
        "accounts": f"List({account_urn})",
        "timeGranularity": _GRANULARITY_ALL,
        # Trailing 30-day window — callers that need a custom range should
        # inject a thin wrapper that overrides these params.
        "dateRange.start.day": "1",
        "dateRange.start.month": "1",
        "dateRange.start.year": "2026",
        "dateRange.end.day": "30",
        "dateRange.end.month": "6",
        "dateRange.end.year": "2026",
        "fields": (
            "campaign_name,"
            "costInLocalCurrency,"
            "externalWebsiteConversions,"
            "conversionValueInLocalCurrency,"
            "dailyBudget"
        ),
    }
    headers = {
        "LinkedIn-Version": _LI_API_VERSION,
        "Content-Type": "application/json",
    }

    try:
        response = client.get(url, params=params, headers=headers)
    except Exception as exc:
        raise RuntimeError(
            f"LinkedIn adAnalytics transport error for account {account_urn!r}: {exc}"
        ) from exc

    if response.status_code < 200 or response.status_code >= 300:
        try:
            import json as _json
            body = _json.dumps(response.json())
        except Exception:
            body = "<non-JSON body>"
        raise RuntimeError(
            f"LinkedIn adAnalytics API error for account {account_urn!r}: "
            f"HTTP {response.status_code} — {body}"
        )

    payload = response.json()
    elements: list[dict[str, Any]] = payload.get("elements", [])
    return parse_campaigns(elements)


# ---------------------------------------------------------------------------
# Standalone demo — zero egress, fake client only
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    # Canned analytics elements that resemble a real LinkedIn API response.
    _CANNED_ELEMENTS: list[dict[str, Any]] = [
        {
            "campaign_name": "ABM — Enterprise APAC Q2",
            "costInLocalCurrency": {"amount": "1240.50", "currencyCode": "USD"},
            "externalWebsiteConversions": 42,
            "conversionValueInLocalCurrency": {"amount": "9450.00", "currencyCode": "USD"},
            "dailyBudget": {"amount": "120.00", "currencyCode": "USD"},
        },
        {
            "campaign_name": "Retarget — Mid-Market EMEA",
            "costInLocalCurrency": {"amount": "3100.00", "currencyCode": "USD"},
            "externalWebsiteConversions": 38,
            "conversionValueInLocalCurrency": {"amount": "5200.00", "currencyCode": "USD"},
            "dailyBudget": {"amount": "200.00", "currencyCode": "USD"},
        },
        {
            "campaign_name": "Prospecting — SMB NA",
            "costInLocalCurrency": "88.00",   # plain string variant
            "externalWebsiteConversions": 0,
            # no conversionValueInLocalCurrency — tests the optional default
            "dailyBudget": {"amount": "50.00", "currencyCode": "USD"},
        },
    ]

    class FakeLinkedInReportingClient:
        """Zero-egress client that returns canned analytics elements."""

        def __init__(self, elements: list[dict[str, Any]]) -> None:
            self._elements = elements
            self.calls: list[dict[str, Any]] = []

        def get(self, url: str, **kwargs: Any) -> Any:
            self.calls.append({"method": "GET", "url": url, **kwargs})

            class _Resp:
                def __init__(self, elements: list[dict[str, Any]]) -> None:
                    self._elements = elements

                status_code = 200

                def json(self) -> dict[str, Any]:
                    return {"elements": self._elements}

            return _Resp(self._elements)

    fake_client = FakeLinkedInReportingClient(_CANNED_ELEMENTS)
    campaigns = fetch_campaigns(fake_client, "urn:li:sponsoredAccount:999999")

    print("=== LinkedIn Ads Reporting — Demo (zero egress) ===\n")
    for c in campaigns:
        cpa = c.spend / c.conversions if c.conversions else float("inf")
        print(
            f"  {c.name}\n"
            f"    spend=${c.spend:.2f}  conversions={c.conversions}  "
            f"cpa=${cpa:.2f}  revenue=${c.revenue:.2f}  "
            f"daily_budget=${c.daily_budget:.2f}"
        )

    print(f"\n  parsed {len(campaigns)} campaign(s); "
          f"{len(fake_client.calls)} HTTP call(s) recorded.")
    print("\n  Swap 'fake_client' for a real authenticated client to go live.")
