"""Meta + LinkedIn ad-creative primitives — the RSA validator's counterpart
for the two channels Google's hard character limits don't apply to.

UNLIKE Google RSA (rsa_schema.py), Meta and LinkedIn do not hard-reject text
past a fixed length — copy beyond these figures is ACCEPTED by both APIs but
risks truncation ("See more") in the placements that convert best (mobile
feed). The constants below are each platform's own published creative-specs
guidance, not API-enforced ceilings — ad_creative.py's validators emit
WARNINGS the caller can ship past, never hard failures, matching that
distinction honestly rather than pretending these are Google-style limits.
"""

from __future__ import annotations

from dataclasses import dataclass

# Meta feed/Instagram single-image creative guidance (object_story_spec.link_data).
META_PRIMARY_TEXT_RECOMMENDED_MAX = 125
META_HEADLINE_RECOMMENDED_MAX = 40
META_DESCRIPTION_RECOMMENDED_MAX = 30

# LinkedIn Sponsored Content (Single Image/Video) creative guidance.
LINKEDIN_INTRO_TEXT_RECOMMENDED_MAX = 150
LINKEDIN_HEADLINE_RECOMMENDED_MAX = 70


@dataclass(frozen=True)
class MetaAdCreative:
    primary_text: str
    headline: str
    description: str = ""


@dataclass(frozen=True)
class LinkedInAdCreative:
    introductory_text: str
    headline: str


@dataclass(frozen=True)
class CreativeValidation:
    """ok reflects hard issues only (e.g. a blank required field) — truncation
    risk is advisory and lives in `warnings`, never blocks `ok`."""

    ok: bool
    issues: tuple[str, ...]
    warnings: tuple[str, ...]
