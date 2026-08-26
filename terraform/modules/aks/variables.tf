variable "resource_group_name" {
  description = "Azure Resource Group name"
  type        = string
  default     = "student-voting-rg"
}

variable "kubernetes_version" {
  description = "Kubernetes version for the AKS cluster"
  type        = string
  default     = "1.35"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "cluster_name" {
  description = "AKS Cluster name"
  type        = string
  default     = "student-voting-aks"
}

variable "node_vm_size" {
  description = "VM size for AKS default node pool"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "min_nodes" {
  description = "Minimum nodes in pool"
  type        = number
  default     = 2
}

variable "max_nodes" {
  description = "Maximum nodes in pool"
  type        = number
  default     = 8
}
