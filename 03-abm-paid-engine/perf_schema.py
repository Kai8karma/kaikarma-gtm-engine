"""Performance-marketing primitives for the autonomous paid controller.

A Campaign is one row of live metrics. A PerfPolicy is the doctrine encoded as
numbers — target CPA, the ratios that trigger scale/cut/kill, and the HARD CAPS
the controller may never breach. An Action is the verdict for one campaign:
what to do, the new daily budget, and why.

Pure data — no network, no state. The controller (perf_controller.py) turns
Campaigns + a PerfPolicy into Actions deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass

# Verdicts the controller can emit.
SCALE = "SCALE"        # beating target after exiting learning → raise budget
HOLD = "HOLD"          # on target → leave it
CUT = "CUT"            # over target → trim budget
KILL = "KILL"          # non-performer → budget to 0
LEARNING = "LEARNING"  # too little data → don't disturb the learning phase


@dataclass(frozen=True)
class Campaign:
    name: str
    spend: float          # period spend
    conversions: int      # qualified conversions in the period
    daily_budget: float   # current daily budget
    revenue: float = 0.0  # optional, for ROAS reporting


@dataclass(frozen=True)
class PerfPolicy:
    target_cpa: float
    account_daily_cap: float                 # HARD CAP: total daily budget ceiling
    min_conversions_to_exit_learning: int = 30
    scale_when_ratio_below: float = 0.8      # actual_cpa/target below this → scale
    cut_when_ratio_above: float = 1.5        # above this → cut
    kill_when_ratio_above: float = 2.0       # at/above this → kill
    max_budget_change_pct: float = 0.25      # HARD CAP: max single-step budget move
    min_daily_budget: float = 10.0           # floor; cuts never go below this (kill → 0)

    def __post_init__(self) -> None:
        if self.target_cpa <= 0:
            raise ValueError("target_cpa must be positive")
        if self.account_daily_cap <= 0:
            raise ValueError("account_daily_cap must be positive")
        if not (self.scale_when_ratio_below
                < self.cut_when_ratio_above
                <= self.kill_when_ratio_above):
            raise ValueError("ratio thresholds must be ordered: scale < cut <= kill")


@dataclass
class Action:
    """Mutable on purpose — the pacing pass adjusts new_budget under the cap."""

    campaign: str
    verdict: str
    old_budget: float
    new_budget: float
    actual_cpa: float  # float('inf') when zero conversions
    reason: str
