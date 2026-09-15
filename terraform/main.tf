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

resource "google_service_account" "finops_agent" {
  account_id   = "finops-agent-runtime"
  display_name = "FinOps Agent Runtime"
  description  = "Service account used by the FinOps agent when running on AWS Lambda"
}

resource "google_bigquery_dataset_iam_member" "finops_agent_reader" {
  dataset_id = google_bigquery_dataset.dbt_finops.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.finops_agent.email}"
}

resource "google_project_iam_member" "finops_agent_job_user" {
  project = var.gcp_project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.finops_agent.email}"
}