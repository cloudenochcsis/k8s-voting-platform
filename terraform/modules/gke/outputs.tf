output "cluster_name" {
  value = google_container_cluster.primary.name
}

output "cluster_endpoint" {
  value = google_container_cluster.primary.endpoint
}

output "cluster_ca_certificate" {
  value = google_container_cluster.primary.master_auth[0].cluster_ca_certificate
}

output "workload_identity_emails" {
  description = "GSA emails keyed by workload; these are the values in k8s/overlays/gke/patches/sa-patch.yaml"
  value       = { for k, sa in google_service_account.wi : k => sa.email }
}
