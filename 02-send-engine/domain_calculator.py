"""Domain / mailbox infrastructure calculator for cold outbound.

Answers: "I need to send N emails a month — how many mailboxes, how many domains,
and what does the warmup look like?" in a deterministic, explainable way.

    python3 02-send-engine/domain_calculator.py        # demo
    python3 02-send-engine/test_send.py                # tests

Stdlib only, no network. Warmup ramp is conservative by design — inbox placement
matters more than speed. Outcomes from real campaigns should feed back into the
warmup curve via 05-brain-integration/ so the ramp tunes to observed deliverability.
"""

from __future__ import annotations

import math

from send_schema import InfraPlan, RampWeek

# Sending days per month (weekdays only — weekends tank deliverability for B2B).
SENDING_DAYS_PER_MONTH = 22


def _ramp_schedule(
    mailboxes: int,
    warmup_weeks: int,
    full_cap: int,
) -> tuple[RampWeek, ...]:
    """Build a linear warmup from 1 send/mailbox/day up to full_cap.

    Week 1 starts at 1 send per mailbox per day.
    The final week (post-warmup) runs at full_cap.
    Intermediate steps are linearly spaced and rounded down to stay conservative.
    """
    steps: list[RampWeek] = []
    for w in range(1, warmup_weeks + 1):
        # Linear interpolation: week 1 → 1, last warmup week → full_cap.
        if warmup_weeks == 1:
            daily = full_cap
        else:
            daily = max(1, round(1 + (full_cap - 1) * (w - 1) / (warmup_weeks - 1)))
        steps.append(RampWeek(week=w, daily_sends=daily, total_daily=daily * mailboxes))
    return tuple(steps)


def plan_infra(
    monthly_emails: int,
    per_mailbox_daily_cap: int = 30,
    mailboxes_per_domain: int = 2,
    warmup_weeks: int = 3,
) -> InfraPlan:
    """Return the infrastructure plan needed to hit a monthly send target.

    Args:
        monthly_emails: total emails to send per month.
        per_mailbox_daily_cap: maximum sends per mailbox per day after warmup.
            Industry guidance is 20-40; default 30 is intentionally conservative.
        mailboxes_per_domain: how many mailboxes share one domain.
            Keep at 2 — more risks domain-level reputation bleed.
        warmup_weeks: weeks to ramp from 1 → full cap before going full speed.

    Returns:
        InfraPlan with mailboxes_needed, domains_needed, and ramp_schedule.

    Raises:
        ValueError: on nonsensical inputs (zero/negative or cap/mailboxes < 1).
    """
    if monthly_emails < 1:
        raise ValueError(f"monthly_emails must be at least 1, got {monthly_emails}")
    if per_mailbox_daily_cap < 1:
        raise ValueError(f"per_mailbox_daily_cap must be at least 1, got {per_mailbox_daily_cap}")
    if mailboxes_per_domain < 1:
        raise ValueError(f"mailboxes_per_domain must be at least 1, got {mailboxes_per_domain}")
    if warmup_weeks < 1:
        raise ValueError(f"warmup_weeks must be at least 1, got {warmup_weeks}")

    # How many mailboxes to sustain the target after warmup?
    monthly_capacity_per_mailbox = per_mailbox_daily_cap * SENDING_DAYS_PER_MONTH
    mailboxes_needed = math.ceil(monthly_emails / monthly_capacity_per_mailbox)

    # Each domain hosts mailboxes_per_domain mailboxes.
    domains_needed = math.ceil(mailboxes_needed / mailboxes_per_domain)

    ramp = _ramp_schedule(mailboxes_needed, warmup_weeks, per_mailbox_daily_cap)

    return InfraPlan(
        monthly_emails=monthly_emails,
        per_mailbox_daily_cap=per_mailbox_daily_cap,
        mailboxes_per_domain=mailboxes_per_domain,
        mailboxes_needed=mailboxes_needed,
        domains_needed=domains_needed,
        ramp_schedule=ramp,
    )


if __name__ == "__main__":
    scenarios = [
        ("Early-stage (1 k/mo)",    1_000),
        ("Mid-market (5 k/mo)",     5_000),
        ("Scale (20 k/mo)",        20_000),
        ("Enterprise (100 k/mo)", 100_000),
    ]
    for label, volume in scenarios:
        p = plan_infra(volume)
        print(f"{label}")
        print(f"  mailboxes: {p.mailboxes_needed}  domains: {p.domains_needed}")
        print(f"  warmup ramp ({len(p.ramp_schedule)} weeks):")
        for w in p.ramp_schedule:
            print(f"    week {w.week}: {w.daily_sends}/mailbox/day  "
                  f"→ {w.total_daily} total/day")
        print()
