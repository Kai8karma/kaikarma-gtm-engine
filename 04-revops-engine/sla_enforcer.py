"""SLA enforcer for the RevOps engine.

check_sla(elapsed_minutes, sla_minutes) → status string:

    ok        — elapsed < sla
    warning   — elapsed >= sla * 0.8  (approaching)
    breach    — elapsed >= sla
    escalate  — elapsed >= sla * 2.0  (double the SLA — escalate immediately)

batch_check(pairs, sla_minutes) — apply check_sla across many leads at once.

Deterministic. Stdlib only. Air-gapped safe.

    python3 04-revops-engine/sla_enforcer.py        # demo
    python3 04-revops-engine/test_revops_extended.py # tests
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Status constants — import these instead of string literals.
# ---------------------------------------------------------------------------
OK = "ok"
WARNING = "warning"
BREACH = "breach"
ESCALATE = "escalate"

# Thresholds as fractions of sla_minutes.
_WARNING_RATIO: float = 0.8   # >= 80% of SLA → warn
_ESCALATE_RATIO: float = 2.0  # >= 2× SLA → escalate


def check_sla(elapsed_minutes: float, sla_minutes: float) -> str:
    """Return the SLA status for a single lead or ticket.

    Args:
        elapsed_minutes: how long has passed since the lead entered this stage.
        sla_minutes:     the contracted response time for this stage.

    Returns:
        One of: 'ok' | 'warning' | 'breach' | 'escalate'

    Raises:
        ValueError: if sla_minutes <= 0.
    """
    if sla_minutes <= 0:
        raise ValueError(f"sla_minutes must be > 0, got {sla_minutes}")

    ratio = elapsed_minutes / sla_minutes

    if ratio >= _ESCALATE_RATIO:
        return ESCALATE
    if ratio >= 1.0:
        return BREACH
    if ratio >= _WARNING_RATIO:
        return WARNING
    return OK


@dataclass(frozen=True)
class SLACheck:
    """Result of a single SLA check — name, status, and the elapsed time."""

    lead_name: str
    elapsed_minutes: float
    sla_minutes: float
    status: str


def batch_check(
    pairs: list[tuple[str, float]],
    sla_minutes: float,
) -> list[SLACheck]:
    """Check SLA status for many leads sharing the same SLA target.

    Args:
        pairs:       list of (lead_name, elapsed_minutes).
        sla_minutes: SLA that applies to all leads in this batch.

    Returns:
        List of SLACheck, one per lead, in input order.
    """
    return [
        SLACheck(
            lead_name=name,
            elapsed_minutes=elapsed,
            sla_minutes=sla_minutes,
            status=check_sla(elapsed, sla_minutes),
        )
        for name, elapsed in pairs
    ]


if __name__ == "__main__":
    print("SLA enforcer demo\n")

    sla = 60.0   # 60-minute SLA for A-tier leads

    cases = [
        ("FastResponse",  30.0),   # well inside SLA → ok
        ("ApproachingIt", 50.0),   # 83 % of SLA → warning
        ("BarelyBreached",60.0),   # exactly at SLA → breach
        ("LateToBreach",  80.0),   # past SLA → breach
        ("Escalated",    130.0),   # 2× SLA → escalate
    ]

    print(f"  SLA target: {sla} minutes\n")
    results = batch_check(cases, sla_minutes=sla)
    for r in results:
        pct = r.elapsed_minutes / r.sla_minutes * 100
        print(
            f"  {r.lead_name:20s}  elapsed={r.elapsed_minutes:6.1f}m  "
            f"({pct:5.0f}% of SLA)  →  {r.status}"
        )
