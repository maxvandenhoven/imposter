# Setting up GCP in the sandbox project

This guide takes you from an existing sandbox project to one in which the app's
infrastructure is managed by Terraform and Gemini, Claude and open models answer on Vertex
AI. It is written for someone who has never worked with GCP. Plan about an hour, most of
it waiting.

The project already exists and is shared with other work, so Terraform does not create or
own it: it only adds the app's own resources (APIs now, Cloud Run and friends in WP 12),
each labelled `app=imposter`. What you end up with:

- A versioned GCS bucket `<project id>-imposter-tfstate` in `europe-west4` that holds the
  Terraform state.
- The APIs the app needs, enabled by the Terraform in `infra/`.
- Claude and a few open models enabled in Model Garden, checked with one test call each.

Steps 1–3, 7 and 9 need you at the keyboard (browser logins and console clicks). The rest
is `make` targets.

## Terms used here

| Term | Meaning |
|---|---|
| **Organisation** | The company root node in GCP. Policies set here apply to everything below. |
| **Folder** | Groups projects under the organisation. The sandbox is a folder; its policies may restrict regions or services. |
| **Project** | The unit that holds resources, enabled APIs, IAM permissions and quotas. Identified by a globally unique *project ID* (you choose it, it can never be reused) and a *project number* (assigned). |
| **Billing account** | Pays for the projects linked to it. A project without one cannot call paid APIs such as Vertex AI. |
| **Labels** | Key-value pairs on resources (`app=imposter`). GCP has no resource groups like Azure; the project is the smallest container. Labels are how the app's resources and costs are found in a shared project. |
| **API (service)** | Each GCP product has an API that must be *enabled* in a project before it can be used, for example `aiplatform.googleapis.com` for Vertex AI. |
| **ADC** | *Application Default Credentials*: where client libraries and Terraform look for credentials. Locally that is a file written by `gcloud auth application-default login`; on Cloud Run it is the service account of the service. |
| **Quota project** | The project whose quota and billing an API call counts against when you call with your user credentials. |
| **Model Garden** | The Vertex AI catalogue of models. Partner models (Claude) and open models served by Google (MaaS, *model as a service*) must be enabled there once per project, which accepts their terms. |
| **Terraform state** | A JSON file in which Terraform records what it created. Lose it and Terraform no longer knows it manages those resources. |

## 1. Install the tools

- **gcloud CLI**: follow <https://cloud.google.com/sdk/docs/install> for your OS (on
  Debian/Ubuntu the apt package `google-cloud-cli`). Check with `gcloud version`.
- **Terraform >= 1.9**: follow <https://developer.hashicorp.com/terraform/install> (on
  Debian/Ubuntu the HashiCorp apt repository). Check with `terraform version`.
- **uv** and the Python environment: `make sync` (see the root `CLAUDE.md`).

Once Terraform is installed, `make check` also runs `terraform fmt -check` and
`terraform validate`; without it those checks are skipped.

## 2. Log in twice

```
gcloud auth login
gcloud auth application-default login
```

Use your org account both times. The first command logs in the `gcloud` CLI itself. The
second writes ADC (`~/.config/gcloud/application_default_credentials.json`), which
Terraform, `google-genai` and LiteLLM use. They are separate on purpose: tools never use
your `gcloud` login directly.

## 3. Point local tools at the sandbox project

Find the project ID (not the display name) with `gcloud projects list` or in the console
project picker. Then:

```
gcloud config set project <project id>
gcloud auth application-default set-quota-project <project id>
cp .env.example .env    # then set GOOGLE_CLOUD_PROJECT=<project id>
```

The first makes the project the default for `gcloud`. The second records the project as
the quota project in ADC, so Vertex AI calls from your machine count against (and are
billed to) this project instead of failing with a "quota project" error. The third is the
single place the project ID is set for this repo: the app reads it, and the Makefile
passes it to Terraform (as `TF_VAR_project_id`).

Check that the project is linked to billing (`gcloud billing projects describe <project
id>` shows `billingEnabled: true`) and that you have enough rights in it. *Owner* is
simplest; otherwise you need at least *Service Usage Admin*, *Storage Admin* and, later
for WP 12, the admin roles for Cloud Run, Artifact Registry, IAM service accounts and IAP.
`gcloud projects get-iam-policy <project id> --flatten=bindings
--filter="bindings.members:<your email>" --format="value(bindings.role)"` lists yours.

## 4. Create the Terraform state bucket

```
make tf-state-bucket
```

Terraform records what it manages in a state file. It lives in a GCS bucket so it is not
lost with your laptop, and the bucket must exist before Terraform can use it, so it is the
one resource created with `gcloud` instead of Terraform. The target creates
`<project id>-imposter-tfstate` in `europe-west4` with versioning (every earlier state
is kept), uniform access, public access prevention and the label `app=imposter`. It does
nothing if the bucket exists. If `storage.googleapis.com` is disabled in the project,
enable it first with `gcloud services enable storage.googleapis.com`.

## 5. Enable the APIs with Terraform (`infra/`)

```
make tf-plan
make tf-apply
```

`make tf-init` (run by both) points Terraform at the state bucket, under the prefix
`imposter`. Set `TF_STATE_BUCKET=<bucket>` to use a different bucket. For now Terraform
only enables the APIs listed in `infra/apis.tf` (including `aiplatform` for
Vertex AI); some are probably enabled already in a shared project, which is fine.
Terraform never disables them, not even on `terraform destroy`, because other work in
the project may depend on them. WP 12 adds the service account, Artifact Registry, Cloud
Run, IAP and the budget.

Optional settings (region, labels) go in `infra/terraform.tfvars`, see
`terraform.tfvars.example`.

## 6. Finding the app's resources later

Every resource Terraform creates carries the label `app=imposter`, and
their names start with `imposter`. To list them:

```
terraform -chdir=infra state list                               # what Terraform manages
gcloud asset search-all-resources --scope=projects/<project id> --query="labels.app=imposter"
```

In billing reports (*Billing* → *Reports*), filter on the label `app` to see the app's
cost apart from the rest of the project. Vertex AI model calls carry no resource labels,
so their cost shows under the *Vertex AI* service instead.

## 7. Enable Claude and open models in Model Garden

Gemini works as soon as the `aiplatform` API is enabled. Claude and open models must be
enabled once per project in the console:

1. Open <https://console.cloud.google.com/vertex-ai/model-garden> with the sandbox project
   selected.
2. Search for each model below, open its model card and click **Enable**. Fill in the
   short form and accept the terms. This needs the project Owner role or the
   *Consumer Procurement Entitlement Manager* role, and the model may already be enabled
   if others in the project use it.
   - Claude: **Claude Sonnet 5.5** and **Claude Haiku 5.5**.
   - Open models (MaaS, look for the *API service* / *managed* variant, not a self-deployed
     one): **DeepSeek V3.2**, **Qwen3 235B**, **gpt-oss 120B**, **Llama 4 Maverick**.
3. If a model shows no Enable button or an error, the org or sandbox may block it (org
   policy or terms not allowed). Note it; it is dropped from the lineup.

## 8. Check the models

```
uv run python scripts/check_models.py
```

This sends one tiny prompt to every candidate model (Gemini through `google-genai`, Claude
and open models through LiteLLM `vertex_ai/...`), first at location `global`, then at the
fallback region `us-central1` (`--fallback-location` to change it). Each line says `OK`
with the location that answered, or `FAIL` with the errors. It exits with 0 when at least
one Gemini and one Claude model answer. Check single models with `--model <id>`
(repeatable). Record the results in the *Verified model IDs* table of
`docs/plans/models-and-judge.md`.

Common errors:

| Error | Meaning and fix |
|---|---|
| `DefaultCredentialsError` | No ADC: run step 2 again. |
| `403 ... quota project` / `USER_PROJECT_DENIED` | Quota project not set: run step 3. |
| `403 ... has not been used in project ... or it is disabled` | API not enabled: wait a few minutes after step 5, or rerun `make tf-apply`. |
| `404 ... not found` / `Publisher model ... not found` | Wrong ID, model not served in that location, or not enabled in Model Garden (step 7). |
| `403 ... terms of service` / `not allowlisted` | Model not enabled in Model Garden (step 7) or blocked by org policy. |
| `429 Resource exhausted` | Quota too low: see step 9. |
| `constraints/gcp.resourceLocations` | The sandbox restricts locations; ask the admin whether `global` and `us-central1` may be used for Vertex AI. |

## 9. Check quotas

Projects get low default quotas for partner and open models, which a game with up to
eight players can hit. In the console go to *IAM & Admin* → *Quotas & System Limits*,
filter on *Service: Vertex AI API* and search for the model name (for example `claude` or
`sonnet`). The relevant rows are the requests and tokens per minute per model, for the
`global` location (or the fallback region). If a value is very low (or 0), select it and
click **Edit quota** to request an increase; small increases are often approved within
minutes, larger ones can take days. Calls are retried with backoff on 429 (D28), so modest
quotas are fine for a demo.

## Done

You now have:

- `gcloud config get project` printing the sandbox project,
- `make tf-plan` showing no changes,
- `scripts/check_models.py` printing `OK` for at least one Gemini and one Claude model.
