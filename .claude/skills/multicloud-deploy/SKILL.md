---
name: multicloud-deploy
description: |
  Creates production-ready real-time multi-cloud deployment architectures for microservices,
  covering Kubernetes federation, global traffic routing, disaster recovery with defined
  RTO/RPO, FinOps cost intelligence, and compliance frameworks (SOC 2, HIPAA, PCI-DSS v4,
  FedRAMP) across AWS, GCP, Azure, and hybrid/on-prem environments.
  This skill should be used when teams need to deploy microservices across multiple clouds,
  implement active-active or active-passive failover, design global disaster recovery
  strategies, optimize cross-cloud costs with FinOps frameworks, enforce regulatory
  compliance across cloud boundaries, or architect hyperscale globally-distributed platforms.
---

# Multi-Cloud Deploy

Creates production-ready real-time multi-cloud deployment architectures from dual-cloud
active-passive setups to hyperscale globally-federated platforms.

## What This Skill Does

- Designs Kubernetes-first multi-cloud topologies (Karmada, Cluster API, Cilium Cluster Mesh)
- Configures global traffic routing (Cloudflare, AWS Global Accelerator, GCP Anycast)
- Architects disaster recovery with measurable RTO/RPO (Velero, LitmusChaos, runbooks)
- Implements FinOps cost governance (Kubecost, OpenCost, budget alerts, chargeback)
- Enforces compliance (SOC 2 Type II, HIPAA, PCI-DSS v4, FedRAMP/NIST 800-53)
- Generates IaC (Terraform multi-provider, Crossplane) and GitOps (ArgoCD ApplicationSets)
- Configures service mesh federation (Istio multi-cluster east-west gateway, Cilium)
- Sets up multi-region databases (CockroachDB, Cassandra, CloudNativePG streaming replication)
- Scaffolds complete project via `scripts/scaffold_multicloud.py`

## What This Skill Does NOT Do

- Provision cloud accounts or billing setup
- Write application-layer business logic (focuses on platform/infrastructure layer)
- Replace cloud vendor support contracts
- Guarantee cloud SLA — defines architecture to MEET SLAs
- Create requirement-specific configs — always generates reusable, parameterized templates

---

## Before Implementation

Gather context to ensure successful implementation:

| Source | Gather |
|--------|--------|
| **Codebase** | Existing IaC, Helm charts, K8s manifests, CI/CD pipelines, network topology |
| **Conversation** | Cloud providers, tier, service count, RTO/RPO targets, compliance needs |
| **Skill References** | Cloud-specific patterns from `references/` (IAM, networking, DR, cost) |
| **User Guidelines** | Team naming conventions, tag standards, existing CIDR allocations |

Only ask user for THEIR requirements. Domain expertise is embedded in `references/`.

---

## Required Clarifications

### Message 1 — Deployment Scope

**Q1. Deployment Tier**

| Tier | Description | Use When |
|------|-------------|----------|
| **1 — Dual-Cloud Passive** | 2 clouds, active-passive, Terraform + ArgoCD + Velero | New to multi-cloud, DR focus |
| **2 — Tri-Cloud Active** | 3 clouds, Karmada federation, Istio mesh, Cloudflare LB | Production multi-cloud traffic |
| **3 — Enterprise** | + Crossplane, chaos engineering, Vault, FinOps, compliance | Regulated, large-scale |
| **4 — Hyperscale** | + CockroachDB global zones, SRE runbooks, 99.999% SLA design | Netflix/Spotify-scale |

**Q2. Cloud Combination**

`aws+gcp` | `aws+azure` | `aws+gcp+azure` | `aws+onprem` | `gcp+azure` | custom

**Q3. Service Count & Stack** — How many microservices? Primary language(s)?

Defaults if not answered: Tier 2, aws+gcp+azure, 10–20 services, Python/Go.

### Message 2 — DR & Compliance (Tier 3+, or if user mentions DR/compliance)

**Q4. RTO/RPO Targets**

| Class | RPO | RTO | Pattern |
|-------|-----|-----|---------|
| **A — Mission Critical** | < 1 min | < 5 min | Active-active + hot standby |
| **B — Business Critical** | < 15 min | < 1 hr | Active-passive + warm standby |
| **C — Standard** | < 4 hr | < 24 hr | Backup restore + cold standby |

**Q5. Compliance Requirements** — SOC 2 | HIPAA | PCI-DSS v4 | FedRAMP | None

**Q6. Existing Infrastructure** — Any existing clusters, Terraform state, CI/CD pipelines?

---

## Deployment Tiers

### Tier 1: Dual-Cloud Active-Passive

```
[Primary Cloud: AWS EKS]          [Secondary Cloud: GCP GKE / Azure AKS]
      ArgoCD (active)                    ArgoCD (synced, passive)
      Services (live)    ─────────────  Services (warm standby)
      Route53 ──── DNS failover (<30s TTL) ──── Cloud DNS
      Velero backups ──────── Cross-cloud object storage ────────────
```

**Stack**: Terraform + EKS/GKE/AKS + ArgoCD + Velero + Prometheus/Grafana + Kubecost

### Tier 2: Tri-Cloud Active-Active

```
         Cloudflare (Global LB + DNS + WAF + Geo-routing)
        /                   |                    \
   AWS EKS            GCP GKE              Azure AKS
        \                   |                    /
         Karmada Control Plane (federation hub)
        /                   |                    \
   Istio east-west gateway (mTLS, cross-cluster svc discovery)
        \                   |                    /
    CockroachDB / Cassandra (multi-region consensus)
         Thanos (federated metrics) + OTel Collector
```

**Stack**: Terraform + Karmada + Istio multi-cluster + Cloudflare + CockroachDB + Thanos + Kubecost

### Tier 3: Enterprise

All Tier 2 + Crossplane (cloud-native IaC), HashiCorp Vault federated secrets,
LitmusChaos chaos engineering, OPA Gatekeeper / Kyverno policy-as-code,
SPIFFE/SPIRE workload identity, FinOps governance, compliance dashboards.

### Tier 4: Hyperscale

All Tier 3 + Custom anycast routing, CockroachDB SURVIVE REGION FAILURE zones,
SRE runbooks with automated toil reduction, 99.999% SLA architecture,
fleet management for 100–500+ clusters with Cluster API + Karmada.

---

## Implementation Workflow

### Step 1: Topology Design
Map services to cloud/region/zone placement. Define CIDR plan (no overlaps).
Use: 10.0.0.0/8 AWS · 172.16.0.0/12 GCP · 192.168.0.0/16 Azure · 100.64.0.0/10 on-prem.
Read `references/cloud-providers.md` for provider-specific subnet ranges.

### Step 2: IaC Scaffold
```bash
python scripts/scaffold_multicloud.py \
  --tier 2 \
  --providers aws,gcp,azure \
  --regions us-east-1,us-central1,eastus \
  --services 15 \
  --db cockroachdb \
  --compliance soc2,hipaa \
  --output ./multicloud-platform
```

### Step 3: Cluster Provisioning
Generate Terraform for EKS + GKE + AKS from `assets/terraform_aws_eks.tf`,
`assets/terraform_gcp_gke.tf`, `assets/terraform_azure_aks.tf`.
Apply: `terraform workspace select [cloud] && terraform apply`

### Step 4: K8s Federation (Tier 2+)
Deploy Karmada control plane on dedicated management cluster.
Configure PropagationPolicy + ClusterAffinity for workload distribution.
See `assets/karmada_federation.yaml` + `references/k8s-federation.md`.

### Step 5: GitOps Setup
Deploy ArgoCD with ApplicationSet (cluster generator) for automatic multi-cluster sync.
See `assets/argocd_applicationset.yaml` + `references/gitops-multicluster.md`.

### Step 6: Service Mesh Federation
Configure Istio multi-primary or primary-remote per tier.
Deploy east-west gateways for cross-cluster service discovery + mTLS.
See `assets/istio_multicluster.yaml` + `references/service-mesh-federation.md`.

### Step 7: Global Traffic Routing
Configure Cloudflare Load Balancer with health monitors + geo-steering.
Set DNS TTLs ≤30s for fast failover. See `assets/cloudflare_load_balancer.tf`.
Read `references/traffic-routing.md` for active-active vs active-passive patterns.

### Step 8: Database Multi-Region
Choose per use case: CockroachDB (global SQL), Cassandra (wide-column/time-series),
CloudNativePG + Barman (Postgres streaming replication), Redis Cluster.
See `references/database-replication.md`.

### Step 9: Disaster Recovery
Schedule Velero backups with cross-cloud storage target.
Define LitmusChaos test plan (zone failure, node drain, DB node kill).
See `assets/velero_backup_schedule.yaml` + `references/disaster-recovery.md`.

### Step 10: FinOps Setup
Deploy Kubecost with cloud billing API integration. Set per-cloud budget alerts.
Enforce cost tags: `team`, `service`, `environment`, `cloud`, `tier`.
See `references/cost-optimization.md`.

### Step 11: Compliance Hardening (Tier 3+)
Apply Kyverno / OPA policies. Enable cloud-native compliance tools.
(AWS Security Hub, GCP Security Command Center, Azure Defender for Cloud.)
See `references/compliance-frameworks.md`.

### Step 12: Delivery
Provide: topology diagram, IaC modules, GitOps manifests, DR runbook,
Kubecost dashboard config, compliance control mapping.

---

## Output Specification

| Artifact | Description |
|----------|-------------|
| **Topology Diagram** | ASCII/Mermaid cluster map with traffic flows and failover paths |
| **Terraform Modules** | Per-cloud cluster provisioning (EKS/GKE/AKS) |
| **Karmada Manifests** | PropagationPolicy + OverridePolicy for workload distribution |
| **ArgoCD ApplicationSet** | Multi-cluster GitOps config with cluster generator |
| **Istio Config** | East-west gateway + PeerAuthentication (STRICT mTLS) |
| **Cloudflare/LB Config** | Global traffic routing + health checks + geo-steering |
| **DR Runbook** | Step-by-step failover + restore procedures with RTO/RPO targets |
| **Cost Dashboard** | Kubecost allocation + budget alert configs |
| **Compliance Checklist** | Control mapping per framework (SOC 2/HIPAA/PCI-DSS/FedRAMP) |

---

## Domain Standards

### Must Follow

- [ ] No CIDR overlaps across clouds (plan before provisioning)
- [ ] Workload identity everywhere — IRSA (AWS), WIF (GCP), Azure AD WIF — NO static creds
- [ ] mTLS between ALL services (Istio PeerAuthentication: STRICT mode)
- [ ] Encrypt at rest + in transit on all clouds (KMS per provider)
- [ ] Unified observability before going multi-cloud (OTel → Thanos/Grafana)
- [ ] Test failover BEFORE production (chaos engineering in staging first)
- [ ] Cost tags on ALL resources from day 1 (enforce via Kyverno/OPA)
- [ ] GitOps for all config — no manual `kubectl apply` in production
- [ ] Private connectivity between clouds (VPN or private interconnect, not public internet)

### Must Avoid

See `references/anti-patterns.md` for 25 documented pitfalls. Key ones:
- Cloud-specific SDK calls without abstraction layer
- Static credentials across cloud boundaries
- Ignoring data egress costs (can exceed compute costs)
- CIDR conflicts between cloud VPCs
- "Lift and shift" to multi-cloud without re-architecting for distributed systems
- No unified logging/tracing across clouds before declaring "multi-cloud"

---

## Technical Robustness

| Failure Scenario | Mitigation |
|-----------------|------------|
| Cluster unreachable | Karmada ClusterAffinity weight shift + DNS failover |
| DNS propagation delay | Sub-30s TTLs + health-check-triggered failover |
| Config drift | ArgoCD auto-sync self-heal; Terraform drift detection in CI |
| Database split-brain | CockroachDB Raft consensus; Cassandra QUORUM consistency |
| Cost spike | Budget alert → PagerDuty → auto-scale reduction |
| Secret rotation | ESO + Vault dynamic secrets; no hardcoded credentials |

---

## Output Checklist

Before delivering multi-cloud deployment:

- [ ] Topology diagram includes all clusters, regions, traffic flows, and failover paths
- [ ] CIDR plan verified — no overlaps across clouds
- [ ] IaC generates all clusters idempotently (terraform plan is clean on re-run)
- [ ] GitOps syncs all clusters from single source of truth
- [ ] Service mesh provides mTLS and cross-cluster service discovery
- [ ] Global LB configured with health checks and automatic failover
- [ ] DR runbook covers RTO/RPO targets with tested restore procedures
- [ ] Cost tags applied on all resources; Kubecost dashboard configured
- [ ] Compliance controls mapped and enabled per required frameworks
- [ ] Chaos test plan defined (minimum: zone failure, pod failure, DB node failure)

---

## Reference Files

| File | When to Read |
|------|-------------|
| `references/cloud-providers.md` | AWS/GCP/Azure specifics, IAM federation, networking |
| `references/k8s-federation.md` | Karmada, Cluster API, KubeFed, multi-cluster networking |
| `references/traffic-routing.md` | Global LB, Cloudflare, DNS failover, active-active patterns |
| `references/disaster-recovery.md` | RTO/RPO tiers, Velero, chaos engineering, runbooks |
| `references/cost-optimization.md` | FinOps, Kubecost, OpenCost, budget governance |
| `references/service-mesh-federation.md` | Istio multi-cluster, Cilium Cluster Mesh, east-west gateway |
| `references/gitops-multicluster.md` | ArgoCD ApplicationSets, Flux multi-cluster, progressive delivery |
| `references/database-replication.md` | CockroachDB, Cassandra, CloudNativePG, Redis multi-cloud |
| `references/compliance-frameworks.md` | SOC 2, HIPAA, PCI-DSS v4, FedRAMP/NIST 800-53 controls |
| `references/anti-patterns.md` | 25 common multi-cloud mistakes and how to avoid them |

## Official Documentation

| Resource | URL | Use For |
|----------|-----|---------|
| Karmada | https://karmada.io/docs/ | K8s federation patterns |
| Cluster API | https://cluster-api.sigs.k8s.io/ | Multi-cloud cluster lifecycle |
| Istio Multi-cluster | https://istio.io/latest/docs/setup/install/multicluster/ | Service mesh federation |
| Cilium Cluster Mesh | https://docs.cilium.io/en/stable/network/clustermesh/ | Network-layer federation |
| ArgoCD ApplicationSets | https://argo-cd.readthedocs.io/en/stable/user-guide/application-set/ | GitOps multi-cluster |
| Flux Multi-cluster | https://fluxcd.io/flux/use-cases/multi-tenancy/ | GitOps federation |
| Crossplane | https://docs.crossplane.io/ | Kubernetes-native IaC |
| Kubecost | https://www.kubecost.com/kubernetes-cost-optimization/ | FinOps |
| OpenCost | https://www.opencost.io/docs/ | OSS cost monitoring |
| Velero | https://velero.io/docs/ | K8s backup and DR |
| LitmusChaos | https://litmuschaos.io/ | Chaos engineering |
| CockroachDB Multi-Region | https://www.cockroachlabs.com/docs/stable/multiregion-overview.html | Global SQL |
| Cloudflare Load Balancing | https://developers.cloudflare.com/load-balancing/ | Global traffic routing |
| SPIFFE/SPIRE | https://spiffe.io/docs/ | Workload identity |
| FinOps Foundation | https://www.finops.org/framework/ | Cost governance |

*Last verified: February 2026*
