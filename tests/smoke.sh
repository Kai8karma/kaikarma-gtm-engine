#!/usr/bin/env bash
# Regression guard. Nothing ships unless this exits 0.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$(command -v python3 || command -v python)"

echo "▶ list-engine demo"
"$PY" 01-list-engine/icp_scorer.py

echo
echo "▶ list-engine tests"
"$PY" 01-list-engine/test_icp_scorer.py

echo
echo "▶ paid-controller demo"
"$PY" 03-abm-paid-engine/perf_controller.py

echo
echo "▶ paid-controller tests"
"$PY" 03-abm-paid-engine/test_perf_controller.py

echo
echo "✅ smoke passed"
