# Changelog

Notable changes to kaikarma-gtm-engine, newest first. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

The version labels below are the ones used in commit messages. No release
has been tagged yet, and `pyproject.toml` still reads 0.1.0.

## [Unreleased]

### Fixed
- **CI lint.** `ruff check .` ran unpinned with no rule selection. Ruff's
  default rules have grown since, so the same tree now reports 115 findings
  on the current release. The rule set the tree was clean against is now
  written into `pyproject.toml`, and CI and `make lint` pin ruff 0.17.5.

### Added
- CI runs `pytest` (774 tests) next to `tests/smoke.sh`. The smoke script
  runs a hand-kept list of files; pytest collects every test file itself.
- `SECURITY.md` and this changelog.

## 2026-08-21
- README links the browser CRM grader and the gtmos-mcp install.

## 2026-07-11
### Added
- `examples/pitch.py`, a single-command live demo, and `make pitch`.

## 2026-06-17
### Changed
- README leads with the runnable proof.

## 2026-06-16
### Added
- Full-stack API integration layer with injected clients: Apollo
  enrichment, HubSpot CRM, email sequencer and ad campaign creation.
  Zero egress in tests. Not validated against live accounts.
- Google, Meta and LinkedIn ads executors and reporting, behind the
  execution boundary. Dry-run is the default.
- Google responsive search ad builder.
- Pre-registered backtest of the learning loop (`evals/`). Verdict: PARK.
- v0.4: multi-pillar and persistent learning loop.
- v0.3: the learning loop closed end to end, copy frameworks, lifecycle
  state machine, per-engagement configs.

## 2026-06-15
### Added
- v0.2: all five pillars gated in CI, ruff, the learning loop.
- Performance-marketing controller: classify, act, cap.
- v0.1: first commit. GTM decisions as tested code across list, send,
  paid, revops and brain.
