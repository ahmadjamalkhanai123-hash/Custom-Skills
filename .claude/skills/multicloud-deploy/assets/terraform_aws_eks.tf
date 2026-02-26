# AWS EKS Cluster — Production Template
# Variables: cluster_name, region, vpc_cidr, k8s_version

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.0" }
  }
  backend "s3" {
    bucket         = "terraform-state-multicloud"
    key            = "aws-eks/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      cloud       = "aws"
      environment = var.environment
      managed-by  = "terraform"
      tier        = var.tier
    }
  }
}

variable "cluster_name"  { default = "prod-aws-eks" }
variable "region"        { default = "us-east-1" }
variable "k8s_version"   { default = "1.30" }
variable "environment"   { default = "production" }
variable "tier"          { default = "2" }
variable "node_min"      { default = 3 }
variable "node_max"      { default = 50 }
variable "node_type"     { default = "m6g.xlarge" }  # Graviton — 20% cheaper

# ─── VPC ───────────────────────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.cluster_name}-vpc"
  cidr = "10.10.0.0/16"

  azs             = ["${var.region}a", "${var.region}b", "${var.region}c"]
  private_subnets = ["10.10.1.0/24", "10.10.2.0/24", "10.10.3.0/24"]
  public_subnets  = ["10.10.101.0/24", "10.10.102.0/24", "10.10.103.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = false  # HA: one NAT per AZ
  enable_dns_hostnames = true

  # Required for EKS
  public_subnet_tags  = { "kubernetes.io/role/elb" = "1" }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = "1" }
}

# ─── EKS Cluster ───────────────────────────────────────────────────────────────
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.k8s_version

  vpc_id                         = module.vpc.vpc_id
  subnet_ids                     = module.vpc.private_subnets
  cluster_endpoint_public_access = false    # private endpoint only
  cluster_endpoint_private_access = true

  # Cluster Addons
  cluster_addons = {
    coredns          = { most_recent = true }
    kube-proxy       = { most_recent = true }
    vpc-cni          = {
      most_recent = true
      configuration_values = jsonencode({
        env = {
          ENABLE_PREFIX_DELEGATION = "true"    # more pods per node
          WARM_PREFIX_TARGET       = "1"
        }
      })
    }
    aws-ebs-csi-driver = { most_recent = true; service_account_role_arn = module.irsa_ebs_csi.iam_role_arn }
  }

  # Enable IRSA (IAM Roles for Service Accounts)
  enable_irsa = true

  # Managed Node Groups
  eks_managed_node_groups = {
    system = {
      name           = "system-nodes"
      instance_types = ["m6g.large"]    # Graviton ARM64
      ami_type       = "AL2_ARM_64"
      min_size       = 2
      max_size       = 5
      desired_size   = 2
      disk_size      = 50

      labels = { role = "system", managed-by = "terraform" }
      taints = [{ key = "CriticalAddonsOnly", effect = "NO_SCHEDULE", operator = "Exists" }]
    }

    general = {
      name           = "general-nodes"
      instance_types = [var.node_type, "m6g.2xlarge", "m6g.4xlarge"]
      ami_type       = "AL2_ARM_64"
      min_size       = var.node_min
      max_size       = var.node_max
      desired_size   = var.node_min
      disk_size      = 100

      labels = { role = "workload" }
      update_config = { max_unavailable_percentage = 25 }

      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_type           = "gp3"
            volume_size           = 100
            throughput            = 150
            iops                  = 3000
            encrypted             = true
            delete_on_termination = true
          }
        }
      }
    }
  }

  # Cluster Access Entry (replaces aws-auth ConfigMap)
  access_entries = {
    admin = {
      kubernetes_groups = []
      principal_arn     = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/eks-admin"
      policy_associations = {
        cluster_admin = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }

  # Cluster encryption
  cluster_encryption_config = {
    provider_key_arn = aws_kms_key.eks.arn
    resources        = ["secrets"]
  }

  # Logging
  cluster_enabled_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
}

# ─── KMS for Secrets Encryption ───────────────────────────────────────────────
resource "aws_kms_key" "eks" {
  description             = "EKS cluster secrets encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

# ─── IRSA for EBS CSI Driver ──────────────────────────────────────────────────
module "irsa_ebs_csi" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name             = "${var.cluster_name}-ebs-csi"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }
}

# ─── Karpenter Node Provisioner ───────────────────────────────────────────────
module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 20.0"

  cluster_name = module.eks.cluster_name
  irsa_oidc_provider_arn = module.eks.oidc_provider_arn
}

# ─── StorageClass (gp3 encrypted) ─────────────────────────────────────────────
resource "kubernetes_storage_class" "gp3_encrypted" {
  metadata {
    name = "gp3-encrypted"
    annotations = { "storageclass.kubernetes.io/is-default-class" = "true" }
  }
  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy         = "Retain"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true
  parameters = {
    type      = "gp3"
    encrypted = "true"
    kmsKeyId  = aws_kms_key.eks.arn
    iops      = "3000"
    throughput = "125"
  }
}

data "aws_caller_identity" "current" {}

output "cluster_name"     { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "oidc_provider_arn" { value = module.eks.oidc_provider_arn }
output "cluster_certificate_authority_data" {
  value     = module.eks.cluster_certificate_authority_data
  sensitive = true
}
