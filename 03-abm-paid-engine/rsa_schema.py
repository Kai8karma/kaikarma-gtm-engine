"""Google Responsive Search Ad (RSA) primitives.

Encodes the workflow Anthropic's growth-marketing team runs via Claude Code: a
`/rsa` step that produces up to 15 unique headlines + 4 descriptions under
Google's strict character limits, validated and exported as a CSV ready for
Google Ads upload (after human review). See research/anthropic-growth-playbook.md.

This is the deterministic scaffold — limits, validation, CSV, and the generation
brief. The copy itself stays human/LLM-in-the-loop, exactly as Anthropic runs it.
"""

from __future__ import annotations

from dataclasses import dataclass

# Google RSA hard limits (chars include spaces).
HEADLINE_MAX = 30
DESCRIPTION_MAX = 90
PATH_MAX = 15
MIN_HEADLINES = 3
MAX_HEADLINES = 15
MIN_DESCRIPTIONS = 2
MAX_DESCRIPTIONS = 4
MAX_EXCLAMATIONS = 1  # Google allows at most one "!" per ad, and none in headlines.

# All-caps alpha tokens of this length+ are gratuitous capitalization (a Google
# policy reject) UNLESS they are a known acronym.
CAPS_MIN_LEN = 4
ACRONYM_ALLOWLIST = frozenset({
    "ROAS", "HVAC", "SAAS", "B2B", "B2C", "API", "SEO", "RSA",
    "CPA", "CPL", "CTV", "SMB", "CRM", "USA", "FAQ", "ABM",
})


@dataclass(frozen=True)
class ResponsiveSearchAd:
    headlines: tuple[str, ...]
    descriptions: tuple[str, ...]
    path1: str = ""
    path2: str = ""


@dataclass(frozen=True)
class RsaValidation:
    ok: bool
    issues: tuple[str, ...]
    headline_count: int
    description_count: int
