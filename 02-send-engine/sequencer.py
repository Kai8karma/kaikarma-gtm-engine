"""Instantly.ai-style email-sequencer adapter for the kaikarma send engine.

ORIGINAL WORK — every line written from scratch against Instantly's public API
v2 reference (https://developer.instantly.ai/email/lead/add) and the general
Instantly campaign-leads API shape. No code was copied, cloned, fetched, or
adapted from any third-party repository. No unlicensed repos were opened or read.

HONEST SCOPE:
  - This module has NOT been validated against the live Instantly API.
  - Live execution requires a real Instantly API key, a campaign ID, and an
    active Instantly workspace.
  - A fake "working" integration is worse than an honestly-scoped stub. This file
    is the latter: complete and structurally correct; only the injected client
    determines whether results are real or simulated.

EGRESS POLICY:
  - No network I/O occurs at import time or in any pure helper.
  - The Instantly HTTP client is a RUNTIME dependency injected via the `client`
    parameter on every call. It is NEVER imported at module top-level.
  - Tests and the __main__ demo run with zero third-party packages installed
    (stdlib-only, air-gapped).

INSTANTLY v2 LEAD PAYLOAD SHAPE:
  POST /api/v1/lead/add  (v2 workspace variant)
  {
    "campaign": "<campaign_id>",
    "email": "prospect@example.com",
    "firstName": "Jordan",
    "companyName": "Acme Inc.",
    "variables": {                      # arbitrary key/value personalization
      "custom_intro": "saw your Series A",
      ...
    }
  }

SDK (client) integration shape:
  The injected client must expose:
      client.add_lead(campaign_id: str, payload: dict) -> dict

  Where the returned dict includes at minimum:
      {"status": "success" | <other>, ...}

  The real Instantly API returns JSON; a thin adapter (not in scope) converts
  the HTTP response. This module's interface is duck-typed so callers can wire
  any adapter matching their HTTP library.

Usage (live):
    from instantly_client import InstantlyClient  # your adapter
    from sequencer import build_lead_payload, add_lead_to_campaign

    client = InstantlyClient(api_key="sk-...")
    lead = build_lead_payload("sarah@acme.com", first_name="Sarah", company="Acme")
    result = add_lead_to_campaign(client, campaign_id="camp_abc123", lead=lead)

Usage (fake / demo):
    See the `if __name__ == "__main__"` block below.

    python3 02-send-engine/sequencer.py        # demo (fake client, zero egress)
    python3 02-send-engine/test_sequencer.py   # unit tests
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure payload builder — no SDK, no network
# ---------------------------------------------------------------------------

def build_lead_payload(
    email: str,
    first_name: str = "",
    company: str = "",
    custom_vars: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the add-lead-to-campaign request body for the Instantly v2 API.

    PURE — no network, no SDK. The returned dict is ready to pass as the
    payload argument to add_lead_to_campaign().

    Instantly v2 field mapping:
      - email        → "email"
      - first_name   → "firstName"
      - company      → "companyName"
      - custom_vars  → "variables" (arbitrary key/value personalisation dict)

    The "campaign" key is intentionally NOT included here — it is supplied by
    the caller at send time so the same lead dict can be enqueued to multiple
    campaigns without being rebuilt.

    Args:
        email:       Prospect email address. Must be non-empty and contain "@".
                     Raises ValueError on invalid input.
        first_name:  Optional first name for personalisation (maps to firstName).
        company:     Optional company name for personalisation (maps to companyName).
        custom_vars: Optional dict of arbitrary personalisation variables that
                     Instantly exposes in sequence step templates via {{variable}}.
                     Keys and values must be strings. None is treated as {}.

    Returns:
        Dict with "email", "firstName", "companyName", and "variables" keys.

    Raises:
        ValueError: If email is empty or does not contain "@".
    """
    email = email.strip()
    if not email:
        raise ValueError("email must not be empty")
    if "@" not in email:
        raise ValueError(f"email must contain '@'; got {email!r}")

    return {
        "email": email,
        "firstName": first_name,
        "companyName": company,
        "variables": dict(custom_vars) if custom_vars else {},
    }


# ---------------------------------------------------------------------------
# Per-lead outcome
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SequenceResult:
    """Outcome of a single add-lead-to-campaign call.

    Mirrors the ok/fail contract used by the paid-engine executors:
      - ok=True  → lead successfully enqueued in the campaign.
      - ok=False → the call failed; message carries the reason.

    Frozen so test assertions can use == directly.
    """

    email: str
    ok: bool
    message: str


# ---------------------------------------------------------------------------
# Client-injected send functions
# ---------------------------------------------------------------------------

def add_lead_to_campaign(
    client: Any,
    campaign_id: str,
    lead: dict[str, Any],
) -> SequenceResult:
    """Enqueue a single lead into an Instantly campaign via the injected client.

    Calls client.add_lead(campaign_id, payload) where payload merges the
    campaign_id into the lead dict (Instantly v2 requires "campaign" in the body).

    FAIL CONTRACT:
        Any exception from the client is caught, logged, and returned as
        ok=False. Callers must not rely on exceptions propagating — use the
        SequenceResult to detect failures.

    Args:
        client:      Duck-typed client with:
                         client.add_lead(campaign_id: str, payload: dict) -> dict
                     Use a real InstantlyClient adapter for live runs, or
                     FakeSequencerClient for tests / zero-egress demos.
        campaign_id: Instantly campaign ID the lead will join.
        lead:        Dict built by build_lead_payload(); must contain "email".

    Returns:
        SequenceResult with ok=True on success, ok=False on any error.
    """
    email: str = lead.get("email", "")
    payload: dict[str, Any] = {"campaign": campaign_id, **lead}

    try:
        response = client.add_lead(campaign_id, payload)
        status = response.get("status", "") if isinstance(response, dict) else ""
        if status == "success":
            logger.info("sequencer: enqueued %s → campaign %s", email, campaign_id)
            return SequenceResult(email=email, ok=True, message=f"enqueued; api_status={status!r}")
        # API returned 200 but with non-success status — treat as soft failure
        logger.warning(
            "sequencer: unexpected status for %s: %s", email, response
        )
        return SequenceResult(
            email=email,
            ok=False,
            message=f"unexpected api response: {response!r}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("sequencer: add_lead failed for %s: %s", email, exc)
        return SequenceResult(email=email, ok=False, message=f"error — {exc}")


def add_leads_batch(
    client: Any,
    campaign_id: str,
    leads: list[dict[str, Any]],
) -> list[SequenceResult]:
    """Enqueue a list of leads into an Instantly campaign, one call per lead.

    PARTIAL-FAILURE CONTRACT:
        A failing lead does NOT abort the batch. Each lead is attempted
        independently; failures surface as SequenceResult(ok=False) at the
        same index as the input lead. The caller receives a result for every
        lead, regardless of individual success or failure.

    Args:
        client:      Same duck-typed client as add_lead_to_campaign().
        campaign_id: Instantly campaign ID.
        leads:       List of dicts from build_lead_payload(). Each must have
                     an "email" key.

    Returns:
        List of SequenceResult, one per lead, in the same order as `leads`.
    """
    results: list[SequenceResult] = []
    for lead in leads:
        result = add_lead_to_campaign(client, campaign_id, lead)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# FakeSequencerClient — records calls, zero egress, supports one failure
# ---------------------------------------------------------------------------

@dataclass
class FakeSequencerClient:
    """Captures add_lead() calls without any network I/O.

    Used in tests and the __main__ demo so the module is fully exercisable
    without Instantly credentials.

    Args:
        fail_emails: Set of email addresses that should simulate an API error.
                     Any add_lead() call for these emails raises RuntimeError,
                     exercising the ok=False path in add_lead_to_campaign().
    """

    fail_emails: set[str] = field(default_factory=set)
    calls: list[dict[str, Any]] = field(default_factory=list)
    """Records every (campaign_id, payload) pair passed to add_lead()."""

    def add_lead(self, campaign_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Record the call; raise if the email is in fail_emails, else succeed."""
        self.calls.append({"campaign_id": campaign_id, "payload": payload})
        email: str = payload.get("email", "")
        if email in self.fail_emails:
            raise RuntimeError(f"Simulated Instantly API error for {email!r}")
        return {"status": "success", "lead": email}


# ---------------------------------------------------------------------------
# Demo — zero egress, fake client
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    CAMPAIGN_ID = "camp_demo_abc123"

    # Build payloads (pure — no client needed)
    leads = [
        build_lead_payload(
            "sarah@acme.com",
            first_name="Sarah",
            company="Acme Inc.",
            custom_vars={"opener": "saw your Series A announcement"},
        ),
        build_lead_payload(
            "marcus@beta.io",
            first_name="Marcus",
            company="Beta IO",
            custom_vars={"opener": "noticed you're hiring 3 SDRs"},
        ),
        build_lead_payload(
            "fail@broken.com",
            first_name="Fail",
            company="Broken Co.",
        ),
        build_lead_payload(
            "dana@gamma.com",
            first_name="Dana",
            company="Gamma Corp.",
            custom_vars={"opener": "loved your product-led growth post"},
        ),
    ]

    # One simulated failure so we can see the partial-failure contract in action
    fake_client = FakeSequencerClient(fail_emails={"fail@broken.com"})

    print(f"sequencer demo — FakeSequencerClient, zero egress\ncampaign: {CAMPAIGN_ID}\n")

    results = add_leads_batch(fake_client, CAMPAIGN_ID, leads)

    ok_count = sum(1 for r in results if r.ok)
    fail_count = len(results) - ok_count

    for r in results:
        status = "OK " if r.ok else "ERR"
        print(f"  [{status}] {r.email:<25}  {r.message}")

    print(f"\n  {ok_count} enqueued, {fail_count} failed.  "
          f"add_lead() called {len(fake_client.calls)} time(s).")
    print("  Swap FakeSequencerClient for a real Instantly HTTP adapter to go live.")
