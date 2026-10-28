PYTHON ?= python
VENV_PYTHON := .venv/bin/python
NODE_BIN := $(CURDIR)/.tools/node/bin

.PHONY: setup venv node frontend-install download-data download-interaction-mvp preprocess-ddxplus preprocess-workflows preprocess-ehr-sources preprocess-evidence preprocess-interaction-mvp translate-cases validate-sources preprocess-all test validate audit-encounters start api web demo db-up db-down migrate

setup: venv node frontend-install

venv:
	@test -x $(VENV_PYTHON) || $(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip setuptools wheel
	$(VENV_PYTHON) -m pip install -e '.[dev]'

node:
	bash scripts/dev/bootstrap_node.sh

frontend-install: node
	cd frontend && PATH="$(NODE_BIN):$$PATH" npm ci

download-data:
	bash download_data.sh

download-interaction-mvp:
	bash scripts/data/download_interaction_mvp.sh

preprocess-ddxplus:
	$(VENV_PYTHON) -m etl.run_pipeline

preprocess-workflows:
	$(VENV_PYTHON) -m etl.build_workflow_cases

validate-sources:
	$(VENV_PYTHON) -m etl.validate_mcmed_sources
	$(VENV_PYTHON) -m etl.validate_mimic_sources
	$(VENV_PYTHON) -m etl.validate_eicu_sources

preprocess-ehr-sources:
	$(VENV_PYTHON) -m etl.build_ehr_sources

preprocess-interaction-mvp:
	$(VENV_PYTHON) -m etl.build_interaction_mvp
	$(VENV_PYTHON) -m etl.build_evidence_cases

preprocess-evidence:
	$(VENV_PYTHON) -m etl.build_evidence_cases


translate-cases:
	$(VENV_PYTHON) tools/build_case_translations.py

preprocess-all: preprocess-ddxplus preprocess-workflows preprocess-ehr-sources preprocess-interaction-mvp

test:
	$(VENV_PYTHON) -m pytest -q

audit-encounters:
	$(VENV_PYTHON) -m analysis.audit_encounter_mapping

validate: test
	cd frontend && PATH="$(NODE_BIN):$$PATH" npm run lint
	cd frontend && PATH="$(NODE_BIN):$$PATH" npm run build

start:
	bash scripts/dev/start_app.sh

api:
	ARENA_REPOSITORY=sqlite DATABASE_URL=sqlite:///data/clincforestbench.db $(VENV_PYTHON) -m uvicorn backend.app.main:app --reload --port 8000

web:
	cd frontend && PATH="$(NODE_BIN):$$PATH" npm run dev

demo:
	$(VENV_PYTHON) scripts/demo/demo_arena.py

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	$(VENV_PYTHON) -m alembic upgrade head
