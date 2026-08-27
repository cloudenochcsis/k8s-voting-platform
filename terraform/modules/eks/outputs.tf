output "cluster_endpoint" {
  description = "Endpoint for EKS control plane"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_name" {
  description = "Kubernetes Cluster Name"
  value       = aws_eks_cluster.main.name
}

output "cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data for cluster auth"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "irsa_role_arns" {
  description = "IRSA role ARNs keyed by workload; paste into k8s/overlays/eks/patches/sa-patch.yaml and argocd/applications/platform.yaml"
  value       = { for k, r in aws_iam_role.irsa : k => r.arn }
}
