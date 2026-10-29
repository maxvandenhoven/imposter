# Infrastructure

## GCP basics (for orientation)

- **Organisation**: the company root. **Folders** group projects; the sandbox is a folder
  with its own policies (for example allowed regions or services).
- **Project**: the unit that holds resources, enabled APIs, IAM and quotas. The app lives
  in an **existing sandbox project** that the owner already has and that other work
  shares. Terraform does not create or own the project.
- **ADC** (Application Default Credentials): what client libraries and Terraform use
  locally after `gcloud auth application-default login`; on Cloud Run, the service
  account attached to the service.

### Organising resources in a shared project

GCP has no resource groups like Azure: the project is the smallest container, and IAM,
quotas, APIs and billing are per project. Within one project the app's resources are kept
apart by:

- **Labels** `app = "imposter"`, `env = "dev"` on every resource that supports them, set
  once through the providers' `default_labels`. Labels are filterable in the console
  lists, in Cloud Asset Inventory (`gcloud asset search-all-resources
  --query="labels.app=imposter"`) and in billing reports, so the app's cost can be split
  from the rest of the project.
- **Names** starting with `imposter` (service, service account, repository, bucket).
- **Terraform state** as the authoritative list of what the app owns: `terraform state
  list` and `terraform destroy` touch only those resources. APIs are never disabled on
  destroy (`disable_on_destroy = false`), because other work may use them.

Considered and not used: **Resource Manager tags** (org-level tag keys that need tag admin
rights the sandbox likely lacks; useful for IAM conditions and org policies, not needed
here) and **App Hub applications** (group services and workloads into a logical
application with topology and monitoring; more setup than a one-service demo needs).

## Manual prerequisites (once)

The step-by-step guide for the owner is [`docs/setup.md`](../setup.md); this is the
summary.

1. Install the `gcloud` CLI and Terraform (>= 1.9).
2. `gcloud auth login` and `gcloud auth application-default login` with the org account.
3. Point local tools at the sandbox project: `gcloud config set project <project id>`,
   `gcloud auth application-default set-quota-project <project id>`, and
   `GOOGLE_CLOUD_PROJECT` in `.env`.
4. Create the Terraform state bucket once: `make tf-state-bucket`.
5. In the Model Garden console, open each Claude model and chosen open model and click
   Enable / accept the terms. Request quota increases if the defaults are too low (Vertex
   AI quotas page).

## Terraform layout

```
infra/
└─ env/dev/            # backend "gcs" { prefix = "env/dev" }, bucket passed at init
   ├─ versions.tf      # terraform and provider versions, backend
   ├─ providers.tf     # google + google-beta, billed to the project, default labels
   ├─ apis.tf          # google_project_service for the APIs below
   ├─ iam.tf           # runtime service account + roles, Cloud Build SA roles
   ├─ registry.tf      # Artifact Registry docker repo (europe-west4)
   ├─ run.tf           # Cloud Run v2 service with IAP
   ├─ iap.tf           # IAP access for the allowed principal
   ├─ budget.tf        # billing budget with email alerts
   ├─ variables.tf     # project_id, region, labels, image (digest), iap_members, ...
   └─ terraform.tfvars.example
```

Providers `google` and `google-beta` (IAP on Cloud Run may need beta), versions pinned
(`~> 8.9`), with `.terraform.lock.hcl` committed (Linux and macOS hashes).

There is no Terraform bootstrap root: the project exists already, and the only thing
needed before Terraform can run is its state bucket. `make tf-state-bucket` creates
`<project id>-imposter-tfstate` in `europe-west4` with `gcloud` (versioned, uniform
access, public access prevention, label `app=imposter`); it skips an existing bucket. A
backend block cannot use variables, so the backend leaves the bucket out and `make
tf-init` passes it with `-backend-config="bucket=..."` (override with `TF_STATE_BUCKET`).

The project ID has one source, `GOOGLE_CLOUD_PROJECT` in `.env`, which the Makefile
includes and passes to Terraform as `TF_VAR_project_id`. The providers set
`user_project_override` and `billing_project` so API calls count against the project
itself, not the quota project of the caller's credentials.

### APIs

`run`, `artifactregistry`, `cloudbuild`, `aiplatform`, `iap`, `cloudtrace`, `logging`,
`telemetry`, `iam`, `cloudresourcemanager`, `billingbudgets`, `serviceusage`.

### Runtime service account `imposter-run`

Least privilege: `roles/aiplatform.user`, `roles/cloudtrace.agent`,
`roles/logging.logWriter`, `roles/telemetry.tracesWriter` (if the OTLP telemetry API
requires it; verify). No owner or editor roles.

### Cloud Run service `imposter`

- Region `europe-west4`, image by digest from Artifact Registry.
- `min_instance_count = 0`, `max_instance_count = 1`, request-based billing (CPU only
  during requests), `timeout = 3600s`, concurrency 80 (SSE connections are cheap).
- 1 vCPU, 1 GiB memory to start.
- Env: `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, `GOOGLE_CLOUD_PROJECT`,
  `GOOGLE_CLOUD_LOCATION=global`, the telemetry content capture variables from
  `observability.md`, `IMPOSTER_*` settings.
- Ingress all, **IAP enabled directly on the Cloud Run service** (no load balancer);
  invoker access only through IAP. Allowed principals (`user:...` or `group:...`) get
  `roles/iap.httpsResourceAccessor`. The IAP service agent gets `roles/run.invoker`.
- Check the current Terraform support for Cloud Run IAP (`iap_enabled` on
  `google_cloud_run_v2_service`, possibly beta) and the OAuth brand/consent screen
  requirements for an internal org app when implementing.

### Budget

`google_billing_budget` on the project, default €20/month, alerts at 50/90/100% to the
billing admins (and an email channel if set). It does not cap spending; it warns. The
project is shared, so filter the budget on the label `app=imposter` (budget filters
support labels) to count only the app's spend. Vertex AI model calls carry no resource
labels, so check whether request labels or a budget filtered on the Vertex AI service is
the better filter when implementing.

## Build and deploy

- `Dockerfile` (multi-stage):
  1. `css`: download the pinned standalone Tailwind CLI binary, compile
     `web/input.css` → `web/tailwind.css`.
  2. `app`: `python:3.13-slim` with uv, `uv sync --frozen --no-dev`, copy `src/` and the
     compiled CSS, run `uvicorn imposter.api.app:app --host 0.0.0.0 --port $PORT`.
- `make build`: `gcloud builds submit --tag <region>-docker.pkg.dev/<project>/imposter/app:<git sha>`
  (builds in GCP, no local Docker needed).
- `make deploy`: build, resolve the image digest, then
  `terraform -chdir=infra/env/dev apply -var image=<repo>@sha256:...`.
- Rollback: re-apply with an earlier digest.
- `make tf-state-bucket` once, then `make tf-plan` / `make tf-apply` for infra-only
  changes in `env/dev` (both run `make tf-init` first).
- `.env.example` documents the local variables; `make dev` uses ADC and the same project.
