"""Tests for stage_machine, dqs_scorer, and sla_enforcer.

    python3 04-revops-engine/test_revops_extended.py

Every assertion group targets one behavioural contract:
- stage_machine: legal transitions advance correctly; illegal ones raise.
- dqs_scorer:    complete vs sparse score differential; breakdown sums to score.
- sla_enforcer:  ok / warning / breach / escalate thresholds including 2× boundary.
"""

from __future__ import annotations

import unittest

from stage_machine import (
    CUSTOMER,
    DISQUALIFIED,
    LEAD,
    MQL,
    OPPORTUNITY,
    SQL,
    SUBSCRIBER,
    IllegalTransitionError,
    advance,
    stage_info,
)
from dqs_scorer import DQSResult, WEIGHTS, score_record
from sla_enforcer import (
    BREACH,
    ESCALATE,
    OK,
    WARNING,
    SLACheck,
    batch_check,
    check_sla,
)


# ===========================================================================
# stage_machine tests
# ===========================================================================

class TestLegalTransitions(unittest.TestCase):

    def test_subscriber_activate_to_lead(self):
        self.assertEqual(advance(SUBSCRIBER, "activate"), LEAD)

    def test_lead_qualify_to_mql(self):
        self.assertEqual(advance(LEAD, "qualify_marketing"), MQL)

    def test_mql_accept_to_sql(self):
        self.assertEqual(advance(MQL, "accept_sales"), SQL)

    def test_sql_create_opportunity(self):
        self.assertEqual(advance(SQL, "create_opportunity"), OPPORTUNITY)

    def test_opportunity_close_won_to_customer(self):
        self.assertEqual(advance(OPPORTUNITY, "close_won"), CUSTOMER)

    def test_opportunity_close_lost_to_disqualified(self):
        self.assertEqual(advance(OPPORTUNITY, "close_lost"), DISQUALIFIED)

    def test_mql_recycle_back_to_lead(self):
        self.assertEqual(advance(MQL, "recycle"), LEAD)

    def test_sql_recycle_back_to_mql(self):
        self.assertEqual(advance(SQL, "recycle"), MQL)

    def test_customer_churn_to_disqualified(self):
        self.assertEqual(advance(CUSTOMER, "churn"), DISQUALIFIED)

    def test_disqualify_from_subscriber(self):
        self.assertEqual(advance(SUBSCRIBER, "disqualify"), DISQUALIFIED)

    def test_disqualify_from_lead(self):
        self.assertEqual(advance(LEAD, "disqualify"), DISQUALIFIED)

    def test_disqualify_from_mql(self):
        self.assertEqual(advance(MQL, "disqualify"), DISQUALIFIED)

    def test_disqualify_from_sql(self):
        self.assertEqual(advance(SQL, "disqualify"), DISQUALIFIED)

    def test_disqualify_from_opportunity(self):
        self.assertEqual(advance(OPPORTUNITY, "disqualify"), DISQUALIFIED)


class TestIllegalTransitions(unittest.TestCase):

    def test_subscriber_cannot_accept_sales(self):
        with self.assertRaises(IllegalTransitionError):
            advance(SUBSCRIBER, "accept_sales")

    def test_subscriber_cannot_skip_to_customer(self):
        with self.assertRaises(IllegalTransitionError):
            advance(SUBSCRIBER, "close_won")

    def test_lead_cannot_create_opportunity_directly(self):
        with self.assertRaises(IllegalTransitionError):
            advance(LEAD, "create_opportunity")

    def test_disqualified_has_no_exits(self):
        """Sink stage — every event is illegal."""
        for event in ("activate", "qualify_marketing", "accept_sales",
                       "create_opportunity", "close_won", "disqualify"):
            with self.subTest(event=event):
                with self.assertRaises(IllegalTransitionError):
                    advance(DISQUALIFIED, event)

    def test_customer_cannot_advance_forward(self):
        """No event progresses a customer beyond customer."""
        with self.assertRaises(IllegalTransitionError):
            advance(CUSTOMER, "activate")

    def test_unknown_stage_raises_value_error(self):
        with self.assertRaises(ValueError):
            advance("prospect", "qualify_marketing")

    def test_unknown_event_raises_illegal_transition(self):
        with self.assertRaises(IllegalTransitionError):
            advance(LEAD, "bogus_event")


class TestStageSink(unittest.TestCase):

    def test_disqualified_is_sink(self):
        info = stage_info(DISQUALIFIED)
        self.assertTrue(info.is_sink)
        self.assertEqual(info.legal_events, ())

    def test_customer_not_sink(self):
        info = stage_info(CUSTOMER)
        self.assertFalse(info.is_sink)

    def test_unknown_stage_info_raises(self):
        with self.assertRaises(ValueError):
            stage_info("ghost")


# ===========================================================================
# dqs_scorer tests
# ===========================================================================

_COMPLETE: dict[str, object] = {
    "email":             "alice@acmecorp.com",
    "first_name":        "Alice",
    "last_name":         "Smith",
    "full_name":         "Alice Smith",
    "company":           "Acme Corp",
    "title":             "VP Revenue",
    "phone":             "+1-415-555-0100",
    "website":           "acmecorp.com",
    "company_domain":    "acmecorp.com",
    "last_updated_days": 95.0,
    "created_days":      80.0,
    "source":            "hubspot",
    "enriched":          True,
    "linkedin_url":      "https://linkedin.com/in/alice",
}

_SPARSE: dict[str, object] = {
    "email":             "not-an-email",   # fails validity check
    "first_name":        "Bob",
    "full_name":         "Bob Wrong",      # inconsistent with first_name + no last_name
    "last_updated_days": 0.0,              # very old relative to now=100
    "created_days":      50.0,             # created AFTER last_updated → consistency fail
    # no last_name, company, title, phone → low completeness
    # no source, enriched omitted, no linkedin → zero accuracy_hint
}

_NOW = 100.0


class TestDQSScoreRange(unittest.TestCase):

    def test_complete_record_scores_higher_than_sparse(self):
        complete = score_record(_COMPLETE, now_days=_NOW)
        sparse = score_record(_SPARSE, now_days=_NOW)
        self.assertGreater(complete.score, sparse.score)

    def test_score_within_0_100(self):
        for rec in (_COMPLETE, _SPARSE, {}):
            result = score_record(rec, now_days=_NOW)
            self.assertGreaterEqual(result.score, 0.0)
            self.assertLessEqual(result.score, 100.0)

    def test_complete_record_score_above_70(self):
        result = score_record(_COMPLETE, now_days=_NOW)
        self.assertGreater(result.score, 70.0)

    def test_sparse_record_score_below_50(self):
        result = score_record(_SPARSE, now_days=_NOW)
        self.assertLess(result.score, 50.0)

    def test_empty_record_returns_dqs_result(self):
        result = score_record({}, now_days=0.0)
        self.assertIsInstance(result, DQSResult)


class TestDQSBreakdown(unittest.TestCase):

    def _breakdown_sum(self, result: DQSResult) -> float:
        return sum(result.breakdown.values())

    def test_breakdown_sums_to_score_complete(self):
        result = score_record(_COMPLETE, now_days=_NOW)
        self.assertAlmostEqual(self._breakdown_sum(result), result.score, places=0)

    def test_breakdown_sums_to_score_sparse(self):
        result = score_record(_SPARSE, now_days=_NOW)
        self.assertAlmostEqual(self._breakdown_sum(result), result.score, places=0)

    def test_breakdown_sums_to_score_empty(self):
        result = score_record({}, now_days=0.0)
        self.assertAlmostEqual(self._breakdown_sum(result), result.score, places=0)

    def test_breakdown_has_all_six_dimensions(self):
        result = score_record(_COMPLETE, now_days=_NOW)
        self.assertEqual(set(result.breakdown.keys()), set(WEIGHTS.keys()))

    def test_breakdown_dimensions_non_negative(self):
        for rec in (_COMPLETE, _SPARSE, {}):
            result = score_record(rec, now_days=_NOW)
            for dim, val in result.breakdown.items():
                with self.subTest(dim=dim):
                    self.assertGreaterEqual(val, 0.0)

    def test_breakdown_dimension_capped_at_weight(self):
        """No dimension can exceed its weight."""
        result = score_record(_COMPLETE, now_days=_NOW)
        for dim, val in result.breakdown.items():
            with self.subTest(dim=dim):
                self.assertLessEqual(val, WEIGHTS[dim])

    def test_determinism(self):
        r1 = score_record(_COMPLETE, now_days=_NOW)
        r2 = score_record(_COMPLETE, now_days=_NOW)
        self.assertEqual(r1.score, r2.score)
        self.assertEqual(r1.breakdown, r2.breakdown)


class TestDQSTimeliness(unittest.TestCase):

    def test_fresh_record_max_timeliness(self):
        rec = {**_COMPLETE, "last_updated_days": 99.0}  # 1 day ago
        result = score_record(rec, now_days=_NOW)
        # timeliness weight = 20; raw = 1.0 → 20 points
        self.assertAlmostEqual(result.breakdown["timeliness"], 20.0, places=1)

    def test_stale_record_zero_timeliness(self):
        rec = {"last_updated_days": 0.0}   # 100+ days ago with now=100
        result = score_record(rec, now_days=_NOW)
        # age = 100, stale threshold = 150 → should be low but not zero here
        # age=100, fresh=30, stale=150: linear interp = 1 - (100-30)/(150-30) = 1 - 70/120 ≈ 0.417
        self.assertLess(result.breakdown["timeliness"], 10.0)

    def test_no_last_updated_neutral(self):
        rec = {"email": "x@y.com"}
        result = score_record(rec, now_days=_NOW)
        # timeliness raw = 0.5 → 0.5 × 20 = 10
        self.assertAlmostEqual(result.breakdown["timeliness"], 10.0, places=1)


# ===========================================================================
# sla_enforcer tests
# ===========================================================================

class TestCheckSLASingleCall(unittest.TestCase):

    def test_zero_elapsed_is_ok(self):
        self.assertEqual(check_sla(0.0, 60.0), OK)

    def test_well_below_sla_is_ok(self):
        self.assertEqual(check_sla(30.0, 60.0), OK)

    def test_at_80_pct_is_warning(self):
        self.assertEqual(check_sla(48.0, 60.0), WARNING)   # exactly 80%

    def test_just_above_80_pct_is_warning(self):
        self.assertEqual(check_sla(49.0, 60.0), WARNING)

    def test_just_below_80_pct_is_ok(self):
        self.assertEqual(check_sla(47.9, 60.0), OK)

    def test_exactly_at_sla_is_breach(self):
        self.assertEqual(check_sla(60.0, 60.0), BREACH)

    def test_just_above_sla_is_breach(self):
        self.assertEqual(check_sla(61.0, 60.0), BREACH)

    def test_just_below_2x_sla_is_breach_not_escalate(self):
        self.assertEqual(check_sla(119.9, 60.0), BREACH)

    def test_exactly_2x_sla_is_escalate(self):
        self.assertEqual(check_sla(120.0, 60.0), ESCALATE)

    def test_above_2x_sla_is_escalate(self):
        self.assertEqual(check_sla(200.0, 60.0), ESCALATE)

    def test_different_sla_values(self):
        """Thresholds are proportional to sla_minutes, not hardcoded."""
        # SLA = 5 minutes (instant_alert lane)
        self.assertEqual(check_sla(0.0,  5.0), OK)
        self.assertEqual(check_sla(4.0,  5.0), WARNING)   # 80% of 5 = 4
        self.assertEqual(check_sla(5.0,  5.0), BREACH)
        self.assertEqual(check_sla(10.0, 5.0), ESCALATE)  # 2× 5 = 10

    def test_zero_sla_raises(self):
        with self.assertRaises(ValueError):
            check_sla(0.0, 0.0)

    def test_negative_sla_raises(self):
        with self.assertRaises(ValueError):
            check_sla(10.0, -5.0)


class TestBatchCheck(unittest.TestCase):

    def _run(self) -> list[SLACheck]:
        pairs = [
            ("FastResponse",   30.0),
            ("ApproachingIt",  50.0),
            ("BarelyBreached", 60.0),
            ("LateBreached",   80.0),
            ("Escalated",     130.0),
        ]
        return batch_check(pairs, sla_minutes=60.0)

    def test_batch_returns_correct_count(self):
        self.assertEqual(len(self._run()), 5)

    def test_batch_status_sequence(self):
        results = self._run()
        statuses = [r.status for r in results]
        self.assertEqual(statuses, [OK, WARNING, BREACH, BREACH, ESCALATE])

    def test_batch_preserves_lead_names(self):
        results = self._run()
        self.assertEqual(results[0].lead_name, "FastResponse")
        self.assertEqual(results[-1].lead_name, "Escalated")

    def test_batch_returns_sla_check_instances(self):
        for r in self._run():
            self.assertIsInstance(r, SLACheck)

    def test_batch_escalate_boundary_exact_2x(self):
        results = batch_check([("Edge", 120.0)], sla_minutes=60.0)
        self.assertEqual(results[0].status, ESCALATE)

    def test_batch_empty_input(self):
        self.assertEqual(batch_check([], sla_minutes=60.0), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
