"""HubSpot CRM adapter — system-of-record integration for the kaikarma GTM engine.

ORIGINAL WORK — every line written from scratch against the public HubSpot
CRM API v3 shape (https://developers.hubspot.com/docs/api/crm/companies,
https://developers.hubspot.com/docs/api/crm/contacts) and the public HubSpot
properties reference.  No code was copied, fetched, or adapted from any
third-party repository.

HONEST SCOPE:
  - This module has NOT been validated against the live HubSpot API.
  - Live execution requires a HubSpot Private App token (HUBSPOT_TOKEN env var)
    or an OAuth2 bearer token, and an active portal/account.
  - A fake "working" integration is worse than an honestly-scoped one.
    The module is complete and structurally correct; only the injected client
    determines whether results are real or simulated.

EGRESS POLICY:
  - No network I/O occurs at import time or in any pure helper.
  - The HubSpot SDK / requests session is a RUNTIME dependency — it is
    injected via the `client` parameter on the fetch functions and is NEVER
    imported at module top-level.
  - Tests and the __main__ demo run with zero third-party packages installed
    (stdlib-only, air-gapped).

HUBSPOT CRM API SHAPE (v3):
  Companies list endpoint:
      GET /crm/v3/objects/companies
      Response: {"results": [{"id": "...", "properties": {...}}, ...]}

  Company properties relevant to ICP scoring:
      name               — company display name (REQUIRED)
      industry           — HubSpot industry enum string (e.g. "COMPUTER_SOFTWARE")
      numberofemployees  — string-encoded integer ("250")
      hs_analytics_num_visits — website visit count (proxy signal)
      technology_*       — tech-stack tags; HubSpot stores these in fields like
                           'hs_predictive_scoring_tier' or custom properties.
                           We accept any property whose key starts with "tech_"
                           as a tech-stack entry (normalised to lowercase).
      technologies       — comma-separated tech string (common custom field)

  Contacts list endpoint:
      GET /crm/v3/objects/contacts
      Response: {"results": [{"id": "...", "properties": {...}}, ...]}

  Contact properties:
      email, firstname, lastname, lifecyclestage

SDK integration shape (hubspot-api-client 8+ / requests):
  The injected client must expose:
      client.get_companies(limit: int) -> list[dict]
      client.get_contacts(limit: int) -> list[dict]
      client.patch_contact(contact_id: str, payload: dict) -> dict

  Where each element of get_companies/get_contacts is a plain dict of the form:
      {"id": "123", "properties": {"name": "Acme", ...}}

  The real SDK (hubspot-api-client) and a thin requests wrapper both satisfy
  this interface via a small adapter layer (not in scope here).

Usage (live):
    import hubspot
    from hubspot_crm import fetch_companies

    client = _RealHubSpotAdapter(hubspot.Client.create(access_token="..."))
    accounts = fetch_companies(client, limit=100)

Usage (fake / demo):
    See the `if __name__ == "__main__"` block below.
"""

from __future__ import annotations

import pathlib as _pathlib
import sys as _sys

# Ensure both 04-revops-engine/ and 01-list-engine/ are on sys.path so that
# `from icp_schema import Account` resolves regardless of how this module is
# invoked (pytest conftest, direct `python3 04-revops-engine/hubspot_crm.py`,
# or imported from a sibling engine).  All three invocation paths are safe:
# pytest conftest already prepends the dirs; the guard below is idempotent.
_HERE = _pathlib.Path(__file__).parent.resolve()
_ROOT = _HERE.parent
for _p in (_HERE, _ROOT / "01-list-engine"):
    _s = str(_p)
    if _s not in _sys.path:
        _sys.path.insert(0, _s)

from typing import Any  # noqa: E402

from icp_schema import Account  # noqa: E402  (cross-pillar import; must follow the sys.path guard above)
from revops_schema import Route  # noqa: E402

# ---------------------------------------------------------------------------
# HubSpot → ICP property normalisation constants.
# ---------------------------------------------------------------------------

# HubSpot industry strings map to shorter canonical labels used across the
# engine.  Unknown values pass through as-is (lower-cased); the ICP scorer
# treats an unrecognised industry as a weak match rather than an error.
_INDUSTRY_MAP: dict[str, str] = {
    "COMPUTER_SOFTWARE": "software",
    "INFORMATION_TECHNOLOGY_AND_SERVICES": "it_services",
    "INTERNET": "internet",
    "FINANCIAL_SERVICES": "financial_services",
    "BANKING": "banking",
    "INSURANCE": "insurance",
    "HOSPITAL_&_HEALTH_CARE": "healthcare",
    "MEDICAL_DEVICES": "medical_devices",
    "BIOTECHNOLOGY": "biotech",
    "PHARMACEUTICALS": "pharma",
    "RETAIL": "retail",
    "CONSUMER_GOODS": "consumer_goods",
    "MANUFACTURING": "manufacturing",
    "LOGISTICS_AND_SUPPLY_CHAIN": "logistics",
    "AUTOMOTIVE": "automotive",
    "REAL_ESTATE": "real_estate",
    "EDUCATION_MANAGEMENT": "education",
    "STAFFING_AND_RECRUITING": "staffing",
    "MARKETING_AND_ADVERTISING": "marketing",
    "TELECOMMUNICATIONS": "telecom",
}

# HubSpot lifecycle → revops lifecycle values (round-trip safe).
_LIFECYCLE_MAP: dict[str, str] = {
    "subscriber": "subscriber",
    "lead": "lead",
    "marketingqualifiedlead": "mql",
    "salesqualifiedlead": "sql",
    "opportunity": "opportunity",
    "customer": "customer",
    "evangelist": "evangelist",
    "other": "other",
}

# HubSpot lead status → hs_lead_status string written back via PATCH.
_DESTINATION_TO_LEAD_STATUS: dict[str, str] = {
    "ae_queue":       "IN_PROGRESS",
    "instant_alert":  "IN_PROGRESS",
    "sdr_sequence":   "OPEN",
    "nurture":        "OPEN",
    "disqualified":   "UNQUALIFIED",
}

# Destination → lifecycle stage written back (best-effort mapping).
_DESTINATION_TO_LIFECYCLE: dict[str, str] = {
    "ae_queue":      "opportunity",
    "instant_alert": "opportunity",
    "sdr_sequence":  "salesqualifiedlead",
    "nurture":       "marketingqualifiedlead",
    "disqualified":  "lead",
}


# ---------------------------------------------------------------------------
# Pure helpers.
# ---------------------------------------------------------------------------


def _require_prop(props: dict[str, Any], key: str) -> Any:
    """Return props[key]; raise ValueError naming the field if absent or blank.

    Keeps error messages consistent across the module — every required-field
    failure surfaces the exact HubSpot property name so callers know exactly
    what to fix in the CRM.
    """
    value = props.get(key)
    if value is None or value == "":
        raise ValueError(
            f"Required HubSpot property '{key}' is missing or blank in: {props!r}"
        )
    return value


def _parse_employees(raw: Any) -> int:
    """Convert HubSpot numberofemployees (string or int) to int.

    HubSpot stores employee count as a string even though it is numeric.
    Non-numeric or blank values return 0 — downstream scorers treat 0 as
    "unknown headcount" rather than raising so that one bad field does not
    drop an entire company batch.
    """
    if raw is None or raw == "":
        return 0
    try:
        return int(str(raw).replace(",", "").strip())
    except ValueError:
        return 0


def _extract_tech_stack(props: dict[str, Any]) -> frozenset[str]:
    """Build tech-stack frozenset from HubSpot company properties.

    Two sources (both optional, additive):
    1. ``technologies`` — comma-separated string of technology names
       (common custom property in HubSpot portals synced from Clearbit/Apollo).
    2. Any property whose key starts with ``tech_`` — value is treated as a
       single technology name if non-blank (e.g. ``tech_crm="Salesforce"``).

    All entries are lower-cased and stripped before collection.
    """
    techs: set[str] = set()

    raw_csv = props.get("technologies") or ""
    for item in raw_csv.split(","):
        item = item.strip().lower()
        if item:
            techs.add(item)

    for key, val in props.items():
        if key.startswith("tech_") and val and isinstance(val, str):
            item = val.strip().lower()
            if item:
                techs.add(item)

    return frozenset(techs)


# ---------------------------------------------------------------------------
# READ side — pure parse functions (no SDK, no network).
# ---------------------------------------------------------------------------


def company_to_account(props: dict[str, Any]) -> Account:
    """Map a HubSpot company properties dict to an ICP-schema Account.

    PURE — no network, no SDK.  The caller is responsible for extracting the
    ``properties`` sub-dict from the HubSpot API row before calling this.

    Required HubSpot properties:
        name               — company display name.

    Optional HubSpot properties (gracefully absent):
        industry           — normalised via _INDUSTRY_MAP; unknown values
                             pass through lower-cased.
        numberofemployees  — string-encoded int; defaults to 0 if missing.
        technologies       — comma-separated tech names.
        tech_*             — individual tech-stack properties.

    Args:
        props: Flat dict of HubSpot company property key→value pairs.
               The top-level ``id`` field is NOT included — pass only the
               contents of the ``"properties"`` sub-dict from the API row.

    Returns:
        Account with signals=frozenset() and fit=0.0 (neither is derivable
        from a bare CRM pull; callers enrich via the signal layer).

    Raises:
        ValueError: If ``name`` is missing or blank — a nameless account
            cannot be scored or routed.
    """
    name: str = _require_prop(props, "name")

    raw_industry = (props.get("industry") or "").strip()
    industry: str = _INDUSTRY_MAP.get(raw_industry, raw_industry.lower())

    employees: int = _parse_employees(props.get("numberofemployees"))
    tech_stack: frozenset[str] = _extract_tech_stack(props)

    return Account(
        name=name,
        industry=industry,
        employees=employees,
        tech_stack=tech_stack,
        signals=frozenset(),
        fit=0.0,
    )


def parse_companies(rows: list[dict[str, Any]]) -> list[Account]:
    """Convert a batch of HubSpot company API rows into ICP Account objects.

    PURE — no network, no SDK.

    Each row is expected to have the shape:
        {"id": "123", "properties": {"name": "Acme", ...}}

    Args:
        rows: List of HubSpot company objects as returned by the v3 API.

    Returns:
        List of Account instances in the same order as rows.

    Raises:
        ValueError: If any row is missing required properties.  The error
            includes the offending row so the caller can trace the problem.
            We raise rather than skip — silently dropping a company would
            produce a scoring gap the operator would never see.
    """
    accounts: list[Account] = []
    for row in rows:
        props: dict[str, Any] = row.get("properties") or {}
        accounts.append(company_to_account(props))
    return accounts


def parse_contacts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise a batch of HubSpot contact API rows into clean dicts.

    PURE — no network, no SDK.

    Each row is expected to have the shape:
        {"id": "456", "properties": {"email": "...", "firstname": "...", ...}}

    The returned dicts are intentionally flat with predictable keys — the
    caller does not need to know HubSpot's internal property naming to work
    with them.

    Output dict shape per contact:
        {
            "id":             str  — HubSpot contact id
            "email":          str  — normalised to lowercase; empty string if absent
            "firstname":      str  — stripped; empty string if absent
            "lastname":       str  — stripped; empty string if absent
            "lifecyclestage": str  — mapped via _LIFECYCLE_MAP; empty string if absent
        }

    Args:
        rows: List of HubSpot contact objects as returned by the v3 API.

    Returns:
        List of normalised contact dicts in the same order as rows.
    """
    contacts: list[dict[str, Any]] = []
    for row in rows:
        props: dict[str, Any] = row.get("properties") or {}
        raw_lifecycle = (props.get("lifecyclestage") or "").strip().lower()
        contacts.append(
            {
                "id":             str(row.get("id", "")),
                "email":          (props.get("email") or "").strip().lower(),
                "firstname":      (props.get("firstname") or "").strip(),
                "lastname":       (props.get("lastname") or "").strip(),
                "lifecyclestage": _LIFECYCLE_MAP.get(raw_lifecycle, raw_lifecycle),
            }
        )
    return contacts


# ---------------------------------------------------------------------------
# WRITE side — pure payload builder (no SDK, no network).
# ---------------------------------------------------------------------------


def build_contact_update(
    route: Route,
    owner_id: str | None = None,
) -> dict[str, Any]:
    """Build a HubSpot contact PATCH payload from a RevOps routing verdict.

    PURE — no network, no SDK.  The caller sends the returned dict to
    update_contact.

    Maps:
        route.destination → hs_lead_status + lifecyclestage
        owner_id          → hubspot_owner_id (omitted if None)

    HubSpot PATCH /crm/v3/objects/contacts/{id} expects:
        {"properties": {"<prop>": "<value>", ...}}

    Args:
        route:    Routing verdict produced by lead_router.route().
        owner_id: HubSpot numeric owner ID (string) to assign the contact to.
                  If None the property is not included in the payload so the
                  existing owner is not overwritten.

    Returns:
        A dict suitable for JSON-serialisation and passing to update_contact.
        Always contains ``hs_lead_status`` and ``lifecyclestage``; contains
        ``hubspot_owner_id`` only when owner_id is not None.
    """
    lead_status = _DESTINATION_TO_LEAD_STATUS.get(route.destination, "OPEN")
    lifecycle = _DESTINATION_TO_LIFECYCLE.get(route.destination, "lead")

    properties: dict[str, str] = {
        "hs_lead_status": lead_status,
        "lifecyclestage": lifecycle,
    }
    if owner_id is not None:
        properties["hubspot_owner_id"] = owner_id

    return {"properties": properties}


# ---------------------------------------------------------------------------
# Thin fetch / update wrappers — inject SDK client, delegate to parse helpers.
# ---------------------------------------------------------------------------


def fetch_companies(
    client: Any,
    limit: int = 100,
) -> list[Account]:
    """Fetch live company records from HubSpot via the injected client.

    Calls client.get_companies(limit) and passes the resulting rows to
    parse_companies.  The SDK is a RUNTIME dependency — never imported here.

    FAIL LOUD CONTRACT:
        Read failures raise RuntimeError with full context so the controller
        never mistakes a fetch error for "no companies".  Silently returning []
        would cause ICP scoring to see an empty universe and fire off wrong
        routes.

    Args:
        client: Duck-typed client exposing:
                    client.get_companies(limit: int) -> list[dict]
                Use a real HubSpot adapter for live runs, or
                FakeHubSpotClient for tests / zero-egress demos.
        limit:  Maximum number of company records to retrieve per page.

    Returns:
        List of Account objects parsed from the company rows.

    Raises:
        RuntimeError: If client.get_companies raises, wrapping the original
            exception with contextual detail.
        ValueError: Propagated from parse_companies if a row is malformed.
    """
    try:
        rows: list[dict[str, Any]] = list(client.get_companies(limit=limit))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"HubSpot fetch_companies failed [limit={limit}]: {exc}"
        ) from exc
    return parse_companies(rows)


def fetch_contacts(
    client: Any,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch live contact records from HubSpot via the injected client.

    FAIL LOUD CONTRACT: read failures raise RuntimeError (same rationale as
    fetch_companies — an empty contact list used downstream is worse than a
    visible error).

    Args:
        client: Duck-typed client exposing:
                    client.get_contacts(limit: int) -> list[dict]
        limit:  Maximum number of contact records to retrieve.

    Returns:
        List of normalised contact dicts (see parse_contacts).

    Raises:
        RuntimeError: If client.get_contacts raises.
        ValueError: Propagated from parse_contacts if a row is malformed.
    """
    try:
        rows: list[dict[str, Any]] = list(client.get_contacts(limit=limit))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"HubSpot fetch_contacts failed [limit={limit}]: {exc}"
        ) from exc
    return parse_contacts(rows)


def update_contact(
    client: Any,
    contact_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Write a contact update payload to HubSpot via the injected client.

    Unlike fetch_companies / fetch_contacts this function does NOT raise on
    failure — it matches the executor contract used across the engine, where
    individual write failures are logged and retried rather than crashing the
    entire routing batch.

    Args:
        client:     Duck-typed client exposing:
                        client.patch_contact(contact_id: str, payload: dict) -> dict
        contact_id: HubSpot numeric contact ID (as string).
        payload:    Dict produced by build_contact_update.

    Returns:
        On success: the dict returned by client.patch_contact (typically
            contains the updated properties).
        On failure: {"ok": False, "contact_id": contact_id, "error": str(exc)}
            — so callers can log/retry without a try/except of their own.
    """
    try:
        return client.patch_contact(contact_id=contact_id, payload=payload)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "contact_id": contact_id,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Fake client for demo and tests (zero egress, stdlib only).
# ---------------------------------------------------------------------------


class FakeHubSpotClient:
    """Returns canned rows instead of calling the real HubSpot API.

    Mirrors the duck-typed interface that fetch_companies / fetch_contacts /
    update_contact expect:
        client.get_companies(limit: int) -> list[dict]
        client.get_contacts(limit: int) -> list[dict]
        client.patch_contact(contact_id: str, payload: dict) -> dict

    Zero network I/O — suitable for unit tests and zero-egress demos.

    Args:
        company_rows:   Canned company rows (HubSpot v3 shape).
        contact_rows:   Canned contact rows (HubSpot v3 shape).
        raise_on_get:   If True, get_companies / get_contacts raise RuntimeError
                        to exercise the fetch error path.
        raise_on_patch: If True, patch_contact raises RuntimeError to exercise
                        the update_contact failure path.
    """

    def __init__(
        self,
        company_rows: list[dict[str, Any]] | None = None,
        contact_rows: list[dict[str, Any]] | None = None,
        raise_on_get: bool = False,
        raise_on_patch: bool = False,
    ) -> None:
        self._company_rows: list[dict[str, Any]] = company_rows or []
        self._contact_rows: list[dict[str, Any]] = contact_rows or []
        self._raise_get = raise_on_get
        self._raise_patch = raise_on_patch
        self.get_company_calls: list[int] = []
        """Recorded limit values per get_companies() call."""
        self.get_contact_calls: list[int] = []
        """Recorded limit values per get_contacts() call."""
        self.patch_calls: list[tuple[str, dict[str, Any]]] = []
        """Recorded (contact_id, payload) per patch_contact() call."""

    def get_companies(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return canned company rows (or raise if configured)."""
        self.get_company_calls.append(limit)
        if self._raise_get:
            raise RuntimeError("Simulated HubSpot companies API error")
        return list(self._company_rows[:limit])

    def get_contacts(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return canned contact rows (or raise if configured)."""
        self.get_contact_calls.append(limit)
        if self._raise_get:
            raise RuntimeError("Simulated HubSpot contacts API error")
        return list(self._contact_rows[:limit])

    def patch_contact(
        self, contact_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Record the call and return a success stub (or raise if configured)."""
        self.patch_calls.append((contact_id, payload))
        if self._raise_patch:
            raise RuntimeError("Simulated HubSpot contact PATCH error")
        return {"id": contact_id, "properties": payload.get("properties", {}), "ok": True}


# ---------------------------------------------------------------------------
# Demo — runs zero-egress, zero-credential.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    CANNED_COMPANIES: list[dict[str, Any]] = [
        {
            "id": "1001",
            "properties": {
                "name": "Acme Cloud Inc",
                "industry": "COMPUTER_SOFTWARE",
                "numberofemployees": "480",
                "technologies": "Salesforce, HubSpot",
                "tech_data_warehouse": "Snowflake",
            },
        },
        {
            "id": "1002",
            "properties": {
                "name": "MidFin Corp",
                "industry": "FINANCIAL_SERVICES",
                "numberofemployees": "1200",
                "technologies": "SAP,Oracle",
            },
        },
        {
            "id": "1003",
            "properties": {
                "name": "ScaleUp Biotech",
                "industry": "BIOTECHNOLOGY",
                "numberofemployees": "75",
            },
        },
    ]

    CANNED_CONTACTS: list[dict[str, Any]] = [
        {
            "id": "501",
            "properties": {
                "email": "alice@acmecloud.com",
                "firstname": "Alice",
                "lastname": "Chen",
                "lifecyclestage": "salesqualifiedlead",
            },
        },
        {
            "id": "502",
            "properties": {
                "email": "BOB@midfin.com",
                "firstname": "Bob",
                "lastname": "Singh",
                "lifecyclestage": "lead",
            },
        },
    ]

    client = FakeHubSpotClient(
        company_rows=CANNED_COMPANIES,
        contact_rows=CANNED_CONTACTS,
    )

    print("hubspot_crm demo (FakeHubSpotClient — zero egress):\n")

    print("--- Companies → Accounts ---")
    accounts = fetch_companies(client, limit=50)
    for acct in accounts:
        print(
            f"  {acct.name:<25}  industry={acct.industry:<20}  "
            f"employees={acct.employees:>5}  "
            f"tech={sorted(acct.tech_stack)}"
        )

    print("\n--- Contacts (normalised) ---")
    contacts = fetch_contacts(client, limit=50)
    for c in contacts:
        print(
            f"  [{c['id']}] {c['firstname']} {c['lastname']:<15}  "
            f"{c['email']:<30}  lifecycle={c['lifecyclestage']}"
        )

    print("\n--- Contact update (Route → HubSpot payload) ---")
    from revops_schema import Route

    sample_route = Route(
        lead_name="Alice Chen",
        destination="ae_queue",
        sla_minutes=60,
        reason="A-tier → ae_queue",
    )
    payload = build_contact_update(sample_route, owner_id="77")
    result = update_contact(client, contact_id="501", payload=payload)
    print(f"  Route destination : {sample_route.destination}")
    print(f"  Payload           : {payload}")
    print(f"  PATCH result      : {result}")

    print(
        f"\n  {len(accounts)} account(s), {len(contacts)} contact(s) parsed. "
        f"get_companies called {len(client.get_company_calls)} time(s). "
        f"patch_contact called {len(client.patch_calls)} time(s)."
    )
    print("\n  No network I/O occurred.  Swap in a real client for live execution.")
