"""Google Ads executor for the kaikarma paid engine.

ORIGINAL WORK — every line written from scratch against the public Google Ads API
shape (https://developers.google.com/google-ads/api/docs/campaigns/overview) and the
official `google-ads` Python SDK docs.  No code was copied, fetched, or adapted from
any third-party repository.

HONEST SCOPE:
  - This module has NOT been validated against the live Google Ads API.
  - Live execution requires real OAuth2 credentials, a Google Ads developer token,
    a customer ID, and ideally a sandbox/test account.
  - A fake "working" integration is worse than an honestly-scoped one.
    The module is complete and structurally correct; only the injected client
    (provided by the caller) determines whether mutations are real or simulated.

EGRESS POLICY:
  - No network I/O occurs at import time or in any pure helper.
  - The `google-ads` SDK is a RUNTIME dependency that is injected via the
    `GoogleAdsExecutor` constructor — it is NEVER imported at module top-level.
  - Tests run with zero third-party packages installed (stdlib-only, air-gapped).

SDK integration shape (google-ads 24+):
  Budget mutations:  client.mutate_campaign_budget(customer_id, campaign_budget_id, budget_micros)
  Campaign pauses:   client.mutate_campaign_status(customer_id, campaign_id, status)

  Budget amounts are expressed in MICROS (1 USD = 1_000_000 micros).
  Pausing a campaign uses status string "PAUSED".

Usage (live):
    from google.ads.googleads.client import GoogleAdsClient as _RealClient
    from google_ads_executor import GoogleAdsExecutor

    client = _RealClient.load_from_env()
    executor = GoogleAdsExecutor(
        client=client,
        customer_id="123-456-7890",
        campaign_ids={"LI-ABM": ("budget-001", "camp-001")},
    )
    result = executor.apply(op)

Usage (fake / demo):
    See the `if __name__ == "__main__"` block below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from executor import Executor, ExecResult, PaidOp, SET_BUDGET, PAUSE, NO_OP

# Conversion constant: Google Ads stores budgets in micros (millionths of the
# account currency unit).  Always multiply USD → micros before sending.
MICROS_PER_UNIT: int = 1_000_000

# The status string the Google Ads API accepts to pause a campaign.
_PAUSED_STATUS: str = "PAUSED"


# ---------------------------------------------------------------------------
# Pure request-builder helpers — no SDK import, fully unit-testable.
# These return plain dicts that represent what would be sent to the API.
# ---------------------------------------------------------------------------


def build_budget_payload(
    campaign_id: str,
    budget_micros: int,
) -> dict[str, Any]:
    """Return a plain-dict budget-mutation payload.

    The executor's apply() method passes this to the injected client.
    No SDK required; fully unit-testable with stdlib alone.

    Args:
        campaign_id: Logical campaign identifier (used by the executor to look
            up the real Google Ads campaign / budget resource IDs).
        budget_micros: New daily budget expressed in micros (USD × 1_000_000).

    Returns:
        {"campaign_id": ..., "budget_micros": ...}
    """
    if budget_micros < 0:
        raise ValueError(f"budget_micros must be >= 0, got {budget_micros}")
    return {"campaign_id": campaign_id, "budget_micros": budget_micros}


def dollars_to_micros(dollars: float) -> int:
    """Convert a dollar amount to Google Ads micros (integer).

    Google Ads rejects fractional micros; we round to the nearest micro.
    Raises ValueError on negative input — budgets may not be negative.
    """
    if dollars < 0:
        raise ValueError(f"Budget in dollars must be >= 0, got {dollars}")
    return round(dollars * MICROS_PER_UNIT)


def build_pause_payload(campaign_id: str) -> dict[str, Any]:
    """Return a plain-dict pause-mutation payload.

    Args:
        campaign_id: Logical campaign identifier.

    Returns:
        {"campaign_id": ..., "status": "PAUSED"}
    """
    return {"campaign_id": campaign_id, "status": _PAUSED_STATUS}


# ---------------------------------------------------------------------------
# Campaign ID registry — maps logical names to (budget_resource_id, campaign_resource_id).
# ---------------------------------------------------------------------------

CampaignRegistry = dict[str, tuple[str, str]]
"""Maps logical campaign name → (budget_resource_id, campaign_resource_id).

Example:
    {"LI-ABM": ("customers/123/campaignBudgets/456", "customers/123/campaigns/789")}
"""


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


@dataclass
class GoogleAdsExecutor(Executor):
    """Live Google Ads executor — drives the injected client, never imports the SDK.

    ORIGINAL WORK — not a copy of any third-party executor.
    NOT VALIDATED against the live API; test against a sandbox account first.

    The injected `client` must expose:
        client.mutate_campaign_budget(customer_id, budget_resource_id, budget_micros)
        client.mutate_campaign_status(customer_id, campaign_resource_id, status)

    The real `google-ads` SDK client does NOT have these exact convenience methods
    by default — you'll need a thin adapter or use the generated service clients
    directly.  This executor's interface is intentionally minimal and duck-typed
    so callers can wire the adapter that matches their SDK version.

    Args:
        client: Duck-typed Google Ads client (or FakeGoogleClient for tests/demo).
        customer_id: Google Ads customer ID (with or without dashes, e.g. "123-456-7890").
        campaign_registry: Maps logical campaign name → (budget_resource_id, campaign_resource_id).
    """

    client: Any
    customer_id: str
    campaign_registry: CampaignRegistry = field(default_factory=dict)

    def _lookup(self, campaign_name: str) -> tuple[str, str]:
        """Resolve logical name → (budget_resource_id, campaign_resource_id).

        Raises KeyError with a descriptive message if the campaign is unknown.
        """
        try:
            return self.campaign_registry[campaign_name]
        except KeyError:
            known = ", ".join(self.campaign_registry) or "(none registered)"
            raise KeyError(
                f"Campaign '{campaign_name}' not in registry.  Known: {known}.  "
                "Add it to campaign_registry before applying ops."
            ) from None

    def apply(self, op: PaidOp) -> ExecResult:
        """Apply a PaidOp to Google Ads via the injected client.

        SET_BUDGET: converts dollars → micros, calls mutate_campaign_budget.
        PAUSE:      calls mutate_campaign_status with status "PAUSED".
        NO_OP:      logs intent, makes no API call.

        Returns ExecResult(ok=True) on success, ExecResult(ok=False) on error.
        Any exception from the client is caught and surfaced in ExecResult.message
        rather than propagating — the caller may continue executing other ops.
        """
        if op.kind == NO_OP:
            return ExecResult(
                op=op,
                ok=True,
                message=f"no-op: {op.campaign} — {op.reason}",
            )

        try:
            budget_resource_id, campaign_resource_id = self._lookup(op.campaign)
        except KeyError as exc:
            return ExecResult(op=op, ok=False, message=str(exc))

        if op.kind == SET_BUDGET:
            if op.value is None:
                return ExecResult(
                    op=op,
                    ok=False,
                    message=f"SET_BUDGET for '{op.campaign}' has value=None; skipped.",
                )
            payload = build_budget_payload(
                campaign_id=op.campaign,
                budget_micros=dollars_to_micros(op.value),
            )
            try:
                self.client.mutate_campaign_budget(
                    self.customer_id,
                    budget_resource_id,
                    payload["budget_micros"],
                )
                return ExecResult(
                    op=op,
                    ok=True,
                    message=(
                        f"set_budget: {op.campaign} → "
                        f"${op.value:.2f} ({payload['budget_micros']:,} micros)"
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                return ExecResult(op=op, ok=False, message=f"mutate_campaign_budget error: {exc}")

        if op.kind == PAUSE:
            payload = build_pause_payload(campaign_id=op.campaign)
            try:
                self.client.mutate_campaign_status(
                    self.customer_id,
                    campaign_resource_id,
                    payload["status"],
                )
                return ExecResult(
                    op=op,
                    ok=True,
                    message=f"pause: {op.campaign} → {_PAUSED_STATUS}",
                )
            except Exception as exc:  # noqa: BLE001
                return ExecResult(op=op, ok=False, message=f"mutate_campaign_status error: {exc}")

        return ExecResult(
            op=op,
            ok=False,
            message=f"unknown op kind '{op.kind}'; skipped.",
        )


# ---------------------------------------------------------------------------
# Fake client for demo and tests (zero egress).
# ---------------------------------------------------------------------------


@dataclass
class FakeGoogleClient:
    """Records calls instead of sending them.  Zero network I/O — stdlib only.

    Mirrors the duck-typed interface that GoogleAdsExecutor expects.
    """

    budget_calls: list[tuple[str, str, int]] = field(default_factory=list)
    """(customer_id, budget_resource_id, budget_micros) per mutate_campaign_budget call."""

    status_calls: list[tuple[str, str, str]] = field(default_factory=list)
    """(customer_id, campaign_resource_id, status) per mutate_campaign_status call."""

    raise_on_campaign: str = ""
    """If set, raise RuntimeError when this campaign_resource_id is touched."""

    def mutate_campaign_budget(
        self,
        customer_id: str,
        budget_resource_id: str,
        budget_micros: int,
    ) -> None:
        if self.raise_on_campaign and self.raise_on_campaign in budget_resource_id:
            raise RuntimeError(f"Simulated API error for {budget_resource_id}")
        self.budget_calls.append((customer_id, budget_resource_id, budget_micros))

    def mutate_campaign_status(
        self,
        customer_id: str,
        campaign_resource_id: str,
        status: str,
    ) -> None:
        if self.raise_on_campaign and self.raise_on_campaign in campaign_resource_id:
            raise RuntimeError(f"Simulated API error for {campaign_resource_id}")
        self.status_calls.append((customer_id, campaign_resource_id, status))


# ---------------------------------------------------------------------------
# Demo — runs zero-egress, zero-credential.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from executor import plan_to_ops, execute
    from perf_controller import run
    from perf_schema import Campaign, PerfPolicy

    CUSTOMER_ID = "000-000-0000"
    REGISTRY: CampaignRegistry = {
        "LI-ABM":        ("budgets/101", "campaigns/201"),
        "Meta-broad":    ("budgets/102", "campaigns/202"),
        "Meta-retarget": ("budgets/103", "campaigns/203"),
    }

    policy = PerfPolicy(target_cpa=50.0, account_daily_cap=400.0)
    campaigns = [
        Campaign("LI-ABM",        spend=1200, conversions=40, daily_budget=100),
        Campaign("Meta-broad",    spend=3200, conversions=40, daily_budget=100),
        Campaign("Meta-retarget", spend=120,  conversions=0,  daily_budget=40),
    ]

    ops = plan_to_ops(run(campaigns, policy))
    fake_client = FakeGoogleClient()
    executor = GoogleAdsExecutor(
        client=fake_client,
        customer_id=CUSTOMER_ID,
        campaign_registry=REGISTRY,
    )

    print("GoogleAdsExecutor demo (FakeGoogleClient — zero egress):\n")
    results = execute(ops, executor)
    for res in results:
        status = "OK" if res.ok else "FAIL"
        print(f"  [{status}] {res.message}")

    print(f"\n  budget mutations recorded : {len(fake_client.budget_calls)}")
    print(f"  status mutations recorded : {len(fake_client.status_calls)}")
    print("\n  No network I/O occurred.  Swap in a real client for live execution.")
