# 07 — Revenue Engine

**Which channel actually drove the deal, what MRR moved and why, and how fast pipeline turns into cash — as queryable functions, not a spreadsheet someone re-derives every quarter.**

Fulfils the `07 Revenue` layer of the connected-GTM-stack model (Dreamdata-shaped attribution + Hyperline-shaped billing analytics) and closes out the `pipeline_velocity.py` item that had sat as "Planned" in `04-revops-engine/README.md`.

## Built

- `revenue_schema.py` — typed primitives: `Deal` (amount, touchpoints, closed_won), `Touchpoint` (channel/campaign/timestamp), `AttributionResult` (per-channel dollar credit, model-validated), `Subscription` (Hyperline-shaped billing row), `MRRBridge` (new/expansion/contraction/churned, with a computed `net_new_mrr`), `PipelineVelocityInputs` (validated: win_rate 0-1, cycle days > 0).
- `attribution.py` — five standard multi-touch models over a deal's touchpoint history: `first_touch`, `last_touch`, `linear`, `u_shaped` (40/20/40, degrading gracefully to 50/50 for 2 touches and 100% for 1), `time_decay` (exponential recency weighting, configurable half-life). A touchpoint-less deal attributes to `"unattributed"` rather than raising — direct/referral deals are real, not an error. `attribute(deal, model)` dispatches by name.
- `mrr_calculator.py` — `compute_mrr_bridge(prev, curr)` diffs two `Subscription` snapshots into new/expansion/contraction/churned MRR (a subscription that silently drops out of the export is treated as churned, same as an explicit `canceled` status). `arr()` and `churn_rate()` round out the reporting.
- `pipeline_velocity.py` — `velocity(inputs)` = (qualified opps × win rate × avg deal size) ÷ avg cycle days. `cohort_retention(start, current)` for net-revenue-retention reporting.
- `revenue_outcomes.py` — **feeds the brain**: given an `AttributionResult` + whether the deal closed won, logs one `Outcome` per credited channel (`entity_type="revenue_channel"`, confidence = that channel's share of the deal's total credit) via `record_revenue_outcomes` / `record_revenue_outcomes_batch`. `brain_schema.py`'s `EntityType` literal was extended with `"revenue_channel"` to match.
- `hyperline_billing.py` / `dreamdata_attribution.py` — injected-client vendor adapters (Hyperline for subscriptions, Dreamdata for deal + touchpoint history), mirroring `04-revops-engine/hubspot_crm.py`'s conventions: fail-loud reads, zero-egress `FakeHyperlineClient` / `FakeDreamdataClient`, pure row-mapping functions separate from the fetch wrappers.
- 7 test files, 79 assertions — every attribution model's credit-sums-to-deal-amount invariant, every MRR-bridge transition (new/expansion/contraction/explicit-cancel/silent-disappearance), schema validation boundaries, and fake-client round trips.

## Why here, not bolted onto 04-revops or 05-brain

- `04-revops-engine` governs the *lead's* lifecycle (routing, SLA, data quality) — not the *deal's* revenue math. Attribution and MRR are a different question (which channel gets credit, how much recurring revenue moved) answered after a deal closes, not while a lead is being routed.
- `05-brain-integration` stays a pure reader/writer of Outcomes — it doesn't know what attribution *is*. This pillar computes the Outcome; the brain only ever tunes weights from it, same separation as `03-abm-paid-engine/perf_outcomes.py` and `04-revops-engine/routing_outcomes.py`.

## Honest scope

- **Not validated against live Hyperline/Dreamdata accounts.** Adapters are complete and structurally correct against each vendor's public API shape (documented in the module docstrings), same honesty bar as every other adapter in this repo — live use needs real credentials.
- **Attribution models are standard, not novel.** They're the same five models Dreamdata/Bizible/HubSpot's own reporting expose — the value here is that they're pure, tested functions you can run against your own CRM data without buying a $20k/yr attribution tool, not a new methodology.
- **No revenue-forecasting or predictive churn model.** This pillar reports what happened (attribution, MRR movement, velocity) — it does not predict what will happen. That would be a different, much riskier claim.

## Run it

```bash
python3 07-revenue-engine/attribution.py         # demo: 5 models over one $48k deal
python3 07-revenue-engine/mrr_calculator.py       # demo: MRR bridge across two monthly snapshots
python3 07-revenue-engine/pipeline_velocity.py    # demo: velocity + cohort retention
python3 07-revenue-engine/test_attribution.py -v
```
