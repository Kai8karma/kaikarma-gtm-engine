"""Typed primitives for the brain learning loop.

An Outcome is a single closed feedback signal: which ICP dimension (or
performance threshold) was tested, what the observed result was, and how
confident we are in the signal.  Verdicts mirror the personal-memory ROI
pattern (win / loss / neutral) so outcome accounting stays consistent
across the entire engine.

Can later sync to an external brain DB (e.g. kai-brain.db) but does not
require one — the pillar runs fully air-gapped against a local JSON store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Allowed entity types — expanding when new pillars are wired in.
# 'icp_dimension'    → a dimension weight in ICPProfile (firmographic, etc.)
# 'perf_threshold'   → a policy ratio in PerfPolicy (scale_when, cut_when, etc.)
# 'routing_sla'      → an SLA contract for a routing destination (04-revops-engine)
# 'routing_tier'     → a tier→destination mapping verdict (04-revops-engine)
# 'revenue_channel'  → an attribution channel credited on a closed deal (07-revenue-engine)
EntityType = Literal[
    "icp_dimension", "perf_threshold", "routing_sla", "routing_tier", "revenue_channel"
]

Verdict = Literal["win", "loss", "neutral"]


@dataclass(frozen=True)
class Outcome:
    """A single closed feedback signal from a real campaign or experiment.

    entity_type  — which subsystem owns the key being tuned.
    key          — the exact weight or threshold dimension name
                   (e.g. "firmographic", "scale_when_ratio_below").
    verdict      — 'win'  → this key's value was a positive factor in the
                             result; nudge it up.
                   'loss' → this key's value was a drag; nudge it down.
                   'neutral' → observed but inconclusive; no change.
    confidence   — 0.0–1.0; how certain we are in the attribution.
                   Defaults to 0.7 (same gate used by the brain store).
    note         — free-text rationale, optional.  Recorded for audit but
                   not used by the tuner.
    """

    entity_type: EntityType
    key: str
    verdict: Verdict
    confidence: float = 0.7
    note: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be 0..1, got {self.confidence}")
        if not self.key.strip():
            raise ValueError("key must be a non-empty string")
