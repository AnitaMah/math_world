# Обгортка для Linux/CI навколо tools/frontend/run_tests.py (фаза 19, FE-0618).
# На Windows (де make зазвичай нема) — виклич run_tests.py напряму, див. docs/frontend/README.md.

PYTHON ?= python3

.PHONY: frontend-test frontend-unit frontend-baseline

frontend-unit:
	$(PYTHON) tools/frontend/run_tests.py --no-visual

frontend-test:
	$(PYTHON) tools/frontend/run_tests.py

frontend-baseline:
	$(PYTHON) tools/frontend/run_tests.py --baseline
