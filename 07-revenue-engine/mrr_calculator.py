"""MRR bridge, ARR, and churn-rate math — the Hyperline-shaped billing analytics.

Diffs two Subscription snapshots (e.g. start-of-month vs. end-of-month) into
an MRRBridge: new / expansion / contraction / churned. A subscription id
present in `prev` but absent from `curr` is treated as fully churned (the
billing system stopped tracking it — same as an explicit 'canceled' status).

Pure — no network.
"""

from __future__ import annotations

from revenue_schema import MRRBridge, Subscription

CHURNED_STATUSES: frozenset[str] = frozenset({"canceled"})


def compute_mrr_bridge(
    prev: list[Subscription],
    curr: list[Subscription],
) -> MRRBridge:
    """Diff two subscription snapshots into an MRRBridge.

    `prev` and `curr` are keyed by `subscription_id`; only 'active' rows in
    each snapshot count toward new/expansion/contraction — a subscription
    that was never active in `prev` is 'new' regardless of its label there.
    """
    prev_by_id = {s.subscription_id: s for s in prev}
    curr_by_id = {s.subscription_id: s for s in curr}

    new_mrr = expansion_mrr = contraction_mrr = churned_mrr = 0.0

    for sub_id, curr_sub in curr_by_id.items():
        prev_sub = prev_by_id.get(sub_id)
        if prev_sub is None:
            if curr_sub.status == "active":
                new_mrr += curr_sub.mrr
            continue

        if prev_sub.status != "active":
            if curr_sub.status == "active":
                new_mrr += curr_sub.mrr
            continue

        # prev_sub was active — this subscription can expand, contract, or churn.
        if curr_sub.status in CHURNED_STATUSES:
            churned_mrr += prev_sub.mrr
        elif curr_sub.status == "active":
            delta = curr_sub.mrr - prev_sub.mrr
            if delta > 0:
                expansion_mrr += delta
            elif delta < 0:
                contraction_mrr += -delta

    for sub_id, prev_sub in prev_by_id.items():
        if sub_id not in curr_by_id and prev_sub.status == "active":
            churned_mrr += prev_sub.mrr

    return MRRBridge(
        new_mrr=new_mrr,
        expansion_mrr=expansion_mrr,
        contraction_mrr=contraction_mrr,
        churned_mrr=churned_mrr,
    )


def arr(mrr: float) -> float:
    """Annualize a monthly-recurring-revenue figure."""
    if mrr < 0:
        raise ValueError(f"mrr must be non-negative, got {mrr}")
    return mrr * 12.0


def churn_rate(churned_mrr: float, starting_mrr: float) -> float:
    """Gross MRR churn rate for a period. 0.0 if starting_mrr is 0 (nothing to churn from)."""
    if churned_mrr < 0:
        raise ValueError(f"churned_mrr must be non-negative, got {churned_mrr}")
    if starting_mrr < 0:
        raise ValueError(f"starting_mrr must be non-negative, got {starting_mrr}")
    if starting_mrr == 0:
        return 0.0
    return churned_mrr / starting_mrr


if __name__ == "__main__":
    prev_month = [
        Subscription("sub-1", "acct-acme", mrr=2000.0, status="active"),
        Subscription("sub-2", "acct-midfin", mrr=1500.0, status="active"),
        Subscription("sub-3", "acct-scaleup", mrr=800.0, status="active"),
    ]
    curr_month = [
        Subscription("sub-1", "acct-acme", mrr=2500.0, status="active"),   # expansion
        Subscription("sub-2", "acct-midfin", mrr=1500.0, status="canceled"),  # churned
        # sub-3 dropped from the export entirely — treated as churned too
        Subscription("sub-4", "acct-newco", mrr=1200.0, status="active"),  # new
    ]

    bridge = compute_mrr_bridge(prev_month, curr_month)
    starting_mrr = sum(s.mrr for s in prev_month if s.status == "active")

    print("mrr_calculator demo\n")
    print(f"  starting MRR    : ${starting_mrr:,.2f}")
    print(f"  new MRR         : ${bridge.new_mrr:,.2f}")
    print(f"  expansion MRR   : ${bridge.expansion_mrr:,.2f}")
    print(f"  contraction MRR : ${bridge.contraction_mrr:,.2f}")
    print(f"  churned MRR     : ${bridge.churned_mrr:,.2f}")
    print(f"  net new MRR     : ${bridge.net_new_mrr:,.2f}")
    print(f"  ARR (curr)      : ${arr(starting_mrr + bridge.net_new_mrr):,.2f}")
    print(f"  churn rate      : {churn_rate(bridge.churned_mrr, starting_mrr):.1%}")
    print("\nNo network I/O occurred.")
