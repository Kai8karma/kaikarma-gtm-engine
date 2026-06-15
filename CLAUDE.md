# CLAUDE.md — kaikarma-gtm-engine operating doctrine

Instructions for any Claude Code session working in this repo. This is a GTM **engine**, not a doc set — behave accordingly.

## Prime directive

Every framework in this repo must be **executable, testable, and self-improving**. If you're asked to add a "framework," add code + a test, not a markdown table. Markdown lives in `docs/` and is subordinate to the code it describes.

## Three-layer separation (load-bearing)

- **Strategy** (`00-operating-system/`, `docs/`) never calls live APIs.
- **Execution** (`0X-*-engine/` code) never makes strategic judgment calls — it runs the decision the doctrine encodes.
- **Engagement data** (`engagements/<client>/`) stays isolated per folder. Never let one client's data, config, or results bleed into another.

## Per-engagement governance

Each client gets one `engagements/<name>/` folder. Read its `_INDEX.md` first — it cites the live state and any engagement-specific overrides. Client-specific parameters (ICP weights, channel mix) are JSON loaded at runtime, never hardcoded into a script.

## Verification gate

Nothing ships unverified. Every non-trivial change ends with a falsifiable check:

| change | required check |
|---|---|
| Scorer / router / validator | `python -m pytest <pillar>` — green |
| New engine module | add a test file; `tests/smoke.sh` passes |
| Doctrine / framework doc | the code it describes exists and runs |

## Memory discipline

Outcomes are the point. When a campaign resolves (won/lost, replied/ignored), the result should update weights via `05-brain-integration/` — not vanish. A recommendation made without recalling prior outcomes is a cold-start guess; say so.

## Style

Surgical changes, match surrounding code, simplest thing that runs. No speculative abstractions for single-use code. Fail loud — if a step was skipped or a check didn't pass, say it plainly.
