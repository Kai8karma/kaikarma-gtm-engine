"""Tests for the Instantly-adapter email sequencer.

Stdlib unittest — no third-party packages needed (air-gapped).
The existing conftest.py puts 02-send-engine/ on sys.path, so this file
imports directly from sequencer without a package prefix.

    python3 02-send-engine/test_sequencer.py         # stdlib runner
    python3 -m pytest 02-send-engine/test_sequencer.py  # if pytest installed
"""

import unittest

from sequencer import (
    FakeSequencerClient,
    SequenceResult,
    add_lead_to_campaign,
    add_leads_batch,
    build_lead_payload,
)


# ---------------------------------------------------------------------------
# build_lead_payload — pure function, no client
# ---------------------------------------------------------------------------

class TestBuildLeadPayload(unittest.TestCase):

    def test_minimal_email_only(self):
        p = build_lead_payload("user@example.com")
        self.assertEqual(p["email"], "user@example.com")
        self.assertEqual(p["firstName"], "")
        self.assertEqual(p["companyName"], "")
        self.assertEqual(p["variables"], {})

    def test_all_fields_populated(self):
        p = build_lead_payload(
            "sarah@acme.com",
            first_name="Sarah",
            company="Acme Inc.",
            custom_vars={"signal": "raised Series A"},
        )
        self.assertEqual(p["email"], "sarah@acme.com")
        self.assertEqual(p["firstName"], "Sarah")
        self.assertEqual(p["companyName"], "Acme Inc.")
        self.assertEqual(p["variables"], {"signal": "raised Series A"})

    def test_custom_vars_are_copied_not_aliased(self):
        """Mutating the original dict after building must not affect the payload."""
        original = {"k": "v"}
        p = build_lead_payload("x@y.com", custom_vars=original)
        original["k"] = "mutated"
        self.assertEqual(p["variables"]["k"], "v")

    def test_none_custom_vars_produces_empty_dict(self):
        p = build_lead_payload("a@b.com", custom_vars=None)
        self.assertEqual(p["variables"], {})

    def test_email_stripped_of_whitespace(self):
        p = build_lead_payload("  trimmed@example.com  ")
        self.assertEqual(p["email"], "trimmed@example.com")

    def test_returns_dict_with_expected_keys(self):
        p = build_lead_payload("a@b.com")
        self.assertSetEqual(set(p.keys()), {"email", "firstName", "companyName", "variables"})

    def test_campaign_key_not_in_payload(self):
        """campaign is supplied at send time, never baked into the lead dict."""
        p = build_lead_payload("a@b.com")
        self.assertNotIn("campaign", p)

    def test_deterministic_same_inputs_same_output(self):
        a = build_lead_payload("x@y.com", first_name="X", company="Y", custom_vars={"z": "1"})
        b = build_lead_payload("x@y.com", first_name="X", company="Y", custom_vars={"z": "1"})
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# build_lead_payload — validation / ValueError path
# ---------------------------------------------------------------------------

class TestBuildLeadPayloadValidation(unittest.TestCase):

    def test_empty_email_raises(self):
        with self.assertRaises(ValueError):
            build_lead_payload("")

    def test_whitespace_only_email_raises(self):
        with self.assertRaises(ValueError):
            build_lead_payload("   ")

    def test_email_missing_at_sign_raises(self):
        with self.assertRaises(ValueError):
            build_lead_payload("notanemail")

    def test_email_missing_at_sign_domain_only_raises(self):
        with self.assertRaises(ValueError):
            build_lead_payload("example.com")

    def test_error_message_names_bad_email(self):
        """ValueError message should echo the bad input."""
        bad = "bad-email"
        with self.assertRaises(ValueError) as ctx:
            build_lead_payload(bad)
        self.assertIn(bad, str(ctx.exception))


# ---------------------------------------------------------------------------
# add_lead_to_campaign — single add, ok path
# ---------------------------------------------------------------------------

class TestAddLeadToCampaignOk(unittest.TestCase):

    def setUp(self):
        self.client = FakeSequencerClient()
        self.campaign_id = "camp_test_001"
        self.lead = build_lead_payload("ok@success.com", first_name="Ok", company="Successco")

    def test_returns_sequence_result(self):
        r = add_lead_to_campaign(self.client, self.campaign_id, self.lead)
        self.assertIsInstance(r, SequenceResult)

    def test_ok_is_true_on_success(self):
        r = add_lead_to_campaign(self.client, self.campaign_id, self.lead)
        self.assertTrue(r.ok)

    def test_email_in_result(self):
        r = add_lead_to_campaign(self.client, self.campaign_id, self.lead)
        self.assertEqual(r.email, "ok@success.com")

    def test_message_is_non_empty(self):
        r = add_lead_to_campaign(self.client, self.campaign_id, self.lead)
        self.assertTrue(r.message)

    def test_client_receives_campaign_id_in_payload(self):
        add_lead_to_campaign(self.client, self.campaign_id, self.lead)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.client.calls[0]["payload"]["campaign"], self.campaign_id)

    def test_client_called_exactly_once(self):
        add_lead_to_campaign(self.client, self.campaign_id, self.lead)
        self.assertEqual(len(self.client.calls), 1)

    def test_original_lead_dict_not_mutated(self):
        """add_lead_to_campaign must not modify the caller's lead dict."""
        lead_copy = dict(self.lead)
        add_lead_to_campaign(self.client, self.campaign_id, self.lead)
        self.assertNotIn("campaign", self.lead)
        self.assertEqual(self.lead, lead_copy)


# ---------------------------------------------------------------------------
# add_lead_to_campaign — fail path (client raises)
# ---------------------------------------------------------------------------

class TestAddLeadToCampaignFail(unittest.TestCase):

    def test_client_exception_returns_ok_false(self):
        client = FakeSequencerClient(fail_emails={"bad@fail.com"})
        lead = build_lead_payload("bad@fail.com")
        r = add_lead_to_campaign(client, "camp_x", lead)
        self.assertFalse(r.ok)

    def test_fail_result_carries_email(self):
        client = FakeSequencerClient(fail_emails={"bad@fail.com"})
        lead = build_lead_payload("bad@fail.com")
        r = add_lead_to_campaign(client, "camp_x", lead)
        self.assertEqual(r.email, "bad@fail.com")

    def test_fail_message_is_non_empty(self):
        client = FakeSequencerClient(fail_emails={"bad@fail.com"})
        lead = build_lead_payload("bad@fail.com")
        r = add_lead_to_campaign(client, "camp_x", lead)
        self.assertTrue(r.message)

    def test_non_success_api_status_returns_ok_false(self):
        """Client that returns status!='success' should yield ok=False."""

        class PartialFakeClient:
            def add_lead(self, campaign_id: str, payload: dict) -> dict:
                return {"status": "pending", "detail": "queued for review"}

        r = add_lead_to_campaign(PartialFakeClient(), "camp_y", build_lead_payload("x@y.com"))
        self.assertFalse(r.ok)


# ---------------------------------------------------------------------------
# add_leads_batch — partial-failure containment
# ---------------------------------------------------------------------------

class TestAddLeadsBatch(unittest.TestCase):

    def setUp(self):
        self.campaign_id = "camp_batch_001"
        self.good1 = build_lead_payload("alice@good.com", first_name="Alice")
        self.good2 = build_lead_payload("bob@good.com", first_name="Bob")
        self.bad = build_lead_payload("err@fail.com", first_name="Err")
        self.good3 = build_lead_payload("carol@good.com", first_name="Carol")
        self.leads = [self.good1, self.bad, self.good2, self.good3]
        self.client = FakeSequencerClient(fail_emails={"err@fail.com"})

    def test_returns_one_result_per_lead(self):
        results = add_leads_batch(self.client, self.campaign_id, self.leads)
        self.assertEqual(len(results), len(self.leads))

    def test_failing_lead_does_not_abort_batch(self):
        results = add_leads_batch(self.client, self.campaign_id, self.leads)
        ok_results = [r for r in results if r.ok]
        # 3 good leads must succeed even though the middle one failed
        self.assertEqual(len(ok_results), 3)

    def test_failing_lead_result_is_ok_false(self):
        results = add_leads_batch(self.client, self.campaign_id, self.leads)
        fail_result = next(r for r in results if r.email == "err@fail.com")
        self.assertFalse(fail_result.ok)

    def test_all_clients_called_including_failing_lead(self):
        """Even the failing email must attempt an add_lead() call."""
        add_leads_batch(self.client, self.campaign_id, self.leads)
        called_emails = [c["payload"]["email"] for c in self.client.calls]
        self.assertIn("err@fail.com", called_emails)
        self.assertEqual(len(self.client.calls), len(self.leads))

    def test_result_order_matches_input_order(self):
        results = add_leads_batch(self.client, self.campaign_id, self.leads)
        input_emails = [lead["email"] for lead in self.leads]
        result_emails = [r.email for r in results]
        self.assertEqual(result_emails, input_emails)

    def test_empty_batch_returns_empty_list(self):
        client = FakeSequencerClient()
        results = add_leads_batch(client, self.campaign_id, [])
        self.assertEqual(results, [])

    def test_all_fail_batch_returns_all_ok_false(self):
        all_fail = [build_lead_payload(f"f{i}@fail.com") for i in range(3)]
        client = FakeSequencerClient(fail_emails={lead["email"] for lead in all_fail})
        results = add_leads_batch(client, self.campaign_id, all_fail)
        self.assertTrue(all(not r.ok for r in results))

    def test_all_ok_batch_returns_all_ok_true(self):
        all_ok = [build_lead_payload(f"ok{i}@good.com") for i in range(4)]
        client = FakeSequencerClient()
        results = add_leads_batch(client, self.campaign_id, all_ok)
        self.assertTrue(all(r.ok for r in results))


# ---------------------------------------------------------------------------
# SequenceResult — dataclass contract
# ---------------------------------------------------------------------------

class TestSequenceResult(unittest.TestCase):

    def test_is_frozen(self):
        r = SequenceResult(email="a@b.com", ok=True, message="ok")
        with self.assertRaises((AttributeError, TypeError)):
            r.ok = False  # type: ignore[misc]

    def test_equality_by_value(self):
        r1 = SequenceResult(email="a@b.com", ok=True, message="ok")
        r2 = SequenceResult(email="a@b.com", ok=True, message="ok")
        self.assertEqual(r1, r2)

    def test_inequality_on_different_ok(self):
        r1 = SequenceResult(email="a@b.com", ok=True, message="ok")
        r2 = SequenceResult(email="a@b.com", ok=False, message="ok")
        self.assertNotEqual(r1, r2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
