terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = "us-central1"
}

resource "google_bigquery_dataset" "dbt_finops" {
  dataset_id = "dbt_finops"
  location   = "US"
}