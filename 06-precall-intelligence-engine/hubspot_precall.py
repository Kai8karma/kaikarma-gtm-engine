"""HubSpot adapter for pre-call intelligence — contact/company lookup, briefing writeback.

Looks up the prospect by email, pulls the linked company record for the
industry match used in Section 3/4 of the T-2 briefing, and writes the
generated briefing back to the `precall_briefing` contact property so the
T-1 recap (which reads it, never re-researches) has source content.

SOW Section 10 risk: HubSpot's `industry` field is commonly blank (flagged
by the client's own CRM audits). When blank, `company_to_profile` does NOT
guess — it returns industry="" with industry_source="web_search_fallback"
so the caller knows to ask Claude to classify the industry from web search
instead of silently mismatching customer references.

EGRESS POLICY (mirrors 04-revops-engine/hubspot_crm.py): no network I/O at
import time; the client is injected, never imported at module top-level.

HUBSPOT API SHAPE (v3) used here:
  GET /crm/v3/objects/contacts/search       (search by email)
  GET /crm/v3/objects/companies/{id}
  PATCH /crm/v3/objects/contacts/{id}

  The injected client must expose:
      client.get_contact_by_email(email: str) -> dict | None
      client.get_company(company_id: str) -> dict | None
      client.patch_contact(contact_id: str, payload: dict) -> dict
      client.get_contact_property(contact_id: str, prop: str) -> str | None
"""

from __future__ import annotations

from typing import Any

from precall_schema import CompanyProfile, ContactProfile

BRIEFING_PROPERTY = "precall_briefing"
BRIEFING_DATE_PROPERTY = "precall_briefing_date"


def contact_to_profile(contact_id: str, props: dict[str, Any]) -> ContactProfile:
    """Map a HubSpot contact properties dict to a ContactProfile.

    PURE — no network. Required: none of the fields are hard-required; a
    contact with gaps is still profiled (rep will simply see less detail),
    matching the SOW's "briefing still sends" behaviour on partial data.
    """
    company_id = props.get("associatedcompanyid") or props.get("company_id")
    return ContactProfile(
        contact_id=contact_id,
        first_name=(props.get("firstname") or "").strip(),
        last_name=(props.get("lastname") or "").strip(),
        title=(props.get("jobtitle") or "").strip(),
        email=(props.get("email") or "").strip().lower(),
        linkedin_url=(props.get("hs_linkedin_url") or props.get("linkedin_url") or "").strip(),
        company_id=str(company_id) if company_id else None,
    )


def company_to_profile(
    company_id: str,
    props: dict[str, Any],
    web_search_industry: str | None = None,
) -> CompanyProfile:
    """Map a HubSpot company properties dict to a CompanyProfile.

    PURE — no network. If `industry` is blank in HubSpot:
      - and `web_search_industry` is provided, use it with
        industry_source='web_search_fallback' (Claude classified it live).
      - otherwise, industry="" with industry_source='web_search_fallback' so
        the caller knows this company still needs classification before
        Section 3 (industry-matched customers) can run.
    """
    raw_industry = (props.get("industry") or "").strip()
    if raw_industry:
        industry, source = raw_industry, "crm"
    elif web_search_industry:
        industry, source = web_search_industry.strip(), "web_search_fallback"
    else:
        industry, source = "", "web_search_fallback"

    return CompanyProfile(
        company_id=company_id,
        name=(props.get("name") or "").strip(),
        industry=industry,
        industry_source=source,
        domain=(props.get("domain") or "").strip().lower(),
        employee_count=_parse_int(props.get("numberofemployees")),
        revenue=(props.get("annualrevenue") or "").strip(),
        hq=(props.get("hq_location") or props.get("city") or "").strip(),
    )


def _parse_int(raw: Any) -> int:
    if raw is None or raw == "":
        return 0
    try:
        return int(str(raw).replace(",", "").strip())
    except ValueError:
        return 0


def build_briefing_writeback(html: str, sent_iso: str) -> dict[str, Any]:
    """PATCH payload storing the generated T-2 briefing on the contact.

    So the T-1 recap can re-read it instead of re-researching (SOW 5.1).
    """
    return {"properties": {BRIEFING_PROPERTY: html, BRIEFING_DATE_PROPERTY: sent_iso}}


def fetch_contact_by_email(client: Any, email: str) -> ContactProfile | None:
    """Look up a contact by email. Returns None if not found (not an error).

    Per SOW 5.2: "If the prospect's email isn't found in HubSpot, the
    briefing email still sends" — so a miss here is a normal branch, not a
    failure. A genuine API error still raises.
    """
    try:
        row = client.get_contact_by_email(email=email)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"HubSpot contact lookup failed for {email!r}: {exc}") from exc
    if row is None:
        return None
    return contact_to_profile(str(row.get("id", "")), row.get("properties") or {})


def fetch_company(
    client: Any,
    company_id: str,
    web_search_industry: str | None = None,
) -> CompanyProfile | None:
    """Look up a company record by id. Returns None if not found."""
    try:
        row = client.get_company(company_id=company_id)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"HubSpot company lookup failed for {company_id!r}: {exc}") from exc
    if row is None:
        return None
    return company_to_profile(company_id, row.get("properties") or {}, web_search_industry)


def read_stored_briefing(client: Any, contact_id: str) -> str | None:
    """Read the T-2 briefing HTML stored on the contact, for the T-1 recap.

    Returns None if nothing was stored (e.g. the T-2 write was skipped
    because the prospect wasn't found in HubSpot at the time) — the T-1
    recap step must treat this as "no source content", not crash.
    """
    try:
        return client.get_contact_property(contact_id=contact_id, prop=BRIEFING_PROPERTY)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"HubSpot read of stored briefing failed for contact {contact_id!r}: {exc}"
        ) from exc


def update_contact_briefing(
    client: Any,
    contact_id: str,
    html: str,
    sent_iso: str,
) -> dict[str, Any]:
    """Write the generated briefing back to the contact. Does not raise on failure."""
    payload = build_briefing_writeback(html, sent_iso)
    try:
        return client.patch_contact(contact_id=contact_id, payload=payload)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "contact_id": contact_id, "error": str(exc)}


class FakeHubSpotPrecallClient:
    """Returns canned rows instead of calling the real HubSpot API. Zero egress."""

    def __init__(
        self,
        contacts_by_email: dict[str, dict[str, Any]] | None = None,
        companies_by_id: dict[str, dict[str, Any]] | None = None,
        stored_briefings: dict[str, str] | None = None,
    ) -> None:
        self._contacts_by_email = contacts_by_email or {}
        self._companies_by_id = companies_by_id or {}
        self._stored_briefings = stored_briefings or {}
        self.patch_calls: list[tuple[str, dict[str, Any]]] = []

    def get_contact_by_email(self, email: str) -> dict[str, Any] | None:
        return self._contacts_by_email.get(email.strip().lower())

    def get_company(self, company_id: str) -> dict[str, Any] | None:
        return self._companies_by_id.get(company_id)

    def get_contact_property(self, contact_id: str, prop: str) -> str | None:
        return self._stored_briefings.get(contact_id)

    def patch_contact(self, contact_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.patch_calls.append((contact_id, payload))
        return {"id": contact_id, "properties": payload.get("properties", {}), "ok": True}


if __name__ == "__main__":
    CANNED_CONTACTS = {
        "buyer@acmecloud.com": {
            "id": "501",
            "properties": {
                "firstname": "Jane",
                "lastname": "Buyer",
                "jobtitle": "VP Procurement",
                "email": "buyer@acmecloud.com",
                "hs_linkedin_url": "linkedin.com/in/janebuyer",
                "associatedcompanyid": "1001",
            },
        },
    }
    CANNED_COMPANIES = {
        "1001": {
            "properties": {
                "name": "Acme Cloud Inc",
                "industry": "",  # blank — CRM audit finding in action
                "domain": "acmecloud.com",
                "numberofemployees": "480",
                "annualrevenue": "50000000",
                "city": "Austin",
            },
        },
    }

    client = FakeHubSpotPrecallClient(
        contacts_by_email=CANNED_CONTACTS, companies_by_id=CANNED_COMPANIES
    )

    print("hubspot_precall demo (FakeHubSpotPrecallClient — zero egress):\n")

    contact = fetch_contact_by_email(client, "buyer@acmecloud.com")
    print(f"  Contact: {contact}")

    company = fetch_company(client, contact.company_id, web_search_industry="Cloud Infrastructure")
    print(f"  Company: {company}")
    print(f"  industry_source = {company.industry_source} (blank CRM field, filled via web search)")

    result = update_contact_briefing(client, contact.contact_id, "<html>...</html>", "2026-07-01T08:00:00Z")
    print(f"  Writeback result: {result}")
    print("\n  No network I/O occurred.")
