variable "project_id" {
  description = "ID of the GCP project to create. Globally unique, 6-30 lowercase letters, digits and hyphens."
  type        = string
}

variable "project_name" {
  description = "Display name of the project in the console."
  type        = string
  default     = "Imposter"
}

variable "folder_id" {
  description = "Numeric ID of the sandbox folder the project is created in."
  type        = string
}

variable "billing_account" {
  description = "Billing account ID linked to the project, in the form XXXXXX-XXXXXX-XXXXXX."
  type        = string
}

variable "region" {
  description = "Region for the Terraform state bucket and other regional resources."
  type        = string
  default     = "europe-west4"
}
