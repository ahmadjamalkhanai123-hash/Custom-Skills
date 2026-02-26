# Azure AKS Cluster — Production Template
# Variables: cluster_name, location, resource_group, k8s_version

terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    azuread    = { source = "hashicorp/azuread", version = "~> 2.0" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.0" }
  }
  backend "azurerm" {
    resource_group_name  = "terraform-state-rg"
    storage_account_name = "tfstatemulticloudREPLACE"
    container_name       = "tfstate"
    key                  = "azure-aks/terraform.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

variable "cluster_name"    { default = "prod-azure-aks" }
variable "location"        { default = "eastus" }
variable "resource_group"  { default = "prod-multicloud-rg" }
variable "k8s_version"     { default = "1.30" }
variable "environment"     { default = "production" }
variable "tier"            { default = "2" }
variable "node_min"        { default = 3 }
variable "node_max"        { default = 50 }
variable "node_type"       { default = "Standard_D4ds_v5" }

# ─── Resource Group ───────────────────────────────────────────────────────────
resource "azurerm_resource_group" "main" {
  name     = var.resource_group
  location = var.location
  tags = {
    cloud       = "azure"
    environment = var.environment
    managed-by  = "terraform"
    tier        = var.tier
  }
}

# ─── Virtual Network ──────────────────────────────────────────────────────────
resource "azurerm_virtual_network" "main" {
  name                = "${var.cluster_name}-vnet"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = ["192.168.0.0/16"]   # Azure range (no overlap with AWS 10.x or GCP 172.16.x)

  tags = azurerm_resource_group.main.tags
}

resource "azurerm_subnet" "aks_nodes" {
  name                 = "aks-nodes-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["192.168.1.0/24"]
}

resource "azurerm_subnet" "aks_pods" {
  name                 = "aks-pods-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["192.168.16.0/20"]   # pods overlay
}

# ─── Log Analytics (AKS monitoring) ──────────────────────────────────────────
resource "azurerm_log_analytics_workspace" "aks" {
  name                = "${var.cluster_name}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 90
  tags                = azurerm_resource_group.main.tags
}

# ─── Key Vault (secrets + KMS) ───────────────────────────────────────────────
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "aks" {
  name                        = "${substr(var.cluster_name, 0, 14)}-kv"
  location                    = azurerm_resource_group.main.location
  resource_group_name         = azurerm_resource_group.main.name
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  sku_name                    = "premium"    # required for HSM-backed keys
  soft_delete_retention_days  = 90
  purge_protection_enabled    = true
  enable_rbac_authorization   = true

  network_acls {
    bypass         = "AzureServices"
    default_action = "Deny"
    ip_rules       = []   # populate with corporate CIDR
  }

  tags = azurerm_resource_group.main.tags
}

resource "azurerm_key_vault_key" "aks_etcd" {
  name         = "aks-etcd-encryption"
  key_vault_id = azurerm_key_vault.aks.id
  key_type     = "RSA"
  key_size     = 4096
  key_opts     = ["wrapKey", "unwrapKey"]
}

# ─── User-Assigned Managed Identity (Workload Identity) ──────────────────────
resource "azurerm_user_assigned_identity" "aks_control_plane" {
  name                = "${var.cluster_name}-identity"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
}

resource "azurerm_user_assigned_identity" "kubelet" {
  name                = "${var.cluster_name}-kubelet-identity"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
}

# ─── AKS Cluster ─────────────────────────────────────────────────────────────
resource "azurerm_kubernetes_cluster" "main" {
  name                = var.cluster_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = var.cluster_name
  kubernetes_version  = var.k8s_version
  sku_tier            = "Standard"    # 99.95% SLA for control plane

  # Private cluster — no public API server
  private_cluster_enabled             = true
  private_dns_zone_id                 = "System"
  api_server_authorized_ip_ranges     = null  # private endpoint only

  # Azure CNI Overlay with Cilium (recommended for new clusters)
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"    # CNI Overlay — avoids VNet IP exhaustion
    network_policy      = "cilium"     # Cilium for eBPF network policies
    ebpf_data_plane     = "cilium"
    pod_cidr            = "192.168.16.0/20"
    service_cidr        = "192.169.0.0/16"
    dns_service_ip      = "192.169.0.10"
    load_balancer_sku   = "standard"
    outbound_type       = "userAssignedNATGateway"
  }

  # System node pool (required)
  default_node_pool {
    name                        = "system"
    node_count                  = 2
    vm_size                     = "Standard_D2ds_v5"
    vnet_subnet_id              = azurerm_subnet.aks_nodes.id
    pod_subnet_id               = azurerm_subnet.aks_pods.id
    only_critical_addons_enabled = true    # system pods only
    os_sku                      = "AzureLinux"  # hardened, smaller surface
    os_disk_type                = "Managed"
    os_disk_size_gb             = 50
    ultra_ssd_enabled           = false
    temporary_name_for_rotation = "systemtemp"

    upgrade_settings {
      max_surge = "33%"
    }
  }

  # Identity
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aks_control_plane.id]
  }

  kubelet_identity {
    client_id                 = azurerm_user_assigned_identity.kubelet.client_id
    object_id                 = azurerm_user_assigned_identity.kubelet.principal_id
    user_assigned_identity_id = azurerm_user_assigned_identity.kubelet.id
  }

  # Azure AD Workload Identity (replaces AAD Pod Identity)
  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  # Key Management Service (etcd encryption)
  key_management_service {
    key_vault_network_access = "Private"
    key_vault_key_id         = azurerm_key_vault_key.aks_etcd.id
  }

  # Microsoft Defender for Containers (runtime security)
  microsoft_defender {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.aks.id
  }

  # Azure Monitor (Managed Prometheus + Grafana)
  monitor_metrics {}
  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.aks.id
  }

  # Auto-upgrade channel
  automatic_channel_upgrade = "stable"
  node_os_channel_upgrade   = "NodeImage"

  maintenance_window_auto_upgrade {
    frequency   = "Weekly"
    interval    = 1
    duration    = 4
    day_of_week = "Sunday"
    utc_offset  = "+00:00"
    start_time  = "02:00"
  }

  # Azure Policy (OPA Gatekeeper integration)
  azure_policy_enabled = true

  # Key Vault Secrets Provider (CSI driver)
  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "2m"
  }

  # Image cleaner (remove unused images automatically)
  image_cleaner_enabled        = true
  image_cleaner_interval_hours = 48

  tags = azurerm_resource_group.main.tags
}

# ─── User Node Pool (Spot) ────────────────────────────────────────────────────
resource "azurerm_kubernetes_cluster_node_pool" "general" {
  name                  = "general"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = var.node_type
  vnet_subnet_id        = azurerm_subnet.aks_nodes.id
  pod_subnet_id         = azurerm_subnet.aks_pods.id

  enable_auto_scaling = true
  min_count           = var.node_min
  max_count           = var.node_max

  priority        = "Spot"           # 60-90% cheaper
  eviction_policy = "Delete"
  spot_max_price  = -1               # pay market price

  os_sku          = "AzureLinux"
  os_disk_type    = "Managed"
  os_disk_size_gb = 100

  node_labels = {
    role                                    = "workload"
    cloud                                   = "azure"
    environment                             = var.environment
    "kubernetes.azure.com/scalesetpriority" = "spot"
  }

  node_taints = [
    "kubernetes.azure.com/scalesetpriority=spot:NoSchedule"
  ]

  upgrade_settings {
    max_surge = "33%"
  }
}

# ─── NAT Gateway (for outbound) ───────────────────────────────────────────────
resource "azurerm_public_ip" "nat" {
  name                = "${var.cluster_name}-nat-ip"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  allocation_method   = "Static"
  sku                 = "Standard"
  zones               = ["1", "2", "3"]
}

resource "azurerm_nat_gateway" "main" {
  name                    = "${var.cluster_name}-nat"
  resource_group_name     = azurerm_resource_group.main.name
  location                = azurerm_resource_group.main.location
  sku_name                = "Standard"
  idle_timeout_in_minutes = 10
  zones                   = ["1", "2", "3"]
}

resource "azurerm_nat_gateway_public_ip_association" "main" {
  nat_gateway_id       = azurerm_nat_gateway.main.id
  public_ip_address_id = azurerm_public_ip.nat.id
}

resource "azurerm_subnet_nat_gateway_association" "nodes" {
  subnet_id      = azurerm_subnet.aks_nodes.id
  nat_gateway_id = azurerm_nat_gateway.main.id
}

output "cluster_name"            { value = azurerm_kubernetes_cluster.main.name }
output "cluster_endpoint"        { value = azurerm_kubernetes_cluster.main.kube_config[0].host }
output "oidc_issuer_url"         { value = azurerm_kubernetes_cluster.main.oidc_issuer_url }
output "kubelet_identity_id"     { value = azurerm_user_assigned_identity.kubelet.id }
output "resource_group"          { value = azurerm_resource_group.main.name }
