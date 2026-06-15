# 05 — Brain Integration

**The learning loop. This is the moat.** Every other pillar produces outcomes;
this one makes the engine remember and improve from them.  Without it, every
campaign starts from a cold guess.

## Built

| File | Role |
|---|---|
| `brain_schema.py` | `Outcome` dataclass — entity_type, key, verdict (win/loss/neutral), confidence, note |
| `outcome_store.py` | Append / load Outcomes to `_state/outcomes.json` — pure stdlib, air-gapped |
| `policy_tuner.py` | `tune(base_weights, outcomes) → dict` — nudge weights, clamp bounds, renormalize |
| `test_brain.py` | 19 assertions: roundtrip, win↑ / loss↓, sum preserved, bounds, determinism |
| `conftest.py` | Empty pytest entry point |

## The loop

```
recall prior outcomes  →  act (score / route / send / bid)  →  log the outcome  →  tune weights
        ▲                                                                                 │
        └─────────────────────────────────────────────────────────────────────────────────┘
```

## How to run

```bash
# Demo each module
python3 05-brain-integration/outcome_store.py
python3 05-brain-integration/policy_tuner.py

# Tests
python3 05-brain-integration/test_brain.py
```

## Design

### `Outcome`
A single closed feedback signal: which dimension was tested (`entity_type` +
`key`), what the result was (`verdict`), and how confident the attribution is
(`confidence` 0.0–1.0, default 0.7 matching the brain store gate).

Supported entity types:
- `icp_dimension` — a weight in `ICPProfile.weights` (firmographic, technographic, signal, fit)
- `perf_threshold` — a ratio in `PerfPolicy` (scale_when_ratio_below, etc.)

### `outcome_store`
Appends to `_state/outcomes.json` (pretty-printed JSON array for human
auditability).  Creates the `_state/` directory on first write.  The directory
is `.gitignore`d so live campaign data never enters version control.

### `policy_tuner`
Replays outcomes against a weight dict:

1. **Nudge** — win adds `BASE_STEP × confidence × total`; loss subtracts.
2. **Clamp** — each dimension stays within `[5%, 80%]` of the total (no
   dimension vanishes or takes over regardless of accumulated wins).
3. **Renormalize** — after clamping, scale all weights so they sum to the
   original total (mirrors the ICP sum-to-100 invariant).

Deterministic: same inputs always produce the same output.

## Discipline

Outcomes are logged with a pre-registered expectation (hypothesis + thresholds)
so "it worked" is falsifiable, not a vibe.  Untracked recall is theater — a
recommendation made without recalling prior outcomes should announce a cold
start.

The store can later sync to an external brain DB (e.g. `kai-brain.db`) but does
not require one — the entire pillar runs air-gapped.
