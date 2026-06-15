# 02 — Send Engine

**Infrastructure + copy — as calculators and structured prompts, not prose checklists.**

## Built

- `send_schema.py` — typed dataclasses: `InfraPlan`, `RampWeek`, `DnsCheck`. Pure data primitives, no logic.
- `domain_calculator.py` — `plan_infra(monthly_emails, per_mailbox_daily_cap, mailboxes_per_domain, warmup_weeks)` returns mailboxes needed, domains needed (ceil mailboxes / mailboxes_per_domain), and a conservative linear warmup ramp. Stdlib only, no network.
- `dns_validator.py` — pure-parsing validators for SPF, DKIM, DMARC record strings with no DNS lookup: `validate_spf()`, `validate_dkim()`, `validate_dmarc()`, `validate_all()`. Each returns a `DnsCheck` (pass/fail + specific issues).
- `test_send.py` — 35 stdlib `unittest` assertions covering both modules: valid records, malformed records, edge mailbox counts, determinism, type contracts.

## Planned

- `copywriting/framework_registry.py` — named copy frameworks as structured prompt templates with explicit best-use + slots, not markdown examples.
- `copywriting/copy_eval.py` — score a draft against its framework's criteria before it ships (the eval gate).
- `sequencer/sequence_push.py` — push contacts to Instantly/Smartlead via API.

## Doctrine reference

The strategy (signal-stacked sequencing, infra warmup, copy frameworks) is summarized in [`../docs/`](../docs/) and analyzed against the field in [`../research/teardowns/`](../research/teardowns/) — but the doctrine is subordinate to the code that executes it.
