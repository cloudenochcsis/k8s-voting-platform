# GKE VPC & Subnet
resource "google_compute_network" "vpc" {
  name                    = "${var.cluster_name}-vpc"
  auto_create_subnetworks = false
  project                 = var.project_id
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${var.cluster_name}-subnet"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.10.0.0/20"
  project       = var.project_id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.20.0.0/16"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.30.0.0/20"
  }
}

# Least-privilege node identity instead of the default Compute Engine SA.
resource "google_service_account" "nodes" {
  account_id   = "${var.cluster_name}-nodes"
  display_name = "GKE node service account for ${var.cluster_name}"
  project      = var.project_id
}

resource "google_project_iam_member" "nodes" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

# GKE Cluster with Workload Identity Enabled
resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.region
  project  = var.project_id

  network    = google_compute_network.vpc.name
  subnetwork = google_compute_subnetwork.subnet.name

  remove_default_node_pool = true
  initial_node_count       = 1

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Dataplane V2 (eBPF) enforces NetworkPolicy; the legacy dataplane ignores it unless Calico is added.
  datapath_provider = "ADVANCED_DATAPATH"

  deletion_protection = false

  # No min_master_version: under a release channel the version is a floor GKE upgrades past anyway,
  # and a pinned minor fails to apply once it rotates out of the channel. The channel is the pin.
  release_channel {
    channel = "REGULAR"
  }
}

# Node Pool with Autoscaling
resource "google_container_node_pool" "primary_nodes" {
  name     = "${var.cluster_name}-node-pool"
  location = var.region
  cluster  = google_container_cluster.primary.name
  project  = var.project_id

  autoscaling {
    min_node_count = var.min_nodes
    max_node_count = var.max_nodes
  }

  node_config {
    machine_type    = var.machine_type
    disk_type       = "pd-standard"
    disk_size_gb    = 50
    service_account = google_service_account.nodes.email

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

# ---------------------------------------------------------------------------
# Workload Identity: one GSA per Kubernetes ServiceAccount that needs cloud access.
# This is what makes the iam.gke.io/gcp-service-account annotations in the overlay real.
# ---------------------------------------------------------------------------
locals {
  workload_identities = {
    worker           = "voting/sa-worker"
    vote             = "voting/sa-vote"
    eligibility      = "voting/sa-eligibility"
    external-secrets = "external-secrets/external-secrets"
  }
}

resource "google_service_account" "wi" {
  for_each   = local.workload_identities
  account_id = "voting-${each.key}"
  project    = var.project_id
}

resource "google_service_account_iam_member" "wi" {
  for_each           = local.workload_identities
  service_account_id = google_service_account.wi[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${each.value}]"
}

# External Secrets Operator reads the app secret from Secret Manager.
resource "google_project_iam_member" "external_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.wi["external-secrets"].email}"
}
