# 06 — Pre-Call Intelligence Engine

**Every confirmed demo call gets a researched briefing (T-2) and recap (T-1) — automatically, deduped, and reused across the two emails.** Built for the Aerchain engagement; the trigger/parsing/prompt logic here is generic (any HubSpot + Google Calendar + Gmail + Claude motion), only `engagements/aerchain/precall_config.json` is client-specific.

## Built

- `precall_schema.py` — typed primitives: `CalendarEvent` (attendees, dedup flags), `ContactProfile` / `CompanyProfile` (HubSpot enrichment, with `industry_source` tracking CRM vs. web-search fallback), `BriefingSections` (T-2's 5 sections, validated: 4 non-blank + 6-8 discovery questions), `RecapSummary` (T-1's fields, validated: exactly 3 talking points, 1-2 references, exactly 3 opening questions).
- `trigger_scheduler.py` — the SOW Section 4/6 decision as pure functions: `classify_window(call_date, today)` → `t2`/`t1`/`none` by exact calendar-day distance (matches the SOW's own "exactly 2 days (and 1 day) out" wording); `needs_catchup(event)` → true if booked with under 48h lead time (the case the hybrid webhook trigger exists to catch); `plan_action(event, today, trigger_mode)` combines both with the dedup flags into one verdict: `send_briefing` / `send_recap` / `send_catchup_briefing` / `skip`.
- `calendar_parser.py` — Google Calendar adapter: parses raw event dicts into `CalendarEvent`, splits attendees into internal reps vs. the prospect by domain, reads/builds the `briefingSent`/`summarySent` extended-properties patches. Injected-client I/O boundary (`FakeCalendarClient` for zero-egress tests), fail-loud on read errors.
- `hubspot_precall.py` — HubSpot adapter: contact/company lookup by email, the `precall_briefing` writeback (T-2 writes it, T-1 reads it), and the industry-fallback contract (`industry_source = "web_search_fallback"` whenever HubSpot's `industry` field is blank — a flagged CRM-audit finding, not silently guessed at).
- `briefing_builder.py` — builds the Claude prompt for both emails (T-2's five-section research brief, T-1's condense-the-briefing recap) and assembles the model's output into the HTML actually mailed. Raises loud if asked to build a T-1 recap with no stored T-2 content, or to assemble briefing/recap data that fails schema validation.
- `pipeline.py` — `plan_run(events, today, trigger_mode)` batches `trigger_scheduler.plan_action` across every event on the calendar and attaches the prospect email each downstream step needs; `actionable()` filters to what's actually due today.
- `n8n/precall_intelligence.workflow.json` — the importable n8n workflow (daily-sweep schedule trigger + sub-48h webhook, HubSpot lookup, Claude web-search briefing/recap generation, Gmail send, HubSpot/Calendar writeback). Its Code nodes are hand-ported JS mirrors of `trigger_scheduler.py` — **change the Python spec's tests first, then port the change into the workflow's Code nodes,** or the two drift.
- 5 test files, 80 assertions total — every trigger boundary (exact T-2/T-1 day match, 48h catch-up threshold, dedup skip, invalid trigger mode), every schema invariant, every fake-client round trip.

## Why the split (per CLAUDE.md's three-layer doctrine)

- This directory is **execution**: it runs the decision the doctrine encodes, and is the only layer that may call live APIs (Calendar/HubSpot/Gmail/Claude — all behind injected clients, `FakeCalendarClient`/`FakeHubSpotPrecallClient` by default, zero egress in tests).
- `engagements/aerchain/precall_config.json` is the **client-specific parameter set** — calendar mailbox, internal-domain allowlist, trigger mode, model tier, error-alert routing. Nothing here is hardcoded into this engine's code.
- The n8n workflow is the actual runtime: it is what the client's automation platform executes. The Python modules are the tested spec for the decision logic the workflow's Code nodes implement — run `python3 06-precall-intelligence-engine/test_trigger_scheduler.py` to prove a timing-rule change is correct *before* touching the workflow JSON.

## Honest scope

- **Not validated against live HubSpot/Calendar/Gmail/Anthropic accounts.** Every adapter here is complete and structurally correct against the public API shapes documented in each module's docstring, matching the `hubspot_crm.py` precedent in `04-revops-engine/`. Live use needs real credentials and a pilot run (SOW Section 9: dummy call → 3-4 real calls → portal-wide).
- **Two SOW Section 8 decisions are still open**, not decided here: which calendar the confirmed invites actually land on, and who owns error-alert routing. Both are flagged in `engagements/aerchain/precall_config.json["pending_decisions"]` rather than guessed at — see `engagements/aerchain/_INDEX.md` for the full decision log.
- **Section 10 risk (blank CRM industry field) has a coded fallback**, not a fix: `company_to_profile` flags `industry_source="web_search_fallback"` so the Claude prompt asks the model to classify from web search instead of mismatching customer references — but a clean CRM still gives a better result, per the SOW's own caveat.

## Run it

```bash
python3 06-precall-intelligence-engine/trigger_scheduler.py     # demo: 4 calls, 4 different trigger verdicts
python3 06-precall-intelligence-engine/pipeline.py              # demo: batch decision across a calendar sweep
python3 06-precall-intelligence-engine/test_trigger_scheduler.py -v
python3 engagements/aerchain/precall_config_loader.py            # demo: loads + validates the Aerchain config
```
