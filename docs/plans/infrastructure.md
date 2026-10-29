# Infrastructure

## GCP basics (for orientation)

- **Organisation**: the company root. **Folders** group projects; the sandbox is a folder
  with its own policies (for example allowed regions or services).
- **Project**: the unit that holds resources, enabled APIs, IAM and quotas. Everything in
  this repo lives in one project.
- **Billing account**: pays for projects linked to it.
- **ADC** (Application Default Credentials): what client libraries and Terraform use
  locally after `gcloud auth application-default login`; on Cloud Run, the service
  account attached to the service.

## Manual prerequisites (once)

1. Install the `gcloud` CLI and Terraform (>= 1.9).
2. `gcloud auth login` and `gcloud auth application-default login` with the org account.
3. Find the sandbox folder ID and billing account ID:
   `gcloud resource-manager folders list --organization <org id>` (or from the console) and
   `gcloud billing accounts list`.
4. After `infra/bootstrap` ran: in the Model Garden console, open each Claude model and
   chosen open model and click Enable / accept the terms. Request quota increases if the
   defaults are too low (Vertex AI quotas page).
5. Set the quota project for ADC: `gcloud auth application-default set-quota-project
   <project id>`.

## Terraform layout

```
infra/
├─ bootstrap/          # local state (terraform.tfstate gitignored; keep a copy safe)
│  ├─ main.tf          # google_project, billing link, state bucket (versioned, EU)
│  ├─ variables.tf     # project_id, folder_id, billing_account, region
│  └─ outputs.tf       # project_id, state_bucket
└─ env/dev/            # backend "gcs" { bucket = <state bucket>, prefix = "env/dev" }
   ├─ apis.tf          # google_project_service for the APIs below
   ├─ iam.tf           # runtime service account + roles, Cloud Build SA roles
   ├─ registry.tf      # Artifact Registry docker repo (europe-west4)
   ├─ run.tf           # Cloud Run v2 service with IAP
   ├─ iap.tf           # IAP access for the allowed principal
   ├─ budget.tf        # billing budget with email alerts
   ├─ variables.tf     # project_id, region, image (digest), iap_members, budget_amount
   └─ terraform.tfvars.example
```

Providers `google` and `google-beta` (IAP on Cloud Run may need beta), versions pinned.

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
billing admins (and an email channel if set). It does not cap spending; it warns.

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
- `make tf-plan` / `make tf-apply` for infra-only changes.
- `.env.example` documents the local variables; `make dev` uses ADC and the same project.
