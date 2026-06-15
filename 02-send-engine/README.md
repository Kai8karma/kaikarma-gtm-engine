# 02 — Send Engine

**Infrastructure + copy — as calculators and structured prompts, not prose checklists.**

## Built

- `send_schema.py` — typed dataclasses: `InfraPlan`, `RampWeek`, `DnsCheck`. Pure data primitives, no logic.
- `domain_calculator.py` — `plan_infra(monthly_emails, per_mailbox_daily_cap, mailboxes_per_domain, warmup_weeks)` returns mailboxes needed, domains needed (ceil mailboxes / mailboxes_per_domain), and a conservative linear warmup ramp. Stdlib only, no network.
- `dns_validator.py` — pure-parsing validators for SPF, DKIM, DMARC record strings with no DNS lookup: `validate_spf()`, `validate_dkim()`, `validate_dmarc()`, `validate_all()`. Each returns a `DnsCheck` (pass/fail + specific issues).
- `test_send.py` — 35 stdlib `unittest` assertions covering both modules: valid records, malformed records, edge mailbox counts, determinism, type contracts.

### Copy layer

- `framework_registry.py` — registry of 4 named B2B cold-email copy frameworks (`problem-first`, `do-the-math`, `pattern-interrupt`, `upfront-value`). Each is a `Framework` dataclass with `name`, `best_use`, `required_slots`, and `render(slots) -> str` that raises `KeyError` on any missing slot. Public API: `get_framework(name)`, `list_frameworks()`. Stdlib only, no network.
- `copy_eval.py` — `score_copy(draft, framework) -> EvalResult` with a 0–100 score, issues list, and per-criterion breakdown. Five deterministic criteria: word count in bounds (40–120 words), question or CTA present, no banned hype words, personalization token filled, exactly one clear ask.
- `test_copy.py` — 35 stdlib `unittest` assertions: happy-path renders for all 4 frameworks, missing-slot raises naming the slot, registry lookups, clean draft scores 100/0 issues, hypey/no-CTA draft scores below 50, banned-word detection (case-insensitive), single-ask enforcement.

## Planned

- `sequencer/sequence_push.py` — push contacts to Instantly/Smartlead via API.

## Doctrine reference

The strategy (signal-stacked sequencing, infra warmup, copy frameworks) is summarized in [`../docs/`](../docs/) and analyzed against the field in [`../research/teardowns/`](../research/teardowns/) — but the doctrine is subordinate to the code that executes it.
