# kaikarma-gtm-engine

[![CI](https://github.com/Kai8karma/kaikarma-gtm-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/Kai8karma/kaikarma-gtm-engine/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

**GTM engineering as tested code — scoring, pacing, routing, and a learning loop you can run, verify, and _backtest_ — not a folder of SOPs.**

Most "GTM methodology" repos are markdown: frameworks you still have to implement by hand, in someone else's UI, from a cold start every time. This one is built the other way around. The frameworks are **code you run**. Outcomes are **logged, and the weights tune from them** — and that learning is **backtested, not asserted** ([`evals/`](evals/)). Control logic closes the loop: pull → classify → act under hard caps → log.

Built by Kai ([@Kai8karma](https://github.com/Kai8karma)) — RevOps / GTM engineering / performance marketing. The patterns here come from real B2B pipeline work; the architecture comes from running one operator like a five-person team.

---

## The thesis

GTM engineering has three layers. Most content stops at the first.

| Layer | Most repos | This repo |
|---|---|---|
| **Doctrine** — the frameworks | ✅ Markdown SOPs | ✅ Markdown, but subordinate to code |
| **Execution** — actually doing it | ❌ "build this in Clay/HubSpot" (prose) | ✅ Runnable Python: scorers, routers, validators |
| **Memory + learning** | ❌ stateless, every session cold | ✅ outcomes logged; weights tune from them — _measured_ ([`evals/`](evals/)) |

If a framework can't be run, tested, and improved by its own results, it's a blog post. The bar here is: **falsifiable, executable, and measurably self-tuning** — the learning loop is backtested in [`evals/`](evals/), not just claimed.

---

## What's different

1. **An operating system, not just plays.** `00-operating-system/` encodes how the engine *decides* — three-layer separation (strategy never calls live APIs, execution never makes strategic calls, engagement data stays isolated), per-engagement governance, and a verification gate on every change.
2. **Frameworks are code.** ICP scoring is a tested function, not a 100-point table you eyeball. Lead routing is a state machine. Data-quality decay is a scheduler. See `01-list-engine/icp_scorer.py` for the reference implementation.
3. **A learning loop — and it's _measured_.** `05-brain-integration/` tunes ICP weights from closed-won/lost outcomes. Backtested, pre-registered ([`evals/DEC-learning-loop.md`](evals/DEC-learning-loop.md)): it drifts weights toward the true drivers and captures **78% of the achievable ranking lift** — modest in absolute terms (+3.2pp), but **real and proven**. No comparable repo measures whether its own method works; this one does, and reported an honest PARK.
4. **Control loops, not cron jobs.** The paid controller and RevOps logic are decision functions — classify against a target → act under hard caps → log the outcome. Decisions emit executable ops through a tested, swappable **execution boundary** ([`executor.py`](03-abm-paid-engine/executor.py)) — dry-run and zero-egress by default, one real adapter from live. Invoked, not magically autonomous — and the honesty about that is the point.

---

## Architecture

```
kaikarma-gtm-engine/
├── 00-operating-system/     # how the engine decides — 3-layer split, governance, verification
├── 01-list-engine/          # who to reach — ICP as typed, tested code  ◀ reference module
├── 02-send-engine/          # outbound infra + copy frameworks as structured prompts
├── 03-abm-paid-engine/      # account targeting + the autonomous paid-ads controllers
├── 04-revops-engine/        # routing, lifecycle state machine, data governance, reporting
├── 05-brain-integration/    # the learning loop — outcomes → tuned weights (backtested in evals/)
├── engagements/             # per-client isolation; _INDEX.md cites live state
├── research/teardowns/      # competitive structural analysis (how the best repos are built)
├── docs/                    # frameworks-as-reference, subordinate to the code
├── evals/                   # pre-registered backtests — does the learning loop actually work?
└── tests/                   # smoke + unit; nothing ships unverified
```

Pillars run in GTM execution order: build the list → send → run paid air-cover at the same accounts → govern and route what comes back → learn from outcomes.

---

## Status

**v0.4 — the loop is multi-pillar and persistent across sessions.** Honest about what's real:

- ✅ `01-list-engine/icp_scorer.py` — ICP scorer: deterministic 0-100, 4 weighted dimensions, A/B/C/D tiers
- ✅ `02-send-engine/` — infra planner + pure-parse SPF/DKIM/DMARC validator **+ copy layer** (`framework_registry.py` named frameworks, `copy_eval.py` scoring gate)
- ✅ `03-abm-paid-engine/perf_controller.py` — **performance-marketing controller**: classify each campaign vs target CPA → scale/hold/cut/kill under hard caps, learning-phase protected
- ✅ `03-abm-paid-engine/rsa_builder.py` — **Google RSA builder/validator**, encoding [Anthropic's documented `/rsa` growth workflow](research/anthropic-growth-playbook.md): 15-headline limits, policy checks (`!`/caps/dupes), upload-ready CSV, generation brief — guardrails so LLM-written ads ship policy-clean
- ✅ `03-abm-paid-engine/executor.py` — **execution boundary**: controller verdicts → executable ops (`set_budget` / `pause`) applied through a swappable `Executor`. `DryRunExecutor` (default, tested, **zero egress**); `execute()` is batch-safe (a failing op → `ok=False`, never aborts the batch). The brain stays air-gapped; only this seam touches the network ([egress policy](docs/egress-policy.md))
- ✅ **`{google,meta,linkedin}_ads_executor.py`** — **original** Google/Meta/LinkedIn executors (license-clean, written from public API docs — not copied): pure tested payload builders + an *injected* official-SDK client, so the core stays stdlib and every test is zero-egress (fake clients). Consistent `ok=False` error contract across all three. Live use needs your creds + a sandbox account (`pip install '.[google]'`); **not** validated against live APIs by design
- ✅ `04-revops-engine/` — `lead_router.py` + **`stage_machine.py`** (lifecycle FSM) + **`dqs_scorer.py`** (6-dim data quality) + **`sla_enforcer.py`** (breach/escalation)
- ✅ `05-brain-integration/` — the **learning loop**: outcome store + `policy_tuner.tune()` (win↑/loss↓/renormalize)
- ✅ **`examples/closed_loop.py`** — the learning loop, **wired end-to-end**: score → log outcomes → `tune()` → reload → re-score; signal-driven accounts rise, pure-firmographic fall (one drops a tier)
- ✅ **`examples/persistent_loop.py`** — `load_and_tune()` **warms every new session** from `05-brain-integration/_state/outcomes.json` — outcomes compound across campaigns, not just within one run
- ✅ **`03/perf_outcomes.py` + `04/routing_outcomes.py`** — the paid controller and router now **feed the brain**: each verdict/route logs a win/loss Outcome (the loop is multi-pillar, not list-only)
- ✅ **`examples/list_to_sequences.py`** — `01→02` bridge: scored accounts → framework selection by tier → rendered outbound copy
- ✅ Operating-system doctrine, per-engagement governance (runnable `engagements/_TEMPLATE/` configs), competitive teardowns
- ✅ **`evals/`** — pre-registered backtest of the learning loop, honestly logged (verdict: **PARK**). Proving it helps *before* claiming it does is the whole ethos.
- 🚧 A magnitude-aware tuner to capture the remaining 22% headroom; wire loggers into the controllers as opt-in side-effects — next loop

**426 tests, ruff-clean, `bash tests/smoke.sh` exits 0** — CI gates every pillar, the full cross-pillar loop, the learning-loop backtest, the execution boundary, and the Google/Meta/LinkedIn executors on Python 3.11/3.12/3.13. Grows by loops; nothing ships unless the gate is green.

---

## Credits & inspiration

This repo is original work. It was **informed by**, not copied from, the best of the field — studied openly and credited here:

- The structural patterns are analyzed in [`research/teardowns/`](research/teardowns/) — including how ColdIQ / Ivan Falco's GTM and ads skills are organized. Those repos are excellent methodology references; this one takes the ideas (which aren't ownable) and rebuilds them as a running system (which is the work).
- MIT-licensed neighbors worth forking directly if you want plays fast: [claude-ads](https://github.com/AgriciDaniel/claude-ads), [marketingskills](https://github.com/coreyhaines31/marketingskills), [ai-marketing-skills](https://github.com/ericosiu/ai-marketing-skills).

If you build GTM systems and want to compare notes, find me at [@Kai8karma](https://github.com/Kai8karma).

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, ship with it.
