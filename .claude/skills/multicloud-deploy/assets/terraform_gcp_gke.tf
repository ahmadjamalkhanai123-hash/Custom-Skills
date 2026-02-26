# GCP GKE Cluster — Production Template
# Variables: cluster_name, region, project, k8s_version

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = { source = "hashicorp/google-beta", version = "~> 5.0" }
    kubernetes  = { source = "hashicorp/kubernetes", version = "~> 2.0" }
  }
  backend "gcs" {
    bucket = "terraform-state-multicloud-REPLACE"
    prefix = "gcp-gke/terraform.tfstate"
  }
}

provider "google" {
  project = var.project
  region  = var.region
}

provider "google-beta" {
  project = var.project
  region  = var.region
}

variable "cluster_name" { default = "prod-gcp-gke" }
variable "region"       { default = "us-central1" }
variable "project"      { default = "my-gcp-project-REPLACE" }
variable "k8s_version"  { default = "1.30" }
variable "environment"  { default = "production" }
variable "tier"         { default = "2" }
variable "node_min"     { default = 3 }
variable "node_max"     { default = 50 }
variable "node_type"    { default = "t2d-standard-4" }  # AMD EPYC — cost-optimised

# ─── VPC ─────────────────────────────────────────────────────────────────────
resource "google_compute_network" "vpc" {
  name                    = "${var.cluster_name}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "primary" {
  name          = "${var.cluster_name}-subnet"
  ip_cidr_range = "172.16.0.0/20"    # nodes
  region        = var.region
  network       = google_compute_network.vpc.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "172.17.0.0/16"  # pods (no overlap with AWS 10.x or Azure 192.168.x)
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "172.18.0.0/20"  # services
  }

  private_ip_google_access = true   # pods can reach Google APIs without public IPs
}

# Cloud Router + NAT for private nodes
resource "google_compute_router" "router" {
  name    = "${var.cluster_name}-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${var.cluster_name}-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# ─── GKE Cluster ─────────────────────────────────────────────────────────────
resource "google_container_cluster" "primary" {
  provider = google-beta
  name     = var.cluster_name
  location = var.region    # regional cluster (3 control plane replicas)

  # Use VPC-native (Alias IP) networking
  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.primary.id

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Remove default node pool — we create our own
  remove_default_node_pool = true
  initial_node_count       = 1

  # Private cluster — no public endpoint for API server
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = true    # API server not internet-accessible
    master_ipv4_cidr_block  = "172.19.0.0/28"
  }

  master_authorized_networks_config {
    cidr_blocks {
      cidr_block   = "10.0.0.0/8"     # AWS VPN range
      display_name = "aws-vpn"
    }
    cidr_blocks {
      cidr_block   = "192.168.0.0/16" # Azure VPN range
      display_name = "azure-vpn"
    }
  }

  # Workload Identity — IRSA equivalent for GCP
  workload_identity_config {
    workload_pool = "${var.project}.svc.id.goog"
  }

  # GKE Dataplane V2 (Cilium-based eBPF networking)
  datapath_provider = "ADVANCED_DATAPATH"

  # Binary Authorization (supply chain security)
  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }

  # Shielded nodes
  enable_shielded_nodes = true

  # Cluster autoscaling (Autopilot-like bin-packing for Standard mode)
  cluster_autoscaling {
    enabled             = true
    autoscaling_profile = "OPTIMIZE_UTILIZATION"   # aggressive bin-packing
    resource_limits {
      resource_type = "cpu"
      minimum       = 4
      maximum       = 500
    }
    resource_limits {
      resource_type = "memory"
      minimum       = 16
      maximum       = 2000
    }
  }

  # Maintenance window — avoid business hours
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-01T02:00:00Z"
      end_time   = "2024-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA,SU"
    }
  }

  # Logging and monitoring
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS", "API_SERVER", "SCHEDULER", "CONTROLLER_MANAGER"]
  }
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
    managed_prometheus { enabled = true }   # Google Managed Prometheus
  }

  # Secrets encryption using Cloud KMS
  database_encryption {
    state    = "ENCRYPTED"
    key_name = google_kms_crypto_key.gke_secrets.id
  }

  addons_config {
    gcs_fuse_csi_driver_config { enabled = true }      # mount GCS buckets as volumes
    gcp_filestore_csi_driver_config { enabled = true } # Filestore NFS
    horizontal_pod_autoscaling { disabled = false }
    http_load_balancing { disabled = false }
    network_policy_config { disabled = false }
  }

  resource_labels = {
    cloud       = "gcp"
    environment = var.environment
    managed-by  = "terraform"
    tier        = var.tier
  }
}

# ─── System Node Pool ─────────────────────────────────────────────────────────
resource "google_container_node_pool" "system" {
  name     = "system-pool"
  cluster  = google_container_cluster.primary.id
  location = var.region

  node_count = 1   # 1 per zone (3 total in regional cluster)

  node_config {
    machine_type = "e2-standard-4"
    disk_type    = "pd-ssd"
    disk_size_gb = 50
    image_type   = "COS_CONTAINERD"

    workload_metadata_config { mode = "GKE_METADATA" }   # Workload Identity

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    labels = { role = "system", managed-by = "terraform" }
    taint = [{
      key    = "CriticalAddonsOnly"
      value  = "true"
      effect = "NO_SCHEDULE"
    }]

    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# ─── General Node Pool (Spot + On-Demand) ─────────────────────────────────────
resource "google_container_node_pool" "general" {
  name     = "general-pool"
  cluster  = google_container_cluster.primary.id
  location = var.region

  autoscaling {
    min_node_count = var.node_min
    max_node_count = var.node_max
    location_policy = "BALANCED"
  }

  node_config {
    machine_type = var.node_type
    disk_type    = "pd-ssd"
    disk_size_gb = 100
    image_type   = "COS_CONTAINERD"

    spot = true   # 60-91% cheaper than on-demand; add on-demand pool for critical

    workload_metadata_config { mode = "GKE_METADATA" }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    labels = {
      role        = "workload"
      cloud       = "gcp"
      environment = var.environment
      team        = "platform"
      managed-by  = "terraform"
    }

    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 3
    max_unavailable = 0
    strategy        = "SURGE"
  }
}

# ─── KMS for Secrets Encryption ───────────────────────────────────────────────
resource "google_kms_key_ring" "gke" {
  name     = "${var.cluster_name}-keyring"
  location = var.region
}

resource "google_kms_crypto_key" "gke_secrets" {
  name            = "${var.cluster_name}-secrets-key"
  key_ring        = google_kms_key_ring.gke.id
  rotation_period = "7776000s"   # 90-day rotation
  purpose         = "ENCRYPT_DECRYPT"
}

# Grant GKE service account access to KMS key
resource "google_kms_crypto_key_iam_binding" "gke_kms" {
  crypto_key_id = google_kms_crypto_key.gke_secrets.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  members = [
    "serviceAccount:service-${data.google_project.current.number}@container-engine-robot.iam.gserviceaccount.com"
  ]
}

# ─── Workload Identity Service Account (example: Velero) ─────────────────────
resource "google_service_account" "velero" {
  account_id   = "velero-gke"
  display_name = "Velero backup service account"
}

resource "google_project_iam_member" "velero_storage" {
  project = var.project
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.velero.email}"
}

resource "google_service_account_iam_binding" "velero_wi" {
  service_account_id = google_service_account.velero.name
  role               = "roles/iam.workloadIdentityUser"
  members = [
    "serviceAccount:${var.project}.svc.id.goog[velero/velero]"
  ]
}

data "google_project" "current" {}

output "cluster_name"     { value = google_container_cluster.primary.name }
output "cluster_endpoint" { value = google_container_cluster.primary.endpoint }
output "cluster_ca"       { value = google_container_cluster.primary.master_auth[0].cluster_ca_certificate; sensitive = true }
output "workload_pool"    { value = "${var.project}.svc.id.goog" }
