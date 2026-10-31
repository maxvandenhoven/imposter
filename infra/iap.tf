# IAP is enabled directly on the Cloud Run service (`iap_enabled` in run.tf), without a
# load balancer. Cloud Run IAP needs no OAuth brand or client, because Google manages the
# client. Only the allowed principals may open the service. IAP calls Cloud Run with its
# own service agent, which therefore holds the invoker role. Nobody else does.
resource "google_project_service_identity" "iap" {
  provider = google-beta

  project = var.project_id
  service = "iap.googleapis.com"

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "iap_invoker" {
  count = var.image == "" ? 0 : 1

  name     = google_cloud_run_v2_service.imposter[0].name
  location = google_cloud_run_v2_service.imposter[0].location
  role     = "roles/run.invoker"
  member   = google_project_service_identity.iap.member
}

resource "google_iap_web_cloud_run_service_iam_member" "accessors" {
  for_each = var.image == "" ? toset([]) : toset(var.iap_members)

  cloud_run_service_name = google_cloud_run_v2_service.imposter[0].name
  location               = google_cloud_run_v2_service.imposter[0].location
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = each.value
}
