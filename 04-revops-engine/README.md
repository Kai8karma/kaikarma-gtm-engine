# 04 — RevOps Engine

**The system of record made executable — routing, lifecycle, data governance, reporting as code.**

## Planned

- `routing/lead_router.py` — tier (from ICP + signal) → destination, as a function. `sla_enforcer.py` — a watchdog that queries the CRM and fires alerts on SLA breach (escalate at 2x).
- `lifecycle/stage_machine.py` — lifecycle as an explicit state machine with entry/exit criteria, not a table. `health_scorer.py` — composable customer-health score with segment-specific weights.
- `data-governance/dqs_scorer.py` — 6-dimension data-quality score per record. `decay_scheduler.py` — flag records due for re-enrichment by field half-life (job title decays faster than company name).
- `reporting/pipeline_velocity.py` — velocity = (opps × win-rate × ACV) ÷ cycle-length, as a queryable function. `cohort_builder.py` — cohort tables from CRM deal data.

## Why code, not docs

Every item above is something most repos *describe*. The difference between "here's the lead-routing framework" and "here's `lead_router.py`, run the tests" is the difference between a blog and an engine.
