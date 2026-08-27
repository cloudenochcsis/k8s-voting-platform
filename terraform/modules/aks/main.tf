resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location
}

# Azure Virtual Network & Subnet
resource "azurerm_virtual_network" "vnet" {
  name                = "${var.cluster_name}-vnet"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = ["10.40.0.0/16"]
}

# Azure CNI hands every pod a VNet IP (default 30/node): a /24 caps out at ~8 nodes.
resource "azurerm_subnet" "nodes" {
  name                 = "${var.cluster_name}-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.40.0.0/22"]
}

# AKS Cluster with OIDC and Workload Identity
resource "azurerm_kubernetes_cluster" "aks" {
  name                = var.cluster_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = var.cluster_name
  kubernetes_version  = var.kubernetes_version # minor alias -> latest GA patch; AKS rejects multi-minor jumps

  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  default_node_pool {
    name                = "systempool"
    vm_size             = var.node_vm_size
    vnet_subnet_id      = azurerm_subnet.nodes.id
    enable_auto_scaling = true
    min_count           = var.min_nodes
    max_count           = var.max_nodes
    node_count          = var.min_nodes
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin    = "azure"
    network_policy    = "azure" # without this, NetworkPolicy resources are accepted but never enforced
    load_balancer_sku = "standard"
  }

  # Application Gateway Ingress Controller — the `azure-application-gateway` ingressClass in the overlay.
  ingress_application_gateway {
    gateway_name = "${var.cluster_name}-appgw"
    subnet_cidr  = "10.40.4.0/24"
  }

  # Key Vault CSI driver — the SecretProviderClass in the overlay.
  key_vault_secrets_provider {
    secret_rotation_enabled = true
  }

  lifecycle {
    ignore_changes = [
      default_node_pool[0].node_count
    ]
  }
}

# Key Vault holding the app secrets; the CSI addon's identity reads them.
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "kv" {
  name                      = "${var.cluster_name}-kv"
  location                  = azurerm_resource_group.rg.location
  resource_group_name       = azurerm_resource_group.rg.name
  tenant_id                 = data.azurerm_client_config.current.tenant_id
  sku_name                  = "standard"
  enable_rbac_authorization = true
}

resource "azurerm_role_assignment" "csi_reads_kv" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_kubernetes_cluster.aks.key_vault_secrets_provider[0].secret_identity[0].object_id
}
