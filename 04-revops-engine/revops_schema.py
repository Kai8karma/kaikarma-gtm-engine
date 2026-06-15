"""RevOps primitives for the lead router.

A Lead arrives from the ICP scorer with a tier (A/B/C/D), an optional buying
signal, and a region. A RoutingPolicy encodes where each tier goes, how fast,
and whether a strong signal bumps A-tier to an even faster lane. A Route is the
deterministic verdict: destination, SLA, and reason.

Pure data — no network, no state. The router (lead_router.py) turns Leads +
a RoutingPolicy into Routes deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass

# Valid ICP tiers produced by the list-engine scorer.
VALID_TIERS: frozenset[str] = frozenset({"A", "B", "C", "D"})


@dataclass(frozen=True)
class Lead:
    """A scored lead arriving from the ICP scorer."""

    name: str
    icp_tier: str          # one of 'A' / 'B' / 'C' / 'D'
    signal: str | None     # buying signal present, or None
    region: str            # e.g. 'AMER', 'EMEA', 'APAC'

    def __post_init__(self) -> None:
        if self.icp_tier not in VALID_TIERS:
            raise ValueError(
                f"icp_tier must be one of {sorted(VALID_TIERS)}, got {self.icp_tier!r}"
            )


@dataclass(frozen=True)
class TierPolicy:
    """Routing rules for one ICP tier."""

    destination: str      # e.g. 'ae_queue', 'sdr_sequence', 'nurture', 'disqualified'
    sla_minutes: int      # how quickly the destination must act


@dataclass(frozen=True)
class RoutingPolicy:
    """Full routing doctrine: tier map + escalation toggle."""

    tier_map: dict[str, TierPolicy]  # keys 'A'..'D'
    signal_escalates: bool = True    # A-tier + buying signal → instant_alert lane
    instant_alert_sla_minutes: int = 5  # SLA for the escalated lane

    def __post_init__(self) -> None:
        missing = VALID_TIERS - set(self.tier_map)
        if missing:
            raise ValueError(f"tier_map missing entries for: {sorted(missing)}")


@dataclass(frozen=True)
class Route:
    """The verdict for one lead: where it goes, how fast, and why."""

    lead_name: str
    destination: str
    sla_minutes: int
    reason: str
