---
name: k8s-mastery
description: |
  Creates production-ready Kubernetes manifests, Helm charts, and enterprise
  architectures from single-workload deployments to hyperscale fleet platforms
  with multi-layer RBAC, secrets management, service mesh, GitOps, and compliance.
  This skill should be used when users want to deploy applications to Kubernetes,
  create Helm charts, harden cluster security, implement GitOps, configure service
  mesh, manage secrets, set up observability, or architect multi-cluster platforms.
---

# Kubernetes Mastery

Build production-ready Kubernetes infrastructure — from kubectl apply to Google/Meta-scale fleets.

## What This Skill Does

- Scaffolds Kubernetes manifests at any tier (single pod → hyperscale fleet)
- Implements multi-layer RBAC (User → Namespace → Cluster → Federation)
- Configures secrets (K8s Secrets, Sealed Secrets, External Secrets, Vault)
- Architects service mesh (Istio, Linkerd, Cilium Service Mesh)
- Generates GitOps pipelines (ArgoCD, Flux) with environment promotion
- Creates policy engines (Kyverno, OPA Gatekeeper) for security + compliance
- Implements observability (Prometheus, Grafana, Loki, Tempo, OpenTelemetry)
- Designs multi-cluster federation with cross-cluster service discovery
- Configures networking (Cilium eBPF, NetworkPolicy, Gateway API)
- Creates Helm charts and Kustomize overlays for environment management
- Architects disaster recovery with RPO/RTO guarantees
- Scaffolds custom operators (Kubebuilder, Operator SDK)
- Implements cost optimization (VPA, Karpenter, spot, resource quotas)
- Generates compliance configurations (SOC 2, HIPAA, PCI-DSS, FedRAMP)

## What This Skill Does NOT Do

- Build Docker images (use `docker-mastery`)
- Write application code (only orchestrates existing apps)
- Provision cloud infrastructure (generates IaC configs only)
- Manage DNS registrars (configures ExternalDNS, cert-manager only)
- Create CI pipelines (generates CD/GitOps only; CI is pre-K8s)

---

## Before Implementation

Gather context to ensure successful implementation:

| Source | Gather |
|--------|--------|
| **Codebase** | Existing manifests, Helm charts, Kustomize, Dockerfiles, .env |
| **Conversation** | Workloads to deploy, scale needs, security/compliance requirements |
| **Skill References** | Patterns from `references/` for the appropriate tier |
| **User Guidelines** | Cloud provider, cluster setup, team structure, compliance |

Ensure all required context is gathered before implementing.
Only ask user for THEIR specific requirements (K8s expertise is in this skill).

---

## Required Clarifications

Before building, ask:

1. **Application Type**: "What are you deploying?"
   - Single application (web app, API, worker)
   - Microservices system (2-20 services)
   - Large-scale platform (20+ services, multi-team)
   - Infrastructure component (databases, queues, caches)
   - ML/AI workloads (GPU, batch jobs, model serving)

2. **Scale Tier**: "What scale?"
   - Foundation (learning, dev, single workload)
   - Production (hardened single cluster, single team)
   - Enterprise (multi-namespace, multi-team, compliance)
   - Multi-Cluster (multi-region, federation, DR)
   - Hyperscale (fleet management, platform engineering, 10K+ nodes)

## Optional Clarifications

3. **Cloud Provider**: Auto-detect or ask (EKS, GKE, AKS, On-Prem)
4. **Packaging**: Helm (default), Kustomize, Raw manifests
5. **GitOps**: ArgoCD (default at T3+), Flux, None
6. **Service Mesh**: None (T1-T2), Istio (T3+), Linkerd, Cilium
7. **Secrets**: K8s Secrets (T1), Sealed Secrets (T2), Vault + ESO (T3+)
8. **Compliance**: None, SOC 2, HIPAA, PCI-DSS, FedRAMP

Note: Start with 1-2. Follow up with 3-8 based on context.

### Defaults (If Not Specified)

| Clarification | Default |
|---------------|---------|
| Tier | Foundation (Tier 1) |
| Cloud Provider | AWS EKS |
| K8s Version | 1.31+ |
| Packaging | Helm 3 |
| GitOps | ArgoCD (Tier 3+) |
| Ingress | NGINX Ingress (T1-T2), Gateway API (T3+) |
| Service Mesh | None (T1-T2), Istio (T3+) |
| CNI | VPC-CNI/Calico (T1-T2), Cilium (T3+) |
| Secrets | K8s Secrets (T1), Sealed Secrets (T2), ESO+Vault (T3+) |
| Observability | kubectl logs (T1), Prometheus+Grafana (T2+) |
| Policy Engine | None (T1), Kyverno (T2+), OPA Gatekeeper (T4+) |
| Autoscaling | None (T1), HPA (T2+), Karpenter+VPA (T3+) |

### Before Asking

1. Check conversation history for prior answers
2. Infer from existing project files (Helm charts, kustomization.yaml, manifests/)
3. Only ask what cannot be determined from context

---

## Tier Selection Decision Tree

```
What's the primary need?

Single workload for dev/learning?
  → Tier 1: Foundation (references/core-resources.md)

Harden a single cluster for one team?
  → Tier 2: Production (references/production-hardening.md)

Multi-team org with compliance + policy?
  → Tier 3: Enterprise (references/enterprise-patterns.md)

Multi-region with DR + federation + mesh?
  → Tier 4: Multi-Cluster (references/multi-cluster.md)

Google/Meta-scale fleet + platform engineering?
  → Tier 5: Hyperscale (references/hyperscale-patterns.md)

Not sure? → Start Tier 1, scale up when needed
```

### Tier Comparison

| Factor | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|--------|--------|--------|--------|--------|--------|
| Clusters | 1 | 1 | 1-3 | 3-20 | 20-200+ |
| Workloads | 1-5 | 5-50 | 50-200 | 200-2K | 2K-100K+ |
| RBAC | cluster-admin | Namespace roles | Hierarchical | Federated OIDC | Fleet + tenants |
| Secrets | K8s Secrets | Sealed Secrets | Vault + ESO | Vault HA | Multi-tenant HSM |
| Networking | ClusterIP | Ingress+NetPol | Gateway API+Cilium | Multi-cluster mesh | eBPF+custom CNI |
| Observability | kubectl logs | Prometheus+Grafana | Full stack+alerts | Multi-cluster | Fleet telemetry |
| Policy | None | Kyverno basics | Kyverno/OPA full | Federated policies | Policy platform |
| Deploy | kubectl apply | Helm | ArgoCD GitOps | Multi-cluster ArgoCD | Progressive delivery |
| DR | None | PDB+backups | Multi-AZ+Velero | Multi-region passive | Active-active |
| Best for | Learning | Startups | Mid-size orgs | Large enterprise | FAANG-scale |

---

## Workflow

```
Tier → Namespaces → Labels → Workloads → Networking → Security → Secrets → Observability → GitOps → DR → Troubleshooting
```

### Step 1: Select Tier
Use decision tree. Read relevant reference files.

### Step 2: Define Label Strategy
Read `references/label-strategy.md`:
- Standard labels: `app.kubernetes.io/{name,version,component,part-of,managed-by}`
- Business labels: `team`, `environment`, `cost-center`, `tier`
- Kyverno enforcement for required labels (T2+)

### Step 3: Design Namespace Strategy
Read `references/namespace-patterns.md`:
- **T1**: `default` namespace
- **T2**: Per-environment (`dev`, `staging`, `prod`)
- **T3**: Per-team+env (`team-payments-prod`) with ResourceQuota
- **T4**: Hierarchical namespaces (HNC) + cross-cluster federation
- **T5**: Virtual clusters (vcluster) + namespace-as-a-service

### Step 4: Generate Workload Manifests
Read `references/core-resources.md`:
- Deployments with rolling update strategy
- StatefulSets for databases and stateful workloads
- Jobs/CronJobs for batch processing
- DaemonSets for node-level agents

### Step 5: Configure Networking
Read `references/networking.md`:
- Services (ClusterIP, NodePort, LoadBalancer, Headless)
- Ingress / Gateway API routing
- NetworkPolicy for pod-to-pod isolation
- Service mesh mTLS + traffic management

### Step 6: Implement Security
Read `references/security.md` and `references/rbac-patterns.md`:
- RBAC roles/bindings (namespace + cluster)
- Pod Security Standards (restricted/baseline/privileged)
- NetworkPolicies (default deny + explicit allow)
- Security contexts (non-root, read-only FS, dropped caps)
- Policy engine rules (Kyverno/OPA)

### Step 7: Configure Secrets
Read `references/secrets-management.md`:
- K8s Secrets + encryption at rest (T1-T2)
- Sealed Secrets for GitOps-safe encryption (T2)
- External Secrets Operator + Vault (T3+)
- CSI Secret Store Driver for volume-mounted secrets (T3+)

### Step 8: Setup Observability
Read `references/observability.md`:
- Metrics: Prometheus + Grafana (kube-prometheus-stack)
- Logs: Loki + Promtail / Fluentbit
- Traces: Tempo / Jaeger + OpenTelemetry Collector
- Alerts: AlertManager + PagerDuty / Slack

### Step 9: Implement GitOps
Read `references/gitops-patterns.md`:
- ArgoCD Application + ApplicationSet
- App-of-apps repo structure
- Environment promotion: dev → staging → prod
- Progressive delivery: Argo Rollouts (canary, blue-green)

### Step 10: Disaster Recovery
Read `references/disaster-recovery.md`:
- Velero backups, etcd snapshots
- Multi-AZ topology spread
- Multi-region failover with DNS routing
- RPO/RTO targets by tier

### Step 11: Microservices Orchestration (if multi-service)
Read `references/microservices-patterns.md`:
- Service communication matrix (sync vs async)
- Namespace-per-domain strategy
- Circuit breakers, retry budgets, rate limiting
- Distributed tracing with OpenTelemetry
- Cross-namespace NetworkPolicy for service domains

### Step 12: Troubleshooting Runbook
Read `references/troubleshooting.md`:
- Diagnostic decision tree for common failures
- kubectl debug commands and ephemeral containers
- Prometheus alerting queries for proactive detection
- Error playbooks: CrashLoop, OOM, RBAC 403, NetworkPolicy blocks

---

## Output Specification

### Tier 1 Output
- [ ] Deployment with resource requests/limits
- [ ] Service + ConfigMap + Secret + Namespace
- [ ] Basic Ingress or NodePort
- [ ] README with kubectl instructions

### Tier 2 Output (includes T1 +)
- [ ] Namespace with ResourceQuota + LimitRange
- [ ] RBAC Role + RoleBinding
- [ ] Sealed Secrets + NetworkPolicy (default deny)
- [ ] HPA + PDB + Pod Security Standards
- [ ] Ingress with TLS (cert-manager)
- [ ] Liveness/readiness/startup probes
- [ ] Prometheus ServiceMonitor
- [ ] Helm chart or Kustomize base + overlays

### Tier 3 Output (includes T2 +)
- [ ] Multi-namespace strategy with hierarchy
- [ ] Kyverno/OPA policies (images, resources, security)
- [ ] External Secrets + Vault integration
- [ ] Gateway API + Cilium NetworkPolicy (L7)
- [ ] ArgoCD Application + ApplicationSet (app-of-apps)
- [ ] kube-prometheus-stack + Loki + SLO alerting
- [ ] Velero backup schedules + topology spread
- [ ] Compliance audit policy

### Tier 4 Output (includes T3 +)
- [ ] Multi-cluster ArgoCD hub-spoke
- [ ] Istio/Linkerd service mesh + cross-cluster discovery
- [ ] Multi-region DNS failover (ExternalDNS)
- [ ] Thanos federated metrics
- [ ] Vault HA + Argo Rollouts progressive delivery
- [ ] Cross-region Velero + multi-cluster RBAC via OIDC

### Tier 5 Output (includes T4 +)
- [ ] Fleet management (Rancher/GKE Fleet)
- [ ] Cilium Cluster Mesh (eBPF) + Crossplane compositions
- [ ] Custom operator scaffolding (Kubebuilder)
- [ ] Karpenter NodePool + Kubecost FinOps
- [ ] Platform API (Backstage) + vcluster tenant isolation
- [ ] SLSA verification at admission + Tetragon runtime security

---

## Domain Standards

### Must Follow
- [ ] All workloads have resource requests AND limits
- [ ] All pods run as non-root (runAsNonRoot: true)
- [ ] All containers drop ALL capabilities, add only needed
- [ ] All namespaces have ResourceQuota + LimitRange (T2+)
- [ ] All namespaces have default-deny NetworkPolicy (T2+)
- [ ] All secrets encrypted at rest
- [ ] All production images use digest references
- [ ] All ingress uses TLS in production
- [ ] All RBAC follows least-privilege
- [ ] Standard labels: app.kubernetes.io/{name,version,component}
- [ ] PDB for all production deployments
- [ ] Graceful shutdown (preStop + terminationGracePeriodSeconds)
- [ ] Health probes (liveness + readiness + startup)

### Must Avoid
- Running as root or privileged: true
- Using `default` namespace for production
- Hardcoding secrets in manifests
- Using `latest` tag in production
- ClusterRoleBinding to cluster-admin for apps
- Missing NetworkPolicies / resource limits
- hostNetwork/hostPID without justification
- Storing sensitive data in ConfigMaps
- Committing unencrypted secrets to Git

---

## Error Handling

| Scenario | Action |
|----------|--------|
| CrashLoopBackOff | Check probes, resources, startup time |
| ImagePullBackOff | Verify image, registry auth, pull secret |
| Pending (unschedulable) | Check resources, taints, affinity |
| OOMKilled | Increase memory limits, check leaks |
| RBAC 403 | Check Role/RoleBinding, subject name |
| NetworkPolicy blocking | Verify selectors, DNS egress rule |
| Secret not found | Check name, namespace, ESO sync |
| Ingress 502/503 | Verify backend, readiness, health |
| ArgoCD sync failed | Check validation, RBAC, diff |
| HPA not scaling | Verify metrics-server, metric availability |

---

## Output Checklist

### Architecture
- [ ] Tier appropriate for requirements
- [ ] Namespace strategy defined
- [ ] Packaging (Helm/Kustomize) consistent
- [ ] GitOps configured (T3+)

### Security
- [ ] RBAC configured (least privilege)
- [ ] Pod Security Standards enforced
- [ ] NetworkPolicies applied
- [ ] Secrets at appropriate tier
- [ ] Security contexts on all containers
- [ ] Policy engine rules (T2+)

### Reliability
- [ ] Resource requests AND limits
- [ ] Liveness/readiness/startup probes
- [ ] PDB for production workloads
- [ ] HPA + topology spread (multi-AZ)
- [ ] Graceful shutdown configured
- [ ] Backup strategy (T2+)

### Observability
- [ ] Prometheus ServiceMonitor
- [ ] Logging to stdout/stderr
- [ ] SLO/SLI alerting (T3+)
- [ ] Dashboards provisioned (T2+)

---

## Reference Files

| File | When to Read |
|------|--------------|
| `references/core-resources.md` | Deployment, Service, ConfigMap, StatefulSet, Jobs |
| `references/namespace-patterns.md` | Namespace strategy, ResourceQuota, LimitRange, HNC |
| `references/rbac-patterns.md` | Roles, Bindings, OIDC, Aggregation, Cross-cluster |
| `references/secrets-management.md` | K8s Secrets, Sealed Secrets, ESO, Vault, CSI Driver |
| `references/networking.md` | NetworkPolicy, Gateway API, Ingress, Service types |
| `references/service-mesh.md` | Istio, Linkerd, Cilium mesh, mTLS, traffic mgmt |
| `references/security.md` | Pod Security Standards, security context, Falco |
| `references/policy-engines.md` | Kyverno, OPA Gatekeeper, ValidatingAdmissionPolicy |
| `references/observability.md` | Prometheus, Grafana, Loki, Tempo, Thanos, SLOs |
| `references/gitops-patterns.md` | ArgoCD, Flux, app-of-apps, progressive delivery |
| `references/multi-cluster.md` | Federation, cross-cluster discovery, hub-spoke |
| `references/hyperscale-patterns.md` | Fleet mgmt, Crossplane, custom operators, eBPF |
| `references/disaster-recovery.md` | Velero, etcd backup, multi-region failover |
| `references/cost-optimization.md` | VPA, Karpenter, spot, Kubecost, FinOps |
| `references/production-hardening.md` | Full production checklist, compliance, audit |
| `references/helm-kustomize.md` | Helm chart patterns, Kustomize overlays |
| `references/troubleshooting.md` | kubectl debug, diagnostic trees, error playbooks |
| `references/microservices-patterns.md` | Multi-service orchestration, circuit breakers, tracing |
| `references/label-strategy.md` | Label taxonomy, kubectl searching, cardinality, Kyverno |
| `references/anti-patterns.md` | 25+ common K8s mistakes with fixes |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scaffold_k8s.py` | Generate K8s project. Usage: `python scaffold_k8s.py <name> --tier <1\|2\|3\|4\|5> --path <dir> [--provider <eks\|gke\|aks\|onprem>] [--packaging <helm\|kustomize\|raw>] [--gitops <argocd\|flux\|none>] [--mesh <none\|istio\|linkerd\|cilium>] [--secrets <k8s\|sealed\|vault>]` |

## Asset Templates

| Template | Purpose |
|----------|---------|
| `assets/templates/deployment_basic.yaml` | Tier 1 complete deployment |
| `assets/templates/deployment_production.yaml` | Tier 2 hardened (probes, PDB, HPA) |
| `assets/templates/namespace_enterprise.yaml` | Tier 3 namespace + quota + netpol |
| `assets/templates/helm_chart/` | Complete Helm chart skeleton |
| `assets/templates/kustomize_base/` | Kustomize base for microservices |
| `assets/templates/kustomize_overlays/` | Per-environment overlays |
| `assets/templates/argocd_app_of_apps.yaml` | ArgoCD root application |
| `assets/templates/argocd_applicationset.yaml` | Multi-cluster ApplicationSet |
| `assets/templates/kyverno_policies.yaml` | Production policy bundle |
| `assets/templates/external_secret.yaml` | Vault integration template |
| `assets/templates/prometheus_rules.yaml` | SLO alerting rules |
| `assets/templates/velero_schedule.yaml` | Backup schedule template |
| `assets/templates/gateway_api.yaml` | Gateway + HTTPRoute template |
| `assets/templates/karpenter_nodepool.yaml` | Node autoscaling template |
| `assets/templates/istio_authz.yaml` | Istio L7 authorization policy |

## Official Documentation

| Resource | URL |
|----------|-----|
| Kubernetes Docs | https://kubernetes.io/docs/ |
| Helm Docs | https://helm.sh/docs/ |
| ArgoCD | https://argo-cd.readthedocs.io/ |
| Istio | https://istio.io/latest/docs/ |
| Cilium | https://docs.cilium.io/ |
| Kyverno | https://kyverno.io/docs/ |
| Gateway API | https://gateway-api.sigs.k8s.io/ |
| External Secrets | https://external-secrets.io/latest/ |
| Vault | https://developer.hashicorp.com/vault/docs |
| Karpenter | https://karpenter.sh/docs/ |
| Velero | https://velero.io/docs/ |
| Falco | https://falco.org/docs/ |

Last verified: February 2026.
