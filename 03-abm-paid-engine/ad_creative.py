"""Meta + LinkedIn ad-creative validator/brief-generator.

rsa_builder.py covers Google — the one channel where going over the limit
gets an ad rejected outright. This module is its counterpart for Meta and
LinkedIn, where going long doesn't get rejected, it gets truncated in the
placement that matters most. The validators here are honest about that
difference: `issues` are hard problems (blank required fields); `warnings`
are truncation-risk advisories the caller can ship past deliberately.

    python3 03-abm-paid-engine/ad_creative.py        # demo
    python3 03-abm-paid-engine/test_ad_creative.py   # tests

Copy generation stays human/LLM-in-the-loop, exactly like rsa_builder.py —
this is the deterministic scaffold, not the copywriter.
"""

from __future__ import annotations

from creative_schema import (
    LINKEDIN_HEADLINE_RECOMMENDED_MAX,
    LINKEDIN_INTRO_TEXT_RECOMMENDED_MAX,
    META_DESCRIPTION_RECOMMENDED_MAX,
    META_HEADLINE_RECOMMENDED_MAX,
    META_PRIMARY_TEXT_RECOMMENDED_MAX,
    CreativeValidation,
    LinkedInAdCreative,
    MetaAdCreative,
)


def validate_meta_creative(ad: MetaAdCreative) -> CreativeValidation:
    """Validate Meta feed/Instagram creative. Deterministic."""
    issues: list[str] = []
    warnings: list[str] = []

    if not ad.primary_text.strip():
        issues.append("primary_text: empty")
    if not ad.headline.strip():
        issues.append("headline: empty")

    if len(ad.primary_text) > META_PRIMARY_TEXT_RECOMMENDED_MAX:
        warnings.append(
            f"primary_text: {len(ad.primary_text)} chars exceeds the "
            f"{META_PRIMARY_TEXT_RECOMMENDED_MAX}-char truncation-risk guideline"
        )
    if len(ad.headline) > META_HEADLINE_RECOMMENDED_MAX:
        warnings.append(
            f"headline: {len(ad.headline)} chars exceeds the "
            f"{META_HEADLINE_RECOMMENDED_MAX}-char truncation-risk guideline"
        )
    if ad.description and len(ad.description) > META_DESCRIPTION_RECOMMENDED_MAX:
        warnings.append(
            f"description: {len(ad.description)} chars exceeds the "
            f"{META_DESCRIPTION_RECOMMENDED_MAX}-char truncation-risk guideline"
        )

    return CreativeValidation(ok=not issues, issues=tuple(issues), warnings=tuple(warnings))


def validate_linkedin_creative(ad: LinkedInAdCreative) -> CreativeValidation:
    """Validate LinkedIn Sponsored Content creative. Deterministic."""
    issues: list[str] = []
    warnings: list[str] = []

    if not ad.introductory_text.strip():
        issues.append("introductory_text: empty")
    if not ad.headline.strip():
        issues.append("headline: empty")

    if len(ad.introductory_text) > LINKEDIN_INTRO_TEXT_RECOMMENDED_MAX:
        warnings.append(
            f"introductory_text: {len(ad.introductory_text)} chars exceeds the "
            f"{LINKEDIN_INTRO_TEXT_RECOMMENDED_MAX}-char truncation-risk guideline"
        )
    if len(ad.headline) > LINKEDIN_HEADLINE_RECOMMENDED_MAX:
        warnings.append(
            f"headline: {len(ad.headline)} chars exceeds the "
            f"{LINKEDIN_HEADLINE_RECOMMENDED_MAX}-char truncation-risk guideline"
        )

    return CreativeValidation(ok=not issues, issues=tuple(issues), warnings=tuple(warnings))


def meta_generation_brief(product: str, audience: str, tone: str) -> str:
    """Structured spec an LLM copy-generation step fills — mirrors rsa_builder.generation_brief."""
    return "\n".join([
        f"Generate Meta (Facebook/Instagram) feed ad copy for: {product}",
        f"Target audience: {audience}",
        f"Brand tone: {tone}",
        "",
        "Guidance (truncation-risk, NOT a hard API limit like Google RSA):",
        f"- Primary text ≤ {META_PRIMARY_TEXT_RECOMMENDED_MAX} chars to avoid 'See more' truncation",
        f"- Headline ≤ {META_HEADLINE_RECOMMENDED_MAX} chars",
        f"- Description ≤ {META_DESCRIPTION_RECOMMENDED_MAX} chars",
        "",
        "Output for human review before upload.",
    ])


def linkedin_generation_brief(product: str, audience: str, tone: str) -> str:
    """Structured spec an LLM copy-generation step fills — mirrors rsa_builder.generation_brief."""
    return "\n".join([
        f"Generate LinkedIn Sponsored Content ad copy for: {product}",
        f"Target audience: {audience}",
        f"Brand tone: {tone}",
        "",
        "Guidance (truncation-risk, NOT a hard API limit like Google RSA):",
        f"- Introductory text ≤ {LINKEDIN_INTRO_TEXT_RECOMMENDED_MAX} chars (mobile truncates hardest)",
        f"- Headline ≤ {LINKEDIN_HEADLINE_RECOMMENDED_MAX} chars",
        "",
        "Output for human review before upload.",
    ])


if __name__ == "__main__":
    good_meta = MetaAdCreative(
        primary_text="Rank accounts, route leads, and optimize spend from one engine.",
        headline="GTM Engineering as Code",
        description="Open-source, 943 tests, MIT.",
    )
    long_meta = MetaAdCreative(
        primary_text="A" * 200,
        headline="B" * 60,
    )
    good_linkedin = LinkedInAdCreative(
        introductory_text="Rank accounts, route leads, and optimize spend — all from one auditable engine.",
        headline="B2B Pipeline on Autopilot",
    )
    blank_linkedin = LinkedInAdCreative(introductory_text="", headline="")

    print("ad_creative demo\n--- Meta ---")
    for label, ad in (("VALID", good_meta), ("LONG", long_meta)):
        v = validate_meta_creative(ad)
        print(f"[{label}] ok={v.ok}")
        for i in v.issues:
            print("   issue  -", i)
        for w in v.warnings:
            print("   warn   -", w)

    print("\n--- LinkedIn ---")
    for label, ad in (("VALID", good_linkedin), ("BLANK", blank_linkedin)):
        v = validate_linkedin_creative(ad)
        print(f"[{label}] ok={v.ok}")
        for i in v.issues:
            print("   issue  -", i)
        for w in v.warnings:
            print("   warn   -", w)

    print("\n--- generation briefs ---")
    print(meta_generation_brief("kaikarma-gtm-engine", "B2B RevOps leaders", "confident, technical, no hype"))
    print()
    print(linkedin_generation_brief("kaikarma-gtm-engine", "B2B RevOps leaders", "confident, technical, no hype"))
