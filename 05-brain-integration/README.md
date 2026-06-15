# 05 — Brain Integration

**The learning loop. This is the moat.** Every other pillar produces outcomes; this one makes the engine remember and improve from them. Without it, every campaign starts from a cold guess.

## The loop

```
recall prior outcomes  →  act (score / route / send / bid)  →  log the outcome  →  update weights
        ▲                                                                                 │
        └─────────────────────────────────────────────────────────────────────────────────┘
```

## Design

- `brain_icp_updater.py` — on closed-won/lost, nudge the ICP dimension weights toward what actually closed. The `icp_scorer` you run next quarter is sharper because of it.
- `brain_copy_learner.py` — track which copy framework won for which persona; feed the registry's defaults.
- `brain_signal_tuner.py` — adjust signal weights by measured conversion correlation, not folklore.

## Discipline

Outcomes are logged with a pre-registered expectation (hypothesis + thresholds) so "it worked" is falsifiable, not a vibe. Untracked recall is theater — a recommendation made without recalling prior outcomes should announce that it's a cold start. This mirrors a personal-memory system with explicit win/loss accounting on every recall.
