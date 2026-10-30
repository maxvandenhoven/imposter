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


.PHONY: format
format:
	@uv run ruff format
	@uv run ruff check --fix --select I --output-format concise


.PHONY: lint
lint:
	@uv run ruff check --fix --output-format concise
	@uv run python scripts/tooling/check_comments.py src tests scripts
	@uv run python scripts/tooling/check_docstrings.py src


.PHONY: type
type:
	@uv run ty check


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


.PHONY: test
test:
	@uv run pytest -m "not slow" --cov --cov-report term-missing


.PHONY: test-slow
test-slow:
	@uv run $(if $(wildcard .env),--env-file .env) pytest -m slow


# Pass options with ARGS, for example `make play ARGS="--god --seed 7"`.
.PHONY: play
play:
	@uv run $(if $(wildcard .env),--env-file .env) imposter play $(ARGS)


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
