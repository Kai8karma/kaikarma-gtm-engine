"""Data-quality scorer (DQS) for the RevOps engine.

score_record(record, now_days) → 0-100 score across 6 weighted dimensions:

  completeness    (25) — required fields present and non-empty
  validity        (20) — values pass format checks (email, phone, domain)
  consistency     (15) — cross-field logic holds (no future created dates, etc.)
  uniqueness_hint (10) — proxy for deduplication risk (email domain diversity)
  timeliness      (20) — how fresh the record is (penalises age of last_updated)
  accuracy_hint   (10) — structured signals that data looks trustworthy

Weights sum to 100.  Each dimension contributes (raw_0_to_1 × weight) points.
The per-dimension breakdown dict values sum exactly to the overall score.

Deterministic: same inputs → same output, no randomness, no network.

    python3 04-revops-engine/dqs_scorer.py        # demo
    python3 04-revops-engine/test_revops_extended.py # tests

Stdlib only, air-gapped safe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Dimension weights — must sum to 100.
# ---------------------------------------------------------------------------
WEIGHTS: dict[str, int] = {
    "completeness":    25,
    "validity":        20,
    "consistency":     15,
    "uniqueness_hint": 10,
    "timeliness":      20,
    "accuracy_hint":   10,
}

assert sum(WEIGHTS.values()) == 100, "WEIGHTS must sum to 100"

# Fields considered required for a B2B lead record.
_REQUIRED_FIELDS: tuple[str, ...] = (
    "email", "first_name", "last_name", "company", "title", "phone",
)

# Loose but practical email regex (stdlib only).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# E.164-ish phone: optional +, digits, spaces/dashes/parens, 7–15 digits total.
_PHONE_RE = re.compile(r"^\+?[\d\s\-(]{7,20}$")
# Domain / URL presence check (contains a dot and no spaces).
_DOMAIN_RE = re.compile(r"^[^\s]+\.[^\s]+$")

# Timeliness: full score if updated within this many days; zero at 5×.
_FRESH_DAYS: float = 30.0
_STALE_DAYS: float = 150.0   # 5× fresh → zero timeliness score


# ---------------------------------------------------------------------------
# Dimension scorers — each returns a float in [0.0, 1.0].
# ---------------------------------------------------------------------------

def _completeness(record: dict[str, object]) -> float:
    """Fraction of required fields that are present and non-empty."""
    present = sum(
        1 for f in _REQUIRED_FIELDS
        if record.get(f) not in (None, "", [])
    )
    return present / len(_REQUIRED_FIELDS)


def _validity(record: dict[str, object]) -> float:
    """Fraction of *present* checkable fields that pass format validation."""
    checks: list[bool] = []

    email = record.get("email")
    if email:
        checks.append(bool(_EMAIL_RE.match(str(email))))

    phone = record.get("phone")
    if phone:
        checks.append(bool(_PHONE_RE.match(str(phone))))

    website = record.get("website")
    if website:
        checks.append(bool(_DOMAIN_RE.match(str(website))))

    return (sum(checks) / len(checks)) if checks else 0.5  # no data → neutral


def _consistency(record: dict[str, object]) -> float:
    """Cross-field logic checks. Each failing check deducts 1/n of the score."""
    issues = 0
    total = 3

    # 1. created_days should be <= last_updated_days (created earlier in time).
    #    Both fields are expressed as days-since-epoch (higher = more recent).
    #    A record updated before it was created is impossible.
    created = record.get("created_days")
    updated = record.get("last_updated_days")
    if isinstance(created, (int, float)) and isinstance(updated, (int, float)):
        if created > updated:
            issues += 1  # record was "created" after it was "updated" — impossible
    else:
        total -= 1  # can't check — don't penalise

    # 2. If both first_name and last_name present, full_name should match if given.
    first = str(record.get("first_name") or "").strip()
    last = str(record.get("last_name") or "").strip()
    full = str(record.get("full_name") or "").strip()
    if first and last and full:
        expected = f"{first} {last}"
        if full.lower() != expected.lower():
            issues += 1
    else:
        total -= 1

    # 3. Email domain should match company_domain if both present.
    email = str(record.get("email") or "")
    company_domain = str(record.get("company_domain") or "").lower().strip()
    if "@" in email and company_domain:
        email_domain = email.split("@")[-1].lower().strip()
        # allow sub-domains: email_domain ends with company_domain
        if not (email_domain == company_domain or
                email_domain.endswith("." + company_domain)):
            issues += 1
    else:
        total -= 1

    if total <= 0:
        return 1.0
    return max(0.0, (total - issues) / total)


def _uniqueness_hint(record: dict[str, object]) -> float:
    """Proxy for deduplication risk.

    Heuristic: if the record carries a ``duplicate_score`` field (0.0 = unique,
    1.0 = likely duplicate) we invert it. Otherwise we check whether email is
    from a personal/generic domain (higher dupe risk in B2B contexts).
    """
    dup_score = record.get("duplicate_score")
    if isinstance(dup_score, (int, float)):
        return max(0.0, min(1.0, 1.0 - float(dup_score)))

    # Fallback: generic/personal email domains are higher-risk.
    email = str(record.get("email") or "")
    if "@" in email:
        domain = email.split("@")[-1].lower()
        _generic = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                    "aol.com", "icloud.com", "protonmail.com", "me.com"}
        if domain in _generic:
            return 0.4   # personal email in B2B → mild dupe/quality risk
    return 0.8           # no signal either way → optimistic default


def _timeliness(record: dict[str, object], now_days: float) -> float:
    """Recency score based on last_updated_days (days since epoch or since import).

    age = now_days - last_updated_days.
    score = 1.0 at age ≤ _FRESH_DAYS, linearly decays to 0.0 at _STALE_DAYS.
    """
    updated = record.get("last_updated_days")
    if not isinstance(updated, (int, float)):
        return 0.5   # unknown — neutral

    age = now_days - float(updated)
    if age < 0:
        age = 0.0   # future update → treat as fresh (consistency catches it)

    if age <= _FRESH_DAYS:
        return 1.0
    if age >= _STALE_DAYS:
        return 0.0
    return 1.0 - (age - _FRESH_DAYS) / (_STALE_DAYS - _FRESH_DAYS)


def _accuracy_hint(record: dict[str, object]) -> float:
    """Signals that data was collected from a trustworthy source.

    Checks:
    - source field is present and non-generic
    - enriched flag is True
    - linkedin_url is present (structured identity anchor)
    Each present positive signal earns 1/3.
    """
    score = 0.0
    total = 3.0

    source = str(record.get("source") or "").lower()
    if source and source not in ("unknown", "other", ""):
        score += 1.0

    if record.get("enriched") is True:
        score += 1.0

    if record.get("linkedin_url"):
        score += 1.0

    return score / total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DQSResult:
    """Score + per-dimension breakdown for one record."""

    score: float                     # 0–100, rounded to 1 dp
    breakdown: dict[str, float]      # dimension → points contributed (sums to score)


def score_record(record: dict[str, object], now_days: float = 0.0) -> DQSResult:
    """Score a single CRM record for data quality.

    Args:
        record:   dict of CRM field → value.
        now_days: the "current time" expressed as days (same unit as
                  ``last_updated_days`` and ``created_days`` fields).
                  Defaults to 0 — callers should pass the real wall-clock day
                  number for timeliness to be meaningful.

    Returns:
        DQSResult with .score (0-100) and .breakdown (sums to score).
    """
    raw: dict[str, float] = {
        "completeness":    _completeness(record),
        "validity":        _validity(record),
        "consistency":     _consistency(record),
        "uniqueness_hint": _uniqueness_hint(record),
        "timeliness":      _timeliness(record, now_days),
        "accuracy_hint":   _accuracy_hint(record),
    }
    breakdown: dict[str, float] = {
        dim: round(raw[dim] * WEIGHTS[dim], 4)
        for dim in WEIGHTS
    }
    total = round(sum(breakdown.values()), 1)
    # Clamp floating-point drift to [0, 100].
    total = max(0.0, min(100.0, total))
    # Re-round breakdown values to 1 dp for readability.
    breakdown = {k: round(v, 1) for k, v in breakdown.items()}
    return DQSResult(score=total, breakdown=breakdown)


if __name__ == "__main__":
    import pprint

    print("Data-quality scorer demo\n")

    now = 100.0   # arbitrary reference day

    complete_record: dict[str, object] = {
        "email":            "alice@acmecorp.com",
        "first_name":       "Alice",
        "last_name":        "Smith",
        "full_name":        "Alice Smith",
        "company":          "Acme Corp",
        "title":            "VP Revenue",
        "phone":            "+1-415-555-0100",
        "website":          "acmecorp.com",
        "company_domain":   "acmecorp.com",
        "last_updated_days": 95.0,    # 5 days ago → fresh
        "created_days":     80.0,
        "source":           "hubspot",
        "enriched":         True,
        "linkedin_url":     "https://linkedin.com/in/alice-smith",
    }

    sparse_record: dict[str, object] = {
        "email":            "bob@gmail.com",
        "first_name":       "Bob",
        "last_updated_days": 0.0,    # 100 days ago → stale
    }

    for label, rec in [("complete", complete_record), ("sparse", sparse_record)]:
        result = score_record(rec, now_days=now)
        print(f"  [{label}]  score={result.score}")
        pprint.pprint(result.breakdown, indent=4)
        print()
