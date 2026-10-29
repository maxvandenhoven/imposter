# Setting up GCP in the sandbox project

This guide takes you from an existing sandbox project to a project in which Terraform
manages the app's infrastructure and Gemini, Claude and open models answer on Vertex AI.
It is written for someone who has never worked with GCP. Plan for about an hour, most of
which is spent waiting.

The project already exists and is shared with other work, so Terraform does not create or
own it. Terraform only adds the app's own resources and labels each of them
`app=imposter`. For now those resources are APIs. Cloud Run and the services around it
will follow once the app is deployed. When you have finished this guide, you will have
the following:

- A versioned GCS bucket `<project id>-imposter-tfstate` in `europe-west4` holds the
  Terraform state.
- The Terraform in `infra/` has enabled the APIs that the app needs.
- Claude and a few open models are enabled in Model Garden, and one test call to each
  model has confirmed that it answers.

Steps 1 to 3, 7 and 9 need you at the keyboard, because they involve browser logins and
clicks in the console. The other steps run `make` targets.

[`infrastructure.md`](infrastructure.md) lists every resource with the reason it exists
and shows how the pieces connect.

## Terms used here

| Term | Meaning |
|---|---|
| **Organisation** | The organisation is the company root node in GCP. Policies set on it apply to everything below it. |
| **Folder** | A folder groups projects under the organisation. The sandbox is a folder, and its policies may restrict regions or services. |
| **Project** | A project holds resources, enabled APIs, IAM permissions and quotas. It is identified by a globally unique *project ID*, which its creator chooses and which can never be reused, and by a *project number*, which GCP assigns. |
| **Billing account** | A billing account pays for the projects linked to it. A project without one cannot call paid APIs such as Vertex AI. |
| **Labels** | Labels are key-value pairs on resources, such as `app=imposter`. GCP has no resource groups like Azure, and the project is the smallest container. Labels are therefore how you find the app's resources and costs in a shared project. |
| **API (service)** | Each GCP product has an API that must be *enabled* in a project before the project can use it. Vertex AI, for example, uses `aiplatform.googleapis.com`. |
| **ADC** | *Application Default Credentials* are where client libraries and Terraform look for credentials. On your laptop they are a file written by `gcloud auth application-default login`, and on Cloud Run they are the service account of the service. |
| **Quota project** | The quota project is the project whose quota and billing an API call counts against when you call with your user credentials. |
| **Model Garden** | Model Garden is the Vertex AI catalogue of models. Partner models such as Claude and the open models that Google serves (MaaS, *model as a service*) must be enabled there once per project, which accepts their terms. |
| **Terraform state** | The state is a JSON file in which Terraform records what it created. If you lose it, Terraform no longer knows that it manages those resources. |

## 1. Install the tools

- **gcloud CLI:** Follow <https://cloud.google.com/sdk/docs/install> for your operating
  system. On Debian or Ubuntu, install the apt package `google-cloud-cli`. Check the
  installation with `gcloud version`.
- **Terraform 1.9 or later:** Follow <https://developer.hashicorp.com/terraform/install>.
  On Debian or Ubuntu, use the HashiCorp apt repository. Check the installation with
  `terraform version`.
- **uv and the Python environment:** Install uv by following
  <https://docs.astral.sh/uv/getting-started/installation/>, then run `make sync` in the
  repository to install the Python dependencies.

Once Terraform is installed, `make check` also runs `terraform fmt -check` and
`terraform validate`. Without Terraform, it skips those two checks.

## 2. Log in twice

```
gcloud auth login
gcloud auth application-default login
```

Use your org account both times. The first command logs in the `gcloud` CLI itself. The
second command writes the ADC file
`~/.config/gcloud/application_default_credentials.json`, which Terraform, `google-genai`
and LiteLLM use. The two logins are separate on purpose, because other tools never use
your `gcloud` login directly.

## 3. Point local tools at the sandbox project

Find the project ID, which is not the same as the display name, with `gcloud projects
list` or in the project picker of the console. Then run the following commands:

```
gcloud config set project <project id>
gcloud auth application-default set-quota-project <project id>
cp .env.example .env    # then set GOOGLE_CLOUD_PROJECT=<project id>
```

The first command makes the project the default for `gcloud`. The second command records
the project as the quota project in ADC, so that Vertex AI calls from your laptop are
counted against and billed to this project instead of failing with a "quota project"
error. The third command creates `.env`, which is the single place where this repository
sets the project ID. The app reads it from there, and the Makefile passes it to Terraform
as `TF_VAR_project_id`.

Next, check that the project is linked to billing and that you have enough rights in it.
`gcloud billing projects describe <project id>` should show `billingEnabled: true`. The
*Owner* role is the simplest choice. Without it, you need at least *Service Usage Admin*
and *Storage Admin*. Deploying the app later also needs the admin roles for Cloud Run,
Artifact Registry, IAM service accounts and IAP. The following command lists the roles
you have:

```
gcloud projects get-iam-policy <project id> --flatten=bindings \
  --filter="bindings.members:<your email>" --format="value(bindings.role)"
```

## 4. Prepare the project for Terraform

```
make tf-setup
```

Two things must exist before Terraform can run, so this target creates them with
`gcloud`. It is safe to run the target again.

- **Base APIs:** The target enables `serviceusage`, `cloudresourcemanager` and `storage`.
  Terraform bills its own API calls to the project, so that they count against the
  project's quota instead of yours. That only works when the Service Usage API is already
  enabled in the project. Without it, `make tf-apply` fails on every API with `Service
  Usage API has not been used in project ... or it is disabled`. `gcloud` can enable the
  API because it bills that one call to its own client project.
- **State bucket:** The target creates `<project id>-imposter-tfstate`. Terraform records
  what it manages in a state file, which lives in a GCS bucket so that it is not lost
  with your laptop. The bucket must exist before Terraform can use it. The target creates
  it in `europe-west4` with versioning, so every earlier state is kept, and with uniform
  access, public access prevention and the label `app=imposter`. If the bucket already
  exists, the target leaves it alone.

## 5. Enable the APIs with Terraform (`infra/`)

```
make tf-plan
make tf-apply
```

Both targets first run `make tf-init`, which points Terraform at the state bucket and
stores the state under the prefix `imposter`. To use a different bucket, set
`TF_STATE_BUCKET=<bucket>`. For now, Terraform only enables the APIs listed in
`infra/apis.tf`, including `aiplatform` for Vertex AI. In a shared project some of them
are probably enabled already, which is fine. Terraform never disables them, not even on
`terraform destroy`, because other work in the project may depend on them. Deploying the
app later adds a service account, Artifact Registry, Cloud Run, IAP and a budget.

Optional settings such as the region and the labels go in `infra/terraform.tfvars`. See
`infra/terraform.tfvars.example` for the available settings.

## 6. Find the app's resources later

Every resource that Terraform creates carries the label `app=imposter`, and every name
starts with `imposter`. The first command below lists what Terraform manages, and the
second searches the project for resources with the label:

```
terraform -chdir=infra state list
gcloud asset search-all-resources --scope=projects/<project id> --query="labels.app=imposter"
```

In the billing reports under *Billing* → *Reports*, filter on the label `app` to see the
app's cost apart from the rest of the project. Vertex AI model calls carry no resource
labels, so their cost appears under the *Vertex AI* service instead.

## 7. Enable Claude and open models in Model Garden

Gemini works as soon as the `aiplatform` API is enabled. Claude and the open models must
be enabled once per project in the console:

1. Open <https://console.cloud.google.com/vertex-ai/model-garden> with the sandbox project
   selected.
2. Search for each model in the list below, open its model card and click **Enable**.
   Fill in the short form and accept the terms. You need the project Owner role or the
   *Consumer Procurement Entitlement Manager* role for this. A model may already be
   enabled if others in the project use it.
   - Claude: **Claude Sonnet 5.5** and **Claude Haiku 5.5**.
   - Open models: **DeepSeek V3.2**, **Qwen3 235B**, **gpt-oss 120B** and **Llama 4
     Maverick**. Pick the *API service* or *managed* variant (MaaS), not a variant that
     you deploy yourself.
3. If a model shows no Enable button or shows an error, the organisation or the sandbox
   may block it through an org policy or by not allowing its terms. Write the model down,
   and it will be dropped from the lineup.

## 8. Check the models

```
uv run --env-file .env python scripts/check_models.py
```

The `--env-file .env` option loads `GOOGLE_CLOUD_PROJECT` from the `.env` file you created
in step 3, and the script uses that value as its `--project`. Without the option, the
script stops with `Missing option '--project'` unless you pass `--project <project id>`
yourself.

The script sends one tiny prompt to every candidate model. It calls Gemini through
`google-genai` and calls Claude and the open models through LiteLLM (`vertex_ai/...`). It
tries the location `global` first and then the fallback region `us-central1`, which you
can change with `--fallback-location`. Each output line says `OK` with the location that
answered, or `FAIL` with the errors. The script exits with 0 when at least one Gemini
model and one Claude model answer. To check a single model, pass `--model <id>`, which
you can repeat for several models. A model that keeps failing after the fixes below
cannot be used in this project and should be left out of the app's model catalog.

The following table explains the common errors and how to fix them:

| Error | Meaning and fix |
|---|---|
| `Missing option '--project'` | `GOOGLE_CLOUD_PROJECT` is not set. Run the script with `uv run --env-file .env`, or pass `--project`. |
| `DefaultCredentialsError` | There are no ADC on your laptop. Run step 2 again. |
| `403 ... quota project` or `USER_PROJECT_DENIED` | The quota project is not set. Run step 3 again. |
| `403 ... has not been used in project ... or it is disabled` | The API is not enabled. If the error names `serviceusage`, run `make tf-setup` (step 4). For other APIs, wait a few minutes after step 5 or run `make tf-apply` again. |
| `404 ... not found` or `Publisher model ... not found` | The model ID is wrong, the model is not served in that location, or the model is not enabled in Model Garden (step 7). |
| `403 ... terms of service` or `not allowlisted` | The model is not enabled in Model Garden (step 7), or an org policy blocks it. |
| `429 Resource exhausted` | The quota is too low. See step 9. |
| `constraints/gcp.resourceLocations` | The sandbox restricts locations. Ask the admin whether Vertex AI may use `global` and `us-central1`. |

## 9. Check quotas

Projects get low default quotas for partner and open models, and a game with up to eight
players can hit them. In the console, go to *IAM & Admin* → *Quotas & System Limits*,
filter on *Service: Vertex AI API* and search for the model name, for example `claude` or
`sonnet`. The relevant rows are the requests and tokens per minute for each model in the
`global` location or the fallback region. If a value is very low or 0, select it and
click **Edit quota** to request an increase. Small increases are often approved within
minutes, while larger ones can take days. The app retries calls with backoff when it gets
a 429 error, so modest quotas are fine for a demo.

## Done

You have finished the setup when all three of these checks succeed:

- `gcloud config get project` prints the sandbox project.
- `make tf-plan` shows no changes.
- `uv run --env-file .env python scripts/check_models.py` prints `OK` for at least one
  Gemini model and one Claude model.
