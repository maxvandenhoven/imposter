terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.9"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 8.9"
    }
  }

  # The bucket is passed at init time, it comes from the `state_bucket` output of
  # `infra/bootstrap`: `make tf-init` does this.
  backend "gcs" {
    prefix = "env/dev"
  }
}
