# Cloud Security (4C Layer 1)

## The 4C's Security Model

```
┌─────────────────────────────────────────────────────────┐
│  Cloud     (IAM, VPC, KMS, CloudTrail, Security Groups) │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Cluster  (RBAC, NetworkPolicy, PSS, Audit Log)   │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  Container  (Image, seccomp, AppArmor, FS)  │  │  │
│  │  │  ┌───────────────────────────────────────┐  │  │  │
│  │  │  │  Code  (SAST, DAST, deps, secrets)    │  │  │  │
│  │  │  └───────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

Each layer adds defense-in-depth. Compromise of one layer should NOT compromise inner layers.

---

## AWS Security

### IAM Roles for Service Accounts (IRSA)

```yaml
# K8s ServiceAccount with IRSA annotation
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-service
  namespace: production
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/my-service-role
---
# Corresponding IAM Role Trust Policy
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B716D3041E"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B716D3041E:sub":
          "system:serviceaccount:production:my-service",
        "oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B716D3041E:aud":
          "sts.amazonaws.com"
      }
    }
  }]
}
```

### AWS Service Control Policies (SCPs)

```json
// Deny any action outside approved regions
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyNonApprovedRegions",
      "Effect": "Deny",
      "NotAction": [
        "iam:*", "sts:*", "cloudfront:*",
        "route53:*", "support:*"
      ],
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:RequestedRegion": ["us-east-1", "us-west-2", "eu-west-1"]
        }
      }
    },
    {
      "Sid": "RequireMFAForConsole",
      "Effect": "Deny",
      "Action": "*",
      "Resource": "*",
      "Condition": {
        "BoolIfExists": {"aws:MultiFactorAuthPresent": "false"},
        "Bool": {"aws:ViaAWSService": "false"}
      }
    },
    {
      "Sid": "ProtectSecurityTools",
      "Effect": "Deny",
      "Action": [
        "guardduty:DeleteDetector",
        "securityhub:DisableSecurityHub",
        "cloudtrail:DeleteTrail",
        "config:DeleteConfigRule"
      ],
      "Resource": "*"
    }
  ]
}
```

### AWS Network Security

```hcl
# VPC with private subnets only (Terraform)
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "production-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["us-east-1a", "us-east-1b", "us-east-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway     = true
  single_nat_gateway     = false   # HA: one per AZ
  enable_vpn_gateway     = false
  enable_dns_hostnames   = true
  enable_dns_support     = true

  # Flow logs for security analysis
  enable_flow_log                      = true
  create_flow_log_cloudwatch_log_group = true
  create_flow_log_cloudwatch_iam_role  = true
  flow_log_max_aggregation_interval    = 60

  tags = {
    Environment = "production"
    Terraform   = "true"
  }
}

# EKS API server: private endpoint only
resource "aws_eks_cluster" "main" {
  vpc_config {
    endpoint_private_access = true
    endpoint_public_access  = false   # CRITICAL: no public API server
    subnet_ids              = module.vpc.private_subnets
  }

  encryption_config {
    provider { key_arn = aws_kms_key.eks.arn }
    resources = ["secrets"]
  }

  enabled_cluster_log_types = [
    "api", "audit", "authenticator",
    "controllerManager", "scheduler"
  ]
}
```

### AWS KMS Customer Managed Keys

```hcl
# Dedicated KMS key per service (not shared)
resource "aws_kms_key" "service_key" {
  description             = "CMK for my-service secrets"
  deletion_window_in_days = 30
  enable_key_rotation     = true   # Annual auto-rotation
  multi_region            = false

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowKeyAdministration"
        Effect = "Allow"
        Principal = { AWS = "arn:aws:iam::${var.account_id}:role/KMSAdmins" }
        Action   = ["kms:*"]
        Resource = "*"
      },
      {
        Sid    = "AllowServiceUsage"
        Effect = "Allow"
        Principal = { AWS = "arn:aws:iam::${var.account_id}:role/my-service-role" }
        Action   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
        Resource = "*"
      }
    ]
  })
}
```

### AWS Security Hub + GuardDuty

```hcl
# Enable AWS Security Hub with CIS benchmark
resource "aws_securityhub_account" "main" {}
resource "aws_securityhub_standards_subscription" "cis" {
  depends_on    = [aws_securityhub_account.main]
  standards_arn = "arn:aws:securityhub:::ruleset/cis-aws-foundations-benchmark/v/1.4.0"
}
resource "aws_securityhub_standards_subscription" "nist" {
  depends_on    = [aws_securityhub_account.main]
  standards_arn = "arn:aws:securityhub:us-east-1::standards/nist-800-53/v/5.0.0"
}

# GuardDuty with S3, EKS, RDS, Lambda protection
resource "aws_guardduty_detector" "main" {
  enable                       = true
  finding_publishing_frequency = "FIFTEEN_MINUTES"

  datasources {
    s3_logs { enable = true }
    kubernetes {
      audit_logs { enable = true }
    }
    malware_protection {
      scan_ec2_instance_with_findings { ebs_volumes { enable = true } }
    }
  }
}
```

---

## GCP Security

### Workload Identity Federation

```yaml
# GKE Workload Identity
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-service
  namespace: production
  annotations:
    iam.gke.io/gcp-service-account: my-service@my-project.iam.gserviceaccount.com
---
# Bind K8s SA to GCP SA
# gcloud iam service-accounts add-iam-policy-binding \
#   my-service@my-project.iam.gserviceaccount.com \
#   --role roles/iam.workloadIdentityUser \
#   --member "serviceAccount:my-project.svc.id.goog[production/my-service]"
```

### Org-Level Security Controls

```yaml
# Organization Policy: deny public IPs on GCE
constraints/compute.vmExternalIpAccess: DENY_ALL

# Require shielded VMs
constraints/compute.requireShieldedVm: true

# Disable service account key creation
constraints/iam.disableServiceAccountKeyCreation: true

# Require OS Login
constraints/compute.requireOsLogin: true

# Restrict resource location
constraints/gcp.resourceLocations:
  allowedValues: ["in:us-locations", "in:eu-locations"]
```

### VPC Service Controls

```python
# VPC-SC Perimeter (Google Cloud Python SDK example)
perimeter = {
    "name": f"accessPolicies/{policy_name}/servicePerimeters/production_perimeter",
    "title": "Production Data Perimeter",
    "status": {
        "restrictedServices": [
            "storage.googleapis.com",
            "bigquery.googleapis.com",
            "secretmanager.googleapis.com"
        ],
        "accessLevels": [f"accessPolicies/{policy_name}/accessLevels/corporate_network"],
        "resources": ["projects/123456789"],
        "vpcAccessibleServices": {
            "enableRestriction": True,
            "allowedServices": ["RESTRICTED-SERVICES"]
        }
    }
}
```

---

## Azure Security

### Azure Workload Identity

```yaml
# AKS Workload Identity
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-service
  namespace: production
  annotations:
    azure.workload.identity/client-id: "00000000-0000-0000-0000-000000000000"
    azure.workload.identity/tenant-id: "00000000-0000-0000-0000-000000000000"
```

### Azure Policy

```json
// Deny public IP on AKS nodes
{
  "if": {
    "allOf": [
      {"field": "type", "equals": "Microsoft.ContainerService/managedClusters"},
      {"field": "Microsoft.ContainerService/managedClusters/enableRBAC", "notEquals": "true"}
    ]
  },
  "then": {"effect": "Deny"}
}
```

---

## Multi-Cloud Security Baseline

| Control | AWS | GCP | Azure |
|---------|-----|-----|-------|
| Workload Identity | IRSA | Workload Identity | Workload Identity |
| Network isolation | VPC + SG + NACL | VPC + Firewall | VNet + NSG |
| Secrets | AWS SM + KMS | Secret Manager + CMEK | Key Vault |
| Audit logs | CloudTrail + CloudWatch | Cloud Audit Logs | Azure Monitor |
| Threat detection | GuardDuty + Security Hub | Security Command Center | Defender for Cloud |
| Policy enforcement | SCP + Config | Org Policy | Azure Policy |
| Private cluster | Private EKS endpoint | Private GKE | Private AKS |

---

## CloudTrail / Audit Logging

```json
// CloudTrail — all management events, S3 data events
{
  "TrailName": "production-audit-trail",
  "S3BucketName": "audit-logs-immutable",
  "IncludeGlobalServiceEvents": true,
  "IsMultiRegionTrail": true,
  "EnableLogFileValidation": true,   // SHA-256 integrity check
  "EventSelectors": [
    {
      "ReadWriteType": "All",
      "IncludeManagementEvents": true,
      "DataResources": [
        {"Type": "AWS::S3::Object", "Values": ["arn:aws:s3:::sensitive-data-bucket/"]},
        {"Type": "AWS::Lambda::Function", "Values": ["arn:aws:lambda"]}
      ]
    }
  ]
}
```

---

## STRIDE Threat Mapping

| Threat | Cloud Control | Cluster Control | Container Control |
|--------|---------------|-----------------|-------------------|
| **Spoofing** | IRSA/Workload Identity | RBAC + OIDC | SPIFFE SVID |
| **Tampering** | CloudTrail + MFA | Admission webhooks | Cosign image signing |
| **Repudiation** | CloudTrail immutable | K8s audit log | Falco event stream |
| **Info Disclosure** | KMS encryption + VPC-SC | NetworkPolicy + TLS | readOnlyRootFilesystem |
| **DoS** | WAF + Shield | ResourceQuota + LimitRange | CPU/Memory limits |
| **Elevation** | SCP deny + least privilege | PSS Restricted | drop ALL caps + non-root |
