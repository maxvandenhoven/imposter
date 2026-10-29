# The project, its billing link and the bucket that holds the state of `infra/env/dev`.
# This root keeps its own state locally in `terraform.tfstate`; keep a copy of that file
# somewhere safe.

locals {
  # APIs needed before `infra/env/dev` can run: Service Usage and Resource Manager to
  # manage the project and its APIs, Storage for the state bucket, Vertex AI so models can
  # be enabled in Model Garden.
  bootstrap_apis = [
    "aiplatform.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
  ]
}

resource "google_project" "imposter" {
  project_id      = var.project_id
  name            = var.project_name
  folder_id       = var.folder_id
  billing_account = var.billing_account
  deletion_policy = "PREVENT"
}

resource "google_project_service" "bootstrap" {
  for_each = toset(local.bootstrap_apis)

  project            = google_project.imposter.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "tfstate" {
  project                     = google_project.imposter.project_id
  name                        = "${google_project.imposter.project_id}-tfstate"
  location                    = upper(var.region)
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  # Keep the 10 most recent earlier versions of each state file.
  lifecycle_rule {
    condition {
      num_newer_versions = 10
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.bootstrap]
}
