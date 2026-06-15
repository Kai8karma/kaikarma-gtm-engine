"""Brain-integration bridge: log lead-router Routes as brain Outcomes.

Given a routed Lead + Route and whether the lead converted, build and log an
Outcome so the brain can tune routing policy over time.

Two entity types:
  'routing_sla'  — was the SLA met by the destination? key = destination name.
  'routing_tier' — did this tier→destination mapping produce a conversion?
                   key = icp_tier (A / B / C / D).

verdict = 'win' if converted else 'loss'

    python3 04-revops-engine/routing_outcomes.py        # demo (TEMPFILE store)
    python3 04-revops-engine/test_routing_outcomes.py   # tests

Stdlib only, no network. Feeds the brain air-gapped.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Cross-pillar sys.path bridge — pillar dirs are not packages.
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("04-revops-engine", "05-brain-integration"):
    _p = os.path.join(_BASE, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from brain_schema import Outcome  # noqa: E402
from outcome_store import load_outcomes, log_outcome  # noqa: E402
from revops_schema import Lead, Route  # noqa: E402


def build_sla_outcome(lead: Lead, route: Route, converted: bool) -> Outcome:
    """Outcome measuring whether the routing *destination* produced a conversion.

    entity_type = 'routing_sla'
    key         = route.destination  (e.g. 'ae_queue', 'instant_alert')
    verdict     = 'win' if converted else 'loss'
    """
    note = (
        f"lead={lead.name!r} tier={lead.icp_tier}"
        f" destination={route.destination!r}"
        f" sla_minutes={route.sla_minutes}"
        f" converted={converted}"
    )
    return Outcome(
        entity_type="routing_sla",
        key=route.destination,
        verdict="win" if converted else "loss",  # type: ignore[arg-type]
        note=note,
    )


def build_tier_outcome(lead: Lead, route: Route, converted: bool) -> Outcome:
    """Outcome measuring whether the *tier* assignment produced a conversion.

    entity_type = 'routing_tier'
    key         = lead.icp_tier  ('A' / 'B' / 'C' / 'D')
    verdict     = 'win' if converted else 'loss'
    """
    note = (
        f"lead={lead.name!r} tier={lead.icp_tier}"
        f" destination={route.destination!r}"
        f" converted={converted}"
    )
    return Outcome(
        entity_type="routing_tier",
        key=lead.icp_tier,
        verdict="win" if converted else "loss",  # type: ignore[arg-type]
        note=note,
    )


def record_routing_outcome(
    lead: Lead,
    route: Route,
    converted: bool,
    store_path: Path,
) -> tuple[Outcome, Outcome]:
    """Log both SLA and tier Outcomes for one routed lead.

    Returns (sla_outcome, tier_outcome) for inspection / testing.
    """
    sla_o = build_sla_outcome(lead, route, converted)
    tier_o = build_tier_outcome(lead, route, converted)
    log_outcome(sla_o, store_path)
    log_outcome(tier_o, store_path)
    return sla_o, tier_o


def record_routing_outcomes_batch(
    triples: list[tuple[Lead, Route, bool]],
    store_path: Path,
) -> list[tuple[Outcome, Outcome]]:
    """Log routing Outcomes for a batch of (Lead, Route, converted) triples.

    Processes in list order; returns list of (sla_outcome, tier_outcome) pairs.
    """
    return [record_routing_outcome(lead, route, converted, store_path)
            for lead, route, converted in triples]


# ── demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    from lead_router import route as router_route, DEFAULT_POLICY

    demo_leads = [
        Lead("Acme Cloud",      icp_tier="A", signal="job_change", region="AMER"),
        Lead("MidFin Co",       icp_tier="A", signal=None,         region="EMEA"),
        Lead("ScaleUp Inc",     icp_tier="B", signal="hiring",     region="APAC"),
        Lead("NicheAgency",     icp_tier="C", signal=None,         region="AMER"),
        Lead("LocalBakery LLC", icp_tier="D", signal=None,         region="AMER"),
    ]

    # Simulated conversion results.
    realized = [True, True, False, False, False]

    routes = [router_route(lead, DEFAULT_POLICY) for lead in demo_leads]

    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "outcomes.json"
        triples = list(zip(demo_leads, routes, realized))
        record_routing_outcomes_batch(triples, store)

        print(f"Logged routing Outcomes (2 per lead → {len(demo_leads) * 2} total):\n")
        for o in load_outcomes(store):
            print(
                f"  [{o.verdict:4s}] {o.entity_type:12s}.{o.key:16s}"
                f"  conf={o.confidence}  note={o.note!r}"
            )
