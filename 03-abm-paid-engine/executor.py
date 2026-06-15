"""Execution boundary for the paid engine — the brain's hands, swappable.

The engine DECIDES (`perf_controller`) and VALIDATES (`rsa_builder`). This is the
seam where a decision becomes an action against a real platform — and the seam is
the point. The brain stays air-gapped; **only an Executor may touch the network.**

- `DryRunExecutor` (default) records actions and sends nothing — provably
  correct, zero egress, fully tested.
- A live executor (e.g. `GoogleAdsExecutor`) is an explicit, isolated opt-in that
  must be wired to real credentials and tested against a real account first.

Deliberately NOT a pile of hardcoded API scripts: one interface can drive any
backend — a real API client, or an existing script library — while the
decision/learning layer (where this repo is strongest) stays platform-agnostic.
That's the difference between a brain with hands and a worse copy of someone
else's hands. See docs/egress-policy.md.

    python3 03-abm-paid-engine/executor.py        # demo (dry-run, zero egress)
    python3 03-abm-paid-engine/test_executor.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from perf_schema import CUT, KILL, SCALE, Action

# Platform-agnostic operation kinds the controller's verdicts map onto.
SET_BUDGET = "set_budget"
PAUSE = "pause"
NO_OP = "no_op"


@dataclass(frozen=True)
class PaidOp:
    kind: str
    campaign: str
    value: float | None  # new daily budget for set_budget; None otherwise
    reason: str


@dataclass(frozen=True)
class ExecResult:
    op: PaidOp
    ok: bool
    message: str


def plan_to_ops(actions: list[Action]) -> list[PaidOp]:
    """Map controller verdicts → executable, platform-agnostic ops. Deterministic."""
    ops: list[PaidOp] = []
    for a in actions:
        if a.verdict == KILL:
            ops.append(PaidOp(PAUSE, a.campaign, None, a.reason))
        elif a.verdict in (SCALE, CUT):
            ops.append(PaidOp(SET_BUDGET, a.campaign, a.new_budget, a.reason))
        else:  # HOLD, LEARNING — nothing to push
            ops.append(PaidOp(NO_OP, a.campaign, a.new_budget, a.reason))
    return ops


class Executor(ABC):
    """A backend that can apply a PaidOp. The only layer allowed to egress."""

    @abstractmethod
    def apply(self, op: PaidOp) -> ExecResult: ...


@dataclass
class DryRunExecutor(Executor):
    """Records ops, performs NO network I/O. The safe, tested default."""

    log: list[PaidOp] = field(default_factory=list)

    def apply(self, op: PaidOp) -> ExecResult:
        self.log.append(op)
        tail = f" → {op.value}" if op.value is not None else ""
        return ExecResult(op, ok=True, message=f"dry-run: {op.kind} {op.campaign}{tail}")


class GoogleAdsExecutor(Executor):
    """LIVE executor — NOT IMPLEMENTED, NOT VALIDATED, on purpose.

    Implementing this sends real changes to Google Ads (egress + real spend
    impact). It must be wired to real OAuth credentials and tested against a real
    (ideally sandbox) account before any trust. A fake 'working' integration is
    worse than an honest unimplemented one — so this stays an explicit stub.
    """

    def apply(self, op: PaidOp) -> ExecResult:
        raise NotImplementedError(
            "GoogleAdsExecutor is a stub. Wire real credentials and test against a "
            "live account before use. Egress: this would send changes to Google Ads."
        )


def execute(ops: list[PaidOp], executor: Executor) -> list[ExecResult]:
    return [executor.apply(op) for op in ops]


if __name__ == "__main__":
    from perf_controller import run
    from perf_schema import Campaign, PerfPolicy

    policy = PerfPolicy(target_cpa=50.0, account_daily_cap=400.0)
    campaigns = [
        Campaign("LI-ABM", 1200, 40, 100),       # beats target → scale
        Campaign("Meta-broad", 3200, 40, 100),   # over target → cut
        Campaign("Meta-retarget", 120, 0, 40),   # runaway → kill → pause
    ]
    ops = plan_to_ops(run(campaigns, policy))
    ex = DryRunExecutor()
    print("Decision → op → execution (DryRun, zero egress):\n")
    for res in execute(ops, ex):
        print(f"  {res.message}")
    kinds = {k: sum(1 for o in ops if o.kind == k) for k in (SET_BUDGET, PAUSE, NO_OP)}
    print(f"\n  planned {kinds}, sent 0. Swap in a live Executor to go real.")
