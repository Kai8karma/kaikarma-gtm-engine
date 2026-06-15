# Engagement: <CLIENT NAME>

> Copy this folder to `engagements/<client>/` per engagement. Read this file first.
> Client data and results live here and **never** bleed into another engagement.

## Live state

- **Status:** <prospecting | active | paused | closed>
- **Started:** <YYYY-MM-DD>
- **Owner:** Kai
- **Memory refs:** <ids/links to where live state is tracked>

## Config (loaded at runtime — not hardcoded)

- `icp-config.json` — ICP weights + targets for this client
- `channels.json` — channel mix + spend caps
- `sla.json` — routing SLA targets

## Scope & guardrails

- **In scope:** <motions, channels>
- **Off-limits:** <named accounts, sectors, or client identities that must NOT appear in any public artifact — e.g. non-compete or NDA constraints>

## Results

- `results/` — gitignored. Raw data stays local.

---
*Anything published from this engagement (case study, post, portfolio) must be sanitized to sector-level framing unless the client identity is explicitly cleared.*
