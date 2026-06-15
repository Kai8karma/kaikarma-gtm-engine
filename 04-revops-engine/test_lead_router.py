"""Tests for the RevOps lead router. Every routing rule must be provably correct.

    python3 04-revops-engine/test_lead_router.py
"""

from __future__ import annotations

import unittest

from revops_schema import Lead, RoutingPolicy, TierPolicy
from lead_router import DEFAULT_POLICY, DISQUALIFIED, INSTANT_ALERT, round_robin, route

# ---------------------------------------------------------------------------
# Shared policy fixture — high SLAs so values are easy to assert.
# ---------------------------------------------------------------------------
POLICY = RoutingPolicy(
    tier_map={
        "A": TierPolicy(destination="ae_queue",     sla_minutes=60),
        "B": TierPolicy(destination="sdr_sequence", sla_minutes=240),
        "C": TierPolicy(destination="nurture",      sla_minutes=1440),
        "D": TierPolicy(destination=DISQUALIFIED,   sla_minutes=0),
    },
    signal_escalates=True,
    instant_alert_sla_minutes=5,
)


class TestTierDestination(unittest.TestCase):

    def test_a_tier_no_signal_routes_to_ae_queue(self):
        r = route(Lead("Acme", "A", None, "AMER"), POLICY)
        self.assertEqual(r.destination, "ae_queue")
        self.assertEqual(r.sla_minutes, 60)

    def test_b_tier_routes_to_sdr_sequence(self):
        r = route(Lead("Beta", "B", None, "EMEA"), POLICY)
        self.assertEqual(r.destination, "sdr_sequence")
        self.assertEqual(r.sla_minutes, 240)

    def test_c_tier_routes_to_nurture(self):
        r = route(Lead("Gamma", "C", None, "APAC"), POLICY)
        self.assertEqual(r.destination, "nurture")
        self.assertEqual(r.sla_minutes, 1440)

    def test_b_tier_with_signal_still_routes_to_sdr(self):
        """Only A-tier triggers escalation — B stays in standard lane."""
        r = route(Lead("Beta", "B", "hiring", "AMER"), POLICY)
        self.assertEqual(r.destination, "sdr_sequence")


class TestSignalEscalation(unittest.TestCase):

    def test_a_tier_with_signal_escalates_to_instant_alert(self):
        r = route(Lead("Acme", "A", "job_change", "AMER"), POLICY)
        self.assertEqual(r.destination, INSTANT_ALERT)
        self.assertEqual(r.sla_minutes, 5)
        self.assertIn("job_change", r.reason)

    def test_a_tier_with_signal_escalates_for_any_signal_type(self):
        for signal in ("hiring", "funding", "website_visit", "tech_change"):
            with self.subTest(signal=signal):
                r = route(Lead("X", "A", signal, "AMER"), POLICY)
                self.assertEqual(r.destination, INSTANT_ALERT)

    def test_a_tier_no_signal_does_not_escalate(self):
        r = route(Lead("Acme", "A", None, "AMER"), POLICY)
        self.assertNotEqual(r.destination, INSTANT_ALERT)

    def test_escalation_disabled_by_policy(self):
        no_esc = RoutingPolicy(
            tier_map=POLICY.tier_map,
            signal_escalates=False,
            instant_alert_sla_minutes=5,
        )
        r = route(Lead("Acme", "A", "job_change", "AMER"), no_esc)
        self.assertEqual(r.destination, "ae_queue")
        self.assertNotEqual(r.destination, INSTANT_ALERT)


class TestDDisqualify(unittest.TestCase):

    def test_d_tier_is_disqualified(self):
        r = route(Lead("Junk Co", "D", None, "AMER"), POLICY)
        self.assertEqual(r.destination, DISQUALIFIED)

    def test_d_tier_with_signal_still_disqualified(self):
        """A buying signal cannot rescue a D-tier lead."""
        r = route(Lead("Junk Co", "D", "job_change", "AMER"), POLICY)
        self.assertEqual(r.destination, DISQUALIFIED)

    def test_d_disqualify_reason_is_informative(self):
        r = route(Lead("Junk Co", "D", None, "EMEA"), POLICY)
        self.assertIn("D-tier", r.reason)
        self.assertIn("disqualified", r.reason)


class TestSLAValues(unittest.TestCase):

    def test_instant_alert_sla_is_policy_value(self):
        policy = RoutingPolicy(
            tier_map=POLICY.tier_map,
            signal_escalates=True,
            instant_alert_sla_minutes=2,
        )
        r = route(Lead("X", "A", "hiring", "AMER"), policy)
        self.assertEqual(r.sla_minutes, 2)

    def test_default_policy_slas(self):
        cases = [
            ("A", None,        60),
            ("A", "job_change", 5),   # escalated
            ("B", None,        240),
            ("C", None,        1440),
            ("D", None,        0),
        ]
        for tier, signal, expected_sla in cases:
            with self.subTest(tier=tier, signal=signal):
                r = route(Lead("X", tier, signal, "AMER"), DEFAULT_POLICY)
                self.assertEqual(r.sla_minutes, expected_sla)


class TestRoundRobin(unittest.TestCase):

    def _make_leads(self, n: int) -> list[Lead]:
        return [Lead(f"L{i}", "B", None, "AMER") for i in range(n)]

    def test_even_distribution_exact_multiple(self):
        """6 leads across 3 owners → 2 each."""
        leads = self._make_leads(6)
        pairs = round_robin(leads, ["alice", "bob", "carol"])
        counts: dict[str, int] = {}
        for _, owner in pairs:
            counts[owner] = counts.get(owner, 0) + 1
        self.assertEqual(counts, {"alice": 2, "bob": 2, "carol": 2})

    def test_even_distribution_non_multiple(self):
        """5 leads across 3 owners → no owner gets more than ceil(5/3)=2."""
        leads = self._make_leads(5)
        pairs = round_robin(leads, ["alice", "bob", "carol"])
        counts: dict[str, int] = {}
        for _, owner in pairs:
            counts[owner] = counts.get(owner, 0) + 1
        self.assertLessEqual(max(counts.values()), 2)

    def test_assignment_order_matches_leads_order(self):
        leads = self._make_leads(3)
        pairs = round_robin(leads, ["alice", "bob", "carol"])
        self.assertEqual([lead.name for lead, _ in pairs], ["L0", "L1", "L2"])
        self.assertEqual([o for _, o in pairs], ["alice", "bob", "carol"])

    def test_single_owner_gets_all(self):
        leads = self._make_leads(4)
        pairs = round_robin(leads, ["solo"])
        self.assertTrue(all(o == "solo" for _, o in pairs))

    def test_empty_owners_raises(self):
        with self.assertRaises(ValueError):
            round_robin(self._make_leads(3), [])

    def test_determinism(self):
        leads = self._make_leads(4)
        owners = ["a", "b"]
        self.assertEqual(round_robin(leads, owners), round_robin(leads, owners))


class TestLeadValidation(unittest.TestCase):

    def test_invalid_tier_raises(self):
        with self.assertRaises(ValueError):
            Lead("X", "Z", None, "AMER")

    def test_valid_tiers_accepted(self):
        for tier in ("A", "B", "C", "D"):
            Lead("X", tier, None, "AMER")   # must not raise


class TestRoutingPolicyValidation(unittest.TestCase):

    def test_missing_tier_raises(self):
        with self.assertRaises(ValueError):
            RoutingPolicy(tier_map={
                "A": TierPolicy("ae_queue", 60),
                "B": TierPolicy("sdr_sequence", 240),
                # C and D missing
            })


if __name__ == "__main__":
    unittest.main(verbosity=2)
