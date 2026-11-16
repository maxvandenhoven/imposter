# The runtime identity of the Cloud Run service. It has no owner or editor role, only what
# the app calls: Vertex AI models, and trace and log export.
resource "google_service_account" "run" {
  account_id   = "imposter-run"
  display_name = "Imposter Cloud Run runtime"

  depends_on = [google_project_service.apis]
}

locals {
  run_roles = [
    "roles/aiplatform.user",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
    "roles/telemetry.tracesWriter",
  ]
}

resource "google_project_iam_member" "run" {
  for_each = toset(local.run_roles)

  project = var.project_id
  role    = each.value
  member  = google_service_account.run.member
}

# The Gemini Decisions API is not part of Vertex AI, so the judge calls it with an API key
# instead of the service account. The key lives in a secret that is created by hand
# (`docs/guides/gcp-setup.md`), and the runtime identity may read only that secret.
resource "google_secret_manager_secret_iam_member" "run_gemini_api_key" {
  count = var.gemini_api_key_secret == "" ? 0 : 1

  project   = var.project_id
  secret_id = var.gemini_api_key_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.run.member

  depends_on = [google_project_service.apis]
}

# Cloud Build runs as its own service account instead of the broad default one.
resource "google_service_account" "build" {
  account_id   = "imposter-build"
  display_name = "Imposter Cloud Build"

  depends_on = [google_project_service.apis]
}

resource "google_project_iam_member" "build_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = google_service_account.build.member
}

resource "google_artifact_registry_repository_iam_member" "build_push" {
  repository = google_artifact_registry_repository.imposter.name
  location   = google_artifact_registry_repository.imposter.location
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.build.member
}

# `make build` uploads the source to this bucket, which only the build account can read.
resource "google_storage_bucket" "build" {
  name                        = "${var.project_id}-imposter-build"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "build_source" {
  bucket = google_storage_bucket.build.name
  role   = "roles/storage.objectViewer"
  member = google_service_account.build.member
}
