"""Typed primitives for the revenue layer — attribution, billing, pipeline velocity.

A Deal closes with zero or more Touchpoints (marketing/sales touches before
close); attribution.py turns those into per-channel credit. A Subscription is
one Hyperline-shaped billing record; mrr_calculator.py diffs two snapshots
into an MRRBridge (new/expansion/contraction/churn). PipelineVelocityInputs
feeds the classic (opps x win-rate x deal-size) / cycle-length formula.

Pure data — no network, no state.
"""

from __future__ import annotations

from dataclasses import dataclass

VALID_ATTRIBUTION_MODELS: frozenset[str] = frozenset(
    {"first_touch", "last_touch", "linear", "u_shaped", "time_decay"}
)
VALID_SUBSCRIPTION_STATUSES: frozenset[str] = frozenset(
    {"active", "canceled", "past_due", "trialing"}
)


@dataclass(frozen=True)
class Touchpoint:
    """One marketing/sales touch on the way to a closed deal."""

    channel: str
    campaign: str
    timestamp_iso: str


@dataclass(frozen=True)
class Deal:
    """A CRM deal with its touchpoint history, for attribution modeling."""

    deal_id: str
    amount: float
    closed_won: bool
    close_date_iso: str
    touchpoints: tuple[Touchpoint, ...] = ()

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError(f"Deal {self.deal_id!r} amount must be non-negative, got {self.amount}")


@dataclass(frozen=True)
class AttributionResult:
    """Per-channel dollar credit for one deal under one attribution model."""

    deal_id: str
    model: str
    channel_credit: dict[str, float]

    def __post_init__(self) -> None:
        if self.model not in VALID_ATTRIBUTION_MODELS:
            raise ValueError(
                f"model must be one of {sorted(VALID_ATTRIBUTION_MODELS)}, got {self.model!r}"
            )


@dataclass(frozen=True)
class Subscription:
    """One Hyperline-shaped billing subscription."""

    subscription_id: str
    account_id: str
    mrr: float
    status: str

    def __post_init__(self) -> None:
        if self.status not in VALID_SUBSCRIPTION_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(VALID_SUBSCRIPTION_STATUSES)}, got {self.status!r}"
            )
        if self.mrr < 0:
            raise ValueError(f"Subscription {self.subscription_id!r} mrr must be non-negative")


@dataclass(frozen=True)
class MRRBridge:
    """MRR movement between two subscription snapshots."""

    new_mrr: float
    expansion_mrr: float
    contraction_mrr: float
    churned_mrr: float

    @property
    def net_new_mrr(self) -> float:
        return self.new_mrr + self.expansion_mrr - self.contraction_mrr - self.churned_mrr


@dataclass(frozen=True)
class PipelineVelocityInputs:
    """Inputs to the classic pipeline-velocity formula."""

    qualified_opps: int
    win_rate: float        # 0.0-1.0
    avg_deal_size: float
    avg_cycle_days: float

    def __post_init__(self) -> None:
        if self.qualified_opps < 0:
            raise ValueError("qualified_opps must be non-negative")
        if not (0.0 <= self.win_rate <= 1.0):
            raise ValueError(f"win_rate must be 0.0-1.0, got {self.win_rate}")
        if self.avg_deal_size < 0:
            raise ValueError("avg_deal_size must be non-negative")
        if self.avg_cycle_days <= 0:
            raise ValueError("avg_cycle_days must be positive")
