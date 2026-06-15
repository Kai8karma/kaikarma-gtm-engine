"""Brain-integration bridge: log paid-controller Actions as brain Outcomes.

Given a controller Action (the verdict emitted by perf_controller.decide) and a
realized result (did the scaled / cut / killed campaign keep CPA under target?),
build and log an Outcome so the brain can tune PerfPolicy thresholds over time.

entity_type = 'perf_threshold'
key         = the policy threshold name that drove the decision
              e.g. 'scale_when_ratio_below', 'cut_when_ratio_above',
                   'kill_when_ratio_above', 'min_conversions_to_exit_learning'
verdict     = 'win'  if kept_under_target else 'loss'

    python3 03-abm-paid-engine/perf_outcomes.py        # demo (TEMPFILE store)
    python3 03-abm-paid-engine/test_perf_outcomes.py   # tests

Stdlib only, no network. Feeds the brain air-gapped.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Cross-pillar sys.path bridge — pillar dirs are not packages.
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("03-abm-paid-engine", "05-brain-integration"):
    _p = os.path.join(_BASE, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from brain_schema import Outcome  # noqa: E402
from outcome_store import load_outcomes, log_outcome  # noqa: E402
from perf_schema import HOLD, KILL, LEARNING, SCALE, CUT, Action  # noqa: E402

# Map controller verdicts to the policy threshold that fired.
_VERDICT_TO_KEY: dict[str, str] = {
    SCALE:    "scale_when_ratio_below",
    CUT:      "cut_when_ratio_above",
    KILL:     "kill_when_ratio_above",
    HOLD:     "scale_when_ratio_below",   # held because ratio wasn't low enough → same gate
    LEARNING: "min_conversions_to_exit_learning",
}


def build_perf_outcome(action: Action, kept_under_target: bool) -> Outcome:
    """Build an Outcome for one controller Action + realized result.

    action            — the Action emitted by perf_controller.decide / run.
    kept_under_target — True if the campaign's subsequent CPA stayed under
                        the policy target_cpa; False if it breached.

    Returns an Outcome with:
      entity_type = 'perf_threshold'
      key         = the threshold name that drove the verdict
      verdict     = 'win' (threshold worked) or 'loss' (it didn't)
    """
    key = _VERDICT_TO_KEY.get(action.verdict, action.verdict.lower())
    verdict: str = "win" if kept_under_target else "loss"
    note = (
        f"campaign={action.campaign!r} verdict={action.verdict}"
        f" actual_cpa={action.actual_cpa:.2f}"
        f" kept_under_target={kept_under_target}"
    )
    return Outcome(
        entity_type="perf_threshold",
        key=key,
        verdict=verdict,  # type: ignore[arg-type]
        note=note,
    )


def record_perf_outcome(
    action: Action,
    kept_under_target: bool,
    store_path: Path,
) -> Outcome:
    """Build and log one Outcome for a controller Action.

    Returns the logged Outcome for inspection / testing.
    """
    outcome = build_perf_outcome(action, kept_under_target)
    log_outcome(outcome, store_path)
    return outcome


def record_perf_outcomes_batch(
    pairs: list[tuple[Action, bool]],
    store_path: Path,
) -> list[Outcome]:
    """Log Outcomes for a batch of (Action, kept_under_target) pairs.

    Processes in list order; returns the list of logged Outcomes.
    """
    return [record_perf_outcome(action, kept, store_path) for action, kept in pairs]


# ── demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    from perf_schema import Campaign, PerfPolicy
    from perf_controller import run as controller_run

    policy = PerfPolicy(target_cpa=50.0, account_daily_cap=400.0)
    campaigns = [
        Campaign("LI-ABM-tier1", spend=1200, conversions=40, daily_budget=100),  # SCALE
        Campaign("Google-brand", spend=2000, conversions=40, daily_budget=100),  # HOLD
        Campaign("Meta-broad",   spend=3200, conversions=40, daily_budget=100),  # CUT
        Campaign("Meta-retarget",spend=120,  conversions=0,  daily_budget=40),   # KILL
        Campaign("LI-newtest",   spend=200,  conversions=8,  daily_budget=30),   # LEARNING
    ]

    # Simulated realized results (did CPA stay under target after the action?)
    realized = [True, True, False, True, True]

    actions = controller_run(campaigns, policy)

    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "outcomes.json"
        batch = list(zip(actions, realized))
        outcomes = record_perf_outcomes_batch(batch, store)

        print(f"Logged {len(outcomes)} perf Outcomes:\n")
        for o in load_outcomes(store):
            print(
                f"  [{o.verdict:4s}] perf_threshold.{o.key}"
                f"  conf={o.confidence}  note={o.note!r}"
            )
