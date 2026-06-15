# 02 — Send Engine

**Infrastructure + copy — as calculators and structured prompts, not prose checklists.**

## Planned

- `infra/domain_calculator.py` — compute mailbox/domain needs from a monthly send goal (sane caps: ~2 mailboxes/domain, conservative warmup).
- `infra/dns_validator.py` — verify SPF/DKIM/DMARC via live DNS lookup, pass/fail. (A prose "check your DNS" is not a check.)
- `copywriting/framework_registry.py` — named copy frameworks as structured prompt templates with explicit best-use + slots, not markdown examples.
- `copywriting/copy_eval.py` — score a draft against its framework's criteria before it ships (the eval gate).
- `sequencer/sequence_push.py` — push contacts to Instantly/Smartlead via API.

## Doctrine reference

The strategy (signal-stacked sequencing, infra warmup, copy frameworks) is summarized in [`../docs/`](../docs/) and analyzed against the field in [`../research/teardowns/`](../research/teardowns/) — but the doctrine is subordinate to the code that executes it.
