"""Pipeline velocity and cohort revenue retention — the Dreamdata-shaped reporting layer.

Fulfils the item flagged as 'Planned' in 04-revops-engine/README.md:
velocity = (qualified opps x win rate x avg deal size) / avg cycle length,
as a queryable function rather than a spreadsheet formula someone re-derives
each quarter.

Pure — no network.
"""

from __future__ import annotations

from revenue_schema import PipelineVelocityInputs


def velocity(inputs: PipelineVelocityInputs) -> float:
    """Dollars of pipeline value converting to revenue per day.

    velocity = (qualified_opps x win_rate x avg_deal_size) / avg_cycle_days
    """
    return (
        inputs.qualified_opps * inputs.win_rate * inputs.avg_deal_size
    ) / inputs.avg_cycle_days


def cohort_retention(cohort_start_mrr: float, cohort_current_mrr: float) -> float:
    """Net revenue retention for one cohort: current MRR / starting MRR.

    Returns 0.0 if the cohort started at $0 (nothing to retain). Values above
    1.0 indicate net expansion (upsell outweighing churn within the cohort).
    """
    if cohort_start_mrr < 0:
        raise ValueError(f"cohort_start_mrr must be non-negative, got {cohort_start_mrr}")
    if cohort_current_mrr < 0:
        raise ValueError(f"cohort_current_mrr must be non-negative, got {cohort_current_mrr}")
    if cohort_start_mrr == 0:
        return 0.0
    return cohort_current_mrr / cohort_start_mrr


if __name__ == "__main__":
    inputs = PipelineVelocityInputs(
        qualified_opps=40,
        win_rate=0.25,
        avg_deal_size=42000.0,
        avg_cycle_days=62.0,
    )

    print("pipeline_velocity demo\n")
    print(f"  inputs   : {inputs}")
    print(f"  velocity : ${velocity(inputs):,.2f} / day")

    print("\n  cohort retention (Q1 cohort, 6 months later):")
    print(f"    started at $50,000 MRR, now at $58,000 -> {cohort_retention(50000, 58000):.1%}")
    print(f"    started at $50,000 MRR, now at $31,000 -> {cohort_retention(50000, 31000):.1%}")
    print("\nNo network I/O occurred.")
