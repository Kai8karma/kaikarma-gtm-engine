#!/usr/bin/env bash
# Regression guard. Nothing ships unless this exits 0.
# Covers EVERY shipped pillar — if a pillar has code, it is gated here and in CI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$(command -v python3 || command -v python)"

run() {  # run <label> <path>
  echo
  echo "▶ $1"
  "$PY" "$2"
}

# 01 — list engine
run "list-engine demo"            01-list-engine/icp_scorer.py
run "list-engine tests"           01-list-engine/test_icp_scorer.py

# 02 — send engine
run "send-engine demo (domains)"  02-send-engine/domain_calculator.py
run "send-engine demo (dns)"      02-send-engine/dns_validator.py
run "send-engine tests"           02-send-engine/test_send.py

# 03 — abm + paid engine
run "paid-controller demo"        03-abm-paid-engine/perf_controller.py
run "paid-controller tests"       03-abm-paid-engine/test_perf_controller.py

# 04 — revops engine
run "revops-engine demo"          04-revops-engine/lead_router.py
run "revops-engine tests"         04-revops-engine/test_lead_router.py

# 05 — brain integration
run "brain demo (outcome store)"  05-brain-integration/outcome_store.py
run "brain demo (policy tuner)"   05-brain-integration/policy_tuner.py
run "brain tests"                 05-brain-integration/test_brain.py

echo
echo "✅ smoke passed — all 5 pillars gated"
