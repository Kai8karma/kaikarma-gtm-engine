"""Google RSA builder/validator — encodes Anthropic's `/rsa` growth workflow.

    python3 03-abm-paid-engine/rsa_builder.py        # demo
    python3 03-abm-paid-engine/test_rsa.py           # tests

LLM/Claude generates the copy (human-in-the-loop); THIS validates it against
Google's format rules so what ships is actually uploadable, and emits both the
upload CSV and the structured generation brief. Pure stdlib, deterministic.
"""

from __future__ import annotations

import csv
import io
import re

from rsa_schema import (
    ACRONYM_ALLOWLIST,
    CAPS_MIN_LEN,
    DESCRIPTION_MAX,
    HEADLINE_MAX,
    MAX_DESCRIPTIONS,
    MAX_EXCLAMATIONS,
    MAX_HEADLINES,
    MIN_DESCRIPTIONS,
    MIN_HEADLINES,
    PATH_MAX,
    ResponsiveSearchAd,
    RsaValidation,
)

_REPEATED_PUNCT = re.compile(r"([!?.])\1")


def _gratuitous_caps(text: str) -> list[str]:
    """All-caps words (not known acronyms) that Google rejects as gimmicky."""
    bad = []
    for word in re.findall(r"[A-Za-z]+", text):
        if word.isupper() and len(word) >= CAPS_MIN_LEN and word not in ACRONYM_ALLOWLIST:
            bad.append(word)
    return bad


def _asset_issues(text: str, where: str, limit: int, is_headline: bool) -> list[str]:
    issues = []
    n = len(text)
    if n == 0:
        issues.append(f"{where}: empty")
    if n > limit:
        issues.append(f"{where}: {n} chars exceeds {limit} ('{text[:limit]}…')")
    if is_headline and "!" in text:
        issues.append(f"{where}: headlines may not contain '!'")
    if _REPEATED_PUNCT.search(text):
        issues.append(f"{where}: repeated punctuation not allowed")
    for word in _gratuitous_caps(text):
        issues.append(f"{where}: gratuitous capitalization '{word}'")
    return issues


def validate_rsa(rsa: ResponsiveSearchAd) -> RsaValidation:
    """Validate a full RSA against Google's limits + policy. Deterministic."""
    issues: list[str] = []
    h, d = rsa.headlines, rsa.descriptions

    if not (MIN_HEADLINES <= len(h) <= MAX_HEADLINES):
        issues.append(f"headlines: need {MIN_HEADLINES}-{MAX_HEADLINES}, got {len(h)}")
    if not (MIN_DESCRIPTIONS <= len(d) <= MAX_DESCRIPTIONS):
        issues.append(f"descriptions: need {MIN_DESCRIPTIONS}-{MAX_DESCRIPTIONS}, got {len(d)}")

    # Google requires the headlines be distinct (case-insensitive).
    seen = [x.strip().lower() for x in h]
    if len(set(seen)) != len(seen):
        issues.append("headlines: must be unique (duplicate found)")

    for i, text in enumerate(h):
        issues += _asset_issues(text, f"headline[{i}]", HEADLINE_MAX, is_headline=True)
    for i, text in enumerate(d):
        issues += _asset_issues(text, f"description[{i}]", DESCRIPTION_MAX, is_headline=False)

    for path, name in ((rsa.path1, "path1"), (rsa.path2, "path2")):
        if len(path) > PATH_MAX:
            issues.append(f"{name}: {len(path)} chars exceeds {PATH_MAX}")

    total_excl = sum(text.count("!") for text in (*h, *d))
    if total_excl > MAX_EXCLAMATIONS:
        issues.append(f"ad: {total_excl} '!' exceeds max {MAX_EXCLAMATIONS} per ad")

    return RsaValidation(
        ok=not issues,
        issues=tuple(issues),
        headline_count=len(h),
        description_count=len(d),
    )


def rsa_to_csv(rsa: ResponsiveSearchAd) -> str:
    """Emit a Google Ads Editor-style upload row (header + values)."""
    cols = (
        [f"Headline {i}" for i in range(1, MAX_HEADLINES + 1)]
        + [f"Description {i}" for i in range(1, MAX_DESCRIPTIONS + 1)]
        + ["Path 1", "Path 2"]
    )
    h = list(rsa.headlines) + [""] * (MAX_HEADLINES - len(rsa.headlines))
    d = list(rsa.descriptions) + [""] * (MAX_DESCRIPTIONS - len(rsa.descriptions))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    w.writerow(h + d + [rsa.path1, rsa.path2])
    return buf.getvalue()


def generation_brief(product: str, keywords: list[str], tone: str,
                     n_headlines: int = MAX_HEADLINES,
                     n_descriptions: int = MAX_DESCRIPTIONS) -> str:
    """The structured spec an LLM/`/rsa` step fills — constraints baked in.

    Mirrors Anthropic's workflow: cross-reference brand tone + product accuracy +
    Google RSA best practices, under the hard format limits.
    """
    return "\n".join([
        f"Generate a Google Responsive Search Ad for: {product}",
        f"Target keywords: {', '.join(keywords)}",
        f"Brand tone: {tone}",
        "",
        "Hard constraints (reject anything that violates these):",
        f"- {n_headlines} UNIQUE headlines, each ≤ {HEADLINE_MAX} characters",
        f"- {n_descriptions} descriptions, each ≤ {DESCRIPTION_MAX} characters",
        f"- At most {MAX_EXCLAMATIONS} '!' in the whole ad, and NONE in headlines",
        "- No gratuitous ALL-CAPS words, no repeated punctuation (!!, ?? , ...)",
        "",
        "Cross-reference before returning: brand tone guide, product-accuracy",
        "facts, and Google RSA best practices. Output for human review, then CSV.",
    ])


if __name__ == "__main__":
    good = ResponsiveSearchAd(
        headlines=(
            "Automate Your Outbound", "GTM Engineering as Code", "Score Leads Instantly",
            "Cut CPA, Not Corners", "B2B Pipeline on Autopilot",
        ),
        descriptions=(
            "Rank accounts, route leads, and optimize spend from one engine.",
            "Open-source GTM stack with a learning loop. 295 tests, MIT.",
        ),
        path1="gtm", path2="engine",
    )
    bad = ResponsiveSearchAd(
        headlines=("GET IT FREE TODAY!!", "Score Leads", "Score Leads"),
        descriptions=("Short.",),
    )
    for label, ad in (("VALID", good), ("BROKEN", bad)):
        v = validate_rsa(ad)
        print(f"[{label}] ok={v.ok}  headlines={v.headline_count} descriptions={v.description_count}")
        for issue in v.issues:
            print("   -", issue)
    print("\n--- upload CSV (valid ad) ---")
    print(rsa_to_csv(good).strip())
    print("\n--- generation brief ---")
    print(generation_brief("kaikarma-gtm-engine", ["gtm engineering", "lead scoring"], "confident, technical, no hype"))
