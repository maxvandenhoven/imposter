# APIs the app needs. In a shared project some are likely enabled already. Enabling is
# idempotent, and `disable_on_destroy = false` keeps them enabled on destroy because other
# work in the project may use them. `serviceusage` and `cloudresourcemanager` must be on
# before Terraform runs, because the providers bill API calls to the project
# (`user_project_override`). `make tf-setup` enables them with `gcloud`, and they are
# listed here too so the configuration names every API the app relies on.
locals {
  apis = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudtrace.googleapis.com",
    "iam.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "run.googleapis.com",
    "serviceusage.googleapis.com",
    "telemetry.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.apis)

  service            = each.value
  disable_on_destroy = false
}
