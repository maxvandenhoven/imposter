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

  # The bucket is passed at init time by `make tf-init`: `<project id>-imposter-tfstate`,
  # created once with `make tf-state-bucket`.
  backend "gcs" {
    prefix = "env/dev"
  }
}
