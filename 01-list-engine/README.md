# 01 — List Engine

**Who to reach — as typed, tested code.** This is the reference pillar: it proves the whole thesis that a framework should be runnable, not eyeballed.

## Built

- `icp_schema.py` — `ICPProfile` / `Account` / `ScoredAccount` as typed dataclasses you can version and diff.
- `icp_scorer.py` — deterministic, explainable 0-100 scorer across four weighted dimensions (firmographic 40 / technographic 20 / **signal 30** / fit 10). Signals are weighted heavily and kept separate from static fit, because "right account" and "right moment" are different questions. `rank()` returns a sorted target list — the actual output of list-building.
- `test_icp_scorer.py` — falsifiable assertions (tier boundaries, signal cap, band logic, weight validation).

Run it:

```bash
python3 01-list-engine/icp_scorer.py        # demo on 3 sample accounts
python3 01-list-engine/test_icp_scorer.py   # tests (stdlib, no install)
```

## Planned

- `enrichment/waterfall.py` — cheapest-provider-first enrichment behind an abstract interface (swap Clay/Apollo/PDL without rewriting logic). Credit discipline as code, not advice.
- `dedup/` — domain- and person-level dedup as functions.
- `activation/crm_push.py` — push the ranked list to HubSpot/Salesforce via API.

## Learning loop

Closed-won/lost outcomes should adjust the ICP weights via [`../05-brain-integration/`](../05-brain-integration/). The scorer you run next quarter should be sharper than today's because it has seen which accounts actually closed.
