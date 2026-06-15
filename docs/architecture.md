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
| 01–04 Engines | yes | no (executes doctrine) | only via `engagements/` config |
| 05 Brain | no (reads/writes memory only) | no | aggregated weights only |
| `engagements/<client>/` | — | — | yes, isolated |

## Build order

Ship a pillar only when it runs and passes a check. Current: **01 list-engine** is live (scorer + tests). Next: 02 send-engine infra calculators, then 04 routing, then wire 05 brain hooks.
