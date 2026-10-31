output "image_repository" {
  description = "Docker repository that `make build` pushes to."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.imposter.repository_id}"
}

output "build_service_account" {
  description = "Service account that Cloud Build runs as."
  value       = google_service_account.build.id
}

output "build_bucket" {
  description = "Bucket that receives the source for Cloud Build."
  value       = google_storage_bucket.build.name
}

output "service_url" {
  description = "URL of the Cloud Run service, empty until an image is deployed."
  value       = one(google_cloud_run_v2_service.imposter[*].uri)
}
