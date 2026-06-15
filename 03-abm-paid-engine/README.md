# 03 — ABM + Paid Engine

**Account-level air cover, run by autonomous controllers — not platform playbooks that rot every quarter.**

This pillar is where the **paid-ads controllers** plug in. The control loop is the product:

> pull metrics → classify against a target (e.g. target cost-per-qualified-lead) → act under hard caps → log the outcome → learn.

That is categorically different from a cron job that pauses ads on a timer.

## Built — performance-marketing controller

- `perf_schema.py` — `Campaign` (live metrics) / `PerfPolicy` (doctrine as numbers + **hard caps**) / `Action` (verdict + new budget + reason).
- `perf_controller.py` — `decide()` classifies one campaign's actual CPA against target and emits **SCALE / HOLD / CUT / KILL / LEARNING**; `run()` decides the whole account then **enforces hard caps** (max single-step move, account daily ceiling) — pacing claws back speculative scale-ups before trimming baseline performers. `blended()` reports portfolio CPA/ROAS.
- `test_perf_controller.py` — 15 stdlib tests; hard-cap enforcement is provably tested, learning-phase protection is provably tested.
- `perf_outcomes.py` — **feeds the brain**: given a controller `Action` + a realized result (`kept_under_target: bool`), builds and logs an `Outcome(entity_type='perf_threshold', key=<threshold name>, verdict='win'|'loss')` via `record_perf_outcome` (single) or `record_perf_outcomes_batch`. Verdict-to-threshold mapping: `SCALE/HOLD → scale_when_ratio_below`, `CUT → cut_when_ratio_above`, `KILL → kill_when_ratio_above`, `LEARNING → min_conversions_to_exit_learning`.
- `test_perf_outcomes.py` — 18 stdlib tests; round-trip, all verdict→key mappings, batch, win/loss/empty-batch edge cases.

```bash
python3 03-abm-paid-engine/perf_controller.py        # demo: 5 campaigns, 5 verdicts
python3 03-abm-paid-engine/test_perf_controller.py   # tests
```

The doctrine is encoded as policy numbers, not prose: protect the learning phase, scale only proven winners, kill runaway zero-conversion spend, never breach the cap. Change the strategy by changing a `PerfPolicy`, not by rewriting code.

## Planned

- `account_targeting/account_scorer.py` — company-level fit scoring (mirrors the list-engine ICP scorer).
- `account_targeting/lookalike_builder.py` — expand from top customers via enrichment APIs.
- `ad_ops/linkedin_audience_sync.py` — push company lists to the LinkedIn Marketing API (audience as code).
- `ad_ops/engagement_tracker.py` — pull ABM engagement → CRM stage progression.
- `signal_router.py` — trigger outbound the moment an account crosses an engagement threshold (the ads→outbound handoff).
- `controllers/` — the autonomous optimization loops, each with an explicit **autonomous vs human-approval boundary** and a hard spend cap.

## Note

Live ad operations run through dedicated controller agents under strict caps. This engine wraps and orchestrates them; tactical platform advice (bidding, creative) lives in [`../docs/`](../docs/) where it can age gracefully without polluting the functional code.
