# Security

This engine can move ad budgets and write to a CRM once a live executor is
wired in. This page says what it does by default, what changes when you
connect it, and how to report a problem.

## Default: nothing leaves your machine

- Every decision module (scoring, sequencing, the paid controller,
  routing, the learning loop) uses the Python standard library only and
  makes no network call.
- The only layer allowed to reach the network is an `Executor`
  (`03-abm-paid-engine/executor.py`). The default is `DryRunExecutor`,
  which records the actions a decision would take and sends nothing.
- The test suite runs with no credentials and no network.

See [`docs/egress-policy.md`](docs/egress-policy.md) for the full policy.

## When you connect a live executor

You accept three risks the dry-run default does not carry:

1. **Spend.** The paid controller can scale, cut or stop campaigns. It
   acts inside hard caps and a learning-phase grace window, but the caps
   are numbers you configure. Check them against your real budget before
   the first live run.
2. **Writes.** The HubSpot adapter and the ads executors change records
   and campaigns in your accounts.
3. **Unproven adapters.** The Apollo, HubSpot, Google, Meta and LinkedIn
   adapters were written from public API documentation and have not been
   validated against live accounts. Run each one against a sandbox or a
   test account first, and compare what it did with what the dry run said
   it would do.

Recommended order for a first live run: dry run, read the recorded
actions, run against a sandbox, then run live with the lowest caps you can
set.

## Credentials

- Adapters take an injected client. The engine does not read, store or
  log credentials itself.
- Keep credentials in your environment or a secret manager, never in
  `engagements/<client>/`. Those folders hold configuration that is meant
  to be committed.
- Use the narrowest scopes each adapter needs, and separate credentials
  per client.

## Client data

Each engagement lives in its own `engagements/<name>/` folder. Do not
commit real prospect or customer records to a public fork. The outcome
store persists what you feed it; treat its files like a CRM export.

## Reporting a vulnerability

Use GitHub's private reporting: **Security → Report a vulnerability** on
this repository. If you cannot, email kai8karma@gmail.com with
"kaikarma-gtm-engine security" in the subject. Include the module, the
input that triggers the problem and what you observed.

A cap that can be bypassed, an executor that egresses in dry-run mode, or
one client's data reaching another's folder are all security issues here,
not ordinary bugs. Please report them privately.
