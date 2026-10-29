# The project is shared with other work in the sandbox, so every resource carries the
# `labels` (filterable in the console, Cloud Asset Inventory and billing reports). API
# calls are billed to and checked against the quota of the project itself, not the
# project of the caller's credentials.
provider "google" {
  project               = var.project_id
  region                = var.region
  billing_project       = var.project_id
  user_project_override = true
  default_labels        = var.labels
}

provider "google-beta" {
  project               = var.project_id
  region                = var.region
  billing_project       = var.project_id
  user_project_override = true
  default_labels        = var.labels
}
