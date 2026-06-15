# Anthropic Growth-Marketing Playbook → what we encoded

**Date:** 2026-06-16 · **Purpose:** turn Anthropic's documented Claude-Code growth workflow into engine code, not commentary.

## Source

Anthropic's growth-marketing function ran as **one non-technical marketer (Austin Lau) for ~10 months** at a **$380B** company ([Series G, Feb 2026](https://www.anthropic.com/news/anthropic-raises-30-billion-series-g-funding-380-billion-post-money-valuation)) — paid search, paid social, ASO, email, SEO, solo. Workflow detail from [How Anthropic uses Claude in Marketing](https://claude.com/blog/how-anthropic-uses-claude-marketing); story via [Ole Lehmann](https://x.com/itsolelehmann/status/2031308486815133905).

## Workflows documented (and where they map here)

| Anthropic workflow | Detail | Encoded as |
|---|---|---|
| **`/rsa` — Google RSA generation** | A slash command produces **15 unique headlines** + descriptions under Google's strict char limits, cross-referencing brand-tone + product-accuracy skills + RSA best practices; outputs a **CSV ready for Google Ads upload** after human review. | ✅ `03-abm-paid-engine/rsa_builder.py` + `rsa_schema.py` |
| **Figma plugin — creative permutations** | Paste headline copy once → one click renders every image permutation across aspect ratios (~30 min saved/batch). | ⬜ candidate (needs an image runtime — out of scope for a stdlib engine) |
| **Ad-performance loop** | Export ad metrics CSV → Claude finds weak ads → generates new variants; build 2 hr → 15 min, ~10× creative tested. | partial — detection fits `perf_controller`; the variant *brief* is `rsa_builder.generation_brief()` |

## The principle we kept

Anthropic's pattern is **human/LLM-in-the-loop generation + deterministic guardrails**: Claude writes the copy; rules decide what's valid and uploadable. We mirror that — `rsa_builder` does **not** generate copy (that's the LLM/`/rsa` step), it **validates** generated copy against Google's format rules, emits the **upload CSV**, and produces the **structured generation brief** that bakes the constraints in. So a non-engineer (or an agent) can ship policy-clean ads at volume — the exact "one operator, whole team" leverage the source describes.

## What encoding it bought

`validate_rsa()` catches, deterministically: over-limit headlines/descriptions, wrong asset counts, duplicate headlines, `!` in headlines + >1 `!` per ad, repeated punctuation, and gratuitous ALL-CAPS (with an acronym allowlist). 15 tests. The difference vs the source's prose checklist: the rules **run**, so generated ads can't silently ship malformed.
