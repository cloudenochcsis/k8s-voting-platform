variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "cluster_name" {
  description = "GKE Cluster Name"
  type        = string
  default     = "student-voting-gke"
}

variable "machine_type" {
  description = "GCE machine type for nodes"
  type        = string
  default     = "e2-standard-2"
}

variable "min_nodes" {
  description = "Minimum nodes per zone in node pool (regional cluster = x3)"
  type        = number
  default     = 1
}

variable "max_nodes" {
  description = "Maximum nodes per zone in node pool"
  type        = number
  default     = 5
}
