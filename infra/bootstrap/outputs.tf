output "project_id" {
  description = "ID of the created project."
  value       = google_project.imposter.project_id
}

output "project_number" {
  description = "Number of the created project."
  value       = google_project.imposter.number
}

output "region" {
  description = "Region of the regional resources."
  value       = var.region
}

output "state_bucket" {
  description = "Name of the GCS bucket that holds the state of `infra/env/dev`."
  value       = google_storage_bucket.tfstate.name
}
