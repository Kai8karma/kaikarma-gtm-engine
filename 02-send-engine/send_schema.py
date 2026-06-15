"""Typed send-engine primitives.

An InfraPlan is what you need to hit a monthly send volume — mailboxes, domains,
and a ramp schedule — computed deterministically from a handful of inputs.
A DnsCheck is the verdict on a single DNS record string: pass/fail plus every
specific issue found.

Pure data — no network, no state. The calculators and validators (domain_calculator.py,
dns_validator.py) produce these from real inputs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RampWeek:
    """One week's slice of the warmup schedule."""

    week: int          # 1-indexed
    daily_sends: int   # per-mailbox daily cap for that week
    total_daily: int   # fleet-wide total (daily_sends × mailboxes)


@dataclass(frozen=True)
class InfraPlan:
    """The output of plan_infra() — everything you need to provision and ramp."""

    monthly_emails: int
    per_mailbox_daily_cap: int       # full-speed cap after warmup
    mailboxes_per_domain: int
    mailboxes_needed: int            # ceil(monthly_emails / (per_mailbox_daily_cap * ~22 days))
    domains_needed: int              # ceil(mailboxes_needed / mailboxes_per_domain)
    ramp_schedule: tuple[RampWeek, ...]   # week-by-week warmup plan


@dataclass(frozen=True)
class DnsCheck:
    """The verdict on a single DNS record string (SPF, DKIM, or DMARC)."""

    record_type: str       # "SPF" | "DKIM" | "DMARC"
    raw: str               # the record string that was checked
    passed: bool           # True only when issues is empty
    issues: tuple[str, ...]  # human-readable failure reasons; empty on pass
