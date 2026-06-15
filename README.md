# kaikarma-gtm-engine

[![CI](https://github.com/Kai8karma/kaikarma-gtm-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/Kai8karma/kaikarma-gtm-engine/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

**GTM engineering as a running system — code, memory, and autonomous agents — not a folder of SOPs.**

Most "GTM methodology" repos are markdown: frameworks you still have to implement by hand, in someone else's UI, from a cold start every time. This one is built the other way around. The frameworks are **code you run**. The decisions are **logged to a memory that learns**. The repetitive operations are **agents that close the loop**.

Built by Kai ([@Kai8karma](https://github.com/Kai8karma)) — RevOps / GTM engineering / performance marketing. The patterns here come from real B2B pipeline work; the architecture comes from running one operator like a five-person team.

---

## The thesis

GTM engineering has three layers. Most content stops at the first.

| Layer | Most repos | This repo |
|---|---|---|
| **Doctrine** — the frameworks | ✅ Markdown SOPs | ✅ Markdown, but subordinate to code |
| **Execution** — actually doing it | ❌ "build this in Clay/HubSpot" (prose) | ✅ Runnable Python: scorers, routers, validators |
| **Memory + agents** — learning & autonomy | ❌ stateless, every session cold | ✅ outcomes feed a brain; agents close the loop |

If a framework can't be run, tested, and improved by its own results, it's a blog post. The bar here is: **falsifiable, executable, and self-improving.**

---

## What's different (the four moats)

1. **An operating system, not just plays.** `00-operating-system/` encodes how the engine *decides* — three-layer separation (strategy never calls live APIs, execution never makes strategic calls, engagement data stays isolated), per-engagement governance, and a verification gate on every change.
2. **Frameworks are code.** ICP scoring is a tested function, not a 100-point table you eyeball. Lead routing is a state machine. Data-quality decay is a scheduler. See `01-list-engine/icp_scorer.py` for the reference implementation.
3. **A memory that learns.** `05-brain-integration/` — closed-won/lost outcomes update ICP weights; which copy framework won for which persona is tracked; signal weights tune against actual conversion. The system gets sharper per campaign instead of starting over.
4. **Autonomous agents.** The paid-ads controllers and RevOps watchdogs run feedback loops — pull metrics → classify against a target → act under hard caps → log the outcome — not cron jobs that pause ads on a timer.

---

## Architecture

```
kaikarma-gtm-engine/
├── 00-operating-system/     # how the engine decides — 3-layer split, governance, verification
├── 01-list-engine/          # who to reach — ICP as typed, tested code  ◀ reference module
├── 02-send-engine/          # outbound infra + copy frameworks as structured prompts
├── 03-abm-paid-engine/      # account targeting + the autonomous paid-ads controllers
├── 04-revops-engine/        # routing, lifecycle state machine, data governance, reporting
├── 05-brain-integration/    # the learning loop — outcomes → updated weights (the moat)
├── engagements/             # per-client isolation; _INDEX.md cites live state
├── research/teardowns/      # competitive structural analysis (how the best repos are built)
├── docs/                    # frameworks-as-reference, subordinate to the code
└── tests/                   # smoke + unit; nothing ships unverified
```

Pillars run in GTM execution order: build the list → send → run paid air-cover at the same accounts → govern and route what comes back → learn from outcomes.

---

## Status

**v0.2 — all five pillars have working code.** Honest about what's real:

- ✅ `01-list-engine/icp_scorer.py` — ICP scorer: deterministic 0-100, 4 weighted dimensions, A/B/C/D tiers
- ✅ `02-send-engine/` — `domain_calculator.py` (mailbox/domain/warmup planner) + `dns_validator.py` (pure-parse SPF/DKIM/DMARC)
- ✅ `03-abm-paid-engine/perf_controller.py` — **performance-marketing controller**: classifies each campaign vs target CPA → scale/hold/cut/kill under hard caps, learning-phase protected
- ✅ `04-revops-engine/lead_router.py` — tier→destination routing, A+signal escalation, round-robin, SLAs
- ✅ `05-brain-integration/` — the **learning loop**: outcome store + `policy_tuner.tune()` (win↑/loss↓/renormalize)
- ✅ Operating-system doctrine, per-engagement governance, competitive teardowns
- 🚧 Cross-pillar wiring (score → log outcome → tune → reload) and the deeper RevOps/copy modules — next loop

**105 tests across all 5 pillars, ruff-clean, `bash tests/smoke.sh` exits 0** — CI gates every pillar on Python 3.11/3.12/3.13. Grows pillar by pillar; nothing ships unless the gate is green.

---

## Credits & inspiration

This repo is original work. It was **informed by**, not copied from, the best of the field — studied openly and credited here:

- The structural patterns are analyzed in [`research/teardowns/`](research/teardowns/) — including how ColdIQ / Ivan Falco's GTM and ads skills are organized. Those repos are excellent methodology references; this one takes the ideas (which aren't ownable) and rebuilds them as a running system (which is the work).
- MIT-licensed neighbors worth forking directly if you want plays fast: [claude-ads](https://github.com/AgriciDaniel/claude-ads), [marketingskills](https://github.com/coreyhaines31/marketingskills), [ai-marketing-skills](https://github.com/ericosiu/ai-marketing-skills).

If you build GTM systems and want to compare notes, find me at [@Kai8karma](https://github.com/Kai8karma).

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, ship with it.
