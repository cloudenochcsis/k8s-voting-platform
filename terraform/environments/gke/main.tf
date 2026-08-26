terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.20"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = "us-central1"
}

variable "project_id" {
  type    = string
  default = "my-voting-gcp-project"
}

module "gke_cluster" {
  source       = "../../modules/gke"
  project_id   = var.project_id
  region       = "us-central1"
  cluster_name = "voting-prod-gke"
  min_nodes    = 2
  max_nodes    = 8
}

output "gke_cluster_name" {
  value = module.gke_cluster.cluster_name
}
