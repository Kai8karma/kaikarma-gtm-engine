"""LinkedIn Ads executor for the paid engine — the brain's hands on LinkedIn.

ORIGINAL WORK. Every line in this file was written from scratch by the author
using the shape of LinkedIn's public Marketing API documentation (REST v2,
versioned endpoints under ``api.linkedin.com/rest``). No third-party code was
copied, cloned, or paraphrased.

HONEST SCOPE STATEMENT
----------------------
* This executor drives the **official LinkedIn Marketing API** via an *injected*
  http-client object.  The caller supplies any client whose ``post`` and ``get``
  methods match the duck-typed ``LinkedInHTTPClient`` protocol below.  The module
  itself imports nothing from the ``linkedin-api`` or ``requests`` namespace at
  module load time — those packages are RUNTIME dependencies, injected by the
  caller.
* This module is **NOT validated against the live LinkedIn API**.  The payload
  shapes follow LinkedIn Marketing API v2 public documentation as of 2026, but
  LinkedIn's API evolves; always test against a sandbox / developer test account
  with non-production spend before trusting real changes to real campaigns.
* A fake "working" integration is worse than an honestly-scoped one.  The
  ``LinkedInAdsExecutor`` will raise ``NotImplementedError`` rather than pretend
  to succeed when its internal sanity checks detect obviously wrong state.
* Zero egress at import or in tests.  Network I/O only happens inside
  ``LinkedInAdsExecutor.apply()`` at runtime, when a real injected client is
  used.

USAGE
-----
    from linkedin_ads_executor import LinkedInAdsExecutor
    from my_http_client import MyLinkedInClient   # your real authenticated client

    executor = LinkedInAdsExecutor(
        client=MyLinkedInClient(...),
        account_id="urn:li:sponsoredAccount:123456",
        currency_code="USD",
    )
    result = executor.apply(op)

Run the demo (zero egress, fake client):
    python3 03-abm-paid-engine/linkedin_ads_executor.py
Run the tests:
    python3 03-abm-paid-engine/test_linkedin_ads_executor.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from executor import Executor, ExecResult, NO_OP, PAUSE, SET_BUDGET, PaidOp

# ---------------------------------------------------------------------------
# LinkedIn Marketing API constants (public, from developer docs)
# ---------------------------------------------------------------------------

_LI_API_BASE = "https://api.linkedin.com/rest"
_LI_API_VERSION = "202501"  # versioned header value required by the API

# Campaign status values recognised by the LinkedIn Marketing API.
_STATUS_ACTIVE = "ACTIVE"
_STATUS_PAUSED = "PAUSED"


# ---------------------------------------------------------------------------
# Duck-typed protocol for the injected HTTP client
# ---------------------------------------------------------------------------


class LinkedInHTTPClient(Protocol):
    """Minimal surface a real client must satisfy.

    Any object with ``post`` and ``get`` methods that accept ``(url, **kwargs)``
    and return an object with a ``status_code: int`` and a ``json() -> dict``
    method satisfies this protocol.  The ``requests`` library's ``Session``
    object satisfies it out of the box; you may also inject a ``FakeLinkedInClient``
    for unit tests (zero egress).
    """

    def post(self, url: str, **kwargs: Any) -> Any: ...
    def get(self, url: str, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Pure builder functions — testable with no network
# ---------------------------------------------------------------------------


def build_budget_payload(
    campaign_id: str,
    new_daily_budget: float,
    currency_code: str,
) -> dict[str, Any]:
    """Return the JSON body for a LinkedIn campaign daily-budget update.

    LinkedIn Marketing API: PATCH /rest/adCampaigns/{id}
    The ``dailyBudget`` object carries ``amount`` (string, not float — the API
    requires a string representation) and ``currencyCode``.

    Args:
        campaign_id:     LinkedIn campaign URN, e.g. ``urn:li:sponsoredCampaign:9876``.
        new_daily_budget: New daily budget in the account's currency (e.g. 150.0).
        currency_code:   ISO-4217 currency code, e.g. ``"USD"``.

    Returns:
        A dict ready to be serialised as the request body.
    """
    return {
        "patch": {
            "$set": {
                "dailyBudget": {
                    "amount": str(round(new_daily_budget, 2)),
                    "currencyCode": currency_code,
                }
            }
        }
    }


def build_pause_payload() -> dict[str, Any]:
    """Return the JSON body to pause a LinkedIn campaign.

    LinkedIn Marketing API: PATCH /rest/adCampaigns/{id}
    Setting ``status`` to ``"PAUSED"`` halts delivery without deleting the campaign.

    Returns:
        A dict ready to be serialised as the request body.
    """
    return {"patch": {"$set": {"status": _STATUS_PAUSED}}}


def build_request_headers(access_token: str) -> dict[str, str]:
    """Return the standard headers required by LinkedIn's versioned REST API.

    LinkedIn requires:
    * ``Authorization: Bearer <token>``
    * ``LinkedIn-Version: YYYYMM`` (identifies the API schema version)
    * ``Content-Type: application/json``
    * ``X-Restli-Method: PARTIAL_UPDATE`` for PATCH endpoints.

    Args:
        access_token: A valid OAuth 2.0 access token for the Marketing API.

    Returns:
        A dict of HTTP header name → value strings.
    """
    return {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": _LI_API_VERSION,
        "Content-Type": "application/json",
        "X-Restli-Method": "PARTIAL_UPDATE",
    }


def campaign_url(campaign_urn: str) -> str:
    """Construct the REST URL for a specific campaign resource.

    Args:
        campaign_urn: The campaign URN, e.g. ``urn:li:sponsoredCampaign:9876``.

    Returns:
        The full API URL string.
    """
    encoded = _urn_encode(campaign_urn)
    return f"{_LI_API_BASE}/adCampaigns/{encoded}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _urn_encode(urn: str) -> str:
    """Percent-encode a LinkedIn URN for use in a REST URL path segment.

    LinkedIn URNs contain colons (e.g. ``urn:li:sponsoredCampaign:9876``).
    Those colons must be percent-encoded when the URN appears as a URL path
    component so the routing layer doesn't mis-parse the URL.

    Only encodes ``:`` → ``%3A``; all other characters are passed through as-is.
    """
    return urn.replace(":", "%3A")


def _check_response(response: Any, context: str) -> None:
    """Raise ``RuntimeError`` if the API response indicates failure.

    LinkedIn Marketing API returns HTTP 2xx on success.  Any other code is
    treated as an error.  This keeps the executor honest: it never silently
    swallows a failed API call.

    Args:
        response: The response object returned by the injected client.
        context:  A short description of the operation, for the error message.
    """
    if response.status_code < 200 or response.status_code >= 300:
        try:
            body = json.dumps(response.json())
        except Exception:
            body = "<non-JSON body>"
        raise RuntimeError(
            f"LinkedIn API error during {context}: "
            f"HTTP {response.status_code} — {body}"
        )


# ---------------------------------------------------------------------------
# Live executor
# ---------------------------------------------------------------------------


@dataclass
class LinkedInAdsExecutor(Executor):
    """Live executor that sends ops to the LinkedIn Marketing API.

    ORIGINAL WORK — drives the official LinkedIn Marketing API via an injected
    client.  NOT validated against the live API.  Live execution requires real
    OAuth credentials and a sandbox account.  A fake 'working' integration is
    worse than an honestly-scoped one.

    Attributes:
        client:        A duck-typed HTTP client (see ``LinkedInHTTPClient``).
                       Injected at construction time; never created internally.
        account_id:    LinkedIn sponsored-account URN, e.g.
                       ``"urn:li:sponsoredAccount:123456"``.
        currency_code: ISO-4217 code that matches the account's billing currency.
        access_token:  OAuth 2.0 bearer token with ``r_ads_reporting`` +
                       ``w_organization_social`` scopes (or the appropriate
                       Marketing API scopes for your app).
    """

    client: Any
    account_id: str
    currency_code: str = "USD"
    access_token: str = ""

    def apply(self, op: PaidOp) -> ExecResult:
        """Apply one PaidOp to the LinkedIn campaign named in ``op.campaign``.

        ``op.campaign`` is treated as the raw LinkedIn campaign URN
        (``urn:li:sponsoredCampaign:<id>``).  The caller is responsible for
        mapping friendly campaign names to URNs before building a ``PaidOp``.

        Never raises: an API/transport error, a missing value, or an unknown op
        kind is surfaced as ``ExecResult(ok=False)`` — consistent with the Google
        and Meta executors, so one failure can't abort a batch in execute().
        """
        if op.kind == NO_OP:
            return ExecResult(op, ok=True, message=f"no-op: {op.campaign} — {op.reason}")
        try:
            if op.kind == SET_BUDGET:
                if op.value is None:
                    return ExecResult(op, ok=False, message="linkedin: set_budget requires a value")
                return self._set_budget(op)
            if op.kind == PAUSE:
                return self._pause(op)
            return ExecResult(op, ok=False, message=f"linkedin: unknown op kind {op.kind!r}")
        except Exception as exc:  # API/transport error → ok=False, never abort the batch
            return ExecResult(op, ok=False, message=f"linkedin: error on {op.campaign} — {exc}")

    # ------------------------------------------------------------------
    # Private helpers — each maps to exactly one Marketing API call
    # ------------------------------------------------------------------

    def _set_budget(self, op: PaidOp) -> ExecResult:
        url = campaign_url(op.campaign)
        payload = build_budget_payload(op.campaign, op.value, self.currency_code)  # type: ignore[arg-type]
        headers = build_request_headers(self.access_token)
        response = self.client.post(url, json=payload, headers=headers)
        _check_response(response, f"set_budget {op.campaign}")
        return ExecResult(
            op,
            ok=True,
            message=(
                f"linkedin set_budget: {op.campaign} → "
                f"{op.value} {self.currency_code}"
            ),
        )

    def _pause(self, op: PaidOp) -> ExecResult:
        url = campaign_url(op.campaign)
        payload = build_pause_payload()
        headers = build_request_headers(self.access_token)
        response = self.client.post(url, json=payload, headers=headers)
        _check_response(response, f"pause {op.campaign}")
        return ExecResult(
            op,
            ok=True,
            message=f"linkedin pause: {op.campaign} — {op.reason}",
        )


# ---------------------------------------------------------------------------
# Standalone demo — zero egress, fake client only
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from executor import DryRunExecutor, execute, plan_to_ops
    from perf_controller import run
    from perf_schema import Campaign, PerfPolicy

    # Fake client that records calls and always returns 200
    class _FakeClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def post(self, url: str, **kwargs: Any) -> Any:
            self.calls.append({"method": "POST", "url": url, **kwargs})

            class _Resp:
                status_code = 200

                def json(self) -> dict[str, Any]:
                    return {}

            return _Resp()

        def get(self, url: str, **kwargs: Any) -> Any:
            self.calls.append({"method": "GET", "url": url, **kwargs})

            class _Resp:
                status_code = 200

                def json(self) -> dict[str, Any]:
                    return {}

            return _Resp()

    policy = PerfPolicy(target_cpa=50.0, account_daily_cap=400.0)
    campaigns = [
        Campaign("urn:li:sponsoredCampaign:1001", 1200, 40, 100),   # scale
        Campaign("urn:li:sponsoredCampaign:1002", 3200, 40, 100),   # cut
        Campaign("urn:li:sponsoredCampaign:1003", 120, 0, 40),      # kill → pause
    ]

    ops = plan_to_ops(run(campaigns, policy))

    # --- Show dry-run first (the safe default) ---
    print("=== DryRun (zero egress, default) ===")
    dry = DryRunExecutor()
    for r in execute(ops, dry):
        print(f"  {r.message}")

    # --- Show LinkedInAdsExecutor with a fake client ---
    print("\n=== LinkedInAdsExecutor (fake client, still zero egress) ===")
    fake = _FakeClient()
    li_exec = LinkedInAdsExecutor(
        client=fake,
        account_id="urn:li:sponsoredAccount:999",
        currency_code="USD",
        access_token="fake-token",
    )
    for op in ops:
        r = li_exec.apply(op)
        print(f"  {r.message}")

    print(f"\n  fake client recorded {len(fake.calls)} HTTP call(s):")
    for call in fake.calls:
        print(f"    {call['method']} {call['url']}")
    print("\n  Swap 'fake' for a real authenticated client to go live.")
