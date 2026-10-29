# Setting up GCP from zero

This guide takes you from an org sandbox folder with no project to a Terraform-managed GCP
project in which Gemini, Claude and open models answer on Vertex AI. It is written for
someone who has never set up a GCP project. Plan about an hour, most of it waiting.

What you end up with:

- A project (for example `imposter-dev-1234`) in the sandbox folder, linked to billing.
- A versioned GCS bucket `<project id>-tfstate` in `europe-west4` that holds the Terraform
  state of `infra/env/dev`.
- The APIs the app needs, enabled by `infra/env/dev`.
- Claude and a few open models enabled in Model Garden, checked with one test call each.

Steps 1–3, 6 and 7 need you at the keyboard (browser logins and console clicks). The rest
is `make` targets.

## Terms used here

| Term | Meaning |
|---|---|
| **Organisation** | The company root node in GCP. Policies set here apply to everything below. |
| **Folder** | Groups projects under the organisation. The sandbox is a folder; its policies may restrict regions or services. |
| **Project** | The unit that holds resources, enabled APIs, IAM permissions and quotas. Identified by a globally unique *project ID* (you choose it, it can never be reused) and a *project number* (assigned). |
| **Billing account** | Pays for the projects linked to it. A project without one cannot call paid APIs such as Vertex AI. |
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

## 3. Find the folder ID and billing account ID

**Folder ID** (a number like `123456789012`):

```
gcloud organizations list                                # note the organisation ID
gcloud resource-manager folders list --organization <org id>
```

If the sandbox folder is nested, list the children of its parent with `--folder <parent
id>` instead. In the console: the project picker at the top → *All* tab, the folder shows
its ID next to the name.

**Billing account ID** (like `012345-6789AB-CDEF01`):

```
gcloud billing accounts list
```

Pick the open account meant for the sandbox. In the console: *Billing* → *Manage billing
accounts*.

You need two permissions, usually granted with the sandbox: *Project Creator*
(`roles/resourcemanager.projectCreator`) on the folder and *Billing Account User*
(`roles/billing.user`) on the billing account. If Terraform fails with a 403 in step 4,
ask the sandbox admin for these.

## 4. Create the project with Terraform (`infra/bootstrap`)

```
cp infra/bootstrap/terraform.tfvars.example infra/bootstrap/terraform.tfvars
```

Fill in `infra/bootstrap/terraform.tfvars` (git-ignored):

- `project_id`: your choice, globally unique, 6–30 lowercase letters, digits and hyphens,
  for example `imposter-dev-<4 random digits>`. It can never be reused, even after
  deletion.
- `folder_id` and `billing_account`: from step 3.
- `region`: keep `europe-west4`.

Then:

```
make tf-bootstrap
```

This runs `terraform init` and `terraform apply` in `infra/bootstrap`. Read the plan (one
project, four APIs, one bucket) and type `yes`. It creates:

- the project in the folder, linked to the billing account (`deletion_policy =
  "PREVENT"`, so Terraform refuses to delete it by accident),
- the APIs `serviceusage`, `cloudresourcemanager`, `storage` and `aiplatform`,
- the versioned state bucket `<project id>-tfstate` in `europe-west4`.

**Keep the bootstrap state safe.** `infra/bootstrap` stores its state locally in
`infra/bootstrap/terraform.tfstate` (git-ignored) and is not migrated anywhere: it is the
only record that Terraform manages the project and bucket. Copy it to a safe place (a
password manager or a private drive) after every bootstrap apply. If it is lost, the
resources keep working; you would re-import them with `terraform import`.

## 5. Point local tools at the project

```
gcloud config set project <project id>
gcloud auth application-default set-quota-project <project id>
cp .env.example .env    # then set GOOGLE_CLOUD_PROJECT=<project id>
```

The first makes the project the default for `gcloud`. The second records the project as
the quota project in ADC, so Vertex AI calls from your machine count against (and are
billed to) this project instead of failing with a "quota project" error.

## 6. Enable the remaining APIs (`infra/env/dev`)

```
cp infra/env/dev/terraform.tfvars.example infra/env/dev/terraform.tfvars   # set project_id
make tf-plan
make tf-apply
```

`make tf-init` (run by both) initialises the GCS backend with the bucket name read from
the bootstrap output `state_bucket`, so the state of `env/dev` lives in the bucket under
the prefix `env/dev`. Set `TF_STATE_BUCKET=<bucket>` to skip that lookup, for example on
a machine without the bootstrap state. For now `env/dev` only enables the APIs listed in
`infra/env/dev/apis.tf`; WP 12 adds the service account, Artifact Registry, Cloud Run, IAP
and the budget.

## 7. Enable Claude and open models in Model Garden

Gemini works as soon as the `aiplatform` API is enabled. Claude and open models must be
enabled once per project in the console:

1. Open <https://console.cloud.google.com/vertex-ai/model-garden> with the new project
   selected.
2. Search for each model below, open its model card and click **Enable**. Fill in the
   short form and accept the terms. This needs the project Owner role, which you have as
   the creator of the project.
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
| `403 ... quota project` / `USER_PROJECT_DENIED` | Quota project not set: run step 5. |
| `403 ... has not been used in project ... or it is disabled` | API not enabled: wait a few minutes after step 4, or rerun `make tf-bootstrap`. |
| `404 ... not found` / `Publisher model ... not found` | Wrong ID, model not served in that location, or not enabled in Model Garden (step 7). |
| `403 ... terms of service` / `not allowlisted` | Model not enabled in Model Garden (step 7) or blocked by org policy. |
| `429 Resource exhausted` | Quota too low: see step 9. |
| `constraints/gcp.resourceLocations` | The sandbox restricts locations; ask the admin whether `global` and `us-central1` may be used for Vertex AI. |

## 9. Check quotas

New projects get low default quotas for partner and open models, which a game with up to
eight players can hit. In the console go to *IAM & Admin* → *Quotas & System Limits*,
filter on *Service: Vertex AI API* and search for the model name (for example `claude` or
`sonnet`). The relevant rows are the requests and tokens per minute per model, for the
`global` location (or the fallback region). If a value is very low (or 0), select it and
click **Edit quota** to request an increase; small increases are often approved within
minutes, larger ones can take days. Calls are retried with backoff on 429 (D28), so modest
quotas are fine for a demo.

## Done

You now have:

- `gcloud config get project` printing the new project,
- `make tf-plan` showing no changes,
- `scripts/check_models.py` printing `OK` for at least one Gemini and one Claude model.
