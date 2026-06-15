"""RevOps lead router — tier → destination, deterministic and explainable.

Every lead gets exactly one Route. The policy is a data structure you can
version, diff, and test — not a Notion doc no-one updates. Outcomes from real
pipeline should feed back into tier thresholds via 05-brain-integration/ so the
policy sharpens over time.

    python3 04-revops-engine/lead_router.py        # demo
    python3 04-revops-engine/test_lead_router.py   # tests

Stdlib only, no network, no state. Air-gapped safe.
"""

from __future__ import annotations

from revops_schema import Lead, Route, RoutingPolicy, TierPolicy

# ---------------------------------------------------------------------------
# Escalation sentinel — destination name for A-tier + buying signal.
# Kept as a constant so tests can reference it without string literals.
# ---------------------------------------------------------------------------
INSTANT_ALERT = "instant_alert"
DISQUALIFIED = "disqualified"


def route(lead: Lead, policy: RoutingPolicy) -> Route:
    """Deterministic routing verdict for one lead.

    Rules (in priority order):
    1. D-tier → always disqualified, no further processing.
    2. A-tier with a buying signal + policy.signal_escalates
       → instant_alert lane with the escalated SLA.
    3. All other tiers → standard destination and SLA from the tier map.
    """
    tier_policy = policy.tier_map[lead.icp_tier]

    # Rule 1 — D-tier hard disqualify.
    if lead.icp_tier == "D":
        return Route(
            lead_name=lead.name,
            destination=DISQUALIFIED,
            sla_minutes=tier_policy.sla_minutes,
            reason="D-tier: below ICP floor — disqualified",
        )

    # Rule 2 — A-tier escalation when a buying signal is present.
    if (
        lead.icp_tier == "A"
        and lead.signal is not None
        and policy.signal_escalates
    ):
        return Route(
            lead_name=lead.name,
            destination=INSTANT_ALERT,
            sla_minutes=policy.instant_alert_sla_minutes,
            reason=(
                f"A-tier + buying signal '{lead.signal}' — escalated to instant_alert"
            ),
        )

    # Rule 3 — standard tier routing.
    return Route(
        lead_name=lead.name,
        destination=tier_policy.destination,
        sla_minutes=tier_policy.sla_minutes,
        reason=f"{lead.icp_tier}-tier → {tier_policy.destination}",
    )


def round_robin(leads: list[Lead], owners: list[str]) -> list[tuple[Lead, str]]:
    """Distribute leads evenly across owners in round-robin order.

    Returns a list of (lead, owner) pairs. Order follows the leads list; owner
    assignment cycles through owners by index. Empty owners list raises
    ValueError — the caller is responsible for ensuring the team exists.
    """
    if not owners:
        raise ValueError("owners list must not be empty")
    return [(lead, owners[i % len(owners)]) for i, lead in enumerate(leads)]


# ---------------------------------------------------------------------------
# Default policy — the "out of the box" routing table Kai's RevOps team uses.
# Override any tier's destination or SLA at construction time.
# ---------------------------------------------------------------------------
DEFAULT_POLICY = RoutingPolicy(
    tier_map={
        "A": TierPolicy(destination="ae_queue",     sla_minutes=60),
        "B": TierPolicy(destination="sdr_sequence", sla_minutes=240),
        "C": TierPolicy(destination="nurture",      sla_minutes=1440),
        "D": TierPolicy(destination=DISQUALIFIED,   sla_minutes=0),
    },
    signal_escalates=True,
    instant_alert_sla_minutes=5,
)


if __name__ == "__main__":
    demo_leads = [
        Lead("Acme Cloud",     icp_tier="A", signal="job_change", region="AMER"),
        Lead("MidFin Co",      icp_tier="A", signal=None,         region="EMEA"),
        Lead("ScaleUp Inc",    icp_tier="B", signal="hiring",     region="APAC"),
        Lead("NicheAgency",    icp_tier="C", signal=None,         region="AMER"),
        Lead("LocalBakery LLC",icp_tier="D", signal=None,         region="AMER"),
    ]

    print(f"Policy: signal_escalates={DEFAULT_POLICY.signal_escalates}, "
          f"instant_alert SLA={DEFAULT_POLICY.instant_alert_sla_minutes}m\n")

    routes = [route(lead, DEFAULT_POLICY) for lead in demo_leads]
    for r in routes:
        print(f"  {r.lead_name:20s}  →  {r.destination:16s}  SLA={r.sla_minutes:4d}m  |  {r.reason}")

    print()
    owners = ["alice", "bob", "carol"]
    assignments = round_robin(demo_leads, owners)
    print(f"Round-robin across {owners}:")
    for lead, owner in assignments:
        print(f"  {lead.name:20s}  →  {owner}")
