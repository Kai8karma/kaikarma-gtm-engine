"""Meta Ads reporting for the paid engine — READ side of the control loop.

ORIGINAL WORK: every line written from scratch against Meta's public Marketing
API Insights reference. No code was copied, cloned, fetched, or adapted from
any third-party repository.

NOT VALIDATED AGAINST THE LIVE API. Live execution requires real credentials,
a Meta Business Manager account, and an ad account with Insights data. A fake
'working' integration is worse than an honestly-scoped one — this file is the
latter.

Role in the loop:
    fetch_campaigns()           ← this file (READ)
        → perf_controller.run() ← decision layer
        → executor.apply()      ← write layer (meta_ads_executor.py)

Design: parse_campaigns() is PURE — no SDK, no I/O. fetch_campaigns() takes a
duck-typed client injected at call time; the facebook_business SDK is a RUNTIME
dependency never imported at module top-level. Read failures FAIL LOUD.

Expected raw-row shape from Meta Insights API:
    {
        "campaign_name": "My Campaign",
        "spend": "1234.56",           # string, major currency units (USD)
        "daily_budget": "10000",      # string, MINOR units (cents)
        "actions": [                  # optional; absent means zero conversions
            {"action_type": "lead", "value": "40"},
            {"action_type": "link_click", "value": "120"}
        ],
        "action_values": [            # optional; absent means zero revenue
            {"action_type": "lead", "value": "2000.00"},
            ...
        ]
    }

    python3 03-abm-paid-engine/meta_ads_reporting.py   # demo (fake client, zero egress)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from perf_schema import Campaign

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversion-type classification
# ---------------------------------------------------------------------------

# Meta surfaces dozens of action_type values. We classify a subset as
# "conversions" that typically represent qualified business outcomes.
# Callers running lead-gen funnels will mostly see `lead` and
# `offsite_conversion.fb_pixel_lead`; e-commerce funnels use `purchase` variants.
_CONVERSION_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "lead",
        "offsite_conversion.fb_pixel_lead",
        "offsite_conversion.fb_pixel_purchase",
        "offsite_conversion.fb_pixel_complete_registration",
        "purchase",
        "complete_registration",
    }
)


def _is_conversion(action_type: str) -> bool:
    """Return True if action_type counts as a qualified conversion."""
    return action_type in _CONVERSION_ACTION_TYPES


# ---------------------------------------------------------------------------
# Pure parser — no SDK, no I/O
# ---------------------------------------------------------------------------

def parse_campaigns(rows: list[dict[str, Any]]) -> list[Campaign]:
    """Map Meta Insights API rows to engine Campaign objects.

    PURE FUNCTION — no network I/O, no SDK. Designed so the full
    decision loop is testable without Meta credentials.

    Meta quirks handled:
    - `spend` is a string in major currency units ("1234.56") → float
    - `daily_budget` is a string in MINOR units / cents ("10000") → dollars (÷ 100)
    - `actions` is a list of {"action_type": ..., "value": "N"} dicts;
      absent ⟹ zero conversions; values summed across conversion types
    - `action_values` follows the same list shape; absent ⟹ zero revenue

    Args:
        rows: List of dicts in the shape described above. Each dict is one
              campaign's Insights row for the reporting period.

    Returns:
        List of Campaign objects, one per input row, in the same order.

    Raises:
        ValueError: If a required field is missing or unparseable, naming
                    the field and the campaign_name when available.
    """
    if not rows:
        return []

    campaigns: list[Campaign] = []
    for i, row in enumerate(rows):
        label = f"row[{i}]"  # used in errors before we have a name

        # --- required: campaign_name ---
        if "campaign_name" not in row:
            raise ValueError(f"{label}: required field 'campaign_name' is missing")
        name = row["campaign_name"]
        label = f"campaign '{name}'"

        # --- required: spend ---
        if "spend" not in row:
            raise ValueError(f"{label}: required field 'spend' is missing")
        try:
            spend = float(row["spend"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{label}: could not parse 'spend' as float — got {row['spend']!r}"
            ) from exc

        # --- required: daily_budget ---
        if "daily_budget" not in row:
            raise ValueError(f"{label}: required field 'daily_budget' is missing")
        try:
            daily_budget_cents = float(row["daily_budget"])
            daily_budget = daily_budget_cents / 100.0
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{label}: could not parse 'daily_budget' as float — got {row['daily_budget']!r}"
            ) from exc

        # --- optional: conversions from actions list ---
        conversions = 0
        for action in row.get("actions", []):
            if _is_conversion(action.get("action_type", "")):
                try:
                    conversions += int(float(action["value"]))
                except (KeyError, TypeError, ValueError):
                    # Individual bad action entries are logged but not fatal;
                    # a missing or corrupt value in one action doesn't poison
                    # the whole row's conversion count.
                    logger.warning(
                        "%s: could not parse action value %r — skipping",
                        label,
                        action,
                    )

        # --- optional: revenue from action_values list ---
        revenue = 0.0
        for av in row.get("action_values", []):
            if _is_conversion(av.get("action_type", "")):
                try:
                    revenue += float(av["value"])
                except (KeyError, TypeError, ValueError):
                    logger.warning(
                        "%s: could not parse action_value entry %r — skipping",
                        label,
                        av,
                    )

        campaigns.append(
            Campaign(
                name=name,
                spend=spend,
                conversions=conversions,
                daily_budget=daily_budget,
                revenue=revenue,
            )
        )

    return campaigns


# ---------------------------------------------------------------------------
# Thin fetch wrapper — injects the SDK client
# ---------------------------------------------------------------------------

def fetch_campaigns(
    client: Any,
    account_id: str,
    date_preset: str = "last_7d",
) -> list[Campaign]:
    """Fetch Insights rows from Meta and parse them into Campaign objects.

    The facebook_business SDK is a RUNTIME dependency; it must be injected
    as `client` and is never imported at module top-level. This keeps the
    module stdlib-only at import time and lets tests run without the SDK.

    Expected client interface (duck-typed):
        client.get_insights(
            account_id: str,
            date_preset: str,
            fields: list[str],
            level: str,
        ) -> list[dict]

    Args:
        client:      Duck-typed SDK wrapper with a get_insights() method.
        account_id:  Meta ad account ID, e.g. "act_123456789".
        date_preset: Meta date preset string, e.g. "last_7d", "last_30d",
                     "this_month". Defaults to "last_7d".

    Returns:
        List of Campaign objects for the period.

    Raises:
        RuntimeError: On any read failure from the client, with context.
                      Silently returning [] on error is dangerous — callers
                      that treat an empty list as "no spend" would then
                      mis-classify live campaigns as idle.
    """
    fields = [
        "campaign_name",
        "spend",
        "daily_budget",
        "actions",
        "action_values",
    ]
    try:
        rows: list[dict] = client.get_insights(
            account_id=account_id,
            date_preset=date_preset,
            fields=fields,
            level="campaign",
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"meta reporting: get_insights failed for account {account_id!r} "
            f"date_preset={date_preset!r} — {exc}"
        ) from exc

    logger.info(
        "meta reporting: fetched %d row(s) for account %s date_preset=%s",
        len(rows),
        account_id,
        date_preset,
    )
    return parse_campaigns(rows)


# ---------------------------------------------------------------------------
# FakeMetaReportingClient — canned rows, zero egress
# ---------------------------------------------------------------------------

@dataclass
class FakeMetaReportingClient:
    """Captures and replays canned Insights rows without any network I/O.

    Used in tests and the __main__ demo so the module is fully exercisable
    without Meta credentials.

    Args:
        canned_rows: The list of dicts returned by get_insights(). Callers
                     set this to whatever scenario they want to test.
        calls:       Populated by each get_insights() call so callers can
                     inspect what arguments were passed.
    """

    canned_rows: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def get_insights(
        self,
        account_id: str,
        date_preset: str,
        fields: list[str],
        level: str,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "account_id": account_id,
                "date_preset": date_preset,
                "fields": fields,
                "level": level,
            }
        )
        return list(self.canned_rows)  # return a copy; callers must not mutate


# ---------------------------------------------------------------------------
# Demo — zero egress, fake client
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    _DEMO_ROWS: list[dict[str, Any]] = [
        {
            "campaign_name": "Meta-ABM-warm",
            "spend": "1800.00",
            "daily_budget": "10000",     # $100.00
            "actions": [
                {"action_type": "lead", "value": "38"},
                {"action_type": "link_click", "value": "204"},  # non-conversion, ignored
            ],
            "action_values": [
                {"action_type": "lead", "value": "3800.00"},
            ],
        },
        {
            "campaign_name": "Meta-broad-TOF",
            "spend": "3500.00",
            "daily_budget": "10000",     # $100.00
            "actions": [
                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "40"},
            ],
            "action_values": [
                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "7200.00"},
            ],
        },
        {
            "campaign_name": "Meta-retarget",
            "spend": "80.00",
            "daily_budget": "4000",      # $40.00
            # no actions → zero conversions
        },
    ]

    fake_client = FakeMetaReportingClient(canned_rows=_DEMO_ROWS)
    campaigns = fetch_campaigns(fake_client, account_id="act_demo", date_preset="last_7d")

    print("Meta Ads Reporting — FakeMetaReportingClient demo (zero egress):\n")
    for c in campaigns:
        cpa = c.spend / c.conversions if c.conversions else float("inf")
        print(
            f"  {c.name:<30}  spend=${c.spend:>8.2f}  "
            f"conversions={c.conversions:>3}  daily_budget=${c.daily_budget:>6.2f}  "
            f"revenue=${c.revenue:>8.2f}  cpa=${cpa:>7.2f}"
        )

    print(f"\nfake_client.calls: {json.dumps(fake_client.calls, indent=2)}")
    print("\nSwap FakeMetaReportingClient for a real facebook_business AdAccount wrapper to go live.")
