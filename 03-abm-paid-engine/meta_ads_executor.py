"""Meta Ads executor for the paid engine — drives the facebook_business SDK.

ORIGINAL WORK: every line written from scratch against Meta's public Marketing
API reference and the official facebook_business SDK docs. No code was copied,
cloned, fetched, or adapted from any third-party repository.

NOT VALIDATED AGAINST THE LIVE API. Live execution requires real credentials,
a Meta Business Manager account, and a sandbox ad account. A fake 'working'
integration is worse than an honestly-scoped one — this file is the latter.

Design: builder functions produce plain payload dicts that are fully testable
with zero SDK imports. The SDK is a RUNTIME dependency injected as a duck-typed
client object; it is never imported at module top-level.

    python3 03-abm-paid-engine/meta_ads_executor.py   # demo (fake client, zero egress)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from executor import NO_OP, PAUSE, SET_BUDGET, Executor, ExecResult, PaidOp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Currency helpers
# ---------------------------------------------------------------------------

_USD_CENTS_PER_DOLLAR = 100


def dollars_to_minor(amount: float) -> int:
    """Convert a dollar budget to Meta's minor-currency-unit (cents).

    Meta's AdSet API requires daily_budget in the account's minor currency
    unit. For USD accounts that is cents: $120.00 → 12000.
    """
    return round(amount * _USD_CENTS_PER_DOLLAR)


# ---------------------------------------------------------------------------
# Payload builders — pure functions, no SDK required
# ---------------------------------------------------------------------------

def build_set_budget_payload(campaign_id: str, daily_budget_usd: float) -> dict[str, Any]:
    """Return the params dict for an AdSet daily_budget update.

    Meta Marketing API: PATCH /<ad_set_id>
    Fields: daily_budget (minor currency units), status preserved.

    Args:
        campaign_id:       Caller-assigned campaign name used as the AdSet ID key.
        daily_budget_usd:  New daily budget in whole/fractional USD dollars.

    Returns:
        Dict with 'ad_set_id' and 'params' ready for the SDK's AdSet.update().
    """
    return {
        "ad_set_id": campaign_id,
        "params": {
            "daily_budget": dollars_to_minor(daily_budget_usd),
        },
    }


def build_pause_payload(campaign_id: str) -> dict[str, Any]:
    """Return the params dict for pausing an AdSet (and its parent Campaign).

    Meta Marketing API: PATCH /<ad_set_id>  with status='PAUSED'.
    We surface both the AdSet and the Campaign pause so the caller can
    choose the appropriate object. The executor uses AdSet-level by default.

    Args:
        campaign_id: Caller-assigned campaign name used as the AdSet ID key.

    Returns:
        Dict with 'ad_set_id', 'campaign_id', and 'params' for SDK update().
    """
    return {
        "ad_set_id": campaign_id,
        "campaign_id": campaign_id,
        "params": {
            "status": "PAUSED",
        },
    }


# ---------------------------------------------------------------------------
# Meta Ads executor
# ---------------------------------------------------------------------------

@dataclass
class MetaAdsExecutor(Executor):
    """LIVE executor — drives Meta's facebook_business SDK via an injected client.

    ORIGINAL WORK: written from the public Meta Marketing API reference. NOT
    VALIDATED against the live API. Needs real credentials + sandbox account
    before trust. A fake 'working' integration is worse than an honest stub.

    The SDK is imported lazily (inside apply()) so this file is stdlib-only at
    import time and tests run with zero third-party packages installed.

    Args:
        client: Duck-typed object with the following interface:
            client.update_ad_set(ad_set_id: str, params: dict) -> dict
            client.update_campaign(campaign_id: str, params: dict) -> dict
        dry_run: If True, skip the client call and return a dry-run result.
                 Useful for smoke-testing the builder layer without an account.
    """

    client: Any
    dry_run: bool = False

    def apply(self, op: PaidOp) -> ExecResult:
        if op.kind == SET_BUDGET:
            return self._set_budget(op)
        if op.kind == PAUSE:
            return self._pause(op)
        if op.kind == NO_OP:
            return ExecResult(op, ok=True, message=f"meta: no-op for {op.campaign}")
        return ExecResult(op, ok=False, message=f"meta: unknown op kind {op.kind!r}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _set_budget(self, op: PaidOp) -> ExecResult:
        if op.value is None:
            return ExecResult(op, ok=False, message="meta: set_budget requires a value")

        payload = build_set_budget_payload(op.campaign, op.value)

        if self.dry_run:
            return ExecResult(
                op,
                ok=True,
                message=(
                    f"meta[dry-run]: would PATCH AdSet {payload['ad_set_id']} "
                    f"daily_budget={payload['params']['daily_budget']} cents"
                ),
            )

        try:
            result = self.client.update_ad_set(
                payload["ad_set_id"], payload["params"]
            )
            logger.info("meta set_budget ok: %s → %s cents", op.campaign, payload["params"]["daily_budget"])
            return ExecResult(
                op,
                ok=True,
                message=(
                    f"meta: AdSet {op.campaign} budget set to "
                    f"{payload['params']['daily_budget']} cents; api={result}"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("meta set_budget failed for %s: %s", op.campaign, exc)
            return ExecResult(op, ok=False, message=f"meta: set_budget error — {exc}")

    def _pause(self, op: PaidOp) -> ExecResult:
        payload = build_pause_payload(op.campaign)

        if self.dry_run:
            return ExecResult(
                op,
                ok=True,
                message=(
                    f"meta[dry-run]: would PATCH AdSet {payload['ad_set_id']} "
                    f"status=PAUSED"
                ),
            )

        try:
            result = self.client.update_ad_set(
                payload["ad_set_id"], payload["params"]
            )
            logger.info("meta pause ok: %s", op.campaign)
            return ExecResult(
                op,
                ok=True,
                message=f"meta: AdSet {op.campaign} paused; api={result}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("meta pause failed for %s: %s", op.campaign, exc)
            return ExecResult(op, ok=False, message=f"meta: pause error — {exc}")


# ---------------------------------------------------------------------------
# FakeMetaClient — records calls for tests and demo, never egresses
# ---------------------------------------------------------------------------

@dataclass
class FakeMetaClient:
    """Captures SDK-style calls without any network I/O.

    Used in tests and the __main__ demo so the module is fully exercisable
    without Meta credentials.
    """

    calls: list[dict[str, Any]] = field(default_factory=list)

    def update_ad_set(self, ad_set_id: str, params: dict[str, Any]) -> dict[str, Any]:
        entry = {"method": "update_ad_set", "ad_set_id": ad_set_id, "params": params}
        self.calls.append(entry)
        return {"id": ad_set_id, "success": True}

    def update_campaign(self, campaign_id: str, params: dict[str, Any]) -> dict[str, Any]:
        entry = {"method": "update_campaign", "campaign_id": campaign_id, "params": params}
        self.calls.append(entry)
        return {"id": campaign_id, "success": True}


# ---------------------------------------------------------------------------
# Demo — zero egress, fake client
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from executor import plan_to_ops, execute
    from perf_controller import run
    from perf_schema import Campaign, PerfPolicy

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    policy = PerfPolicy(target_cpa=50.0, account_daily_cap=400.0)
    campaigns = [
        Campaign("Meta-ABM-warm", 1800, 38, 100),    # below target CPA → scale
        Campaign("Meta-broad-TOF", 3500, 40, 100),   # over target CPA → cut
        Campaign("Meta-retarget", 80, 0, 40),         # zero conversions → kill → pause
    ]

    ops = plan_to_ops(run(campaigns, policy))
    fake = FakeMetaClient()
    executor = MetaAdsExecutor(client=fake)

    print("Decision → op → MetaAdsExecutor (FakeClient, zero egress):\n")
    for res in execute(ops, executor):
        status = "OK " if res.ok else "ERR"
        print(f"  [{status}] {res.message}")

    print(f"\nFakeMetaClient recorded {len(fake.calls)} API call(s):")
    for c in fake.calls:
        print(f"  {c}")

    no_op_count = sum(1 for o in ops if o.kind == NO_OP)
    print(f"\n  no-ops skipped (nothing sent to Meta): {no_op_count}")
    print("  Swap FakeMetaClient for a real facebook_business AdAccount client to go live.")
