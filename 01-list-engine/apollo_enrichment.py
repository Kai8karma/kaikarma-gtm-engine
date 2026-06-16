"""Apollo.io enrichment adapter for the kaikarma GTM list-engine.

ORIGINAL WORK — every line written from scratch against Apollo's public
API documentation (https://apolloio.github.io/apollo-api-docs/ and the
Apollo v1 REST spec).  No code was copied, fetched, or adapted from any
third-party repository.

HONEST SCOPE:
  - This module has NOT been validated against the live Apollo API.
  - Live execution requires a valid Apollo API key and network access.
  - A fake "working" integration is worse than an honestly-scoped one.
    The module is complete and structurally correct; only the injected
    client determines whether results are real or simulated.

EGRESS POLICY:
  - No network I/O occurs at import time or in any pure helper.
  - The Apollo REST client is a RUNTIME dependency — it is injected via
    function parameters and is NEVER imported at module top-level.
  - Tests and the __main__ demo run with zero third-party packages
    installed (stdlib-only, air-gapped).

APOLLO ORG ENRICHMENT RECORD SHAPE (organization-enrichment endpoint):
  POST /api/v1/organizations/enrich
  Key fields this module consumes (plain dict after JSON parse):

      {
          "name": "Acme Corp",
          "industry": "software",
          "estimated_num_employees": 320,
          "technology_names": ["HubSpot", "Salesforce", "Stripe"],
          "keywords": ["crm", "saas", "revops"],
          "intent_strength": "strong",  # optional buying-signal field
          "funding_stage": "Series B",  # optional funding signal
          "job_postings_count": 14,     # optional hiring signal
      }

APOLLO PEOPLE SEARCH RECORD SHAPE (people/search endpoint):
  POST /api/v1/people/search
  Key fields per person:

      {
          "name": "Jane Smith",
          "title": "VP of Revenue Operations",
          "email": "jane@acmecorp.com",
          "linkedin_url": "https://www.linkedin.com/in/janesmith",
      }

INJECTED CLIENT INTERFACE:
  The real Apollo REST client (or any adapter) must expose:
      client.enrich_organization(domain: str) -> dict
      client.search_people(domain: str, titles: list[str] | None) -> list[dict]

  Both methods must return plain Python dicts/lists (not raw Response objects).
  This module is intentionally duck-typed so the caller wires the adapter that
  matches their Apollo SDK or requests-based wrapper.

Usage (live):
    from apollo_enrichment import enrich_company, find_contacts
    from my_apollo_client import ApolloClient   # your thin REST wrapper

    client = ApolloClient(api_key=os.environ["APOLLO_API_KEY"])
    account = enrich_company(client, domain="acmecorp.com")
    contacts = find_contacts(client, domain="acmecorp.com", titles=["VP of Sales"])

Usage (fake / demo):
    See the `if __name__ == "__main__"` block below.
"""

from __future__ import annotations

from typing import Any

from icp_schema import Account

# ---------------------------------------------------------------------------
# Buying-signal field names this module understands from Apollo responses.
# Extend here — the parse helpers reference this mapping.
# ---------------------------------------------------------------------------

# Maps Apollo org-level field names to canonical icp_schema signal values
# (must match SIGNAL_VALUE keys in icp_schema).  The adapter checks each key
# in order; if the value is truthy the corresponding signal is added.
_ORG_SIGNAL_MAP: dict[str, str] = {
    "intent_strength": "website_visit",    # Apollo intent → "website_visit" proxy
    "funding_stage": "funding",            # any non-empty funding stage = signal
    "job_postings_count": "hiring",        # > 0 open roles = hiring signal
}


# ---------------------------------------------------------------------------
# Pure helpers — no network, no SDK.
# ---------------------------------------------------------------------------


def _coerce_employees(raw: Any) -> int:
    """Convert Apollo's ``estimated_num_employees`` to a plain int.

    Apollo returns this as an int or None (when unknown). We default to 0
    rather than raising so callers can still score partial records — firmographic
    band scoring will just yield 0 for employee fit.

    Args:
        raw: Value from the Apollo org dict, may be None or int.

    Returns:
        int — 0 when raw is None or non-numeric.
    """
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _extract_tech_stack(org: dict[str, Any]) -> frozenset[str]:
    """Merge technology_names and keywords into a lower-cased frozenset.

    Apollo surfaces installed technologies in ``technology_names`` and free-form
    company tags in ``keywords``.  Both are useful for technographic scoring so
    we pool them.  Values are lower-cased for case-insensitive ICP matching.

    Args:
        org: Apollo organization-enrichment record (plain dict).

    Returns:
        frozenset[str] of lower-cased technology/keyword strings.
    """
    tech: list[str] = org.get("technology_names") or []
    keywords: list[str] = org.get("keywords") or []
    return frozenset(t.lower() for t in (*tech, *keywords) if isinstance(t, str))


def _extract_signals(org: dict[str, Any]) -> frozenset[str]:
    """Derive ICP buying-signal tokens from Apollo org fields.

    Maps three Apollo fields to canonical signal values recognised by
    icp_schema.SIGNAL_VALUE:

    - ``intent_strength`` (any truthy value) → "website_visit"
    - ``funding_stage`` (any truthy value) → "funding"
    - ``job_postings_count`` (> 0) → "hiring"

    This is intentionally conservative: we only emit a signal when the field
    is unambiguously present.  Extend ``_ORG_SIGNAL_MAP`` to add more.

    Args:
        org: Apollo organization-enrichment record (plain dict).

    Returns:
        frozenset[str] of canonical signal tokens.
    """
    signals: set[str] = set()
    for apollo_field, icp_signal in _ORG_SIGNAL_MAP.items():
        value = org.get(apollo_field)
        if apollo_field == "job_postings_count":
            # Numeric threshold — must be > 0 to count as a hiring signal.
            try:
                if int(value) > 0:
                    signals.add(icp_signal)
            except (TypeError, ValueError):
                pass
        elif value:
            signals.add(icp_signal)
    return frozenset(signals)


def enrich_to_account(org: dict[str, Any]) -> Account:
    """Map an Apollo organization-enrichment record to an icp_schema Account.

    PURE — no network, no side effects.  Every field access is defensive:
    missing optional fields fall back to safe defaults so partial Apollo
    records still produce usable Account instances.

    Args:
        org: Apollo organization-enrichment record as a plain dict.  At
             minimum it must contain ``"name"`` (non-empty string); all
             other fields are optional.

    Returns:
        Account dataclass populated from the Apollo record.

    Raises:
        ValueError: If ``org["name"]`` is absent or empty.  A nameless
            account cannot be scored — we fail loud rather than return a
            phantom record.
    """
    name: str = (org.get("name") or "").strip()
    if not name:
        raise ValueError(
            f"Apollo org record is missing 'name'; cannot build Account. "
            f"Record keys present: {list(org.keys())}"
        )

    industry: str = (org.get("industry") or "").lower().strip()
    employees: int = _coerce_employees(org.get("estimated_num_employees"))
    tech_stack: frozenset[str] = _extract_tech_stack(org)
    signals: frozenset[str] = _extract_signals(org)

    return Account(
        name=name,
        industry=industry,
        employees=employees,
        tech_stack=tech_stack,
        signals=signals,
        # fit is a manual/psychographic score — not derivable from Apollo alone.
        # Callers that have psychographic notes should set it post-construction.
        fit=0.0,
    )


def parse_contacts(people: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Normalize Apollo people-search records to a flat contact dict.

    PURE — no network, no side effects.  Strips leading/trailing whitespace
    from all string fields.  Missing fields become empty strings rather than
    None so downstream serialisers don't need to special-case null handling.

    Args:
        people: List of Apollo people-search result dicts.  Each dict may
                contain ``name``, ``title``, ``email``, ``linkedin_url`` and
                arbitrary other fields (ignored).

    Returns:
        List of dicts, one per person, with exactly four keys:
            - ``"name"``         — full name
            - ``"title"``        — job title
            - ``"email"``        — email address
            - ``"linkedin_url"`` — LinkedIn profile URL
        All values are strings (empty string when the source field was absent
        or None).
    """
    normalized: list[dict[str, str]] = []
    for person in people:
        normalized.append(
            {
                "name": (person.get("name") or "").strip(),
                "title": (person.get("title") or "").strip(),
                "email": (person.get("email") or "").strip(),
                "linkedin_url": (person.get("linkedin_url") or "").strip(),
            }
        )
    return normalized


# ---------------------------------------------------------------------------
# Thin fetch wrappers — inject the Apollo client, delegate to pure helpers.
# ---------------------------------------------------------------------------


def enrich_company(
    client: Any,
    domain: str,
) -> Account:
    """Fetch an organization-enrichment record from Apollo and map it to Account.

    Calls client.enrich_organization(domain) and passes the result to
    enrich_to_account.  The Apollo REST client is a RUNTIME dependency — it
    must be injected by the caller; it is never imported at module top-level.

    FAIL LOUD CONTRACT:
        Read failures raise RuntimeError with full context so the list-engine
        never mistakes a fetch error for "no data".  Silently returning an
        empty Account would let un-enriched records flow into the scorer and
        produce misleading ICP verdicts.

    Args:
        client: Duck-typed client exposing:
                    client.enrich_organization(domain: str) -> dict
                Use a real ApolloClient adapter for live runs, or
                FakeApolloClient for tests / zero-egress demos.
        domain: Company domain (e.g. "acmecorp.com").

    Returns:
        Account dataclass built from the Apollo enrichment response.

    Raises:
        RuntimeError: If client.enrich_organization raises for any reason,
            re-raised with domain context.
        ValueError: Propagated from enrich_to_account if name is missing.
    """
    try:
        org: dict[str, Any] = client.enrich_organization(domain)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Apollo organization enrichment fetch failed [domain={domain!r}]: {exc}"
        ) from exc

    return enrich_to_account(org)


def find_contacts(
    client: Any,
    domain: str,
    titles: list[str] | None = None,
) -> list[dict[str, str]]:
    """Search Apollo for people at a company and return normalized contact dicts.

    Calls client.search_people(domain, titles) and passes the resulting list
    to parse_contacts.

    FAIL LOUD CONTRACT:
        Client failures raise RuntimeError with domain and titles context.
        An empty list is a legitimate "no results" response and is returned
        as-is; only exceptions are re-raised.

    Args:
        client: Duck-typed client exposing:
                    client.search_people(domain: str,
                                         titles: list[str] | None) -> list[dict]
        domain: Company domain to search people within.
        titles: Optional list of job titles to filter by (e.g. ["VP of Sales"]).
                Pass None to return all available contacts for the domain.

    Returns:
        List of normalized contact dicts (see parse_contacts for schema).

    Raises:
        RuntimeError: If client.search_people raises for any reason, re-raised
            with domain and titles context.
    """
    try:
        people: list[dict[str, Any]] = list(client.search_people(domain, titles))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Apollo people search failed [domain={domain!r}, titles={titles!r}]: {exc}"
        ) from exc

    return parse_contacts(people)


# ---------------------------------------------------------------------------
# Fake client for demo and tests (zero egress, stdlib only).
# ---------------------------------------------------------------------------


class FakeApolloClient:
    """Returns canned data instead of calling the real Apollo API.

    Mirrors the duck-typed interface that enrich_company / find_contacts expect:
        client.enrich_organization(domain) -> dict
        client.search_people(domain, titles) -> list[dict]

    Zero network I/O — suitable for unit tests and zero-egress demos.

    Args:
        org_record: Canned organization dict returned by enrich_organization.
        people_records: Canned people list returned by search_people.
        raise_on_enrich: If True, enrich_organization raises RuntimeError
            to exercise the enrich_company error path.
        raise_on_search: If True, search_people raises RuntimeError to
            exercise the find_contacts error path.
    """

    def __init__(
        self,
        org_record: dict[str, Any],
        people_records: list[dict[str, Any]],
        raise_on_enrich: bool = False,
        raise_on_search: bool = False,
    ) -> None:
        self._org = org_record
        self._people = people_records
        self._raise_enrich = raise_on_enrich
        self._raise_search = raise_on_search
        self.enrich_calls: list[str] = []
        """Records domain per enrich_organization() invocation."""
        self.search_calls: list[tuple[str, list[str] | None]] = []
        """Records (domain, titles) per search_people() invocation."""

    def enrich_organization(self, domain: str) -> dict[str, Any]:
        """Record the call and return the canned org record (or raise)."""
        self.enrich_calls.append(domain)
        if self._raise_enrich:
            raise RuntimeError("Simulated Apollo enrich error")
        return dict(self._org)

    def search_people(
        self, domain: str, titles: list[str] | None
    ) -> list[dict[str, Any]]:
        """Record the call and return the canned people list (or raise)."""
        self.search_calls.append((domain, titles))
        if self._raise_search:
            raise RuntimeError("Simulated Apollo search error")
        return list(self._people)


# ---------------------------------------------------------------------------
# Demo — runs zero-egress, zero-credential.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    CANNED_ORG: dict[str, Any] = {
        "name": "Acme RevOps",
        "industry": "Software",
        "estimated_num_employees": 320,
        "technology_names": ["HubSpot", "Salesforce", "Stripe", "Segment"],
        "keywords": ["saas", "revops", "b2b"],
        "intent_strength": "strong",    # → "website_visit" signal
        "funding_stage": "Series B",    # → "funding" signal
        "job_postings_count": 8,        # → "hiring" signal
    }

    CANNED_PEOPLE: list[dict[str, Any]] = [
        {
            "name": "Jane Smith",
            "title": "VP of Revenue Operations",
            "email": "jane@acmerevops.com",
            "linkedin_url": "https://www.linkedin.com/in/janesmith",
        },
        {
            "name": "Carlos Reyes",
            "title": "Head of Sales",
            "email": "carlos@acmerevops.com",
            "linkedin_url": "https://www.linkedin.com/in/carlosreyes",
        },
        {
            "name": "  ",             # edge case — blank name
            "title": None,            # edge case — null title
            "email": "anon@acmerevops.com",
            "linkedin_url": "",
        },
    ]

    fake_client = FakeApolloClient(
        org_record=CANNED_ORG,
        people_records=CANNED_PEOPLE,
    )

    account = enrich_company(fake_client, domain="acmerevops.com")
    contacts = find_contacts(fake_client, domain="acmerevops.com", titles=["VP of Revenue Operations"])

    print("apollo_enrichment demo (FakeApolloClient — zero egress):\n")
    print(f"  Account : {account.name}")
    print(f"  Industry: {account.industry}")
    print(f"  Headcount: {account.employees}")
    print(f"  Tech stack ({len(account.tech_stack)}): {sorted(account.tech_stack)}")
    print(f"  Signals ({len(account.signals)}): {sorted(account.signals)}")
    print(f"  Fit: {account.fit}")
    print()
    print(f"  Contacts ({len(contacts)}):")
    for c in contacts:
        print(f"    {c['name'] or '(blank)'!r:<20}  {c['title'] or '(no title)'}")

    print(f"\n  enrich_organization() called {len(fake_client.enrich_calls)} time(s).")
    print(f"  search_people() called {len(fake_client.search_calls)} time(s).")
    print("\n  No network I/O occurred.  Swap in a real client for live execution.")
