terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.95"
    }
  }
  # ponytail: local state. Add an azurerm backend before a second person or CI touches this.
}

provider "azurerm" {
  features {}
}

module "aks_cluster" {
  source              = "../../modules/aks"
  resource_group_name = "voting-prod-rg"
  location            = "eastus"
  cluster_name        = "voting-prod-aks"
  kubernetes_version  = "1.35"
  min_nodes           = 2
  max_nodes           = 8
}

output "aks_cluster_name" {
  value = module.aks_cluster.cluster_name
}

output "key_vault_identity_client_id" {
  value = module.aks_cluster.key_vault_identity_client_id
}

output "tenant_id" {
  value = module.aks_cluster.tenant_id
}
