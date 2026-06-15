# 04 — RevOps Engine

**The system of record made executable — routing, lifecycle, data governance, reporting as code.**

## Built

- `revops_schema.py` — typed primitives: `Lead` (icp_tier, signal, region), `TierPolicy` (destination + SLA), `RoutingPolicy` (tier map + signal-escalation toggle), `Route` (verdict + reason).
- `lead_router.py` — `route(lead, policy)`: D-tier disqualifies; A-tier + buying signal + `signal_escalates=True` → `instant_alert` lane at 5-min SLA; all other tiers hit their standard destination. `round_robin(leads, owners)` distributes evenly across N owners. Includes `DEFAULT_POLICY` with `ae_queue / sdr_sequence / nurture / disqualified` lanes.
- `test_lead_router.py` — 22 assertions: tier→destination mapping, signal escalation (all signal types), escalation-off override, D disqualify (with and without signal), SLA values across all tiers, round-robin even distribution (exact multiple + remainder), order preservation, empty-owners guard, determinism, Lead and RoutingPolicy validation.
- `stage_machine.py` — lifecycle state machine over `[subscriber, lead, mql, sql, opportunity, customer]` plus a `disqualified` sink. `advance(current, event) -> next_stage` raises `IllegalTransitionError` on any illegal pair. Transition table exposed as `TRANSITIONS` data so callers can introspect legal events without parsing code. `stage_info(stage)` returns `StageInfo` (name, is_sink, legal_events).
- `dqs_scorer.py` — `score_record(record, now_days) -> DQSResult` (0-100). Six weighted dimensions: completeness (25), validity (20), consistency (15), uniqueness_hint (10), timeliness (20), accuracy_hint (10). `DQSResult.breakdown` sums exactly to `.score`. Deterministic; stdlib regex only.
- `sla_enforcer.py` — `check_sla(elapsed_minutes, sla_minutes) -> status` one of `ok | warning | breach | escalate` (escalate at ≥ 2× SLA, warning at ≥ 80%). `batch_check(pairs, sla_minutes)` applies the check across many leads sharing one SLA target. Raises on non-positive SLA.
- `test_revops_extended.py` — 58 assertions across all three modules: legal/illegal stage transitions (happy path + sink exhaustion + unknown stage/event), DQS score range (complete > 70, sparse < 50), breakdown sums to score (complete/sparse/empty), all six dimensions present and non-negative, timeliness at fresh/neutral/stale, SLA thresholds including exact 80% warning boundary and exact 2× escalation boundary, batch helper status sequence and edge cases.

## Planned

- `sla_enforcer.py` — a watchdog that queries the CRM and fires alerts on SLA breach (escalate at 2×).
- `lifecycle/stage_machine.py` — lifecycle as an explicit state machine with entry/exit criteria, not a table. `health_scorer.py` — composable customer-health score with segment-specific weights.
- `data-governance/dqs_scorer.py` — 6-dimension data-quality score per record. `decay_scheduler.py` — flag records due for re-enrichment by field half-life (job title decays faster than company name).
- `reporting/pipeline_velocity.py` — velocity = (opps × win-rate × ACV) ÷ cycle-length, as a queryable function. `cohort_builder.py` — cohort tables from CRM deal data.

## Why code, not docs

Every item above is something most repos *describe*. The difference between "here's the lead-routing framework" and "here's `lead_router.py`, run the tests" is the difference between a blog and an engine.
