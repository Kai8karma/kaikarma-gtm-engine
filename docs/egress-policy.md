# Egress policy

The engine is **air-gapped by default**. The brain — scoring, pacing, routing,
validation, the learning loop — never touches the network. Every module is
stdlib-only and runs offline.

The **only** layer permitted to egress is an `Executor` implementation
([`03-abm-paid-engine/executor.py`](../03-abm-paid-engine/executor.py)). This is
deliberate, and it's why this repo doesn't ship a pile of hardcoded API scripts:

- **`DryRunExecutor`** is the default. It records the actions a decision would
  take and sends **nothing**. Provably correct, fully tested, zero egress.
- A **live executor** (e.g. `GoogleAdsExecutor`) is an explicit, isolated opt-in.
  It is a stub until someone wires real credentials and tests it against a real
  account. A fake "working" integration is worse than an honest unimplemented one.

This mirrors the three-layer separation in `00-operating-system/`: strategy never
calls live APIs; execution is the only thing that can. Want it connected? Swap a
real `Executor` in at the boundary — the brain doesn't change, and nothing leaks
until you choose it to.

**What this buys you, honestly:** the engine emits validated, dry-run-tested
actions and is one real adapter away from live. It does **not** yet manage a live
account — that last mile needs a real executor, real credentials, and live
testing against your own account, accepting egress and spend risk.
