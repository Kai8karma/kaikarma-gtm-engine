# Structural Teardown: ivangfalco/ads-skills

**Date:** 2026-06-15 · **Source:** https://github.com/ivangfalco/ads-skills (all-rights-reserved, no license)
**Purpose:** Original competitive analysis. Ideas-only — no verbatim content reproduced. We study how the best repos are organized, then build our own expression.

---

## Spine: how a SKILL.md routes a request

Each channel skill (linkedin/meta/google) follows the same repeatable spine:

1. **Trigger** — SKILL.md frontmatter lists mandatory trigger phrases; a match auto-activates the skill.
2. **Intent classification** — a routing table maps "user intent → load these KB files," so the LLM reads only the 3-5 relevant files, not all 15.
3. **Pre-read rules** — platform invariants hardcoded (e.g. start campaigns paused, audience expansion off) so they fire every time.
4. **Script execution** — a quick-reference table of CLI commands; the LLM picks the right script.
5. **Output standard** — format per task type (plan → docx, performance → xlsx, audit → pass/fail).

## Taxonomy

```
ads-skills/
├── CLAUDE.md                # persona, behavior rules, consulting CTA
├── .env.example             # all platform creds, one flat file
├── ads-foundations/         # 10 cross-platform doctrine files
└── .claude/skills/
    ├── onboarding/          # credential wizard
    ├── linkedin-ads/        # SKILL.md + api-reference + knowledge-base/(15) + scripts/(14)
    ├── meta-ads/            # same pattern, 16 KB / 12 scripts
    └── google-ads/          # same pattern, 1 KB file (notably thin) / 13 scripts
```

Three-layer split: **doctrine → playbooks → scripts**. Strategic decisions never live inside automation code.

## Named frameworks (concepts, paraphrased)

5-Stage Demand Engine (Create/Capture/Accelerate/Revive/Expand) · Scaling Quadrant (2×2 effort vs budget) · Eugene Schwartz Awareness Ladder mapped to demand stages · VOC tiered source hierarchy · 6 headline formulas tied to funnel stage · 5-layer copy audit · Meta Ads OS (derive one target cost-per-qualified-lead, all decisions follow) · Creative Cadence OS · Penetration-based scaling (LinkedIn) · ABM tier split (1:1 / 1:few / 1:many) · Non-performer & maintenance kill rules · RICE experiment prioritization · 5-question measurement scorecard.

## Script architecture

Consistent per platform: `config.py` (load env) + `client.py` (auth session) + `list_* / get_*_performance / create_* (always paused) / update_*`. Raw `requests`, `tabulate` output, no async, no retry. Auth: LinkedIn local OAuth flow, Meta long-lived token (manual rotation), Google OAuth refresh token. Only `ad_scheduler.py` holds state (JSON flat file, cron-triggered pauses) — the closest thing to an agent, but purely time-triggered, not adaptive.

## What's genuinely smart (adopt)

- Intent-routing table in SKILL.md is context-efficient — load only relevant files.
- Clean doctrine/playbook/script separation; strategy never bleeds into code.
- CLAUDE.md as a dedicated persona layer.
- Onboarding as its own skill, credentials testable in-session.
- One derived number (target CPL) driving all thresholds — prevents emotional optimization.
- VOC-first copy process (gather ≥5 real quotes before writing).

## What's thin (where we win)

- **Google Ads dramatically underbuilt** (1 KB file vs 15-16).
- **No memory layer** — every session cold; no retained account history or experiment outcomes.
- **No autonomous control loop** — `ad_scheduler` only pauses on a timer; no pull→classify→act→log feedback.
- **Manual token management**, single-account architecture, no cross-channel attribution tooling (largest doctrine-vs-execution gap).

## Our original answer

Foreground a first-class `brain/` (persistent per-account memory), `agents/` (genuine feedback loops, not cron), a `cross-channel/` skill with real attribution scripts, an explicit `egress-policy.md` (air-gapped positioning as a constraint, not marketing), and Google built to parity. See [`../../03-abm-paid-engine/`](../../03-abm-paid-engine/) and [`../../05-brain-integration/`](../../05-brain-integration/).
