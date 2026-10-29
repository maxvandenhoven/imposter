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
