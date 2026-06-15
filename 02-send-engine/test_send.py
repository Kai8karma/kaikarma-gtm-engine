"""Tests for the send engine. The infrastructure is only real if it's falsifiable.

Stdlib `unittest` — no install needed (runs air-gapped). pytest discovers these
too if you have it:
    python3 02-send-engine/test_send.py            # stdlib
    python3 -m pytest 02-send-engine               # if pytest installed
"""

import unittest

from domain_calculator import SENDING_DAYS_PER_MONTH, plan_infra
from dns_validator import validate_dkim, validate_dmarc, validate_spf
from send_schema import DnsCheck, InfraPlan


# ---------------------------------------------------------------------------
# domain_calculator tests
# ---------------------------------------------------------------------------

class TestDomainCalculator(unittest.TestCase):

    def test_single_mailbox_for_tiny_volume(self):
        # 300 emails/month, cap 30/day → 300/(30*22) = 0.45 → ceil → 1 mailbox
        p = plan_infra(300)
        self.assertEqual(p.mailboxes_needed, 1)
        self.assertEqual(p.domains_needed, 1)  # 1 mailbox / 2 per domain → ceil → 1

    def test_mailboxes_ceiling_rounds_up(self):
        # 1 over the per-mailbox capacity forces a second mailbox
        cap_per_mailbox = 30 * SENDING_DAYS_PER_MONTH  # 660
        p = plan_infra(cap_per_mailbox + 1)
        self.assertEqual(p.mailboxes_needed, 2)

    def test_domains_ceil_over_mailboxes_per_domain(self):
        # 3 mailboxes, 2 per domain → ceil(3/2) = 2 domains
        # Need 2 mailboxes for the base load, then force a 3rd via volume
        cap_per_mailbox = 30 * SENDING_DAYS_PER_MONTH  # 660
        # 2*660 + 1 = 1321 emails → 3 mailboxes → ceil(3/2) = 2 domains
        p = plan_infra(2 * cap_per_mailbox + 1)
        self.assertEqual(p.mailboxes_needed, 3)
        self.assertEqual(p.domains_needed, 2)

    def test_plan_infra_returns_infra_plan(self):
        p = plan_infra(5_000)
        self.assertIsInstance(p, InfraPlan)

    def test_ramp_schedule_length_matches_warmup_weeks(self):
        p = plan_infra(5_000, warmup_weeks=4)
        self.assertEqual(len(p.ramp_schedule), 4)

    def test_ramp_week_1_starts_at_1_send(self):
        p = plan_infra(5_000, warmup_weeks=3)
        self.assertEqual(p.ramp_schedule[0].daily_sends, 1)

    def test_ramp_last_week_reaches_full_cap(self):
        cap = 30
        p = plan_infra(5_000, per_mailbox_daily_cap=cap, warmup_weeks=3)
        self.assertEqual(p.ramp_schedule[-1].daily_sends, cap)

    def test_ramp_total_daily_is_per_mailbox_times_mailboxes(self):
        p = plan_infra(5_000, warmup_weeks=3)
        for week in p.ramp_schedule:
            self.assertEqual(week.total_daily, week.daily_sends * p.mailboxes_needed)

    def test_single_warmup_week_jumps_to_full_cap(self):
        cap = 25
        p = plan_infra(2_000, per_mailbox_daily_cap=cap, warmup_weeks=1)
        self.assertEqual(len(p.ramp_schedule), 1)
        self.assertEqual(p.ramp_schedule[0].daily_sends, cap)

    def test_custom_mailboxes_per_domain(self):
        # 4 mailboxes, 4 per domain → exactly 1 domain
        cap_per_mailbox = 30 * SENDING_DAYS_PER_MONTH  # 660
        volume = 3 * cap_per_mailbox + 1  # forces 4 mailboxes
        p = plan_infra(volume, mailboxes_per_domain=4)
        self.assertEqual(p.mailboxes_needed, 4)
        self.assertEqual(p.domains_needed, 1)

    def test_large_volume_scales_linearly(self):
        p = plan_infra(100_000)
        expected_mailboxes = -(-100_000 // (30 * SENDING_DAYS_PER_MONTH))  # ceil via negation trick
        self.assertEqual(p.mailboxes_needed, expected_mailboxes)

    def test_invalid_monthly_emails_raises(self):
        with self.assertRaises(ValueError):
            plan_infra(0)

    def test_invalid_per_mailbox_cap_raises(self):
        with self.assertRaises(ValueError):
            plan_infra(1_000, per_mailbox_daily_cap=0)

    def test_invalid_mailboxes_per_domain_raises(self):
        with self.assertRaises(ValueError):
            plan_infra(1_000, mailboxes_per_domain=0)

    def test_invalid_warmup_weeks_raises(self):
        with self.assertRaises(ValueError):
            plan_infra(1_000, warmup_weeks=0)

    def test_plan_is_deterministic(self):
        self.assertEqual(plan_infra(5_000), plan_infra(5_000))


# ---------------------------------------------------------------------------
# dns_validator — SPF tests
# ---------------------------------------------------------------------------

class TestSpfValidator(unittest.TestCase):

    def test_valid_spf_softfail(self):
        r = validate_spf("v=spf1 include:sendgrid.net ~all")
        self.assertTrue(r.passed)
        self.assertEqual(r.issues, ())

    def test_valid_spf_hardfail(self):
        r = validate_spf("v=spf1 include:amazonses.com -all")
        self.assertTrue(r.passed)
        self.assertEqual(r.issues, ())

    def test_invalid_spf_no_version(self):
        r = validate_spf("include:sendgrid.net ~all")
        self.assertFalse(r.passed)
        self.assertTrue(any("v=spf1" in i for i in r.issues))

    def test_invalid_spf_plus_all(self):
        r = validate_spf("v=spf1 include:sendgrid.net +all")
        self.assertFalse(r.passed)
        self.assertTrue(any("+all" in i for i in r.issues))

    def test_invalid_spf_neutral_all(self):
        r = validate_spf("v=spf1 include:sendgrid.net ?all")
        self.assertFalse(r.passed)
        self.assertTrue(any("?all" in i for i in r.issues))

    def test_invalid_spf_missing_all(self):
        r = validate_spf("v=spf1 include:sendgrid.net")
        self.assertFalse(r.passed)
        self.assertGreater(len(r.issues), 0)

    def test_returns_dns_check(self):
        r = validate_spf("v=spf1 ~all")
        self.assertIsInstance(r, DnsCheck)
        self.assertEqual(r.record_type, "SPF")

    def test_whitespace_tolerant(self):
        r = validate_spf("  v=spf1 include:sendgrid.net ~all  ")
        self.assertTrue(r.passed)


# ---------------------------------------------------------------------------
# dns_validator — DKIM tests
# ---------------------------------------------------------------------------

class TestDkimValidator(unittest.TestCase):

    def test_valid_dkim(self):
        r = validate_dkim("v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADI")
        self.assertTrue(r.passed)
        self.assertEqual(r.issues, ())

    def test_invalid_dkim_no_version(self):
        r = validate_dkim("k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADI")
        self.assertFalse(r.passed)
        self.assertTrue(any("v=DKIM1" in i for i in r.issues))

    def test_invalid_dkim_empty_key(self):
        r = validate_dkim("v=DKIM1; k=rsa; p=")
        self.assertFalse(r.passed)
        self.assertTrue(any("empty" in i.lower() or "revokes" in i.lower() for i in r.issues))

    def test_invalid_dkim_missing_p_tag(self):
        r = validate_dkim("v=DKIM1; k=rsa")
        self.assertFalse(r.passed)
        self.assertTrue(any("p=" in i for i in r.issues))

    def test_returns_dns_check(self):
        r = validate_dkim("v=DKIM1; k=rsa; p=abc123")
        self.assertIsInstance(r, DnsCheck)
        self.assertEqual(r.record_type, "DKIM")

    def test_case_insensitive_version_check(self):
        # v=dkim1 lowercase should still pass
        r = validate_dkim("v=dkim1; k=rsa; p=abc123")
        self.assertTrue(r.passed)


# ---------------------------------------------------------------------------
# dns_validator — DMARC tests
# ---------------------------------------------------------------------------

class TestDmarcValidator(unittest.TestCase):

    def test_valid_dmarc_quarantine(self):
        r = validate_dmarc("v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com")
        self.assertTrue(r.passed)
        self.assertEqual(r.issues, ())

    def test_valid_dmarc_reject(self):
        r = validate_dmarc("v=DMARC1; p=reject; rua=mailto:dmarc@example.com")
        self.assertTrue(r.passed)

    def test_valid_dmarc_none(self):
        # p=none is a valid policy value (monitoring mode)
        r = validate_dmarc("v=DMARC1; p=none; rua=mailto:dmarc@example.com")
        self.assertTrue(r.passed)

    def test_invalid_dmarc_no_version(self):
        r = validate_dmarc("p=reject; rua=mailto:dmarc@example.com")
        self.assertFalse(r.passed)
        self.assertTrue(any("v=DMARC1" in i for i in r.issues))

    def test_invalid_dmarc_missing_policy(self):
        r = validate_dmarc("v=DMARC1; rua=mailto:dmarc@example.com")
        self.assertFalse(r.passed)
        self.assertTrue(any("p=" in i for i in r.issues))

    def test_invalid_dmarc_bad_policy_value(self):
        r = validate_dmarc("v=DMARC1; p=accept")
        self.assertFalse(r.passed)
        self.assertTrue(any("accept" in i for i in r.issues))

    def test_returns_dns_check(self):
        r = validate_dmarc("v=DMARC1; p=reject")
        self.assertIsInstance(r, DnsCheck)
        self.assertEqual(r.record_type, "DMARC")

    def test_issues_is_tuple(self):
        r = validate_dmarc("v=DMARC1; p=reject")
        self.assertIsInstance(r.issues, tuple)

    def test_multiple_issues_captured(self):
        # Missing both v= and p=
        r = validate_dmarc("rua=mailto:x@example.com")
        self.assertFalse(r.passed)
        self.assertGreaterEqual(len(r.issues), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
