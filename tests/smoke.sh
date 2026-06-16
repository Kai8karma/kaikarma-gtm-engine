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
run "rsa-builder demo"            03-abm-paid-engine/rsa_builder.py
run "rsa-builder tests"           03-abm-paid-engine/test_rsa.py
run "executor demo (dry-run)"     03-abm-paid-engine/executor.py
run "executor tests"              03-abm-paid-engine/test_executor.py
run "google-ads executor demo"    03-abm-paid-engine/google_ads_executor.py
run "google-ads executor tests"   03-abm-paid-engine/test_google_ads_executor.py
run "meta-ads executor demo"      03-abm-paid-engine/meta_ads_executor.py
run "meta-ads executor tests"     03-abm-paid-engine/test_meta_ads_executor.py
run "linkedin-ads executor demo"  03-abm-paid-engine/linkedin_ads_executor.py
run "linkedin-ads executor tests" 03-abm-paid-engine/test_linkedin_ads_executor.py
run "google reporting demo"       03-abm-paid-engine/google_ads_reporting.py
run "google reporting tests"      03-abm-paid-engine/test_google_ads_reporting.py
run "meta reporting demo"         03-abm-paid-engine/meta_ads_reporting.py
run "meta reporting tests"        03-abm-paid-engine/test_meta_ads_reporting.py
run "linkedin reporting demo"     03-abm-paid-engine/linkedin_ads_reporting.py
run "linkedin reporting tests"    03-abm-paid-engine/test_linkedin_ads_reporting.py

# 04 — revops engine
run "revops-engine demo"          04-revops-engine/lead_router.py
run "revops-engine tests"         04-revops-engine/test_lead_router.py

# 05 — brain integration
run "brain demo (outcome store)"  05-brain-integration/outcome_store.py
run "brain demo (policy tuner)"   05-brain-integration/policy_tuner.py
run "brain tests"                 05-brain-integration/test_brain.py

# 02 — send engine: copy layer
run "copy demo (frameworks)"      02-send-engine/framework_registry.py
run "copy tests"                  02-send-engine/test_copy.py

# 04 — revops engine: lifecycle / DQS / SLA
run "revops lifecycle demo"       04-revops-engine/stage_machine.py
run "revops dqs demo"             04-revops-engine/dqs_scorer.py
run "revops sla demo"             04-revops-engine/sla_enforcer.py
run "revops extended tests"       04-revops-engine/test_revops_extended.py

# engagements — runnable template config
run "engagement config demo"      engagements/_TEMPLATE/config_loader.py
run "engagement config tests"     engagements/_TEMPLATE/test_config.py

# 03 / 04 → brain outcome logging
run "perf-outcomes demo"          03-abm-paid-engine/perf_outcomes.py
run "perf-outcomes tests"         03-abm-paid-engine/test_perf_outcomes.py
run "routing-outcomes demo"       04-revops-engine/routing_outcomes.py
run "routing-outcomes tests"      04-revops-engine/test_routing_outcomes.py

# cross-pillar — the end-to-end learning loop (the moat)
run "closed-loop demo"            examples/closed_loop.py
run "closed-loop tests"           examples/test_closed_loop.py

# cross-pillar — persistent multi-session warm-start
run "persistent-loop demo"        examples/persistent_loop.py
run "persistent-loop tests"       examples/test_persistent_loop.py

# cross-pillar — list → send bridge
run "list-to-sequences demo"      examples/list_to_sequences.py
run "list-to-sequences tests"     examples/test_list_to_sequences.py

# evals — does the learning loop actually work? (pre-registered backtest)
run "learning-loop backtest"      evals/learning_loop_eval.py
run "learning-loop guard tests"   evals/test_learning_loop.py

# API integrations — original, injected-client channel adapters (zero egress in tests)
run "apollo enrichment demo"      01-list-engine/apollo_enrichment.py
run "apollo enrichment tests"     01-list-engine/test_apollo_enrichment.py
run "email sequencer demo"        02-send-engine/sequencer.py
run "email sequencer tests"       02-send-engine/test_sequencer.py
run "ads campaign builder demo"   03-abm-paid-engine/ads_campaigns.py
run "ads campaign builder tests"  03-abm-paid-engine/test_ads_campaigns.py
run "hubspot crm demo"            04-revops-engine/hubspot_crm.py
run "hubspot crm tests"           04-revops-engine/test_hubspot_crm.py

echo
echo "✅ smoke passed — 5 pillars + full read/write API layer (ads · CRM · enrichment · email) + loops + backtested learning gated"
