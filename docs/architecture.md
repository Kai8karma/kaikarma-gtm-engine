# Architecture

One sentence: **a GTM motion expressed as code + memory + agents, governed by an operating system.**

## Flow

```
                      ┌─────────────────────────────────────────────┐
                      │  00 OPERATING SYSTEM                         │
                      │  3-layer separation · governance · verify    │
                      └─────────────────────────────────────────────┘
                                        │ governs
   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
   │ 01 LIST      │──▶│ 02 SEND      │   │ 03 ABM+PAID  │──▶│ 04 REVOPS    │
   │ ICP scorer   │   │ infra + copy │   │ controllers  │   │ route/lifecyc│
   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
          │                  │                  │                  │
          └──────────────────┴───────┬──────────┴──────────────────┘
                                     ▼ outcomes
                      ┌─────────────────────────────────────────────┐
                      │  05 BRAIN INTEGRATION                        │
                      │  recall → act → log → update weights         │
                      └─────────────────────────────────────────────┘
                                     │ sharper weights feed back ▲
                                     └──────────────────────────-┘
```

## Layer rules

| Layer | May call live APIs? | May make strategic calls? | Holds client data? |
|---|---|---|---|
| 00 Operating System | no | yes | no |
| 01–04, 06–07 Engines | yes | no (executes doctrine) | only via `engagements/` config |
| 05 Brain | no (reads/writes memory only) | no | aggregated weights only |
| `engagements/<client>/` | — | — | yes, isolated |

## Build order

Ship a pillar only when it runs and passes a check. **All seven pillars are live** (01-05 the core GTM motion, 06 pre-call intelligence for the Aerchain engagement, 07 revenue attribution/MRR/velocity), plus the end-to-end learning loop (`examples/closed_loop.py`): 943 tests green, ruff-clean, gated in CI. Next: extend the loop so the 03 paid controller and 04 router also `log_outcome`, and make accumulated multi-session learning (persistent `_state/outcomes.json` warm-start) the default rather than a tempfile demo.
