# Local settings such as `GOOGLE_CLOUD_PROJECT` (see `.env.example`).
-include .env

TF_DEV := infra/env/dev
TF_ROOTS := $(TF_DEV)
TF_REGION ?= europe-west4
TF_STATE_BUCKET ?= $(GOOGLE_CLOUD_PROJECT)-imposter-tfstate
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
		terraform fmt -check -recursive infra && \
		for root in $(TF_ROOTS); do \
			terraform -chdir=$$root init -backend=false -input=false >/dev/null && \
			terraform -chdir=$$root validate -no-color >/dev/null || exit 1; \
		done; \
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
	@uv run pytest -m slow


.PHONY: tf-require-project
tf-require-project:
	@test -n "$(GOOGLE_CLOUD_PROJECT)" || { echo "Set GOOGLE_CLOUD_PROJECT in .env first"; exit 1; }


.PHONY: tf-state-bucket
tf-state-bucket: tf-require-project
	@if gcloud storage buckets describe gs://$(TF_STATE_BUCKET) --project=$(GOOGLE_CLOUD_PROJECT) >/dev/null 2>&1; then \
		echo "State bucket gs://$(TF_STATE_BUCKET) already exists"; \
	else \
		gcloud storage buckets create gs://$(TF_STATE_BUCKET) --project=$(GOOGLE_CLOUD_PROJECT) \
			--location=$(TF_REGION) --uniform-bucket-level-access --public-access-prevention && \
		gcloud storage buckets update gs://$(TF_STATE_BUCKET) --versioning --update-labels=app=imposter; \
	fi


.PHONY: tf-init
tf-init: tf-require-project
	@terraform -chdir=$(TF_DEV) init -input=false -reconfigure -backend-config="bucket=$(TF_STATE_BUCKET)"


.PHONY: tf-plan
tf-plan: tf-init
	@terraform -chdir=$(TF_DEV) plan


.PHONY: tf-apply
tf-apply: tf-init
	@terraform -chdir=$(TF_DEV) apply


.PHONY: install-hooks
install-hooks:
	@uv run pre-commit install
	@uv run pre-commit install --hook-type commit-msg
