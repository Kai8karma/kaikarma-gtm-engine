# 03 — ABM + Paid Engine

**Account-level air cover, run by autonomous controllers — not platform playbooks that rot every quarter.**

This pillar is where the **paid-ads controllers** plug in. The control loop is the product:

> pull metrics → classify against a target (e.g. target cost-per-qualified-lead) → act under hard caps → log the outcome → learn.

That is categorically different from a cron job that pauses ads on a timer.

## Design

- `account_targeting/account_scorer.py` — company-level fit scoring (mirrors the list-engine ICP scorer).
- `account_targeting/lookalike_builder.py` — expand from top customers via enrichment APIs.
- `ad_ops/linkedin_audience_sync.py` — push company lists to the LinkedIn Marketing API (audience as code).
- `ad_ops/engagement_tracker.py` — pull ABM engagement → CRM stage progression.
- `signal_router.py` — trigger outbound the moment an account crosses an engagement threshold (the ads→outbound handoff).
- `controllers/` — the autonomous optimization loops, each with an explicit **autonomous vs human-approval boundary** and a hard spend cap.

## Note

Live ad operations run through dedicated controller agents under strict caps. This engine wraps and orchestrates them; tactical platform advice (bidding, creative) lives in [`../docs/`](../docs/) where it can age gracefully without polluting the functional code.
