PYTHON ?= python
VENV_PYTHON := .venv/bin/python
NODE_BIN := $(CURDIR)/.tools/node/bin

.PHONY: setup venv node frontend-install download-interaction-mvp preprocess-ddxplus preprocess-guidance2 preprocess-temporal preprocess-interaction-mvp validate-temporal-sources preprocess-all test validate api web demo db-up db-down migrate

setup: venv node frontend-install

venv:
	@test -x $(VENV_PYTHON) || $(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip setuptools wheel
	$(VENV_PYTHON) -m pip install -e '.[dev]'

node:
	bash scripts/bootstrap_node.sh

frontend-install: node
	cd frontend && PATH="$(NODE_BIN):$$PATH" npm ci

download-interaction-mvp:
	bash scripts/download_interaction_mvp.sh

preprocess-ddxplus:
	$(VENV_PYTHON) -m etl.run_pipeline

preprocess-guidance2:
	$(VENV_PYTHON) -m etl.build_guidance2_cases

validate-temporal-sources:
	$(VENV_PYTHON) -m etl.validate_mcmed_sources
	$(VENV_PYTHON) -m etl.validate_mimic_sources
	$(VENV_PYTHON) -m etl.validate_eicu_sources

preprocess-temporal:
	$(VENV_PYTHON) -m etl.build_temporal_mvp

preprocess-interaction-mvp:
	$(VENV_PYTHON) -m etl.build_interaction_mvp

preprocess-all: preprocess-ddxplus preprocess-guidance2 preprocess-temporal preprocess-interaction-mvp

test:
	$(VENV_PYTHON) -m pytest -q

validate: test
	cd frontend && PATH="$(NODE_BIN):$$PATH" npm run lint
	cd frontend && PATH="$(NODE_BIN):$$PATH" npm run build

api:
	ARENA_REPOSITORY=sqlite DATABASE_URL=sqlite:///data/clincforestbench.db $(VENV_PYTHON) -m uvicorn backend.app.main:app --reload --port 8000

web:
	cd frontend && PATH="$(NODE_BIN):$$PATH" npm run dev

demo:
	$(VENV_PYTHON) scripts/demo_arena.py

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	$(VENV_PYTHON) -m alembic upgrade head
