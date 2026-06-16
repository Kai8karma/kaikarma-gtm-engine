"""Tests for hubspot_crm.py — HubSpot CRM adapter.

Stdlib unittest only.  Zero network I/O — all tests use FakeHubSpotClient or
call pure helpers directly.  Run with:

    python3 04-revops-engine/test_hubspot_crm.py

or via pytest (conftest.py puts the directory on sys.path).
"""

from __future__ import annotations

import unittest

from hubspot_crm import (
    FakeHubSpotClient,
    build_contact_update,
    company_to_account,
    fetch_companies,
    fetch_contacts,
    parse_companies,
    parse_contacts,
    update_contact,
)
from icp_schema import Account
from revops_schema import Route


# ---------------------------------------------------------------------------
# Helpers — shared fixtures.
# ---------------------------------------------------------------------------

def _company_row(
    name: str = "Acme Corp",
    industry: str = "COMPUTER_SOFTWARE",
    employees: str = "300",
    technologies: str = "",
    extra_props: dict | None = None,
) -> dict:
    """Build a minimal HubSpot company API row."""
    props: dict = {
        "name": name,
        "industry": industry,
        "numberofemployees": employees,
    }
    if technologies:
        props["technologies"] = technologies
    if extra_props:
        props.update(extra_props)
    return {"id": "100", "properties": props}


def _contact_row(
    contact_id: str = "501",
    email: str = "alice@example.com",
    firstname: str = "Alice",
    lastname: str = "Chen",
    lifecyclestage: str = "salesqualifiedlead",
) -> dict:
    """Build a minimal HubSpot contact API row."""
    return {
        "id": contact_id,
        "properties": {
            "email": email,
            "firstname": firstname,
            "lastname": lastname,
            "lifecyclestage": lifecyclestage,
        },
    }


def _route(destination: str = "ae_queue", sla_minutes: int = 60) -> Route:
    """Build a minimal Route for update tests."""
    return Route(
        lead_name="Test Lead",
        destination=destination,
        sla_minutes=sla_minutes,
        reason=f"test → {destination}",
    )


# ---------------------------------------------------------------------------
# 1. company_to_account — field mapping.
# ---------------------------------------------------------------------------

class TestCompanyToAccount(unittest.TestCase):

    def test_basic_mapping_industry_and_employees(self) -> None:
        row = _company_row(name="Acme Cloud", industry="COMPUTER_SOFTWARE", employees="480")
        acct = company_to_account(row["properties"])
        self.assertIsInstance(acct, Account)
        self.assertEqual(acct.name, "Acme Cloud")
        self.assertEqual(acct.industry, "software")
        self.assertEqual(acct.employees, 480)

    def test_unknown_industry_passes_through_lowercased(self) -> None:
        row = _company_row(industry="MYSTERY_VERTICAL")
        acct = company_to_account(row["properties"])
        self.assertEqual(acct.industry, "mystery_vertical")

    def test_empty_industry_maps_to_empty_string(self) -> None:
        props = {"name": "NoInd Co", "numberofemployees": "50"}
        acct = company_to_account(props)
        self.assertEqual(acct.industry, "")

    def test_employees_parsed_from_string(self) -> None:
        row = _company_row(employees="1200")
        acct = company_to_account(row["properties"])
        self.assertEqual(acct.employees, 1200)

    def test_employees_zero_when_missing(self) -> None:
        props = {"name": "Headless Co"}
        acct = company_to_account(props)
        self.assertEqual(acct.employees, 0)

    def test_employees_zero_when_blank(self) -> None:
        props = {"name": "BlankEmp", "numberofemployees": ""}
        acct = company_to_account(props)
        self.assertEqual(acct.employees, 0)

    def test_employees_zero_on_non_numeric(self) -> None:
        props = {"name": "BadEmp", "numberofemployees": "N/A"}
        acct = company_to_account(props)
        self.assertEqual(acct.employees, 0)

    def test_tech_stack_from_technologies_csv(self) -> None:
        row = _company_row(technologies="Salesforce, HubSpot, Snowflake")
        acct = company_to_account(row["properties"])
        self.assertIn("salesforce", acct.tech_stack)
        self.assertIn("hubspot", acct.tech_stack)
        self.assertIn("snowflake", acct.tech_stack)

    def test_tech_stack_from_tech_prefix_props(self) -> None:
        row = _company_row(extra_props={"tech_data_warehouse": "BigQuery"})
        acct = company_to_account(row["properties"])
        self.assertIn("bigquery", acct.tech_stack)

    def test_tech_stack_additive_both_sources(self) -> None:
        row = _company_row(
            technologies="Salesforce",
            extra_props={"tech_bi": "Tableau"},
        )
        acct = company_to_account(row["properties"])
        self.assertIn("salesforce", acct.tech_stack)
        self.assertIn("tableau", acct.tech_stack)

    def test_tech_stack_empty_when_no_tech_props(self) -> None:
        row = _company_row()
        acct = company_to_account(row["properties"])
        self.assertEqual(acct.tech_stack, frozenset())

    def test_signals_always_empty(self) -> None:
        row = _company_row()
        acct = company_to_account(row["properties"])
        self.assertEqual(acct.signals, frozenset())

    def test_fit_always_zero(self) -> None:
        row = _company_row()
        acct = company_to_account(row["properties"])
        self.assertEqual(acct.fit, 0.0)

    def test_missing_name_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            company_to_account({"industry": "COMPUTER_SOFTWARE"})
        self.assertIn("name", str(ctx.exception))

    def test_blank_name_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            company_to_account({"name": "", "industry": "RETAIL"})
        self.assertIn("name", str(ctx.exception))

    def test_account_is_frozen_dataclass(self) -> None:
        row = _company_row()
        acct = company_to_account(row["properties"])
        with self.assertRaises((AttributeError, TypeError)):
            acct.name = "hacked"  # type: ignore[misc]

    def test_financial_services_industry_mapping(self) -> None:
        row = _company_row(industry="FINANCIAL_SERVICES")
        acct = company_to_account(row["properties"])
        self.assertEqual(acct.industry, "financial_services")

    def test_employees_with_comma_formatted_number(self) -> None:
        # Some portals export "1,500" — should parse to 1500.
        row = _company_row(employees="1,500")
        acct = company_to_account(row["properties"])
        self.assertEqual(acct.employees, 1500)


# ---------------------------------------------------------------------------
# 2. parse_companies — batch mapping.
# ---------------------------------------------------------------------------

class TestParseCompanies(unittest.TestCase):

    def test_empty_list_returns_empty(self) -> None:
        self.assertEqual(parse_companies([]), [])

    def test_single_row_maps_correctly(self) -> None:
        rows = [_company_row(name="Solo Corp")]
        accounts = parse_companies(rows)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].name, "Solo Corp")

    def test_multiple_rows_preserve_order(self) -> None:
        rows = [
            _company_row(name="Alpha"),
            _company_row(name="Beta"),
            _company_row(name="Gamma"),
        ]
        accounts = parse_companies(rows)
        self.assertEqual([a.name for a in accounts], ["Alpha", "Beta", "Gamma"])

    def test_missing_name_in_batch_raises_value_error(self) -> None:
        rows = [
            _company_row(name="Good Corp"),
            {"id": "999", "properties": {}},  # no name
        ]
        with self.assertRaises(ValueError):
            parse_companies(rows)

    def test_row_without_properties_key_raises_value_error(self) -> None:
        # Missing 'properties' key → company_to_account gets empty dict → missing name.
        with self.assertRaises(ValueError):
            parse_companies([{"id": "777"}])

    def test_all_accounts_are_account_instances(self) -> None:
        rows = [_company_row(name=f"Corp {i}") for i in range(5)]
        accounts = parse_companies(rows)
        self.assertTrue(all(isinstance(a, Account) for a in accounts))

    def test_deterministic_across_identical_calls(self) -> None:
        rows = [_company_row(name="Stable Corp", technologies="AWS,GCP")]
        first = parse_companies(rows)
        second = parse_companies(rows)
        self.assertEqual(first[0].name, second[0].name)
        self.assertEqual(first[0].tech_stack, second[0].tech_stack)


# ---------------------------------------------------------------------------
# 3. parse_contacts — normalisation.
# ---------------------------------------------------------------------------

class TestParseContacts(unittest.TestCase):

    def test_empty_list_returns_empty(self) -> None:
        self.assertEqual(parse_contacts([]), [])

    def test_basic_contact_fields(self) -> None:
        rows = [_contact_row()]
        result = parse_contacts(rows)
        self.assertEqual(len(result), 1)
        c = result[0]
        self.assertEqual(c["id"], "501")
        self.assertEqual(c["email"], "alice@example.com")
        self.assertEqual(c["firstname"], "Alice")
        self.assertEqual(c["lastname"], "Chen")

    def test_email_lowercased(self) -> None:
        rows = [_contact_row(email="BOB@Company.COM")]
        result = parse_contacts(rows)
        self.assertEqual(result[0]["email"], "bob@company.com")

    def test_lifecycle_mapped_salesqualifiedlead(self) -> None:
        rows = [_contact_row(lifecyclestage="salesqualifiedlead")]
        result = parse_contacts(rows)
        self.assertEqual(result[0]["lifecyclestage"], "sql")

    def test_lifecycle_mapped_marketingqualifiedlead(self) -> None:
        rows = [_contact_row(lifecyclestage="marketingqualifiedlead")]
        result = parse_contacts(rows)
        self.assertEqual(result[0]["lifecyclestage"], "mql")

    def test_lifecycle_mapped_customer(self) -> None:
        rows = [_contact_row(lifecyclestage="customer")]
        result = parse_contacts(rows)
        self.assertEqual(result[0]["lifecyclestage"], "customer")

    def test_unknown_lifecycle_passes_through(self) -> None:
        rows = [_contact_row(lifecyclestage="custom_stage")]
        result = parse_contacts(rows)
        self.assertEqual(result[0]["lifecyclestage"], "custom_stage")

    def test_missing_email_gives_empty_string(self) -> None:
        row = {"id": "600", "properties": {"firstname": "Noemail", "lastname": "Person"}}
        result = parse_contacts([row])
        self.assertEqual(result[0]["email"], "")

    def test_missing_lifecyclestage_gives_empty_string(self) -> None:
        row = {"id": "601", "properties": {"email": "x@y.com"}}
        result = parse_contacts([row])
        self.assertEqual(result[0]["lifecyclestage"], "")

    def test_multiple_contacts_preserve_order(self) -> None:
        rows = [
            _contact_row(contact_id=str(i), email=f"user{i}@co.com")
            for i in range(4)
        ]
        result = parse_contacts(rows)
        self.assertEqual([c["id"] for c in result], ["0", "1", "2", "3"])

    def test_contact_dict_has_required_keys(self) -> None:
        rows = [_contact_row()]
        result = parse_contacts(rows)
        required_keys = {"id", "email", "firstname", "lastname", "lifecyclestage"}
        self.assertEqual(set(result[0].keys()), required_keys)


# ---------------------------------------------------------------------------
# 4. build_contact_update — payload construction.
# ---------------------------------------------------------------------------

class TestBuildContactUpdate(unittest.TestCase):

    def test_ae_queue_produces_correct_properties(self) -> None:
        route = _route(destination="ae_queue")
        payload = build_contact_update(route)
        props = payload["properties"]
        self.assertEqual(props["hs_lead_status"], "IN_PROGRESS")
        self.assertEqual(props["lifecyclestage"], "opportunity")

    def test_instant_alert_produces_in_progress(self) -> None:
        route = _route(destination="instant_alert")
        payload = build_contact_update(route)
        self.assertEqual(payload["properties"]["hs_lead_status"], "IN_PROGRESS")
        self.assertEqual(payload["properties"]["lifecyclestage"], "opportunity")

    def test_sdr_sequence_produces_open_and_sql(self) -> None:
        route = _route(destination="sdr_sequence")
        payload = build_contact_update(route)
        self.assertEqual(payload["properties"]["hs_lead_status"], "OPEN")
        self.assertEqual(payload["properties"]["lifecyclestage"], "salesqualifiedlead")

    def test_nurture_produces_open_and_mql(self) -> None:
        route = _route(destination="nurture")
        payload = build_contact_update(route)
        self.assertEqual(payload["properties"]["hs_lead_status"], "OPEN")
        self.assertEqual(payload["properties"]["lifecyclestage"], "marketingqualifiedlead")

    def test_disqualified_produces_unqualified(self) -> None:
        route = _route(destination="disqualified")
        payload = build_contact_update(route)
        self.assertEqual(payload["properties"]["hs_lead_status"], "UNQUALIFIED")
        self.assertEqual(payload["properties"]["lifecyclestage"], "lead")

    def test_owner_id_included_when_provided(self) -> None:
        route = _route(destination="ae_queue")
        payload = build_contact_update(route, owner_id="77")
        self.assertEqual(payload["properties"]["hubspot_owner_id"], "77")

    def test_owner_id_omitted_when_none(self) -> None:
        route = _route(destination="ae_queue")
        payload = build_contact_update(route, owner_id=None)
        self.assertNotIn("hubspot_owner_id", payload["properties"])

    def test_payload_has_properties_key(self) -> None:
        payload = build_contact_update(_route())
        self.assertIn("properties", payload)

    def test_unknown_destination_defaults_to_open_lead(self) -> None:
        route = Route(
            lead_name="X",
            destination="mystery_queue",
            sla_minutes=30,
            reason="test",
        )
        payload = build_contact_update(route)
        self.assertEqual(payload["properties"]["hs_lead_status"], "OPEN")
        self.assertEqual(payload["properties"]["lifecyclestage"], "lead")

    def test_deterministic_same_route_same_payload(self) -> None:
        route = _route(destination="sdr_sequence")
        p1 = build_contact_update(route, owner_id="42")
        p2 = build_contact_update(route, owner_id="42")
        self.assertEqual(p1, p2)

    def test_all_known_destinations_produce_valid_statuses(self) -> None:
        for dest in ("ae_queue", "instant_alert", "sdr_sequence", "nurture", "disqualified"):
            with self.subTest(destination=dest):
                route = _route(destination=dest)
                payload = build_contact_update(route)
                props = payload["properties"]
                self.assertIn("hs_lead_status", props)
                self.assertIn("lifecyclestage", props)
                self.assertIsInstance(props["hs_lead_status"], str)
                self.assertIsInstance(props["lifecyclestage"], str)


# ---------------------------------------------------------------------------
# 5. fetch_companies / fetch_contacts via FakeHubSpotClient.
# ---------------------------------------------------------------------------

class TestFetchViaFakeClient(unittest.TestCase):

    def _make_client(self) -> FakeHubSpotClient:
        return FakeHubSpotClient(
            company_rows=[
                _company_row(name="Acme", industry="COMPUTER_SOFTWARE", employees="200"),
                _company_row(name="BetaCo", industry="FINANCIAL_SERVICES", employees="900"),
            ],
            contact_rows=[
                _contact_row(contact_id="1", email="a@a.com"),
                _contact_row(contact_id="2", email="b@b.com"),
            ],
        )

    def test_fetch_companies_returns_accounts(self) -> None:
        client = self._make_client()
        accounts = fetch_companies(client, limit=50)
        self.assertEqual(len(accounts), 2)
        self.assertIsInstance(accounts[0], Account)

    def test_fetch_companies_records_call(self) -> None:
        client = self._make_client()
        fetch_companies(client, limit=25)
        self.assertEqual(client.get_company_calls, [25])

    def test_fetch_companies_raises_runtime_error_on_api_failure(self) -> None:
        client = FakeHubSpotClient(raise_on_get=True)
        with self.assertRaises(RuntimeError) as ctx:
            fetch_companies(client)
        self.assertIn("fetch_companies", str(ctx.exception))

    def test_fetch_contacts_returns_normalised_dicts(self) -> None:
        client = self._make_client()
        contacts = fetch_contacts(client, limit=50)
        self.assertEqual(len(contacts), 2)
        self.assertIn("email", contacts[0])

    def test_fetch_contacts_records_call(self) -> None:
        client = self._make_client()
        fetch_contacts(client, limit=10)
        self.assertEqual(client.get_contact_calls, [10])

    def test_fetch_contacts_raises_runtime_error_on_api_failure(self) -> None:
        client = FakeHubSpotClient(raise_on_get=True)
        with self.assertRaises(RuntimeError) as ctx:
            fetch_contacts(client)
        self.assertIn("fetch_contacts", str(ctx.exception))

    def test_limit_respected_by_fake_client(self) -> None:
        client = FakeHubSpotClient(
            company_rows=[_company_row(name=f"Co{i}") for i in range(10)]
        )
        accounts = fetch_companies(client, limit=3)
        self.assertEqual(len(accounts), 3)

    def test_fetch_then_update_roundtrip(self) -> None:
        client = self._make_client()
        contacts = fetch_contacts(client)
        route = _route(destination="ae_queue")
        payload = build_contact_update(route, owner_id="99")
        result = update_contact(client, contacts[0]["id"], payload)
        self.assertTrue(result.get("ok"))
        self.assertEqual(client.patch_calls[0][0], contacts[0]["id"])

    def test_update_contact_returns_success_dict(self) -> None:
        client = self._make_client()
        payload = build_contact_update(_route())
        result = update_contact(client, "501", payload)
        self.assertIn("id", result)
        self.assertTrue(result.get("ok"))

    def test_update_contact_returns_failure_dict_on_error(self) -> None:
        client = FakeHubSpotClient(raise_on_patch=True)
        payload = build_contact_update(_route())
        result = update_contact(client, "501", payload)
        self.assertFalse(result.get("ok"))
        self.assertEqual(result["contact_id"], "501")
        self.assertIn("error", result)

    def test_update_contact_does_not_raise(self) -> None:
        """update_contact must NEVER propagate an exception — executor contract."""
        client = FakeHubSpotClient(raise_on_patch=True)
        payload = build_contact_update(_route())
        try:
            update_contact(client, "501", payload)
        except Exception as exc:
            self.fail(f"update_contact raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# 6. Missing required field — ValueError propagation.
# ---------------------------------------------------------------------------

class TestMissingFieldErrors(unittest.TestCase):

    def test_company_missing_name_names_field_in_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            company_to_account({"industry": "INTERNET", "numberofemployees": "50"})
        self.assertIn("name", str(ctx.exception))

    def test_parse_companies_missing_name_in_one_row(self) -> None:
        rows = [
            _company_row(name="Good"),
            {"id": "bad", "properties": {"industry": "RETAIL"}},
        ]
        with self.assertRaises(ValueError):
            parse_companies(rows)

    def test_company_to_account_missing_name_raises_not_returns(self) -> None:
        """Ensures the function raises, not silently returns a bad Account."""
        with self.assertRaises(ValueError):
            company_to_account({})

    def test_fetch_companies_propagates_value_error_from_bad_row(self) -> None:
        client = FakeHubSpotClient(
            company_rows=[{"id": "nope", "properties": {}}]
        )
        with self.assertRaises(ValueError):
            fetch_companies(client)


# ---------------------------------------------------------------------------
# 7. Determinism.
# ---------------------------------------------------------------------------

class TestDeterminism(unittest.TestCase):

    def test_company_to_account_is_deterministic(self) -> None:
        props = {
            "name": "Stable Corp",
            "industry": "COMPUTER_SOFTWARE",
            "numberofemployees": "300",
            "technologies": "AWS,GCP,Snowflake",
        }
        a1 = company_to_account(props)
        a2 = company_to_account(props)
        self.assertEqual(a1, a2)

    def test_build_contact_update_is_deterministic(self) -> None:
        route = _route(destination="nurture")
        p1 = build_contact_update(route, owner_id="55")
        p2 = build_contact_update(route, owner_id="55")
        self.assertEqual(p1, p2)

    def test_parse_companies_order_stable(self) -> None:
        names = ["Zeta", "Alpha", "Mu"]
        rows = [_company_row(name=n) for n in names]
        result = parse_companies(rows)
        self.assertEqual([a.name for a in result], names)

    def test_parse_contacts_order_stable(self) -> None:
        rows = [_contact_row(contact_id=str(i)) for i in range(5)]
        result = parse_contacts(rows)
        self.assertEqual([c["id"] for c in result], [str(i) for i in range(5)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
