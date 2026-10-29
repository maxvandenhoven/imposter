TF_BOOTSTRAP := infra/bootstrap
TF_DEV := infra/env/dev
TF_ROOTS := $(TF_BOOTSTRAP) $(TF_DEV)
# Read from the bootstrap state on use; set it explicitly to skip that lookup.
TF_STATE_BUCKET ?= $(shell terraform -chdir=$(TF_BOOTSTRAP) output -raw state_bucket 2>/dev/null)


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


.PHONY: tf-bootstrap
tf-bootstrap:
	@terraform -chdir=$(TF_BOOTSTRAP) init -input=false
	@terraform -chdir=$(TF_BOOTSTRAP) apply


.PHONY: tf-init
tf-init:
	@test -n "$(TF_STATE_BUCKET)" || { echo "No state bucket: run make tf-bootstrap first or set TF_STATE_BUCKET"; exit 1; }
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
