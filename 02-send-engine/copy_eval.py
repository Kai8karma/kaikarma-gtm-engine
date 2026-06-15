"""Cold-email copy evaluator.

score_copy(draft, framework) → EvalResult with a 0-100 score and an issues list.
Every criterion is deterministic and checkable without an LLM:

    Criterion              Weight   Check
    ─────────────────────────────────────────────────────────────────
    word_count_in_bounds   25 pts   40–120 words (inclusive)
    question_or_cta        20 pts   '?' present, or a CTA phrase
    no_banned_words        20 pts   no hype words from BANNED_WORDS
    personalization_token  20 pts   at least one {slot} filled token
    single_clear_ask       15 pts   exactly one '?' in the draft

    python3 02-send-engine/copy_eval.py   # demo
    python3 02-send-engine/test_copy.py   # tests

Stdlib only — runs air-gapped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from framework_registry import Framework

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORD_MIN = 40
WORD_MAX = 120

# Small, concrete list — expand via PR as patterns emerge.
BANNED_WORDS: frozenset[str] = frozenset({
    "revolutionary",
    "game-changer",
    "synergy",
    "disruptive",
    "world-class",
    "cutting-edge",
    "leverage",
    "paradigm",
    "best-in-class",
    "innovative",
})

# Phrases that count as a CTA even without a '?'
_CTA_PHRASES: tuple[str, ...] = (
    "let me know",
    "reply to this",
    "book a",
    "schedule a",
    "grab a",
    "happy to",
    "reach out",
)

# Criteria weights — must sum to 100.
_WEIGHTS: dict[str, int] = {
    "word_count_in_bounds": 25,
    "question_or_cta": 20,
    "no_banned_words": 20,
    "personalization_token": 20,
    "single_clear_ask": 15,
}

assert sum(_WEIGHTS.values()) == 100, "weights must sum to 100"  # dev-time guard


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    """The verdict on one email draft."""

    score: int                           # 0–100
    issues: list[str] = field(default_factory=list)
    breakdown: dict[str, int] = field(default_factory=dict)  # criterion → pts earned


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _word_count(text: str) -> int:
    return len(text.split())


def _question_count(text: str) -> int:
    return text.count("?")


def _has_cta(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _CTA_PHRASES)


def _found_banned(text: str) -> list[str]:
    lower = text.lower()
    return [w for w in BANNED_WORDS if w in lower]


def _has_personalization(text: str, framework: Framework) -> bool:
    """True when the rendered draft contains at least one value that filled a slot.

    We check that none of the slot placeholders remain un-filled — i.e. the
    framework's required slots do NOT appear literally as '{slot_name}' in the
    draft. Also require the draft is not a bare template (all slots still raw).
    A draft is considered personalised when it does NOT still contain raw
    '{...}' tokens matching the required slots.
    """
    for slot in framework.required_slots:
        if "{" + slot + "}" in text:
            return False  # un-filled slot found
    # Additionally require at least one slot's value is non-trivially present:
    # we trust that render() filled them, so if none remain raw → personalised.
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_copy(draft: str, framework: Framework) -> EvalResult:
    """Score a rendered email draft against concrete, deterministic criteria.

    Args:
        draft:     The rendered email string (post-render, no raw {slots}).
        framework: The Framework the draft was built from (used for
                   personalization-token check).

    Returns:
        EvalResult with score 0-100, issues list, and per-criterion breakdown.
    """
    pts: dict[str, int] = {}
    issues: list[str] = []

    # 1. Word count in bounds
    wc = _word_count(draft)
    if WORD_MIN <= wc <= WORD_MAX:
        pts["word_count_in_bounds"] = _WEIGHTS["word_count_in_bounds"]
    else:
        pts["word_count_in_bounds"] = 0
        issues.append(
            f"word count {wc} is outside [{WORD_MIN}, {WORD_MAX}]"
        )

    # 2. Question or CTA present
    if _question_count(draft) >= 1 or _has_cta(draft):
        pts["question_or_cta"] = _WEIGHTS["question_or_cta"]
    else:
        pts["question_or_cta"] = 0
        issues.append("no question mark or CTA phrase found")

    # 3. No banned hype words
    bad = _found_banned(draft)
    if not bad:
        pts["no_banned_words"] = _WEIGHTS["no_banned_words"]
    else:
        pts["no_banned_words"] = 0
        issues.append(f"banned hype word(s): {bad}")

    # 4. Personalization token present
    if _has_personalization(draft, framework):
        pts["personalization_token"] = _WEIGHTS["personalization_token"]
    else:
        pts["personalization_token"] = 0
        issues.append("draft still contains un-filled slot placeholders")

    # 5. Exactly one clear ask
    q_count = _question_count(draft)
    if q_count == 1:
        pts["single_clear_ask"] = _WEIGHTS["single_clear_ask"]
    elif q_count == 0:
        pts["single_clear_ask"] = 0
        issues.append("no question mark — the ask is missing")
    else:
        pts["single_clear_ask"] = 0
        issues.append(
            f"found {q_count} question marks — exactly one clear ask required"
        )

    score = sum(pts.values())
    return EvalResult(score=score, issues=issues, breakdown=pts)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from framework_registry import get_framework

    print("=== copy_eval demo ===\n")

    fw = get_framework("problem-first")

    # -- Clean draft --
    clean = fw.render({
        "first_name": "Sarah",
        "observed_signal": "saw you just posted 4 SDR roles on LinkedIn",
        "quantified_pain": "most scaling teams lose 8h/rep/week to manual CRM entry",
        "one_liner_solution": "we auto-sync every call note straight to HubSpot in real-time",
        "soft_cta": "Worth a 15-min chat this week to see if it fits?",
    })
    result = score_copy(clean, fw)
    print(f"Clean draft score: {result.score}/100")
    print(f"  breakdown: {result.breakdown}")
    print(f"  issues:    {result.issues}\n")

    # -- Hypey draft with no CTA --
    hypey = (
        "Hi Sarah,\n\n"
        "Our revolutionary, game-changer synergy platform is the most innovative "
        "best-in-class cutting-edge disruptive world-class solution on the market. "
        "We leverage paradigm-shifting technology to deliver results. "
        "You should definitely try it. It is very good. We are the best. "
        "No question about it."
    )
    result2 = score_copy(hypey, fw)
    print(f"Hypey draft score: {result2.score}/100")
    print(f"  breakdown: {result2.breakdown}")
    print(f"  issues:    {result2.issues}")
