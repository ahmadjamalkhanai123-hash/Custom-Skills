# Cloud Providers Reference

## AWS

### Compute / Kubernetes
- **EKS**: Managed K8s — use `eksctl` or Terraform `aws_eks_cluster`
- **Fargate profiles**: Serverless node groups, ideal for burst workloads
- **Karpenter**: Node autoprovisioner (preferred over Cluster Autoscaler on AWS)
- **Node groups**: Use managed node groups with launch templates for customization

### IAM & Identity
- **IRSA (IAM Roles for Service Accounts)**: Annotate SA with `eks.amazonaws.com/role-arn`
  - Never mount static credentials; IRSA provides scoped, rotated tokens
- **OIDC Provider**: Register EKS OIDC endpoint in IAM for IRSA
- **Cross-account**: Use STS AssumeRole with external ID for cross-account access
- **Workload Identity Federation**: For GCP/Azure workloads accessing AWS resources

### Networking
- **VPC CIDR**: Reserve 10.0.0.0/8 for AWS across all regions
- **EKS VPC CNI**: Uses native VPC IPs; enable prefix delegation for pod density
- **PrivateLink**: For internal service exposure across VPCs without internet
- **Transit Gateway**: Multi-VPC and VPN hub — use for multi-region AWS connectivity
- **Direct Connect**: Private circuit to AWS (10/100 Gbps) for on-prem hybrid
- **VPC Peering**: For simple cross-VPC connectivity within same account/region

### Global Traffic
- **AWS Global Accelerator**: Anycast IPs; routes to closest healthy endpoint
  - Use for TCP/UDP acceleration (not just HTTP)
  - Traffic dials for weighted routing and canary shifts
- **Route 53**: DNS with health checks + latency/geolocation routing policies
  - Set TTLs ≤ 30s for fast failover
  - Alias records for zero-TTL failover for CloudFront/ALB endpoints
- **CloudFront**: CDN + edge WAF; use Lambda@Edge for request manipulation

### Storage
- **S3**: Multi-region replication with S3 Replication Rules for DR
- **EBS**: gp3 volumes — specify IOPS/throughput explicitly
- **EFS**: Shared NFS for cross-AZ workloads (use when stateful sharing needed)

### Databases
- **RDS Aurora Global**: Multi-region replica with <1s replication lag; global failover in <1 min
- **DynamoDB Global Tables**: Multi-region active-active; use for session data, config
- **ElastiCache Redis Cluster**: Multi-AZ; use Global Datastore for cross-region

### Cost Tools
- **AWS Cost Explorer**: Tag-based cost breakdown; export to S3 for FinOps dashboards
- **AWS Budgets**: Set alerts at 80%/100% of budget; integrate with SNS/PagerDuty
- **Savings Plans**: 1-year Compute Savings Plans cover EKS/Fargate/Lambda
- **Spot Instances**: Use with Karpenter's `consolidation: whenUnderutilized`

### Compliance
- **AWS Security Hub**: Aggregates findings (GuardDuty, Inspector, Config Rules)
- **AWS Config**: Drift detection + compliance rules (managed + custom)
- **CloudTrail**: API audit log; enable in all regions + S3 cross-region replication
- **KMS**: Per-region CMKs; enable automatic key rotation

---

## GCP

### Compute / Kubernetes
- **GKE Autopilot**: Fully managed nodes — recommended for new clusters
- **GKE Standard**: Manual node pool control; use for specialized hardware (GPUs, high-mem)
- **Node Auto-provisioning**: GKE equivalent of Karpenter (use for Standard mode)
- **Workload Identity**: GCP-native IRSA equivalent (annotate K8s SA → GCP SA)

### IAM & Identity
- **Workload Identity Federation**: Allow AWS/Azure/on-prem workloads to access GCP
  ```
  gcloud iam workload-identity-pools create "multi-cloud-pool" --location="global"
  gcloud iam workload-identity-pools providers create-aws "aws-provider" \
    --workload-identity-pool="multi-cloud-pool" --account-id="[AWS_ACCOUNT_ID]"
  ```
- **Service Account impersonation**: Short-lived tokens via `generateAccessToken`
- **Org-level IAM**: Prefer folder/org-level policies over project-level

### Networking
- **VPC CIDR**: Reserve 172.16.0.0/12 for GCP
- **GKE Dataplane V2**: Cilium-based; enables NetworkPolicy + eBPF observability
- **Shared VPC**: Central host project owns VPC; service projects attach
- **Cloud Interconnect**: Dedicated/partner interconnect to on-prem (10/100 Gbps)
- **Cloud VPN**: IPSec HA VPN for AWS/Azure connectivity (99.99% SLA with 2 tunnels)
- **Private Google Access**: Pods reach Google APIs without public IPs
- **VPC Network Peering**: Cross-project connectivity; no transitive peering

### Global Traffic
- **GCP Premium Tier**: Routes traffic on Google's backbone to nearest PoP
  - Always use Premium Tier for cross-region; Standard Tier uses public internet
- **Cloud Load Balancing**: Global Anycast HTTP(S) LB — single global IP, 80+ PoPs
- **Cloud Armor**: WAF + DDoS protection; attach to global LB backend services
- **Cloud DNS**: Geo-routing + health checks; use Private Zones for internal services
- **Traffic Director**: Service mesh control plane for Envoy-based xDS (alternative to Istio CP)

### Storage
- **Cloud Storage**: Multi-region buckets for DR; use dual-region for lowest latency
- **Filestore**: NFS for GKE persistent volumes
- **Persistent Disk**: pd-ssd for production; pd-extreme for DB workloads

### Databases
- **Cloud Spanner**: Globally distributed SQL, 99.999% SLA, TrueTime
  - Use for multi-region SQL that must be consistent (financial, inventory)
  - Regional: 3 zones | Multi-region: 10+ zones
- **Bigtable**: Wide-column; multi-cluster replication with failover
- **Memorystore (Redis)**: Regional; use Terraform for cross-region setup
- **AlloyDB**: Postgres-compatible, 4x faster than standard RDS for analytics

### Cost Tools
- **Cloud Billing Export**: BigQuery export for detailed cost analysis
- **Budget Alerts**: Project/folder/org-level budgets with Pub/Sub integration
- **Committed Use Discounts**: 1/3-year commitments for consistent workloads
- **Spot VMs (Preemptible)**: Up to 91% discount; 30-second eviction notice

---

## Azure

### Compute / Kubernetes
- **AKS**: Managed K8s; use `az aks create` or Terraform `azurerm_kubernetes_cluster`
- **Virtual Node / ACI**: Serverless burst capacity (Azure Container Instances)
- **KEDA**: Event-driven autoscaling (originated at Azure, now CNCF)
- **Azure Linux**: Hardened OS for AKS nodes (replaces CBL-Mariner)

### IAM & Identity
- **Azure AD Workload Identity**: OIDC-based SA federation (replaces AAD Pod Identity)
  ```yaml
  annotations:
    azure.workload.identity/client-id: "<CLIENT_ID>"
  ```
- **Managed Identity**: System/user-assigned; preferred over service principals
- **Federated Identity Credentials**: Allow AWS/GCP workloads to access Azure resources
- **PIM (Privileged Identity Management)**: Just-in-time admin access

### Networking
- **VNet CIDR**: Reserve 192.168.0.0/16 for Azure
- **AKS CNI Overlay**: Reduces VNet IP exhaustion; pods get overlay IPs
- **Azure CNI with cilium**: Use for network policy + eBPF; recommended for new clusters
- **ExpressRoute**: Private circuit to Azure (10/100 Gbps); use with FastPath
- **VPN Gateway**: IPSec to AWS/GCP; use Zone-Redundant SKU (VpnGw1AZ+)
- **Azure Private Link**: Expose services privately across subscriptions/VNets

### Global Traffic
- **Azure Front Door**: Global CDN + WAF + anycast routing
  - Standard: Basic CDN | Premium: Private Link + WAF + bot protection
- **Traffic Manager**: DNS-based routing (latency, weighted, geographic, priority)
- **Azure Load Balancer**: Regional L4 LB; use Standard SKU (zone-redundant)
- **Application Gateway**: Regional L7 LB + WAF; use for internal app exposure

### Storage
- **Azure Blob Storage**: Geo-redundant (GZRS) for DR; use RA-GZRS for read access
- **Azure Files**: SMB/NFS for AKS PVs; Premium tier for <10ms latency
- **Azure Disk**: Premium SSD v2 for production; Ultra Disk for DB workloads

### Databases
- **Azure Cosmos DB**: Multi-region writes; multiple consistency levels
  - Strong → Bounded Staleness → Session → Consistent Prefix → Eventual
  - Enable multi-region write with conflict resolution policy
- **Azure SQL Hyperscale**: Postgres/SQL Server; up to 100TB, rapid scale
- **Azure Cache for Redis**: Enterprise SKU supports active geo-replication

### Cost Tools
- **Azure Cost Management**: Tag-based analysis; export to Storage for Power BI
- **Azure Advisor**: Right-sizing recommendations; integrate alerts
- **Reserved Instances**: 1/3-year for AKS node pools; Hybrid Benefit for Windows/SQL
- **Spot VMs**: Eviction-based; use with AKS spot node pools + `tolerations`

---

## IAM Federation Patterns (Cross-Cloud)

### Pattern 1: SPIFFE/SPIRE (Recommended for Production)
```
SPIRE Server (management cluster)
  → issues SVID (X.509/JWT) to workloads
  → workload presents SVID to cloud IAM
  → cloud IAM validates via OIDC federation
```
All three clouds accept OIDC JWTs — SPIRE issues JWTs, clouds trust SPIRE's OIDC endpoint.

### Pattern 2: Direct OIDC Federation (Simpler)
Each cloud K8s cluster's OIDC endpoint registered in target cloud's IAM:
- AWS: `aws iam create-open-id-connect-provider --url [OIDC_URL]`
- GCP: Workload Identity Pool with provider type "OIDC"
- Azure: Federated Identity Credential on Managed Identity

### Pattern 3: HashiCorp Vault (Centralized)
Vault deployed with cloud auth backends (AWS, GCP, Azure).
Workloads authenticate to Vault using cloud-native identity → Vault issues short-lived secrets.

---

## Private Connectivity Between Clouds

| Connection | Latency | Bandwidth | Use For |
|-----------|---------|-----------|---------|
| AWS VPN ↔ GCP Cloud VPN | ~10ms | Up to 3 Gbps | Dev/test, low-traffic |
| AWS Direct Connect ↔ GCP Interconnect (via colocation) | <5ms | 10/100 Gbps | Production data plane |
| Megaport / Equinix Fabric | <2ms | Up to 100 Gbps | Enterprise cross-cloud |
| WireGuard overlay | 2-5ms overhead | Software-limited | Dev/small deployments |

**Never use public internet for inter-cloud microservice traffic in production.**

---

## Resource Tagging Standards

Apply uniformly across ALL cloud providers:

| Tag Key | Example Value | Purpose |
|---------|---------------|---------|
| `team` | `payments` | Cost allocation |
| `service` | `checkout-api` | Per-service cost |
| `environment` | `production` | Env separation |
| `cloud` | `aws` | Cross-cloud analysis |
| `tier` | `2` | Deployment tier |
| `managed-by` | `terraform` | IaC ownership |
| `compliance` | `pci-dss` | Audit scoping |
