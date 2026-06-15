"""Cold-email copy framework registry.

Each framework is a named, structured template with explicit required slots and
a render() call that raises on any missing slot. Deterministic: same slots →
same output every time, so copy can be tested and diffed.

    python3 02-send-engine/framework_registry.py   # demo
    python3 02-send-engine/test_copy.py            # tests

Stdlib only — runs air-gapped.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Framework:
    """A named B2B cold-email copy framework."""

    name: str
    best_use: str
    required_slots: tuple[str, ...]
    _template: str

    def render(self, slots: dict[str, str]) -> str:
        """Fill the template with slot values.

        Raises KeyError naming the first missing slot so the caller
        knows exactly what to supply.
        """
        missing = [s for s in self.required_slots if s not in slots]
        if missing:
            raise KeyError(
                f"Framework '{self.name}' is missing required slot(s): {missing}"
            )
        return self._template.format_map(slots)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Framework] = {}


def _register(f: Framework) -> None:
    _REGISTRY[f.name] = f


# ------------------------------------------------------------------
# 1. problem-first
# ------------------------------------------------------------------
_register(Framework(
    name="problem-first",
    best_use=(
        "When you have a verified pain point the buyer recognises. "
        "Opens with their problem, not your product."
    ),
    required_slots=(
        "observed_signal",   # e.g. "saw you just hired 3 SDRs"
        "quantified_pain",   # e.g. "most teams waste 6h/rep/week on CRM hygiene"
        "one_liner_solution", # e.g. "we auto-sync call notes to Salesforce"
        "soft_cta",          # e.g. "worth a 15-min chat this week?"
        "first_name",
    ),
    _template=(
        "Hi {first_name},\n\n"
        "{observed_signal} — which usually means {quantified_pain}.\n\n"
        "{one_liner_solution}.\n\n"
        "{soft_cta}"
    ),
))

# ------------------------------------------------------------------
# 2. do-the-math
# ------------------------------------------------------------------
_register(Framework(
    name="do-the-math",
    best_use=(
        "When you can attach a believable number to the outcome. "
        "The prospect runs the math themselves and the email sells itself."
    ),
    required_slots=(
        "first_name",
        "observed_signal",
        "cost_of_problem",   # e.g. "$4 200/mo in wasted rep time"
        "what_we_do",        # e.g. "we cut that by ~70%"
        "proof_point",       # e.g. "similar result at Acme in 3 weeks"
        "soft_cta",
    ),
    _template=(
        "Hi {first_name},\n\n"
        "Quick one: {observed_signal}.\n\n"
        "For teams your size that typically costs {cost_of_problem}. "
        "{what_we_do} — {proof_point}.\n\n"
        "{soft_cta}"
    ),
))

# ------------------------------------------------------------------
# 3. pattern-interrupt
# ------------------------------------------------------------------
_register(Framework(
    name="pattern-interrupt",
    best_use=(
        "When the buyer is flooded with samey pitches. "
        "Opens with something unexpected or self-aware to earn a second read."
    ),
    required_slots=(
        "first_name",
        "disruptive_opener",  # e.g. "I know you get 30 cold emails a day"
        "unexpected_angle",   # e.g. "so I'll skip the pitch and ask one question"
        "single_question",    # the actual question that creates curiosity
        "soft_cta",
    ),
    _template=(
        "Hi {first_name},\n\n"
        "{disruptive_opener}. {unexpected_angle}:\n\n"
        "{single_question}\n\n"
        "{soft_cta}"
    ),
))

# ------------------------------------------------------------------
# 4. upfront-value
# ------------------------------------------------------------------
_register(Framework(
    name="upfront-value",
    best_use=(
        "When you can hand something useful before asking for anything. "
        "Works well with research-heavy buyers who respect the homework."
    ),
    required_slots=(
        "first_name",
        "value_artifact",    # e.g. "a teardown of your onboarding flow"
        "key_finding",       # e.g. "found 3 drop-off points in the first 48h"
        "why_it_matters",    # e.g. "fixing the first one alone could lift activation 15%"
        "soft_cta",
    ),
    _template=(
        "Hi {first_name},\n\n"
        "I put together {value_artifact} — no strings.\n\n"
        "Top finding: {key_finding}. {why_it_matters}.\n\n"
        "{soft_cta}"
    ),
))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_framework(name: str) -> Framework:
    """Return a Framework by name. Raises KeyError on unknown name."""
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown framework '{name}'. Available: {list(_REGISTRY)}"
        )
    return _REGISTRY[name]


def list_frameworks() -> list[str]:
    """Return all registered framework names in insertion order."""
    return list(_REGISTRY)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== framework_registry demo ===\n")
    print(f"Registered frameworks: {list_frameworks()}\n")

    fw = get_framework("problem-first")
    rendered = fw.render({
        "first_name": "Sarah",
        "observed_signal": "saw you just posted 4 SDR roles on LinkedIn",
        "quantified_pain": "most scaling teams lose 8h/rep/week to manual CRM entry",
        "one_liner_solution": "we auto-sync every call note straight to HubSpot in real-time",
        "soft_cta": "Worth a 15-min chat this week to see if it fits?",
    })
    print(f"[problem-first render]\n{rendered}\n")

    fw2 = get_framework("do-the-math")
    rendered2 = fw2.render({
        "first_name": "Marcus",
        "observed_signal": "noticed you raised your Series A last month",
        "cost_of_problem": "$6 k/mo in wasted rep admin time",
        "what_we_do": "we typically cut that by 70 %",
        "proof_point": "similar outcome at Deel inside 3 weeks",
        "soft_cta": "Open to a 15-min call Tuesday or Thursday?",
    })
    print(f"[do-the-math render]\n{rendered2}\n")
