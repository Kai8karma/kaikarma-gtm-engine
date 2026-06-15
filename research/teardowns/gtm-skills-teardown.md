# Structural Teardown: ivangfalco/gtm-skills

**Date:** 2026-06-15 · **Source:** https://github.com/ivangfalco/gtm-skills — "ColdIQ's GTM methodology" (all-rights-reserved, no license)
**Purpose:** Original competitive analysis. Ideas-only — no verbatim content reproduced.

---

## Spine

Root `SKILL.md` is a pure dispatch table — one screen mapping intent → exact file. No logic, no agents, no code. Pattern: `intent → pillar (01/02/03) → sub-module → single .md`. Three pillars in dependency order: **01-outbound** (build list, write, send) → **02-abm** (paid air-cover at the same accounts) → **03-revops** (govern, route, measure). Sub-module pattern: `[function]-guide.md` (framework) + satellite deep-dives + troubleshooting.

## Taxonomy

```
01-outbound/   email-infra · list-building · clay-operations · copywriting
02-abm/        account-targeting · google-ads · linkedin-ads · meta-ads · retargeting · measurement
03-revops/     lead-management · data-governance · pipeline-reporting · sales-operations
```

Pillars run left-to-right in execution order; sub-folders split by function (not tool — Clay is under outbound, not a top-level pillar). 39 content files + 1 dispatch file. **Zero executable code.**

## Named frameworks (concepts, paraphrased)

**Outbound:** 8-phase list-building pipeline (ICP → discovery → enrich → dedup → personalize → activate; two sources ≈ 85% TAM) · 4-layer ICP (firmographic/technographic/behavioral/psychographic → 100-pt score → A/B/C/D) · waterfall enrichment (cheapest-first, 60-90% credit savings) · 5-signal hierarchy (job change 3× > hiring > website visit > funding > tech change) · email-infra checklist (≤2 mailboxes/domain, 60/40 Google/MS, 2-3wk warmup) · 13 named copy frameworks + HOT outreach 3-section structure.

**ABM:** revenue-reverse-engineered account sizing (target ÷ ACV ÷ funnel conversions → list size) · 5-stage ABM progression (Identified → Aware → Interested → Considering → Selecting) · 4-layer account selection · channel decision tree · ads→outbound signaling coordination.

**RevOps:** full lifecycle stage model (pre-pipeline / pipeline / post-sale with entry-exit + SLA) · tier-based lead routing (score → tier → destination, SLA by tier) · 6-dimension data-quality score with per-field decay rates · weighted customer-health score (segment-specific weights) · pipeline velocity formula · SLA management · territory + capacity planning (ramped-rep-equivalents).

## What's genuinely smart (adopt)

- Waterfall-first credit discipline (free providers before paid).
- Signal-tiered routing — separate static fit from dynamic buying signal, route on both.
- Backwards capacity math — size the list the revenue requires, not the list you can build.
- Data-decay schedules with per-field half-life.
- Segment-specific health-score weighting.

## What's thin (where we win)

- **No executable code anywhere** — every framework is a table; a "Clay workflow" is prose, not a runnable template. This is the single biggest gap.
- **No verification / eval layer** — benchmarks cited with no methodology, no way to validate against your own data.
- **No memory or state** — stateless; nothing learns from past campaigns.
- **Clay-monoculture** — no abstract enrichment interface.
- **No agents** — described workflows require a human to build them in third-party UIs.
- **ABM overweight on platform tactics** (11/16 files) — shortest shelf-life content.

## Our original answer

Rebuild as **code + system**: ICP and routing as tested functions, enrichment behind a provider interface, a brain that learns from closed-won/lost, per-engagement isolation, and a verification gate on every change. Frameworks live in `docs/`, subordinate to the code that runs them. See [`../../01-list-engine/`](../../01-list-engine/) for the reference implementation and [`../../04-revops-engine/`](../../04-revops-engine/) for the routing/lifecycle plan.
