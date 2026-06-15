# 00 — Operating System

The layer Ivan's repos (and most GTM content) don't have: **how the engine decides.** Plays are commodity. The operating system is the moat.

## Three-layer separation

- **Strategy** never calls live APIs. It reasons; it doesn't reach out and touch production.
- **Execution** never makes strategic judgment calls. It runs the decision the doctrine encodes — nothing more.
- **Engagement data** stays isolated per `engagements/<client>/` folder. No cross-client bleed, ever.

This is the same discipline a paid-ads controller uses to stay under hard caps, applied to the whole GTM motion.

## Per-engagement governance

One folder per client. `_INDEX.md` is read first and cites live state. Client-specific parameters (ICP weights, channel mix, SLA targets) are JSON loaded at runtime — never hardcoded into a script. Swapping clients swaps a config, not the code.

## Verification gate

Nothing ships unverified. Every change ends with a falsifiable check (`tests/smoke.sh`, pillar pytest, or "the code this doc describes runs"). See [`../CLAUDE.md`](../CLAUDE.md) for the full table.

## Memory-first reflex

Before any recommendation, recall prior outcomes for this account/segment. A rec made cold is a guess — and the engine says so rather than pretending. The recall→act→log→learn loop lives in [`../05-brain-integration/`](../05-brain-integration/).
