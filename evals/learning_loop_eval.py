"""Does the learning loop actually work? A pre-registered backtest.

The repo claims `policy_tuner` makes ICP scoring "self-improving." That is the
moat — so it has to be PROVEN, not asserted. This is the eval that proves or
kills the claim.

PRE-REGISTRATION (fixed before running; see evals/DEC-learning-loop.md):
  H1     tuning the ICP weights on TRAIN outcomes beats the fixed DEFAULT
         weights at ranking real converters on a held-out TEST set.
  Control  default weights, no learning (the no-information arm).
  Metric   precision@top-20% on TEST, averaged over seeds; + weight drift.
  SHIP   tuned >= baseline + 5pp     PARK  0..+5pp     KILL  tuned <= baseline
         (KILL ⇒ the "self-improving" claim is cut and the README reworded.)

Method: conversion is truly driven by signal+fit (TRUE_WEIGHTS). The engine
ships DEFAULT_WEIGHTS that deliberately misspecify that (over-weight
firmographic/technographic). A working loop should learn from won/lost deals
and drift the weights toward the true drivers, improving held-out ranking.
The component under test is the real policy_tuner.tune(); scoring is the ICP
weighted sum (score = Σ subscore_d · weight_d). Stdlib + fixed seeds.

    python3 evals/learning_loop_eval.py
"""

from __future__ import annotations

import os
import random
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "05-brain-integration"))

from brain_schema import Outcome          # noqa: E402
from policy_tuner import tune             # noqa: E402

DIMS = ("firmographic", "technographic", "signal", "fit")
DEFAULT_WEIGHTS = {"firmographic": 40.0, "technographic": 20.0, "signal": 30.0, "fit": 10.0}
TRUE_WEIGHTS = {"firmographic": 15.0, "technographic": 10.0, "signal": 45.0, "fit": 30.0}

N_TRAIN, N_TEST, K_FRAC = 300, 300, 0.20
STRONG = 0.60          # a dimension is "strong" for an account at/above this sub-score
SEEDS = range(20)      # average over many splits to kill noise


def _accounts(rng: random.Random, n: int) -> list[tuple[dict, bool]]:
    out = []
    for _ in range(n):
        sub = {d: rng.random() for d in DIMS}
        prob = sum(sub[d] * TRUE_WEIGHTS[d] for d in DIMS) / 100.0  # in [0,1]
        out.append((sub, rng.random() < prob))
    return out


def _score(sub: dict, w: dict) -> float:
    return sum(sub[d] * w[d] for d in DIMS)


def _precision_at_k(accounts: list[tuple[dict, bool]], w: dict, k_frac: float) -> float:
    k = max(1, int(len(accounts) * k_frac))
    ranked = sorted(accounts, key=lambda a: _score(a[0], w), reverse=True)
    top = ranked[:k]
    return sum(1 for _, conv in top if conv) / k


def _outcomes(train: list[tuple[dict, bool]]) -> list[Outcome]:
    """Credit a dimension when a deal it was strong for won; debit when it lost."""
    obs = []
    for sub, conv in train:
        for d in DIMS:
            if sub[d] >= STRONG:
                obs.append(Outcome("icp_dimension", d, "win" if conv else "loss", confidence=0.8))
    return obs


def run_trial(seed: int) -> dict:
    rng = random.Random(seed)
    train, test = _accounts(rng, N_TRAIN), _accounts(rng, N_TEST)
    tuned = tune(DEFAULT_WEIGHTS, _outcomes(train))
    return {
        "baseline": _precision_at_k(test, DEFAULT_WEIGHTS, K_FRAC),
        "tuned": _precision_at_k(test, tuned, K_FRAC),
        "oracle": _precision_at_k(test, TRUE_WEIGHTS, K_FRAC),
        "tuned_weights": tuned,
    }


def main() -> None:
    trials = [run_trial(s) for s in SEEDS]
    n = len(trials)
    avg = {k: sum(t[k] for t in trials) / n for k in ("baseline", "tuned", "oracle")}
    wins = sum(1 for t in trials if t["tuned"] > t["baseline"])
    lift = avg["tuned"] - avg["baseline"]
    headroom = avg["oracle"] - avg["baseline"]

    print(f"Backtest: {n} seeds · {N_TRAIN} train / {N_TEST} test · precision@top-{int(K_FRAC*100)}%\n")
    print(f"  baseline (default weights, no learning) : {avg['baseline']:.3f}")
    print(f"  tuned    (learned from train outcomes)  : {avg['tuned']:.3f}")
    print(f"  oracle   (true weights, upper bound)    : {avg['oracle']:.3f}")
    print(f"\n  lift (tuned − baseline)  : {lift:+.3f}  ({lift / headroom * 100:+.0f}% of the {headroom:.3f} headroom to oracle)")
    print(f"  tuned beat baseline in   : {wins}/{n} seeds")

    mean_w = {d: sum(t["tuned_weights"][d] for t in trials) / n for d in DIMS}
    print("\n  mean tuned weights vs default → true:")
    for d in DIMS:
        print(f"    {d:15s} {DEFAULT_WEIGHTS[d]:5.1f} → {mean_w[d]:5.1f}   (true {TRUE_WEIGHTS[d]:.0f})")

    verdict = "SHIP" if lift >= 0.05 else ("KILL" if lift <= 0 else "PARK")
    print(f"\n  PRE-REGISTERED VERDICT: {verdict}  (SHIP ≥ +0.05 · PARK 0..+0.05 · KILL ≤ 0)")


if __name__ == "__main__":
    main()
