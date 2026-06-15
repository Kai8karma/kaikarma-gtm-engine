# DEC — Does the learning loop actually improve scoring?

**Status:** resolved · **Verdict:** PARK · **Date:** 2026-06-16

## Pre-registration (fixed before running)

- **Hypothesis (H1):** tuning the ICP weights with `policy_tuner.tune()` on TRAIN
  outcomes beats the fixed DEFAULT weights at ranking real converters on a
  held-out TEST set.
- **Control arm (no-information):** default weights, no learning.
- **Metric:** precision@top-20% on TEST, averaged over 20 seeds; plus weight drift
  toward the true generative weights.
- **Thresholds:** SHIP ≥ baseline +0.05 · PARK 0…+0.05 · **KILL ≤ baseline** (KILL ⇒
  cut the "self-improving" claim and reword the README).

## Setup

Conversion is truly driven by `signal` (45) + `fit` (30), with `firmographic` (15)
and `technographic` (10) minor — i.e. the shipped default weights
(40/20/30/10) are deliberately misspecified. 300 train / 300 test accounts,
20 seeds. The component under test is the real `tune()`. Reproduce:
`python3 evals/learning_loop_eval.py`.

## Result

| | precision@20% |
|---|---|
| baseline (default, no learning) | 0.692 |
| **tuned (learned from outcomes)** | **0.724** |
| oracle (true weights, ceiling) | 0.733 |

- **Lift: +0.032** — captured **78% of the 0.042 headroom** to the oracle.
- Tuned beat baseline in **14/20** seeds.
- Weight drift, correct direction: firmographic 40→24 (true 15), fit 10→28 (true
  30), technographic 20→16 (true 10). `signal` under-moved (30→31, true 45).

## Verdict & action

**PARK.** The loop is directionally real — it learns the right drivers and
captures most of the achievable lift — but the absolute gain is modest, so the
"self-improving moat" framing was an overclaim. Action taken:

1. README reworded: "self-improving moat" → "measured learning loop (backtested,
   modest)" with a link to this DEC.
2. Regression guard added (`evals/test_learning_loop.py`): tuned must keep
   beating baseline, else the claim regressed and CI fails.

## Known improvement (not yet built)

`signal` under-moves because the tuner saturates against its clamp bounds and the
co-occurrence attribution spreads credit. A confidence-weighted or
magnitude-aware tuner would likely capture more of the remaining 22% headroom —
a real v2 lever, logged not hidden.
