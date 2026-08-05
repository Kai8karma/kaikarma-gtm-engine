# Engagement: Aerchain

> Client data and results live here and never bleed into another engagement.

## Live state

- **Status:** active — building
- **Started:** 2026-07-01
- **Owner:** Kai
- **Motion:** Pre-Call Intelligence Automation — T-2 full briefing + T-1 recap for confirmed demo calls, orchestrated in n8n over Google Calendar, HubSpot, Claude, and Gmail.
- **Memory refs:** decision log below; engine code lives in [`06-precall-intelligence-engine/`](../../06-precall-intelligence-engine/), the importable workflow in [`06-precall-intelligence-engine/n8n/precall_intelligence.workflow.json`](../../06-precall-intelligence-engine/n8n/precall_intelligence.workflow.json).

## Config (loaded at runtime — not hardcoded)

- `precall_config.json` — calendar mailbox, HubSpot portal id, internal-domain allowlist, trigger mode, catch-up threshold, model tier, error-alert routing.
- `precall_config_loader.py` — `load_precall_config(dir)` reads and validates the JSON; run directly for a demo.
- `test_precall_config_loader.py` — stdlib unittest suite: required keys, trigger-mode validity, catch-up threshold, and that pending decisions are surfaced rather than silently assumed.
- `conftest.py` — empty; puts this directory on `sys.path` for pytest.

## Decisions (SOW Section 8)

| # | Decision | Status |
|---|---|---|
| 1 | Trigger approach | **Hybrid** — daily sweep for the normal case + webhook for sub-48h bookings. Taken per the SOW's own recommendation; encoded in `precall_config.json` (`trigger_mode: "hybrid"`) and `06-precall-intelligence-engine/trigger_scheduler.py`. |
| 2 | Calendar location — is every confirmed call live on `marketing@aerchain.io`? | **Pending.** `calendar_email` in `precall_config.json` is a placeholder from the SOW's own phrasing, not a confirmed fact. If invites land elsewhere, the sweep runs and silently finds nothing (SOW Section 10 risk) — needs a yes/no from the team before go-live. |
| 3 | *(SOW numbering skips 3)* | — |
| 4 | Error-alert routing — shared `marketing@aerchain.io` alias vs. `animesh.bajpai@aerchain.io` directly | **Pending.** Defaulted to the shared alias in `precall_config.json`; swap `error_alert_email` once the team names an owner. |
| 5 | Model tier | **Default Claude model first**, upgrade only if briefing quality falls short. Taken per the SOW's own recommendation; encoded as `claude_model_tier: "default"`. |

Per CLAUDE.md doctrine: decisions 2 and 4 are genuine business calls for the client team, not something code can resolve — they are flagged in `precall_config.json["pending_decisions"]` rather than guessed at silently.

## Scope & guardrails

- **In scope:** pre-call briefing (T-2) and recap (T-1) generation for confirmed Aerchain demo calls; HubSpot enrichment; Google Calendar dedup; Gmail send.
- **Off-limits:** this folder holds Aerchain-specific config only — the reusable trigger/parsing/prompt logic lives in `06-precall-intelligence-engine/` so it isn't locked to one client.
- Outbound call *recording* is explicitly out of scope (flagged as a pain point in the SOW, not solved here).

## Results

- `results/` — gitignored. Raw data stays local.

---
*Anything published from this engagement (case study, post, portfolio) must be sanitized to sector-level framing unless the client identity is explicitly cleared.*
