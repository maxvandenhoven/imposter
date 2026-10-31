variable "project_id" {
  description = "ID of the existing sandbox project the app lives in. `make` sets it from `GOOGLE_CLOUD_PROJECT`."
  type        = string
}

variable "region" {
  description = "Region for the app resources."
  type        = string
  default     = "europe-west4"
}

variable "labels" {
  description = "Labels put on every resource that supports them, to find the app's resources in a shared project."
  type        = map(string)
  default = {
    app = "imposter"
  }
}

variable "image" {
  description = "Container image of the Cloud Run service, pinned by digest (`<repo>@sha256:...`). `make deploy` sets it. While it is empty, Terraform creates everything except the service."
  type        = string
  default     = ""
}

variable "invokers" {
  description = "Principals (`user:...` or `group:...`) that may call the private service, for example through `gcloud run services proxy`. Project owners can do so without being listed. IAP replaces this later."
  type        = list(string)
  default     = []
}

variable "billing_account_id" {
  description = "ID of the billing account of the project, for the budgets. While it is empty, no budget is created."
  type        = string
  default     = ""
}

variable "budget_amount" {
  description = "Monthly amount in USD of each budget, which warns at 50, 90 and 100 percent but does not cap spending."
  type        = number
  default     = 20
}

variable "vertex_budget_amount" {
  description = "Monthly amount in USD of the budget on all Vertex AI spend of the project. Zero turns it off."
  type        = number
  default     = 50
}

variable "budget_emails" {
  description = "Email addresses that receive budget alerts, in addition to the billing admins."
  type        = list(string)
  default     = []
}
