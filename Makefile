# Local settings such as `GOOGLE_CLOUD_PROJECT` (see `.env.example`).
-include .env

TF_DIR := infra
TF_REGION ?= europe-west4
TF_STATE_BUCKET ?= $(GOOGLE_CLOUD_PROJECT)-imposter-tfstate
# Needed before Terraform can run: it bills its own API calls to the project.
TF_BASE_APIS := serviceusage.googleapis.com cloudresourcemanager.googleapis.com storage.googleapis.com
export TF_VAR_project_id := $(GOOGLE_CLOUD_PROJECT)


.PHONY: sync
sync:
	@uv sync --all-groups
	@cd frontend && npm ci --silent


# Installs the frontend dependencies on first use and whenever the lockfile changes.
frontend/node_modules: frontend/package-lock.json
	@cd frontend && npm ci --silent
	@touch frontend/node_modules


.PHONY: format format-python format-frontend
format: format-python format-frontend

format-python:
	@uv run ruff format
	@uv run ruff check --fix --select I --output-format concise

format-frontend: frontend/node_modules
	@cd frontend && npm run --silent format


.PHONY: lint lint-python lint-frontend
lint: lint-python lint-frontend

lint-python:
	@uv run ruff check --fix --output-format concise
	@uv run python scripts/tooling/check_comments.py src tests scripts
	@uv run python scripts/tooling/check_docstrings.py src

lint-frontend: frontend/node_modules
	@cd frontend && npm run --silent lint:fix


.PHONY: type type-python type-frontend
type: type-python type-frontend

type-python:
	@uv run ty check

type-frontend: frontend/node_modules
	@cd frontend && npm run --silent typecheck


.PHONY: tf-check
tf-check:
	@if command -v terraform >/dev/null 2>&1; then \
		terraform fmt -check -recursive $(TF_DIR) && \
		terraform -chdir=$(TF_DIR) init -backend=false -input=false >/dev/null && \
		terraform -chdir=$(TF_DIR) validate -no-color >/dev/null; \
	else \
		echo "terraform not found, skipping Terraform checks"; \
	fi


.PHONY: check
check: format lint type tf-check


.PHONY: test test-python test-frontend
test: test-python test-frontend

test-python:
	@uv run pytest -m "not slow" --cov --cov-report term-missing

test-frontend: frontend/node_modules
	@cd frontend && npm run --silent test


.PHONY: test-slow
test-slow:
	@uv run $(if $(wildcard .env),--env-file .env) pytest -m slow


# Pass options with ARGS, for example `make play ARGS="--god --seed 7"`.
.PHONY: play
play:
	@uv run $(if $(wildcard .env),--env-file .env) imposter play $(ARGS)


# Serves the game API on port 8000, restarted on code changes, and the frontend with hot
# reload on port 5173, which forwards the API paths to it. The Vite server is stopped
# when the API server exits. Options of the API server go in ARGS.
.PHONY: dev
dev: frontend/node_modules
	@(cd frontend && exec node_modules/.bin/vite) & trap "kill $$!" EXIT; \
		uv run $(if $(wildcard .env),--env-file .env) imposter serve --reload $(ARGS)


# Builds the frontend into `frontend/dist`, which the API app serves at `/`.
.PHONY: frontend
frontend: frontend/node_modules
	@cd frontend && npm run --silent build


# Exports the OpenAPI schema from the app, without a server, and generates the types.
.PHONY: api-client
api-client: frontend/node_modules
	@uv run imposter openapi --output frontend/openapi.json
	@cd frontend && npm run --silent api-client
	@rm frontend/openapi.json


# Builds the image and plays it on port 8080, with `.env` and the gcloud application
# default credentials mounted, as Cloud Run would run it.
DOCKER_IMAGE ?= imposter
ADC_FILE ?= $(HOME)/.config/gcloud/application_default_credentials.json

.PHONY: docker
docker:
	@docker build -t $(DOCKER_IMAGE) .
	@docker run --rm -it -p 8080:8080 \
		$(if $(wildcard .env),--env-file .env) \
		-v $(ADC_FILE):/tmp/adc.json:ro \
		-e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json --user $$(id -u):$$(id -g) \
		$(DOCKER_IMAGE)


.PHONY: adk-web
adk-web:
	@uv run $(if $(wildcard .env),--env-file .env) adk web --otel_to_cloud src


.PHONY: tf-require-project
tf-require-project:
	@test -n "$(GOOGLE_CLOUD_PROJECT)" || { echo "Set GOOGLE_CLOUD_PROJECT in .env first"; exit 1; }


.PHONY: tf-setup
tf-setup: tf-require-project
	@gcloud services enable $(TF_BASE_APIS) --project=$(GOOGLE_CLOUD_PROJECT)
	@if gcloud storage buckets describe gs://$(TF_STATE_BUCKET) --project=$(GOOGLE_CLOUD_PROJECT) >/dev/null 2>&1; then \
		echo "State bucket gs://$(TF_STATE_BUCKET) already exists"; \
	else \
		gcloud storage buckets create gs://$(TF_STATE_BUCKET) --project=$(GOOGLE_CLOUD_PROJECT) \
			--location=$(TF_REGION) --uniform-bucket-level-access --public-access-prevention && \
		gcloud storage buckets update gs://$(TF_STATE_BUCKET) --versioning --update-labels=app=imposter; \
	fi


.PHONY: tf-init
tf-init: tf-require-project
	@terraform -chdir=$(TF_DIR) init -input=false -reconfigure -backend-config="bucket=$(TF_STATE_BUCKET)"


.PHONY: tf-plan
tf-plan: tf-init
	@terraform -chdir=$(TF_DIR) plan


.PHONY: tf-apply
tf-apply: tf-init
	@terraform -chdir=$(TF_DIR) apply


.PHONY: install-hooks
install-hooks:
	@uv run pre-commit install
	@uv run pre-commit install --hook-type commit-msg
