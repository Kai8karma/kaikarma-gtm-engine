"""Tests for apollo_enrichment.py.

Runs zero-egress, stdlib-only.  All network I/O is replaced by FakeApolloClient.
Uses stdlib unittest (TestCase + unittest.main) per project convention.

Run:
    python 01-list-engine/test_apollo_enrichment.py
    python -m pytest 01-list-engine  (conftest.py puts the dir on sys.path)
"""

from __future__ import annotations

import unittest
from typing import Any

from apollo_enrichment import (
    FakeApolloClient,
    _coerce_employees,
    _extract_signals,
    _extract_tech_stack,
    enrich_company,
    enrich_to_account,
    find_contacts,
    parse_contacts,
)
from icp_schema import Account


# ---------------------------------------------------------------------------
# Helpers shared across test cases.
# ---------------------------------------------------------------------------

def _org(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid Apollo org dict, optionally overridden."""
    base: dict[str, Any] = {
        "name": "Acme Corp",
        "industry": "Software",
        "estimated_num_employees": 200,
        "technology_names": ["HubSpot", "Stripe"],
        "keywords": ["saas", "b2b"],
    }
    base.update(overrides)
    return base


def _person(**overrides: Any) -> dict[str, Any]:
    """Return a minimal Apollo person dict, optionally overridden."""
    base: dict[str, Any] = {
        "name": "Jane Smith",
        "title": "VP Sales",
        "email": "jane@acme.com",
        "linkedin_url": "https://linkedin.com/in/janesmith",
    }
    base.update(overrides)
    return base


def _fake_client(**kwargs: Any) -> FakeApolloClient:
    """Return a FakeApolloClient with sensible defaults."""
    return FakeApolloClient(
        org_record=kwargs.get("org_record", _org()),
        people_records=kwargs.get("people_records", [_person()]),
        raise_on_enrich=kwargs.get("raise_on_enrich", False),
        raise_on_search=kwargs.get("raise_on_search", False),
    )


# ---------------------------------------------------------------------------
# Unit tests: pure helpers.
# ---------------------------------------------------------------------------


class TestCoerceEmployees(unittest.TestCase):
    def test_integer_passthrough(self) -> None:
        self.assertEqual(_coerce_employees(320), 320)

    def test_string_numeric(self) -> None:
        self.assertEqual(_coerce_employees("150"), 150)

    def test_none_yields_zero(self) -> None:
        self.assertEqual(_coerce_employees(None), 0)

    def test_non_numeric_string_yields_zero(self) -> None:
        self.assertEqual(_coerce_employees("unknown"), 0)

    def test_zero_passthrough(self) -> None:
        self.assertEqual(_coerce_employees(0), 0)


class TestExtractTechStack(unittest.TestCase):
    def test_technology_names_lowercased(self) -> None:
        org = _org(technology_names=["HubSpot", "Salesforce"], keywords=[])
        result = _extract_tech_stack(org)
        self.assertEqual(result, frozenset({"hubspot", "salesforce"}))

    def test_keywords_merged(self) -> None:
        org = _org(technology_names=[], keywords=["CRM", "RevOps"])
        result = _extract_tech_stack(org)
        self.assertEqual(result, frozenset({"crm", "revops"}))

    def test_union_of_both_fields(self) -> None:
        org = _org(
            technology_names=["HubSpot"],
            keywords=["saas"],
        )
        result = _extract_tech_stack(org)
        self.assertIn("hubspot", result)
        self.assertIn("saas", result)

    def test_missing_fields_yield_empty(self) -> None:
        org: dict[str, Any] = {"name": "X", "industry": "tech"}
        result = _extract_tech_stack(org)
        self.assertEqual(result, frozenset())

    def test_none_fields_yield_empty(self) -> None:
        org = _org(technology_names=None, keywords=None)
        result = _extract_tech_stack(org)
        self.assertEqual(result, frozenset())

    def test_returns_frozenset(self) -> None:
        result = _extract_tech_stack(_org())
        self.assertIsInstance(result, frozenset)

    def test_deduplication(self) -> None:
        org = _org(technology_names=["Stripe", "stripe"], keywords=["STRIPE"])
        result = _extract_tech_stack(org)
        self.assertEqual(result, frozenset({"stripe"}))


class TestExtractSignals(unittest.TestCase):
    def test_intent_strength_yields_website_visit(self) -> None:
        org = _org(intent_strength="strong")
        self.assertIn("website_visit", _extract_signals(org))

    def test_funding_stage_yields_funding(self) -> None:
        org = _org(funding_stage="Series A")
        self.assertIn("funding", _extract_signals(org))

    def test_job_postings_positive_yields_hiring(self) -> None:
        org = _org(job_postings_count=5)
        self.assertIn("hiring", _extract_signals(org))

    def test_job_postings_zero_no_hiring_signal(self) -> None:
        org = _org(job_postings_count=0)
        self.assertNotIn("hiring", _extract_signals(org))

    def test_no_signal_fields_yields_empty(self) -> None:
        org = _org()  # no intent/funding/postings fields
        result = _extract_signals(org)
        self.assertEqual(result, frozenset())

    def test_all_three_signals_present(self) -> None:
        org = _org(
            intent_strength="medium",
            funding_stage="Seed",
            job_postings_count=3,
        )
        result = _extract_signals(org)
        self.assertIn("website_visit", result)
        self.assertIn("funding", result)
        self.assertIn("hiring", result)

    def test_returns_frozenset(self) -> None:
        result = _extract_signals(_org())
        self.assertIsInstance(result, frozenset)

    def test_job_postings_nonnumeric_no_signal(self) -> None:
        org = _org(job_postings_count="many")
        self.assertNotIn("hiring", _extract_signals(org))


# ---------------------------------------------------------------------------
# Unit tests: enrich_to_account (pure mapping).
# ---------------------------------------------------------------------------


class TestEnrichToAccount(unittest.TestCase):
    def test_returns_account_instance(self) -> None:
        result = enrich_to_account(_org())
        self.assertIsInstance(result, Account)

    def test_name_mapped(self) -> None:
        result = enrich_to_account(_org(name="Widgets Inc"))
        self.assertEqual(result.name, "Widgets Inc")

    def test_industry_lowercased(self) -> None:
        result = enrich_to_account(_org(industry="FinTech"))
        self.assertEqual(result.industry, "fintech")

    def test_employees_int(self) -> None:
        result = enrich_to_account(_org(estimated_num_employees=450))
        self.assertIsInstance(result.employees, int)
        self.assertEqual(result.employees, 450)

    def test_employees_none_defaults_zero(self) -> None:
        result = enrich_to_account(_org(estimated_num_employees=None))
        self.assertEqual(result.employees, 0)

    def test_technology_names_in_tech_stack(self) -> None:
        result = enrich_to_account(_org(technology_names=["HubSpot", "Clay"], keywords=[]))
        self.assertIn("hubspot", result.tech_stack)
        self.assertIn("clay", result.tech_stack)

    def test_keywords_in_tech_stack(self) -> None:
        result = enrich_to_account(_org(technology_names=[], keywords=["RevOps"]))
        self.assertIn("revops", result.tech_stack)

    def test_intent_maps_to_website_visit_signal(self) -> None:
        result = enrich_to_account(_org(intent_strength="strong"))
        self.assertIn("website_visit", result.signals)

    def test_funding_stage_maps_to_funding_signal(self) -> None:
        result = enrich_to_account(_org(funding_stage="Series C"))
        self.assertIn("funding", result.signals)

    def test_hiring_signal_from_postings(self) -> None:
        result = enrich_to_account(_org(job_postings_count=12))
        self.assertIn("hiring", result.signals)

    def test_fit_defaults_zero(self) -> None:
        result = enrich_to_account(_org())
        self.assertEqual(result.fit, 0.0)

    def test_missing_name_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            enrich_to_account({"industry": "tech"})

    def test_empty_name_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            enrich_to_account({"name": "", "industry": "tech"})

    def test_whitespace_only_name_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            enrich_to_account({"name": "   ", "industry": "tech"})

    def test_none_name_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            enrich_to_account({"name": None, "industry": "tech"})

    def test_tech_stack_is_frozenset(self) -> None:
        result = enrich_to_account(_org())
        self.assertIsInstance(result.tech_stack, frozenset)

    def test_signals_is_frozenset(self) -> None:
        result = enrich_to_account(_org())
        self.assertIsInstance(result.signals, frozenset)

    def test_determinism(self) -> None:
        """Same input must yield identical Account on repeated calls."""
        record = _org(
            name="Stable Co",
            technology_names=["A", "B", "C"],
            keywords=["x", "y"],
            intent_strength="strong",
        )
        r1 = enrich_to_account(record)
        r2 = enrich_to_account(record)
        self.assertEqual(r1, r2)

    def test_partial_record_no_tech_or_signals(self) -> None:
        """Minimal valid record with only name+industry should not raise."""
        result = enrich_to_account({"name": "Bare Co", "industry": "retail"})
        self.assertEqual(result.name, "Bare Co")
        self.assertEqual(result.tech_stack, frozenset())
        self.assertEqual(result.signals, frozenset())


# ---------------------------------------------------------------------------
# Unit tests: parse_contacts (pure normalization).
# ---------------------------------------------------------------------------


class TestParseContacts(unittest.TestCase):
    def test_returns_list_of_dicts(self) -> None:
        result = parse_contacts([_person()])
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], dict)

    def test_four_keys_present(self) -> None:
        result = parse_contacts([_person()])
        self.assertEqual(set(result[0].keys()), {"name", "title", "email", "linkedin_url"})

    def test_values_are_strings(self) -> None:
        result = parse_contacts([_person()])
        for v in result[0].values():
            self.assertIsInstance(v, str)

    def test_none_fields_become_empty_string(self) -> None:
        result = parse_contacts([_person(title=None, email=None)])
        self.assertEqual(result[0]["title"], "")
        self.assertEqual(result[0]["email"], "")

    def test_whitespace_stripped(self) -> None:
        result = parse_contacts([_person(name="  Alice  ", title="  CEO  ")])
        self.assertEqual(result[0]["name"], "Alice")
        self.assertEqual(result[0]["title"], "CEO")

    def test_empty_list_yields_empty_list(self) -> None:
        self.assertEqual(parse_contacts([]), [])

    def test_multiple_people_preserved_in_order(self) -> None:
        people = [_person(name="A"), _person(name="B"), _person(name="C")]
        result = parse_contacts(people)
        self.assertEqual([r["name"] for r in result], ["A", "B", "C"])

    def test_extra_apollo_fields_ignored(self) -> None:
        person = _person(city="San Francisco", phone_numbers=["415-555-0001"])
        result = parse_contacts([person])
        self.assertNotIn("city", result[0])
        self.assertNotIn("phone_numbers", result[0])

    def test_linkedin_url_preserved(self) -> None:
        url = "https://linkedin.com/in/testuser"
        result = parse_contacts([_person(linkedin_url=url)])
        self.assertEqual(result[0]["linkedin_url"], url)

    def test_determinism(self) -> None:
        people = [_person(name="X"), _person(name="Y")]
        r1 = parse_contacts(people)
        r2 = parse_contacts(people)
        self.assertEqual(r1, r2)


# ---------------------------------------------------------------------------
# Unit tests: enrich_company (injected client path).
# ---------------------------------------------------------------------------


class TestEnrichCompany(unittest.TestCase):
    def test_returns_account(self) -> None:
        client = _fake_client()
        result = enrich_company(client, domain="acme.com")
        self.assertIsInstance(result, Account)

    def test_name_from_org_record(self) -> None:
        client = _fake_client(org_record=_org(name="TargetCo"))
        result = enrich_company(client, domain="targetco.com")
        self.assertEqual(result.name, "TargetCo")

    def test_domain_passed_to_client(self) -> None:
        client = _fake_client()
        enrich_company(client, domain="check.io")
        self.assertEqual(client.enrich_calls, ["check.io"])

    def test_client_error_raises_runtime_error(self) -> None:
        client = _fake_client(raise_on_enrich=True)
        with self.assertRaises(RuntimeError) as ctx:
            enrich_company(client, domain="bad.io")
        self.assertIn("bad.io", str(ctx.exception))

    def test_missing_name_propagates_value_error(self) -> None:
        client = _fake_client(org_record={"industry": "tech"})
        with self.assertRaises(ValueError):
            enrich_company(client, domain="nameless.io")

    def test_enrich_calls_counter(self) -> None:
        client = _fake_client()
        enrich_company(client, domain="a.io")
        enrich_company(client, domain="b.io")
        self.assertEqual(len(client.enrich_calls), 2)


# ---------------------------------------------------------------------------
# Unit tests: find_contacts (injected client path).
# ---------------------------------------------------------------------------


class TestFindContacts(unittest.TestCase):
    def test_returns_list_of_dicts(self) -> None:
        client = _fake_client()
        result = find_contacts(client, domain="acme.com")
        self.assertIsInstance(result, list)

    def test_domain_and_titles_passed_to_client(self) -> None:
        client = _fake_client()
        find_contacts(client, domain="acme.com", titles=["VP Sales"])
        self.assertEqual(client.search_calls, [("acme.com", ["VP Sales"])])

    def test_titles_none_passed_through(self) -> None:
        client = _fake_client()
        find_contacts(client, domain="acme.com", titles=None)
        self.assertEqual(client.search_calls[0][1], None)

    def test_client_error_raises_runtime_error(self) -> None:
        client = _fake_client(raise_on_search=True)
        with self.assertRaises(RuntimeError) as ctx:
            find_contacts(client, domain="err.io")
        self.assertIn("err.io", str(ctx.exception))

    def test_empty_people_returns_empty_list(self) -> None:
        client = _fake_client(people_records=[])
        result = find_contacts(client, domain="acme.com")
        self.assertEqual(result, [])

    def test_contacts_normalized(self) -> None:
        client = _fake_client(
            people_records=[_person(name="  Bob  ", title=None)]
        )
        result = find_contacts(client, domain="acme.com")
        self.assertEqual(result[0]["name"], "Bob")
        self.assertEqual(result[0]["title"], "")

    def test_search_calls_counter(self) -> None:
        client = _fake_client()
        find_contacts(client, domain="acme.com")
        find_contacts(client, domain="beta.io")
        self.assertEqual(len(client.search_calls), 2)


# ---------------------------------------------------------------------------
# Integration-style smoke: enrich + score in one pass.
# ---------------------------------------------------------------------------


class TestEnrichThenScore(unittest.TestCase):
    """Verify that an Apollo-enriched Account flows cleanly into the scorer."""

    def test_account_scoreable(self) -> None:
        from icp_schema import ICPProfile
        from icp_scorer import score_account

        client = FakeApolloClient(
            org_record={
                "name": "Acme RevOps",
                "industry": "Software",
                "estimated_num_employees": 320,
                "technology_names": ["HubSpot", "Salesforce"],
                "keywords": ["saas"],
                "intent_strength": "strong",
                "funding_stage": "Series B",
                "job_postings_count": 4,
            },
            people_records=[],
        )
        account = enrich_company(client, domain="acmerevops.com")
        profile = ICPProfile(
            name="B2B SaaS",
            target_industries=frozenset({"software", "saas", "fintech"}),
            employee_min=50,
            employee_max=1000,
            target_tech=frozenset({"hubspot", "salesforce"}),
        )
        scored = score_account(account, profile)
        # Signal + tech + firmographic all firing → must beat tier C cutoff (35).
        self.assertGreater(scored.score, 35.0)
        self.assertIn(scored.tier, {"A", "B", "C"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
