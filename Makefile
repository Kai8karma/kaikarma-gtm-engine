.PHONY: test lint demo

test:
	bash tests/smoke.sh

lint:
	uvx ruff check .

demo:
	python3 01-list-engine/icp_scorer.py
	python3 02-send-engine/domain_calculator.py
	python3 02-send-engine/dns_validator.py
	python3 03-abm-paid-engine/perf_controller.py
	python3 04-revops-engine/lead_router.py
	python3 05-brain-integration/policy_tuner.py
