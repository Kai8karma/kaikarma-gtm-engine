"""Google Ads reporting/fetch for the kaikarma paid engine.

ORIGINAL WORK — every line written from scratch against the public Google Ads
API shape (https://developers.google.com/google-ads/api/docs/reporting/overview
and https://developers.google.com/google-ads/api/fields/v17/campaign) and the
official `google-ads` Python SDK docs.  No code was copied, fetched, or adapted
from any third-party repository.

HONEST SCOPE:
  - This module has NOT been validated against the live Google Ads API.
  - Live execution requires real OAuth2 credentials, a Google Ads developer
    token, a customer ID, and ideally a sandbox/test account.
  - A fake "working" integration is worse than an honestly-scoped one.
    The module is complete and structurally correct; only the injected client
    determines whether results are real or simulated.

EGRESS POLICY:
  - No network I/O occurs at import time or in any pure helper.
  - The `google-ads` SDK is a RUNTIME dependency — it is injected via the
    `fetch_campaigns` `client` parameter and is NEVER imported at module
    top-level.
  - Tests and the __main__ demo run with zero third-party packages installed
    (stdlib-only, air-gapped).

RAW ROW SHAPE (what Google Ads GAQL returns via the SDK):
  Each row from a GAQL SELECT is an object whose attributes mirror the GAQL
  resource path.  In plain-dict form (as this module expects from the client):

      {
          "campaign": {
              "name": "LI-ABM Q3",
              "resource_name": "customers/123/campaigns/456",
          },
          "metrics": {
              "cost_micros": 12_000_000,       # spend in micros (USD × 1_000_000)
              "conversions": 4.0,              # fractional — round to int
              "conversions_value": 600.0,      # revenue in account currency
          },
          "campaign_budget": {
              "amount_micros": 50_000_000,     # daily budget in micros
          },
      }

SDK integration shape (google-ads 24+):
  The injected client must expose:
      client.search(customer_id, query) -> Iterable[dict]

  Where each element is a plain dict with the nested structure above.  The real
  SDK returns proto-like objects; a thin adapter (not in scope here) converts
  them.  This module's interface is intentionally duck-typed so callers wire the
  adapter that matches their SDK version.

MICROS CONVENTION:
  Google Ads stores monetary values in MICROS (1 USD = 1_000_000 micros).
  This module always converts micros → dollars before constructing Campaign
  objects:   dollars = micros / 1_000_000

Usage (live):
    from google.ads.googleads.client import GoogleAdsClient as _RealClient
    from google_ads_reporting import fetch_campaigns

    client = _RealClient.load_from_env()  # or load_from_storage(yaml_path)
    campaigns = fetch_campaigns(client, customer_id="123-456-7890")

Usage (fake / demo):
    See the `if __name__ == "__main__"` block below.
"""

from __future__ import annotations

from typing import Any

from perf_schema import Campaign

# Conversion constant — matches the one in google_ads_executor.py so the
# reporting and mutation sides agree on the same denominator.
MICROS_PER_UNIT: int = 1_000_000

# Default GAQL query used when the caller does not supply one.
# Selects the four fields this module needs for the Campaign dataclass.
DEFAULT_QUERY: str = """
    SELECT
        campaign.name,
        metrics.cost_micros,
        metrics.conversions,
        metrics.conversions_value,
        campaign_budget.amount_micros
    FROM campaign
    WHERE campaign.status = 'ENABLED'
      AND segments.date DURING LAST_30_DAYS
""".strip()


# ---------------------------------------------------------------------------
# Pure parse helper — no SDK, no network.
# ---------------------------------------------------------------------------


def _require(row: dict[str, Any], *path: str) -> Any:
    """Walk a nested dict by key path; raise ValueError naming the missing field.

    Example:
        _require(row, "metrics", "cost_micros")

    Raises ValueError if any key in the path is absent — never silently drops
    a campaign that the controller would later try to set a budget on.
    """
    node: Any = row
    for key in path:
        if not isinstance(node, dict) or key not in node:
            dotted = ".".join(path)
            raise ValueError(
                f"Required field '{dotted}' missing from reporting row: {row!r}"
            )
        node = node[key]
    return node


def parse_campaigns(rows: list[dict[str, Any]]) -> list[Campaign]:
    """Convert Google Ads GAQL rows into engine Campaign objects.

    PURE — no network, no SDK.  All monetary values arrive in MICROS and are
    divided by 1_000_000 to yield dollars.  Fractional conversions (Google may
    return 4.5 for partial cross-device attribution) are rounded to int.

    Args:
        rows: List of plain dicts shaped like a GAQL reporting row.
              See module docstring for the expected structure.

    Returns:
        List of Campaign dataclass instances in the same order as rows.

    Raises:
        ValueError: If any required field is missing from a row.  The error
            message names the missing field and includes the offending row so
            callers can trace the problem.  We raise rather than skip because
            silently dropping a campaign would cause the controller to act on
            incomplete data.
    """
    campaigns: list[Campaign] = []
    for row in rows:
        name: str = _require(row, "campaign", "name")
        cost_micros: int = _require(row, "metrics", "cost_micros")
        conversions_raw: float = _require(row, "metrics", "conversions")
        conversions_value: float = _require(row, "metrics", "conversions_value")
        budget_micros: int = _require(row, "campaign_budget", "amount_micros")

        campaigns.append(
            Campaign(
                name=name,
                spend=cost_micros / MICROS_PER_UNIT,
                conversions=round(conversions_raw),
                daily_budget=budget_micros / MICROS_PER_UNIT,
                revenue=float(conversions_value),
            )
        )
    return campaigns


# ---------------------------------------------------------------------------
# Thin fetch wrapper — injects SDK client, delegates to parse_campaigns.
# ---------------------------------------------------------------------------


def fetch_campaigns(
    client: Any,
    customer_id: str,
    query: str | None = None,
) -> list[Campaign]:
    """Fetch live campaign metrics from Google Ads via the injected client.

    Calls client.search(customer_id, query) and passes the resulting rows to
    parse_campaigns.  The SDK is a RUNTIME dependency — it must be injected by
    the caller; it is never imported at module top-level.

    FAIL LOUD CONTRACT:
        Read failures raise RuntimeError with full context so the controller
        never mistakes a fetch error for "no campaigns".  Silently returning []
        would cause the controller to see phantom "no campaigns" data and
        potentially kill all budgets.

    Args:
        client: Duck-typed client exposing:
                    client.search(customer_id: str, query: str) -> Iterable[dict]
                Use a real GoogleAdsClient adapter for live runs, or
                FakeGoogleReportingClient for tests / zero-egress demos.
        customer_id: Google Ads customer ID (e.g. "123-456-7890").
        query: GAQL SELECT statement.  Defaults to DEFAULT_QUERY when None.

    Returns:
        List of Campaign objects parsed from the reporting rows.

    Raises:
        RuntimeError: If the client.search call fails for any reason, wrapping
            the original exception with customer_id and query context.
        ValueError: Propagated from parse_campaigns if a row is malformed.
    """
    effective_query = query if query is not None else DEFAULT_QUERY
    try:
        rows: list[dict[str, Any]] = list(client.search(customer_id, effective_query))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Google Ads reporting fetch failed "
            f"[customer_id={customer_id!r}, query={effective_query[:80]!r}...]: {exc}"
        ) from exc

    return parse_campaigns(rows)


# ---------------------------------------------------------------------------
# Fake client for demo and tests (zero egress, stdlib only).
# ---------------------------------------------------------------------------


class FakeGoogleReportingClient:
    """Returns canned rows instead of calling the real API.

    Mirrors the duck-typed interface that fetch_campaigns expects:
        client.search(customer_id, query) -> list[dict]

    Zero network I/O — suitable for unit tests and zero-egress demos.

    Args:
        rows: The canned rows to return on every search() call.
        raise_on_search: If True, search() raises RuntimeError to exercise
            the fetch_campaigns error path.
    """

    def __init__(
        self,
        rows: list[dict[str, Any]],
        raise_on_search: bool = False,
    ) -> None:
        self._rows = rows
        self._raise = raise_on_search
        self.calls: list[tuple[str, str]] = []
        """Records (customer_id, query) per search() invocation."""

    def search(self, customer_id: str, query: str) -> list[dict[str, Any]]:
        """Record the call and return canned rows (or raise if configured)."""
        self.calls.append((customer_id, query))
        if self._raise:
            raise RuntimeError("Simulated reporting API error")
        return list(self._rows)


# ---------------------------------------------------------------------------
# Demo — runs zero-egress, zero-credential.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Canned GAQL-shaped rows that represent a real API response.
    CANNED_ROWS: list[dict[str, Any]] = [
        {
            "campaign": {"name": "LI-ABM-Q3", "resource_name": "customers/123/campaigns/1"},
            "metrics": {
                "cost_micros": 48_500_000,     # $48.50 spend
                "conversions": 12.0,           # exactly 12
                "conversions_value": 720.0,    # $720 revenue
            },
            "campaign_budget": {"amount_micros": 75_000_000},  # $75/day
        },
        {
            "campaign": {"name": "Meta-Retarget", "resource_name": "customers/123/campaigns/2"},
            "metrics": {
                "cost_micros": 31_250_000,     # $31.25 spend
                "conversions": 5.5,            # fractional — rounds to 6
                "conversions_value": 330.0,
            },
            "campaign_budget": {"amount_micros": 50_000_000},  # $50/day
        },
        {
            "campaign": {"name": "GGL-Branded", "resource_name": "customers/123/campaigns/3"},
            "metrics": {
                "cost_micros": 9_800_000,      # $9.80 spend
                "conversions": 0.0,
                "conversions_value": 0.0,
            },
            "campaign_budget": {"amount_micros": 20_000_000},  # $20/day
        },
    ]

    fake_client = FakeGoogleReportingClient(rows=CANNED_ROWS)
    campaigns = fetch_campaigns(fake_client, customer_id="000-000-0000")

    print("google_ads_reporting demo (FakeGoogleReportingClient — zero egress):\n")
    for c in campaigns:
        print(
            f"  {c.name:<20} spend=${c.spend:>7.2f}  "
            f"conv={c.conversions:>3}  budget/day=${c.daily_budget:>6.2f}  "
            f"revenue=${c.revenue:>7.2f}"
        )
    print(f"\n  {len(campaigns)} campaign(s) parsed.  search() called {len(fake_client.calls)} time(s).")
    print("\n  No network I/O occurred.  Swap in a real client for live execution.")
