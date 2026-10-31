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
# default credentials mounted, as Cloud Run would run it. Under `sudo`, `HOME` is root's,
# so pass the file: `sudo make docker ADC_FILE=$HOME/.config/gcloud/...`.
DOCKER_IMAGE ?= imposter
ADC_FILE ?= $(HOME)/.config/gcloud/application_default_credentials.json

.PHONY: docker
docker:
	@test -f "$(ADC_FILE)" || { echo "No credentials at $(ADC_FILE): run gcloud auth application-default login or set ADC_FILE"; exit 1; }
	@docker build -t $(DOCKER_IMAGE) .
	@docker run --rm -it -p 8080:8080 \
		$(if $(wildcard .env),--env-file .env) \
		--mount type=bind,source=$(ADC_FILE),target=/tmp/adc.json,readonly \
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


# The image of the running service, so that plan and apply keep it. Without it Terraform
# would see an empty `image` and remove the service. Empty when nothing is deployed.
CURRENT_IMAGE = $(shell gcloud run services describe imposter --project=$(GOOGLE_CLOUD_PROJECT) \
	--region=$(TF_REGION) --format='value(spec.template.spec.containers[0].image)' 2>/dev/null)


.PHONY: tf-plan
tf-plan: tf-init
	@terraform -chdir=$(TF_DIR) plan $(if $(CURRENT_IMAGE),-var image=$(CURRENT_IMAGE))


.PHONY: tf-apply
tf-apply: tf-init
	@terraform -chdir=$(TF_DIR) apply $(if $(CURRENT_IMAGE),-var image=$(CURRENT_IMAGE))


# The Artifact Registry repository, the build account and the source bucket that
# `make build` needs, which the first deploy creates before anything can be built.
TF_BUILD_TARGETS := -target=google_artifact_registry_repository.imposter \
	-target=google_storage_bucket_iam_member.build_source \
	-target=google_artifact_registry_repository_iam_member.build_push \
	-target=google_project_iam_member.build_logs
IMAGE_REPO = $(TF_REGION)-docker.pkg.dev/$(GOOGLE_CLOUD_PROJECT)/imposter
IMAGE_TAG ?= $(shell git rev-parse --short HEAD)$(shell git diff --quiet HEAD || echo -dirty)
BUILD_SA = imposter-build@$(GOOGLE_CLOUD_PROJECT).iam.gserviceaccount.com


# Creates the registry and build account when they are missing.
.PHONY: tf-build-resources
tf-build-resources: tf-init
	@terraform -chdir=$(TF_DIR) apply -input=false -auto-approve $(TF_BUILD_TARGETS)


# Builds the image from the Dockerfile in Cloud Build and pushes it to Artifact Registry.
.PHONY: build
build: tf-build-resources
	@gcloud builds submit . --project=$(GOOGLE_CLOUD_PROJECT) --region=$(TF_REGION) \
		--config=cloudbuild.yaml --substitutions=_IMAGE=$(IMAGE_REPO)/app:$(IMAGE_TAG) \
		--service-account=projects/$(GOOGLE_CLOUD_PROJECT)/serviceAccounts/$(BUILD_SA) \
		--gcs-source-staging-dir=gs://$(GOOGLE_CLOUD_PROJECT)-imposter-build/source


# Builds, resolves the digest of the new image and deploys exactly that digest. Roll back
# with `make deploy-image IMAGE=<repo>/app@sha256:...` (see `docs/infrastructure.md`).
.PHONY: deploy
deploy: build
	@digest=$$(gcloud artifacts docker images describe $(IMAGE_REPO)/app:$(IMAGE_TAG) \
		--project=$(GOOGLE_CLOUD_PROJECT) --format='value(image_summary.digest)') && \
		test -n "$$digest" && \
		$(MAKE) --no-print-directory deploy-image IMAGE=$(IMAGE_REPO)/app@$$digest


.PHONY: deploy-image
deploy-image: tf-init
	@test -n "$(IMAGE)" || { echo "Set IMAGE=<repo>/app@sha256:..."; exit 1; }
	@terraform -chdir=$(TF_DIR) apply -var image=$(IMAGE)


# Prints the checklist for trying the deployed app behind IAP, with the links to use.
.PHONY: smoke
smoke:
	@url=$$(terraform -chdir=$(TF_DIR) output -raw service_url) && \
		test -n "$$url" || { echo "Nothing is deployed, run make deploy."; exit 1; }; \
	echo "Smoke test of $$url:"; \
	echo "1. Open the URL in a private window: IAP must ask for a Google login."; \
	echo "2. Sign in with an account that is not in iap_members: access must be refused."; \
	echo "3. Sign in with an allowed account, start a game with a mixed lineup and watch it end."; \
	echo "4. Export the game and import the file again."; \
	echo "5. Find the trace by the identity of the account:"; \
	echo "   https://console.cloud.google.com/traces/explorer?project=$(GOOGLE_CLOUD_PROJECT)"; \
	echo "   (filter on the attribute enduser.id, or on imposter.game.id from the game page)"


# Everything from scratch: the state bucket, the base APIs, the registry and build account,
# the image and the service. Prints the service URL. Run `make smoke` to try it.
.PHONY: up
up: tf-setup deploy
	@echo "Deployed: $$(terraform -chdir=$(TF_DIR) output -raw service_url)"
	@echo "IAP only lets in the principals in iap_members. Run make smoke to try it."


# Removes every resource Terraform manages, after a confirmation. The state bucket, the
# enabled APIs and the Model Garden terms stay, so `make up` works again right away.
.PHONY: down
down: tf-init
	@terraform -chdir=$(TF_DIR) destroy $(if $(CURRENT_IMAGE),-var image=$(CURRENT_IMAGE))


# Like `down`, and then also deletes the state bucket with every earlier state.
.PHONY: nuke
nuke: down
	@gcloud storage rm --recursive gs://$(TF_STATE_BUCKET) --project=$(GOOGLE_CLOUD_PROJECT)


.PHONY: install-hooks
install-hooks:
	@uv run pre-commit install
	@uv run pre-commit install --hook-type commit-msg
