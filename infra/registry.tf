resource "google_artifact_registry_repository" "imposter" {
  repository_id = "imposter"
  location      = var.region
  format        = "DOCKER"
  description   = "Images of the Imposter app, deployed by digest."

  # Keep the ten newest images, so storage stays at a few cents a month.
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  cleanup_policies {
    id     = "delete-rest"
    action = "DELETE"
    condition {
      older_than = "2592000s"
    }
  }

  depends_on = [google_project_service.apis]
}
