# GCP infrastructure

What the app creates in GCP, and why. Setup steps are in [`setup.md`](setup.md). The
design and decisions behind it are in [`plans/infrastructure.md`](plans/infrastructure.md)
and D17 in [`plans/README.md`](plans/README.md). Keep this page in sync with `infra/`:
every change to the Terraform updates the tables below in the same PR.

## Where it lives

Everything goes into the owner's **existing sandbox project**, which other work shares.
The app does not create or own the project, its billing link or its IAM policy as a whole.
GCP has no resource groups, so the app's resources are kept apart by:

| Mechanism | How |
|---|---|
| Label `app=imposter` | Set on every resource that supports labels, through the providers' `default_labels` (`infra/providers.tf`). Filter on it in the console, in billing reports and with `gcloud asset search-all-resources --query="labels.app=imposter"`. |
| Name prefix `imposter` | Every resource name starts with it. |
| Terraform state | `terraform -chdir=infra state list` is the exact list of what the app manages. `terraform destroy` touches nothing else. |

Region: app resources in `europe-west4` (D31). Models are called at the Vertex AI `global`
location, which is not a resource.

## How it connects

Three flows use the infrastructure: playing a game, deploying a new version, and running
the app or Terraform locally. Parts marked *(WP n)* are planned and not created yet.

### Playing a game (deployed)

```mermaid
flowchart LR
  user(["Browser, org account"]) -->|HTTPS| iap["IAP (WP 13)"]
  iap -->|"signed identity header"| run["Cloud Run imposter (WP 12)<br/>runs as imposter-run"]
  run -->|"Gemini: google-genai<br/>Claude, open: LiteLLM"| vertex["Vertex AI<br/>location global"]
  run -->|"OTLP spans"| trace["Cloud Trace (WP 07)"]
  run -->|"prompt and completion events"| logging["Cloud Logging (WP 07)"]
  logging -.->|"trace ID"| trace
```

1. The browser opens the Cloud Run URL. **IAP** checks the org Google login and lets only
   the allowed principals through (`roles/iap.httpsResourceAccessor`). IAP itself calls
   Cloud Run with `roles/run.invoker`, nobody else can. IAP passes the user's identity in a
   header, which the app puts on the root span (`enduser.id`).
2. **Cloud Run** serves the static page and the API, and streams the game over SSE. A
   game runs while that request is open, which is why the timeout is 3600 s.
3. For each turn the app calls **Vertex AI** as the service account `imposter-run`
   (`roles/aiplatform.user`). There are no API keys: the Google client libraries take the
   service account credentials from the Cloud Run metadata server. Gemini is called
   natively, Claude and open models through LiteLLM, all at `global` unless the model
   catalog sets a regional location.
4. **OpenTelemetry** exports spans to **Cloud Trace** through the telemetry API
   (`roles/cloudtrace.agent`, `roles/telemetry.tracesWriter`) and writes prompts and
   completions to **Cloud Logging** (`roles/logging.logWriter`), linked by trace ID.

### Deploying (`make deploy`, WP 12)

```mermaid
flowchart LR
  dev(["Laptop, owner ADC"]) -->|"gcloud builds submit"| build["Cloud Build"]
  build -->|"push image"| ar["Artifact Registry imposter"]
  dev -->|"terraform apply -var image=...@sha256"| tf["Terraform"]
  tf <-->|"state"| bucket[("State bucket")]
  tf -->|"new revision"| run["Cloud Run imposter"]
  run -.->|"pulls image by digest"| ar
```

Cloud Build builds the image in GCP from the local source and pushes it to Artifact
Registry. Terraform then points the Cloud Run service at that exact image digest, so a
rollback is an apply with an earlier digest. Terraform reads and writes its state in the
state bucket on every run.

### Local development

```mermaid
flowchart LR
  laptop(["Laptop"]) -->|"ADC, quota project = sandbox"| vertex["Vertex AI global"]
  laptop -->|"ADC"| trace["Cloud Trace / Logging (WP 07)"]
  laptop -->|"make tf-setup (gcloud): base APIs, bucket"| project
  laptop -->|"make tf-plan / tf-apply"| tf["Terraform"] -->|"enables APIs, creates resources"| project["Sandbox project"]
  tf <--> bucket[("State bucket")]
```

Locally everything runs as the owner: the app, `scripts/check_models.py` and Terraform
use ADC from `gcloud auth application-default login`. The ADC quota project and
`GOOGLE_CLOUD_PROJECT` in `.env` point at the sandbox project, so calls are billed there.
Terraform additionally bills its own API calls to the project (`user_project_override`). That
is why `make tf-setup` enables the Service Usage API with `gcloud` before the first
Terraform run.

## Created outside Terraform

| Resource | Created by | Why |
|---|---|---|
| APIs `serviceusage`, `cloudresourcemanager`, `storage` | `make tf-setup` (`gcloud services enable`) | Terraform bills its API calls to the project (`user_project_override`), which needs the Service Usage API enabled in the project first. Terraform cannot enable it for itself. The first two are also listed in `infra/apis.tf`. |
| GCS bucket `<project id>-imposter-tfstate` (`europe-west4`, label `app=imposter`) | `make tf-setup` (`gcloud`) | Holds the Terraform state under the prefix `imposter`, so it survives a lost laptop and can be shared. Terraform needs the bucket before it can run, so it cannot create it itself. Versioning keeps every earlier state for recovery, and uniform access and public access prevention keep it private. |
| Model enablement for Claude and open models | Owner, in the Model Garden console | Partner and open models need their terms accepted once per project, and there is no API for it. |
| Quota increases | Owner, on the Quotas page | Default per-model quotas can be too low for 8 players. |

## Managed by Terraform (`infra/`)

### Enabled APIs (`infra/apis.tf`)

Enabling an API costs nothing, only usage is billed. In a shared project some are likely
enabled already. Terraform never disables them, not even on destroy
(`disable_on_destroy = false`), because other work may depend on them.

| API | Why | Used from |
|---|---|---|
| `aiplatform.googleapis.com` | Vertex AI: Gemini, Claude and open models for players, judge and word generator | WP 02 (model check), WP 04 |
| `serviceusage.googleapis.com` | Lets Terraform enable APIs. Also needed to bill API calls to the project (`user_project_override`). Enabled first by `make tf-setup` | WP 02 |
| `cloudresourcemanager.googleapis.com` | Lets Terraform read the project and manage its IAM bindings. Enabled first by `make tf-setup` | WP 02, WP 12 |
| `iam.googleapis.com` | Runtime service account `imposter-run` | WP 12 |
| `artifactregistry.googleapis.com` | Docker repository for the app image | WP 12 |
| `cloudbuild.googleapis.com` | Builds the image in GCP (`make build`), no local Docker | WP 12 |
| `run.googleapis.com` | Cloud Run service that hosts API, UI and SSE | WP 12 |
| `billingbudgets.googleapis.com` | Budget with email alerts | WP 12 |
| `iap.googleapis.com` | Identity-Aware Proxy in front of Cloud Run (org Google login) | WP 13 |
| `cloudtrace.googleapis.com` | One trace per game (game → phase → turn spans) | WP 07 |
| `telemetry.googleapis.com` | OTLP endpoint for OpenTelemetry traces | WP 07 |
| `logging.googleapis.com` | Prompts and completions as log events linked to the trace | WP 07 |

### Provider settings (`infra/providers.tf`)

| Setting | Why |
|---|---|
| `default_labels = { app = "imposter" }` | Makes every labelled resource findable in the shared project (variable `labels`). |
| `billing_project` + `user_project_override = true` | API calls count against this project's quota and billing, not the quota project of whoever runs Terraform. |
| `google` and `google-beta` pinned to `~> 8.9`, lock file committed | Reproducible plans. Beta is there for IAP on Cloud Run if it needs it. |

### Planned resources

Not created yet. This table moves up into the sections above when they land.

| Resource | Why | WP |
|---|---|---|
| Service account `imposter-run` with `roles/aiplatform.user`, `roles/cloudtrace.agent`, `roles/logging.logWriter` (and `roles/telemetry.tracesWriter` if needed) | Least-privilege identity of the Cloud Run service, with no owner or editor roles | 12 |
| Artifact Registry repository `imposter` (`europe-west4`) | Stores the app images. Deploys pin an image digest | 12 |
| Cloud Run service `imposter` (min 0, max 1 instance, request-based billing, 3600 s timeout) | Hosts the app and scales to zero (D11, D14) | 12 |
| Billing budget, filtered on `app=imposter` | Warns at 50/90/100% of the monthly amount but does not cap spend (D29) | 12 |
| IAP on the Cloud Run service, `roles/iap.httpsResourceAccessor` for the allowed principals | Only the owner (or a group) can reach the app (D12) | 13 |

## Costs (excluding model tokens)

An estimate for demo use: about 50 games a month of about 10 minutes each, about 10
deploys a month, and Cloud Run at 1 vCPU and 1 GiB. Prices are USD list prices for
`europe-west4` as known in October 2026, not checked against the live pricing pages, so
confirm them with the [pricing calculator](https://cloud.google.com/products/calculator)
before relying on them.

Several free tiers are per billing account, not per project. The sandbox billing account
is shared with other work, so others may already use them up. The last column shows the
cost when no free tier is left.

| Item | What drives the cost | Free tier per month | Cost after the free tier |
|---|---|---|---|
| Enabled APIs | Nothing, enabling is free | Not needed | $0 |
| State bucket | A few KB of state and its earlier versions | 5 GB in US regions only | Below $0.01 a month |
| Cloud Run (WP 12) | CPU and memory while a request is open. A 10 minute game uses about 600 vCPU-seconds and 600 GiB-seconds | 180,000 vCPU-seconds, 360,000 GiB-seconds and 2 million requests per billing account, about 300 games | About $0.016 per game ($0.000024 per vCPU-second, $0.0000025 per GiB-second), so about $0.80 for 50 games |
| Artifact Registry (WP 12) | Stored images, about 0.3 GB each. Keeping 5 is about 1.5 GB | 0.5 GB | About $0.10 per GB-month, so $0.10 to $0.20 a month |
| Cloud Build (WP 12) | About 3 build minutes per deploy | 2,500 build minutes | About $0.003 per minute, so about $0.10 for 10 deploys |
| Cloud Trace (WP 07) | A few hundred spans per game | 2.5 million spans per billing account | $0.20 per million spans, below $0.01 |
| Cloud Logging (WP 07) | A few MB of prompts and completions per game | 50 GiB per project, shared with the rest of the project | $0.50 per GiB, below $0.10 |
| IAP (WP 13), budget (WP 12) | Nothing | Not needed | $0 |
| Network egress | Page loads and the SSE stream, a few MB | Small free amount | Below $0.01 |

What this adds up to:

- **Idle:** $0.10 to $0.20 a month, mostly stored images. Cloud Run costs nothing while
  scaled to zero.
- **Demo use (50 games, 10 deploys):** close to $0 within the free tiers, about $1 to
  $1.50 a month without them.
- **Hard ceiling:** Cloud Run has at most 1 instance and bills only while a request is
  open. Even a game running nonstop all month would cost about $70 (2.6 million seconds at
  about $0.0000265 per second for 1 vCPU and 1 GiB). The budget alerts (WP 12) warn long
  before that.

Model tokens dominate. A single game with several premium models likely costs more than
a month of all the infrastructure above. Two things keep the infrastructure cost low: a
cleanup policy on Artifact Registry that keeps only the last few images (WP 12), and
`max_instance_count = 1` with request-based billing on Cloud Run.

## Removing the app

1. `terraform -chdir=infra destroy` removes every Terraform-managed resource. APIs stay
   enabled.
2. Delete the state bucket last, if wanted: `gcloud storage rm --recursive
   gs://<project id>-imposter-tfstate`.
3. Model Garden enablement can stay. It costs nothing without calls.
