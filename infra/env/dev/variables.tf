variable "project_id" {
  description = "ID of the project created by `infra/bootstrap`."
  type        = string
}

variable "region" {
  description = "Region for the app resources."
  type        = string
  default     = "europe-west4"
}
