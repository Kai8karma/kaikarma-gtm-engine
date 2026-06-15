# Engagement: <CLIENT NAME>

> Copy this folder to `engagements/<client>/` per engagement. Read this file first.
> Client data and results live here and **never** bleed into another engagement.

## Live state

- **Status:** <prospecting | active | paused | closed>
- **Started:** <YYYY-MM-DD>
- **Owner:** Kai
- **Memory refs:** <ids/links to where live state is tracked>

## Config (loaded at runtime — not hardcoded)

- `icp-config.json` — ICP weights + targets for this client (matches `ICPProfile` in `01-list-engine/icp_schema.py`; weights must sum to 100)
- `channels.json` — channel mix + per-channel daily spend cap + target CPA; `account_daily_cap` is the hard ceiling across all channels
- `sla.json` — per-tier routing SLA in minutes (matches `RoutingPolicy` / `TierPolicy` in `04-revops-engine/revops_schema.py`); covers tiers A–D + signal-escalation lane
- `config_loader.py` — `load_engagement(dir)` reads the three JSONs, validates them, returns a merged `{"icp": …, "channels": …, "sla": …}` dict; run directly for a demo
- `test_config.py` — stdlib unittest suite (24 assertions): all three example configs parse; weights sum to 100; required keys present; validation errors raise correctly
- `conftest.py` — empty; puts this directory on `sys.path` for pytest

## Scope & guardrails

- **In scope:** <motions, channels>
- **Off-limits:** <named accounts, sectors, or client identities that must NOT appear in any public artifact — e.g. non-compete or NDA constraints>

## Results

- `results/` — gitignored. Raw data stays local.

---
*Anything published from this engagement (case study, post, portfolio) must be sanitized to sector-level framing unless the client identity is explicitly cleared.*
