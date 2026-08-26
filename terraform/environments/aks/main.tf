terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.95"
    }
  }
}

provider "azurerm" {
  features {}
}

module "aks_cluster" {
  source              = "../../modules/aks"
  resource_group_name = "voting-prod-rg"
  location            = "eastus"
  cluster_name        = "voting-prod-aks"
  min_nodes           = 2
  max_nodes           = 8
}

output "aks_cluster_name" {
  value = module.aks_cluster.cluster_name
}
