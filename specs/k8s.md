# Kubernetes Mastery — Production Skill Spec

## Spec Metadata

| Field | Value |
|-------|-------|
| **Skill Name** | `k8s-mastery` |
| **Type** | Builder |
| **Domain** | Kubernetes — Zero to Hyperscale Production Orchestration |
| **Target Score** | 90+ (Production) |
| **Pattern** | Follows docker-mastery / fastapi-forge structure |
| **Global Standard** | Google, Meta, Netflix, Uber, Stripe-grade infrastructure |

---

## 1. Purpose & Scope

### What This Skill Creates

Production-ready Kubernetes infrastructure across five tiers:

| Tier | Scale | Architecture | Target |
|------|-------|-------------|--------|
| **1: Foundation** | 1 cluster, 1-5 workloads | Basic Deployments, Services, ConfigMaps | Learning, dev, hobby |
| **2: Production** | 1 cluster, 5-50 workloads | RBAC, Secrets, Ingress, HPA, PDB, NetworkPolicy | Startups, single-team production |
| **3: Enterprise** | 1-3 clusters, 50-200 workloads | Multi-namespace, OPA/Kyverno, Vault, Observability, GitOps | Multi-team orgs, compliance-driven |
| **4: Multi-Cluster** | 3-20 clusters, 200-2000 workloads | Federation, Service Mesh, Multi-Region, Disaster Recovery | Large enterprises, SaaS platforms |
| **5: Hyperscale** | 20+ clusters, 2000+ workloads, 10K+ nodes | Fleet Management, Platform Engineering, eBPF, Custom Controllers | Google/Meta/Netflix/Uber scale |

### What This Skill Does

- Scaffolds Kubernetes manifests at any tier (pod → hyperscale fleet)
- Implements multi-layer RBAC (User → Namespace → Cluster → Federation)
- Configures secrets management (K8s Secrets, Sealed Secrets, External Secrets, Vault)
- Architects service mesh deployments (Istio, Linkerd, Cilium Service Mesh)
- Generates GitOps pipelines (ArgoCD, Flux) with promotion workflows
- Creates policy engines (OPA Gatekeeper, Kyverno) for security + compliance
- Implements observability stacks (Prometheus, Grafana, Loki, Tempo, OpenTelemetry)
- Designs multi-cluster federation with cross-cluster service discovery
- Configures advanced networking (Cilium eBPF, Calico, NetworkPolicy, Gateway API)
- Creates Helm charts and Kustomize overlays for environment management
- Architects disaster recovery with RPO/RTO guarantees
- Scaffolds custom operators and controllers (Kubebuilder, Operator SDK)
- Implements cost optimization (VPA, Karpenter, spot instances, resource quotas)
- Generates compliance-mapped configurations (SOC 2, HIPAA, PCI-DSS, FedRAMP)

### What This Skill Does NOT Do

- Build Docker images (use `docker-mastery` for that)
- Write application code (only orchestrates it)
- Provision cloud infrastructure (generates IaC configs for Terraform/Pulumi but doesn't run them)
- Manage DNS registrars (configures ExternalDNS, cert-manager only)
- Create CI pipelines (generates CD/GitOps only; CI is pre-K8s)
- Build MCP servers or agents (use `mcp-skills` / `hybrid-sdk-agents`)

---

## 2. Before Implementation

Gather context to ensure successful implementation:

| Source | Gather |
|--------|--------|
| **Codebase** | Existing manifests, Helm charts, Kustomize, Dockerfiles, .env files |
| **Conversation** | Workloads to deploy, scale needs, security/compliance requirements |
| **Skill References** | Patterns from `references/` for the appropriate tier |
| **User Guidelines** | Cloud provider, cluster setup, team structure, compliance frameworks |

Ensure all required context is gathered before implementing.
Only ask user for THEIR specific requirements (Kubernetes expertise is embedded in this skill).

---

## 3. Required Clarifications

Before building, ask:

1. **What are you deploying?**
   - Single application (web app, API, worker)
   - Microservices system (2-20 services)
   - Large-scale platform (20+ services, multi-team)
   - Infrastructure component (databases, queues, caches)
   - ML/AI workloads (GPU, batch jobs, model serving)

2. **What scale tier?**
   - Foundation (learning, dev, single workload)
   - Production (hardened single cluster, single team)
   - Enterprise (multi-namespace, multi-team, compliance)
   - Multi-Cluster (multi-region, federation, DR)
   - Hyperscale (fleet management, platform engineering, 10K+ nodes)

## Optional Clarifications

3. **Cloud Provider**: AWS EKS (default), GKE, AKS, On-Prem, Hybrid
4. **Packaging**: Helm (default), Kustomize, Raw manifests, Timoni/CUE
5. **GitOps**: ArgoCD (default), Flux, None
6. **Service Mesh**: None (default T1-T2), Istio (T3+), Linkerd, Cilium
7. **Secrets**: K8s Secrets (T1), Sealed Secrets (T2), External Secrets + Vault (T3+)
8. **Compliance**: None, SOC 2, HIPAA, PCI-DSS, FedRAMP

Note: Start with questions 1-2. Follow up with 3-8 based on tier and context.

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
| CNI | VPC-CNI / Calico (T1-T2), Cilium (T3+) |
| Secrets | K8s Secrets (T1), Sealed Secrets (T2), External Secrets + Vault (T3+) |
| Observability | kubectl logs (T1), Prometheus + Grafana (T2+), Full stack (T3+) |
| Policy Engine | None (T1), Kyverno (T2+), OPA Gatekeeper (T4+) |
| Autoscaling | None (T1), HPA (T2+), Karpenter + VPA (T3+) |

### Before Asking

1. Check conversation history for prior answers
2. Infer from existing project files (Helm charts, kustomization.yaml, manifests/)
3. Only ask what cannot be determined from context

---

## 4. Tier Selection Decision Tree

```
What's the primary need?

Deploy a single workload to a cluster for dev/learning?
  → Tier 1: Foundation (references/core-resources.md)

Production-harden a single cluster with one team?
  → Tier 2: Production (references/production-hardening.md)

Multi-team org with compliance and policy enforcement?
  → Tier 3: Enterprise (references/enterprise-patterns.md)

Multi-region with DR, federation, and service mesh?
  → Tier 4: Multi-Cluster (references/multi-cluster.md)

Google/Meta-scale fleet with platform engineering?
  → Tier 5: Hyperscale (references/hyperscale-patterns.md)

Not sure?
  → Start Tier 1, scale up when needed
```

### Tier Comparison

| Factor | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|--------|--------|--------|--------|--------|--------|
| Clusters | 1 | 1 | 1-3 | 3-20 | 20-200+ |
| Workloads | 1-5 | 5-50 | 50-200 | 200-2K | 2K-100K+ |
| Nodes | 1-5 | 5-50 | 50-200 | 200-2K | 2K-50K+ |
| RBAC | cluster-admin | Per-namespace roles | Hierarchical + aggregated | Cross-cluster federated | Fleet-wide + tenant isolation |
| Secrets | K8s Secrets | Sealed Secrets | Vault + ESO | Vault HA + cross-cluster | Multi-tenant Vault + HSM |
| Networking | ClusterIP/NodePort | Ingress + NetworkPolicy | Gateway API + Cilium | Multi-cluster mesh | eBPF + custom CNI |
| Observability | kubectl logs | Prometheus + Grafana | Full stack + alerting | Multi-cluster dashboards | Fleet telemetry + AIOps |
| Policy | None | Kyverno basics | Kyverno/OPA full | Federated policies | Policy-as-code platform |
| Deploy | kubectl apply | Helm | ArgoCD GitOps | Multi-cluster ArgoCD | Fleet-wide progressive delivery |
| DR | None | PDB + backups | Multi-AZ + Velero | Multi-region active-passive | Multi-region active-active |
| Best for | Learning | Startups | Mid-size orgs | Large enterprise | FAANG-scale |

---

## 5. Workflow

```
Tier → Namespace Design → Workloads → Networking → Security → Secrets → Observability → GitOps → DR
```

### Step 1: Select Tier

Use decision tree above. Read the relevant reference files.

### Step 2: Design Namespace Strategy

Read `references/namespace-patterns.md`:

**Tier 1**: `default` namespace
**Tier 2**: Per-environment (`dev`, `staging`, `prod`)
**Tier 3**: Per-team + per-environment (`team-payments-prod`, `team-search-staging`)
**Tier 4**: Hierarchical namespaces (HNC) with cross-cluster federation
**Tier 5**: Virtual clusters (vcluster) + namespace-as-a-service

```
Tier 3+ Namespace Hierarchy:
├── platform/              ← Platform team (ingress, mesh, observability)
├── team-payments/
│   ├── payments-prod      ← ResourceQuota, LimitRange, NetworkPolicy
│   ├── payments-staging
│   └── payments-dev
├── team-search/
│   ├── search-prod
│   └── search-staging
└── shared/                ← Shared databases, caches, message brokers
```

### Step 3: Generate Workload Manifests

Read `references/core-resources.md`:
- Deployments with rolling update strategy
- StatefulSets for databases and stateful workloads
- Jobs / CronJobs for batch processing
- DaemonSets for node-level agents (logging, monitoring, security)

### Step 4: Configure Networking

Read `references/networking.md`:
- Services (ClusterIP, NodePort, LoadBalancer, Headless)
- Ingress / Gateway API routing rules
- NetworkPolicy for pod-to-pod isolation
- Service Mesh (mTLS, traffic management, observability)

### Step 5: Implement Security

Read `references/security.md` and `references/rbac-patterns.md`:
- RBAC roles and bindings (namespace + cluster level)
- Pod Security Standards (restricted/baseline/privileged)
- NetworkPolicies (default deny + explicit allow)
- Security contexts (non-root, read-only FS, dropped capabilities)
- Policy engine rules (Kyverno/OPA Gatekeeper)

### Step 6: Configure Secrets

Read `references/secrets-management.md`:
- K8s Secrets + encryption at rest (T1-T2)
- Sealed Secrets for GitOps-safe encryption (T2)
- External Secrets Operator + HashiCorp Vault (T3+)
- CSI Secret Store Driver for volume-mounted secrets (T3+)
- Vault Agent Injector for sidecar-based injection (T4+)

### Step 7: Setup Observability

Read `references/observability.md`:
- Metrics: Prometheus + Grafana (kube-prometheus-stack)
- Logs: Loki + Promtail / Fluentbit
- Traces: Tempo / Jaeger + OpenTelemetry Collector
- Alerts: AlertManager + PagerDuty / Slack integration
- Dashboards: Cluster, namespace, workload, SLO/SLI views

### Step 8: Implement GitOps

Read `references/gitops-patterns.md`:
- ArgoCD Application and ApplicationSet resources
- Repo structure: app-of-apps pattern
- Environment promotion: dev → staging → prod
- Sync policies: auto-sync dev, manual-sync prod
- Secrets: Sealed Secrets or External Secrets in Git
- Progressive delivery: Argo Rollouts (canary, blue-green)

### Step 9: Disaster Recovery

Read `references/disaster-recovery.md`:
- Velero backup schedules and restore procedures
- etcd snapshots for cluster state recovery
- Multi-AZ topology spread constraints
- Multi-region failover with DNS-based routing
- RPO/RTO targets by tier

---

## 6. Architecture Patterns (Reference Content)

### Pattern 1: Single Application (Tier 1-2)

```
                    Ingress / Gateway API
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
        ┌──────────┐          ┌──────────┐
        │ Service  │          │ Service  │
        │ (app)    │          │ (api)    │
        └────┬─────┘          └────┬─────┘
             │                     │
        ┌────▼─────┐          ┌────▼─────┐
        │Deployment│          │Deployment│
        │ 3 pods   │          │ 3 pods   │
        └────┬─────┘          └────┬─────┘
             │                     │
        ┌────▼─────────────────────▼─────┐
        │      ConfigMap + Secrets       │
        │      PVC (if stateful)         │
        └────────────────────────────────┘
```

### Pattern 2: Microservices with Mesh (Tier 3)

```
     Gateway API (HTTPRoute)
            │
     ┌──────┴──────┐
     ▼              ▼
┌─────────┐  ┌──────────┐
│ Frontend │  │ API GW   │──── AuthorizationPolicy
│ Service  │  │ Service  │
└────┬─────┘  └────┬─────┘
     │              │
     │    ┌─────────┼──────────┐
     │    ▼         ▼          ▼
     │  ┌─────┐  ┌──────┐  ┌────────┐
     │  │Users│  │Orders│  │Payments│     ← Each in own namespace
     │  │ Svc │  │ Svc  │  │  Svc   │     ← NetworkPolicy isolated
     │  └──┬──┘  └──┬───┘  └───┬────┘     ← mTLS via service mesh
     │     │        │          │
     └─────┴────────┴──────────┘
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
     PostgreSQL   Redis     Kafka
     (StatefulSet) (HA)   (Strimzi)

     Observability: Prometheus → Grafana → AlertManager → PagerDuty
     Policy: Kyverno (image verification, resource limits, labels)
     Secrets: External Secrets → Vault
     GitOps: ArgoCD app-of-apps
```

### Pattern 3: Multi-Region Active-Active (Tier 4)

```
                    Global DNS (Route53 / Cloud DNS)
                    Latency-based routing
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
     ┌────────────┐ ┌──────────┐ ┌──────────┐
     │  US-EAST   │ │ EU-WEST  │ │ AP-SOUTH │
     │  Cluster   │ │  Cluster │ │  Cluster │
     │            │ │          │ │          │
     │ Istio Mesh─┼─┤ Istio   ─┼─┤ Istio   │  ← Multi-cluster mesh
     │            │ │          │ │          │
     │ ArgoCD     │ │ ArgoCD   │ │ ArgoCD   │  ← Hub-spoke GitOps
     │ (spoke)    │ │ (spoke)  │ │ (spoke)  │
     └─────┬──────┘ └────┬─────┘ └────┬─────┘
           │              │            │
     ┌─────▼──────────────▼────────────▼─────┐
     │         Management Cluster              │
     │   ArgoCD Hub + Vault + Prometheus Fed   │
     │   Thanos / Cortex (multi-cluster metrics│)
     │   Policy Hub (Kyverno/OPA)              │
     └────────────────────────────────────────┘
```

### Pattern 4: Hyperscale Platform Engineering (Tier 5)

```
                 Developer Portal (Backstage)
                         │
                 Platform API (Crossplane / KCP)
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
     ┌──────────┐  ┌──────────┐  ┌──────────┐
     │  Fleet   │  │  Fleet   │  │  Fleet   │
     │ Cluster  │  │ Cluster  │  │ Cluster  │    ← 50-200+ clusters
     │ Group A  │  │ Group B  │  │ Group C  │    ← Karpenter autoscaling
     └────┬─────┘  └────┬─────┘  └────┬─────┘
          │              │             │
     ┌────▼──────────────▼─────────────▼─────┐
     │     Fleet Management (Rancher/GKE)     │
     │     Cilium Cluster Mesh (eBPF)         │
     │     Thanos Global View                 │
     │     Argo Rollouts (progressive)        │
     │     Crossplane (infra-as-K8s)          │
     │     Custom Operators (Kubebuilder)     │
     │     Cost: Kubecost + FinOps Dashboard  │
     └────────────────────────────────────────┘
```

---

## 7. RBAC & Authorization Patterns (Reference Content)

### Multi-Layer Authorization Model

```
Layer 1: Authentication (WHO)
  ├── OIDC (Dex, Keycloak, Okta) → K8s API Server
  ├── ServiceAccount tokens (workload identity)
  └── Cloud IAM mapping (IRSA for EKS, Workload Identity for GKE)

Layer 2: RBAC (WHAT CAN THEY DO)
  ├── ClusterRole → cluster-wide permissions
  ├── Role → namespace-scoped permissions
  ├── ClusterRoleBinding → bind users/groups to ClusterRoles
  └── RoleBinding → bind users/groups to Roles in a namespace

Layer 3: Admission Control (WHAT IS ALLOWED)
  ├── Pod Security Standards (restricted/baseline/privileged)
  ├── OPA Gatekeeper / Kyverno policies
  ├── ValidatingAdmissionPolicy (K8s native, v1.30+)
  └── Image verification (Cosign + Kyverno)

Layer 4: Runtime Enforcement (RUNTIME PROTECTION)
  ├── NetworkPolicy (pod-to-pod network isolation)
  ├── AuthorizationPolicy (Istio L7 authorization)
  ├── Seccomp / AppArmor profiles
  └── Falco runtime anomaly detection
```

### RBAC Tier Patterns

**Tier 1: Cluster Admin**
```yaml
# Single admin — acceptable for learning/dev only
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: admin-binding
subjects:
  - kind: User
    name: developer@company.com
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io
```

**Tier 2: Namespace-Scoped Roles**
```yaml
# Developer: deploy workloads within their namespace
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer
  namespace: app-prod
rules:
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: [""]
    resources: ["pods", "pods/log", "services", "configmaps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list"]  # Never "create" for devs in prod
---
# SRE: broader namespace access + debug capabilities
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: sre
  namespace: app-prod
rules:
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
    verbs: ["update", "patch"]
  - apiGroups: [""]
    resources: ["pods/exec", "pods/portforward"]
    verbs: ["create"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["delete"]  # Restart pods
```

**Tier 3: Hierarchical RBAC with Aggregation**
```yaml
# Aggregated ClusterRole: automatically collects rules from labeled roles
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: platform-viewer
  labels:
    rbac.company.com/aggregate-to-viewer: "true"
aggregationRule:
  clusterRoleSelectors:
    - matchLabels:
        rbac.company.com/aggregate-to-viewer: "true"
rules: []  # Auto-populated from matching roles

---
# Team-specific role that aggregates into platform-viewer
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: monitoring-viewer
  labels:
    rbac.company.com/aggregate-to-viewer: "true"
rules:
  - apiGroups: ["monitoring.coreos.com"]
    resources: ["prometheuses", "alertmanagers", "servicemonitors"]
    verbs: ["get", "list", "watch"]
```

**Tier 4-5: Cross-Cluster RBAC with OIDC**
```yaml
# Dex OIDC configuration for multi-cluster auth
apiVersion: v1
kind: ConfigMap
metadata:
  name: oidc-config
  namespace: kube-system
data:
  config.yaml: |
    issuer: https://dex.company.com
    connectors:
      - type: oidc
        id: okta
        name: Okta
        config:
          issuer: https://company.okta.com
          clientID: $CLIENT_ID
          clientSecret: $CLIENT_SECRET
          scopes: [openid, profile, email, groups]
          getUserInfo: true
    staticClients:
      - id: kubectl
        name: Kubectl
        redirectURIs: ['http://localhost:8000/callback']
---
# Map OIDC groups to K8s RBAC across clusters
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: sre-team-binding
subjects:
  - kind: Group
    name: oidc:sre-team  # OIDC group claim
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: sre-cluster-role
  apiGroup: rbac.authorization.k8s.io
```

---

## 8. Secrets Management Patterns (Reference Content)

### Secrets Maturity Model

| Tier | Method | Encryption | Rotation | Audit |
|------|--------|-----------|----------|-------|
| 1 | K8s Secrets (base64) | etcd encryption at rest | Manual | None |
| 2 | Sealed Secrets | Asymmetric (RSA) | Manual, GitOps-safe | kubectl audit |
| 3 | External Secrets + Vault | AES-256-GCM + TLS | Automatic (Vault lease) | Full audit log |
| 4 | Vault HA + Auto-Unseal | HSM-backed (FIPS) | Dynamic secrets (DB creds) | SIEM integration |
| 5 | Multi-tenant Vault + CSI | HSM + cross-region replication | Zero-touch rotation | Compliance-mapped |

### Tier 2: Sealed Secrets

```yaml
# Install: helm install sealed-secrets sealed-secrets/sealed-secrets -n kube-system
# Encrypt: kubeseal --format=yaml < secret.yaml > sealed-secret.yaml

apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: db-credentials
  namespace: app-prod
spec:
  encryptedData:
    DB_PASSWORD: AgBY8sKz...encrypted...==
    DB_HOST: AgCx7mNk...encrypted...==
  template:
    metadata:
      name: db-credentials
      namespace: app-prod
    type: Opaque
# Safe to commit to Git — only the cluster's private key can decrypt
```

### Tier 3: External Secrets Operator + Vault

```yaml
# SecretStore: connects to Vault
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: https://vault.company.com
      path: secret
      version: v2
      auth:
        kubernetes:
          mountPath: kubernetes
          role: external-secrets
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
---
# ExternalSecret: syncs Vault → K8s Secret
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: db-credentials
  namespace: app-prod
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: db-credentials
    creationPolicy: Owner
    deletionPolicy: Retain
  data:
    - secretKey: DB_PASSWORD
      remoteRef:
        key: services/payments/database
        property: password
    - secretKey: DB_HOST
      remoteRef:
        key: services/payments/database
        property: host
```

### Tier 4: Vault Dynamic Secrets (Database)

```hcl
# Vault config: dynamic database credentials
resource "vault_database_secret_backend" "postgres" {
  path = "database"

  postgresql {
    connection_url = "postgresql://{{username}}:{{password}}@db.internal:5432/mydb"
    username       = "vault_admin"
    password       = var.db_admin_password
  }
}

resource "vault_database_secret_backend_role" "app_readonly" {
  backend = vault_database_secret_backend.postgres.path
  name    = "app-readonly"
  db_name = "postgresql"

  creation_statements = [
    "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}';",
    "GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";",
  ]

  default_ttl = "1h"
  max_ttl     = "24h"
}
# Credentials auto-rotate every hour — zero hardcoded passwords
```

### Tier 5: CSI Secret Store Driver

```yaml
# Mount Vault secrets as files (no K8s Secret object created)
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: vault-db-creds
  namespace: app-prod
spec:
  provider: vault
  parameters:
    vaultAddress: https://vault.company.com
    roleName: app-readonly
    objects: |
      - objectName: "db-password"
        secretPath: "database/creds/app-readonly"
        secretKey: "password"
      - objectName: "db-username"
        secretPath: "database/creds/app-readonly"
        secretKey: "username"
---
# Pod mounts secrets as files — never in env vars, never in etcd
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payments-api
spec:
  template:
    spec:
      serviceAccountName: payments-api
      containers:
        - name: api
          volumeMounts:
            - name: secrets
              mountPath: /mnt/secrets
              readOnly: true
      volumes:
        - name: secrets
          csi:
            driver: secrets-store.csi.k8s.io
            readOnly: true
            volumeAttributes:
              secretProviderClass: vault-db-creds
```

---

## 9. Networking Patterns (Reference Content)

### Network Policy: Default Deny + Explicit Allow

```yaml
# Default deny all ingress and egress for a namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: payments-prod
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
# Allow ingress from API gateway only
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-from-gateway
  namespace: payments-prod
spec:
  podSelector:
    matchLabels:
      app: payments-api
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: gateway
          podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - protocol: TCP
          port: 8080
---
# Allow egress to database and DNS only
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-db-egress
  namespace: payments-prod
spec:
  podSelector:
    matchLabels:
      app: payments-api
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: databases
      ports:
        - protocol: TCP
          port: 5432
    - to:  # DNS resolution
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
```

### Gateway API (Modern Ingress Replacement)

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: main-gateway
  namespace: gateway
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  gatewayClassName: istio  # or cilium, nginx
  listeners:
    - name: https
      port: 443
      protocol: HTTPS
      tls:
        mode: Terminate
        certificateRefs:
          - name: wildcard-tls
      allowedRoutes:
        namespaces:
          from: Selector
          selector:
            matchLabels:
              gateway-access: "true"
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: payments-route
  namespace: payments-prod
spec:
  parentRefs:
    - name: main-gateway
      namespace: gateway
  hostnames: ["api.company.com"]
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /payments
      backendRefs:
        - name: payments-api
          port: 8080
          weight: 100
    - matches:
        - path:
            type: PathPrefix
            value: /payments
          headers:
            - name: x-canary
              value: "true"
      backendRefs:
        - name: payments-api-canary
          port: 8080
          weight: 100
```

### Istio Service Mesh Authorization

```yaml
# L7 authorization: only allow GET/POST from specific service accounts
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: payments-authz
  namespace: payments-prod
spec:
  selector:
    matchLabels:
      app: payments-api
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/gateway/sa/api-gateway"
              - "cluster.local/ns/orders-prod/sa/orders-api"
      to:
        - operation:
            methods: ["GET", "POST"]
            paths: ["/api/v1/payments/*"]
    - from:
        - source:
            principals:
              - "cluster.local/ns/platform/sa/prometheus"
      to:
        - operation:
            methods: ["GET"]
            paths: ["/metrics"]
```

---

## 10. Policy Engine Patterns (Reference Content)

### Kyverno: Enforce Best Practices

```yaml
# Block images without digest or from untrusted registries
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-trusted-images
spec:
  validationFailureAction: Enforce
  rules:
    - name: require-registry
      match:
        any:
          - resources:
              kinds: [Pod]
      validate:
        message: "Images must come from approved registries"
        pattern:
          spec:
            containers:
              - image: "registry.company.com/* | gcr.io/distroless/*"
    - name: require-image-digest
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaces: ["*-prod"]
      validate:
        message: "Production images must use digest references"
        pattern:
          spec:
            containers:
              - image: "*@sha256:*"

---
# Auto-inject labels, resource limits, security context
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: mutate-defaults
spec:
  rules:
    - name: add-default-resources
      match:
        any:
          - resources:
              kinds: [Pod]
      mutate:
        patchStrategicMerge:
          spec:
            containers:
              - (name): "*"
                resources:
                  limits:
                    memory: "512Mi"
                    cpu: "500m"
                  requests:
                    memory: "128Mi"
                    cpu: "100m"
    - name: enforce-security-context
      match:
        any:
          - resources:
              kinds: [Pod]
      mutate:
        patchStrategicMerge:
          spec:
            securityContext:
              runAsNonRoot: true
              seccompProfile:
                type: RuntimeDefault
            containers:
              - (name): "*"
                securityContext:
                  allowPrivilegeEscalation: false
                  readOnlyRootFilesystem: true
                  capabilities:
                    drop: ["ALL"]

---
# Verify Cosign signatures on images
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-image-signatures
spec:
  validationFailureAction: Enforce
  rules:
    - name: verify-cosign
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaces: ["*-prod"]
      verifyImages:
        - imageReferences: ["registry.company.com/*"]
          attestors:
            - entries:
                - keyless:
                    issuer: "https://token.actions.githubusercontent.com"
                    subject: "https://github.com/myorg/*"
                    rekor:
                      url: https://rekor.sigstore.dev
```

### OPA Gatekeeper: Constraint Templates (Tier 4+)

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8sresourcelimits
spec:
  crd:
    spec:
      names:
        kind: K8sResourceLimits
      validation:
        openAPIV3Schema:
          type: object
          properties:
            maxCPU:
              type: string
            maxMemory:
              type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8sresourcelimits
        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.resources.limits.cpu
          msg := sprintf("Container %v must have CPU limits", [container.name])
        }
        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.resources.limits.memory
          msg := sprintf("Container %v must have memory limits", [container.name])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sResourceLimits
metadata:
  name: must-have-limits
spec:
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
    namespaces: ["*-prod", "*-staging"]
  parameters:
    maxCPU: "4"
    maxMemory: "8Gi"
```

---

## 11. Observability Stack (Reference Content)

### Prometheus + Grafana (kube-prometheus-stack)

```yaml
# Helm values for kube-prometheus-stack
prometheus:
  prometheusSpec:
    retention: 30d
    storageSpec:
      volumeClaimTemplate:
        spec:
          storageClassName: gp3
          resources:
            requests:
              storage: 100Gi
    serviceMonitorSelectorNilUsesHelmValues: false
    podMonitorSelectorNilUsesHelmValues: false
    resources:
      requests: { cpu: 500m, memory: 2Gi }
      limits: { cpu: 2, memory: 8Gi }

grafana:
  adminPassword: ${GRAFANA_ADMIN_PASSWORD}
  dashboardProviders:
    dashboardproviders.yaml:
      apiVersion: 1
      providers:
        - name: default
          folder: ''
          type: file
          options:
            path: /var/lib/grafana/dashboards
  dashboards:
    default:
      cluster-overview: { gnetId: 7249, datasource: Prometheus }
      pod-resources: { gnetId: 6417, datasource: Prometheus }
      namespace-workloads: { gnetId: 15758, datasource: Prometheus }

alertmanager:
  config:
    global:
      resolve_timeout: 5m
    route:
      receiver: default
      group_by: [namespace, alertname]
      group_wait: 30s
      group_interval: 5m
      repeat_interval: 4h
      routes:
        - match: { severity: critical }
          receiver: pagerduty
        - match: { severity: warning }
          receiver: slack
    receivers:
      - name: default
        slack_configs:
          - api_url: ${SLACK_WEBHOOK_URL}
            channel: '#k8s-alerts'
      - name: pagerduty
        pagerduty_configs:
          - routing_key: ${PAGERDUTY_KEY}
            severity: critical
      - name: slack
        slack_configs:
          - api_url: ${SLACK_WEBHOOK_URL}
            channel: '#k8s-warnings'
```

### SLO/SLI Alerting

```yaml
# PrometheusRule: SLO-based alerting
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: payments-slo
  namespace: payments-prod
spec:
  groups:
    - name: payments-slos
      rules:
        # SLI: Request success rate
        - record: payments:request_success_rate:5m
          expr: |
            sum(rate(http_requests_total{namespace="payments-prod",code=~"2.."}[5m]))
            / sum(rate(http_requests_total{namespace="payments-prod"}[5m]))

        # SLO: 99.9% availability — alert when burning error budget
        - alert: PaymentsSLOBreach
          expr: payments:request_success_rate:5m < 0.999
          for: 5m
          labels:
            severity: critical
            team: payments
          annotations:
            summary: "Payments API below 99.9% SLO"
            description: "Success rate {{ $value | humanizePercentage }} (target: 99.9%)"

        # SLI: P99 latency
        - record: payments:request_latency_p99:5m
          expr: |
            histogram_quantile(0.99,
              sum(rate(http_request_duration_seconds_bucket{namespace="payments-prod"}[5m]))
              by (le))

        # SLO: P99 < 500ms
        - alert: PaymentsLatencySLOBreach
          expr: payments:request_latency_p99:5m > 0.5
          for: 5m
          labels:
            severity: warning
            team: payments
          annotations:
            summary: "Payments P99 latency above 500ms SLO"
```

### Multi-Cluster Observability (Thanos)

```yaml
# Thanos sidecar on each cluster's Prometheus
# Thanos Query in management cluster aggregates all
thanos:
  query:
    stores:
      - dnssrv+_grpc._tcp.thanos-store-gateway.monitoring.svc  # local
      - thanos-sidecar.us-east.monitoring.svc:10901             # us-east
      - thanos-sidecar.eu-west.monitoring.svc:10901             # eu-west
      - thanos-sidecar.ap-south.monitoring.svc:10901            # ap-south
  storeGateway:
    persistence:
      storageClass: gp3
      size: 500Gi
  compactor:
    retention:
      retentionResolutionRaw: 30d
      retentionResolution5m: 90d
      retentionResolution1h: 1y
  bucket:
    type: S3
    config:
      bucket: thanos-metrics-company
      endpoint: s3.amazonaws.com
      region: us-east-1
```

---

## 12. GitOps Patterns (Reference Content)

### ArgoCD App-of-Apps

```yaml
# Root Application: manages all team applications
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/company/k8s-gitops
    targetRevision: main
    path: apps
  destination:
    server: https://kubernetes.default.svc
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
---
# ApplicationSet: auto-generate apps per team/environment
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: team-apps
  namespace: argocd
spec:
  generators:
    - matrix:
        generators:
          - git:
              repoURL: https://github.com/company/k8s-gitops
              directories:
                - path: "teams/*/envs/*"
          - list:
              elements:
                - cluster: us-east
                  url: https://us-east.k8s.company.com
                - cluster: eu-west
                  url: https://eu-west.k8s.company.com
  template:
    metadata:
      name: "{{path.basename}}-{{cluster}}"
    spec:
      project: "{{path[1]}}"  # team name
      source:
        repoURL: https://github.com/company/k8s-gitops
        targetRevision: main
        path: "{{path}}"
      destination:
        server: "{{url}}"
        namespace: "{{path.basename}}"
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
```

### GitOps Repo Structure

```
k8s-gitops/
├── apps/                          ← Root app-of-apps
│   ├── platform.yaml              ← Platform components (cert-manager, ingress, etc.)
│   ├── monitoring.yaml            ← Observability stack
│   └── teams.yaml                 ← Team ApplicationSet
├── platform/
│   ├── cert-manager/
│   │   ├── kustomization.yaml
│   │   └── values.yaml
│   ├── ingress-nginx/
│   ├── external-secrets/
│   ├── kyverno/
│   └── prometheus-stack/
├── teams/
│   ├── payments/
│   │   ├── base/                  ← Shared manifests (Kustomize base)
│   │   │   ├── deployment.yaml
│   │   │   ├── service.yaml
│   │   │   ├── hpa.yaml
│   │   │   ├── pdb.yaml
│   │   │   ├── networkpolicy.yaml
│   │   │   └── kustomization.yaml
│   │   └── envs/
│   │       ├── dev/               ← Dev overrides (1 replica, debug)
│   │       │   └── kustomization.yaml
│   │       ├── staging/           ← Staging overrides (2 replicas)
│   │       │   └── kustomization.yaml
│   │       └── prod/              ← Prod overrides (3+ replicas, PDB)
│   │           ├── kustomization.yaml
│   │           └── sealed-secret.yaml
│   ├── search/
│   │   ├── base/
│   │   └── envs/
│   └── orders/
│       ├── base/
│       └── envs/
└── clusters/                      ← Cluster-specific configs
    ├── us-east/
    │   └── kustomization.yaml
    └── eu-west/
        └── kustomization.yaml
```

### Progressive Delivery (Argo Rollouts)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: payments-api
  namespace: payments-prod
spec:
  replicas: 5
  revisionHistoryLimit: 3
  selector:
    matchLabels:
      app: payments-api
  strategy:
    canary:
      canaryService: payments-api-canary
      stableService: payments-api-stable
      trafficRouting:
        istio:
          virtualServices:
            - name: payments-api
              routes: [primary]
      steps:
        - setWeight: 5       # 5% traffic to canary
        - pause: { duration: 5m }
        - analysis:           # Automated analysis
            templates:
              - templateName: success-rate
            args:
              - name: service-name
                value: payments-api-canary
        - setWeight: 25
        - pause: { duration: 10m }
        - analysis:
            templates:
              - templateName: success-rate
        - setWeight: 50
        - pause: { duration: 10m }
        - setWeight: 100
---
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
spec:
  args:
    - name: service-name
  metrics:
    - name: success-rate
      interval: 60s
      successCondition: result[0] >= 0.999
      failureLimit: 3
      provider:
        prometheus:
          address: http://prometheus.monitoring:9090
          query: |
            sum(rate(http_requests_total{service="{{args.service-name}}",code=~"2.."}[2m]))
            / sum(rate(http_requests_total{service="{{args.service-name}}"}[2m]))
```

---

## 13. Disaster Recovery Patterns (Reference Content)

### DR Tiers

| Tier | Strategy | RPO | RTO | Method |
|------|----------|-----|-----|--------|
| 2 | Backup + Restore | 24h | 4h | Velero daily backups |
| 3 | Multi-AZ + Backup | 1h | 1h | Velero hourly + topology spread |
| 4 | Active-Passive Multi-Region | 15m | 30m | Cross-region Velero + DNS failover |
| 5 | Active-Active Multi-Region | ~0 (RPO) | ~0 (RTO) | Replicated state + global load balancing |

### Velero Backup Configuration

```yaml
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: daily-full-backup
  namespace: velero
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM UTC
  template:
    includedNamespaces: ["*"]
    excludedNamespaces: ["kube-system", "velero"]
    includedResources: ["*"]
    storageLocation: aws-s3-backup
    volumeSnapshotLocations: ["aws-ebs"]
    ttl: 720h  # 30 days retention
    snapshotMoveData: true
---
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: hourly-critical-backup
  namespace: velero
spec:
  schedule: "0 * * * *"  # Every hour
  template:
    includedNamespaces: ["payments-prod", "orders-prod"]
    labelSelector:
      matchLabels:
        backup: critical
    storageLocation: aws-s3-backup-cross-region
    ttl: 168h  # 7 days
```

### Multi-Region Failover

```yaml
# ExternalDNS + health checks for automatic failover
apiVersion: externaldns.k8s.io/v1alpha1
kind: DNSEndpoint
metadata:
  name: payments-failover
spec:
  endpoints:
    - dnsName: api.company.com
      recordType: A
      targets:
        - us-east-lb.company.com  # Primary
        - eu-west-lb.company.com  # Secondary
      setIdentifier: us-east
      providerSpecific:
        - name: aws/failover
          value: PRIMARY
        - name: aws/health-check-id
          value: ${US_EAST_HEALTH_CHECK_ID}
```

---

## 14. Cost Optimization (Reference Content)

### Resource Right-Sizing

```yaml
# VPA: automatically recommend/set resource requests
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: payments-api-vpa
  namespace: payments-prod
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: payments-api
  updatePolicy:
    updateMode: "Auto"  # "Off" for recommendations only
  resourcePolicy:
    containerPolicies:
      - containerName: api
        minAllowed:
          cpu: 100m
          memory: 128Mi
        maxAllowed:
          cpu: 4
          memory: 8Gi
```

### Karpenter Node Autoscaling

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  template:
    spec:
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: default
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64", "arm64"]
        - key: karpenter.k8s.aws/instance-family
          operator: In
          values: ["m7g", "m7i", "c7g", "c7i", "r7g", "r7i"]
        - key: karpenter.k8s.aws/instance-size
          operator: In
          values: ["medium", "large", "xlarge", "2xlarge"]
      taints:
        - key: workload-type
          value: general
          effect: NoSchedule
  limits:
    cpu: 1000
    memory: 2000Gi
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 30s
    budgets:
      - nodes: "10%"  # Max 10% nodes disrupted simultaneously
---
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: default
spec:
  amiSelectorTerms:
    - alias: bottlerocket@latest
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: ${CLUSTER_NAME}
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: ${CLUSTER_NAME}
  blockDeviceMappings:
    - deviceName: /dev/xvda
      ebs:
        volumeType: gp3
        volumeSize: 100Gi
        encrypted: true
```

### Cost Visibility (Kubecost)

```yaml
# Helm values for Kubecost
kubecostProductConfigs:
  clusterName: us-east-prod
  currencyCode: USD
  cloudIntegrationJSON: |
    {
      "aws": [{
        "athenaBucketName": "s3://kubecost-athena-results",
        "athenaRegion": "us-east-1",
        "athenaDatabase": "athenacurcfn_cur_report",
        "athenaTable": "cur_report",
        "projectID": "${AWS_ACCOUNT_ID}"
      }]
    }
networkCosts:
  enabled: true
  config:
    services:
      amazon-web-services: true
```

---

## 15. Compliance Mapping (Reference Content)

### Control-to-Implementation

| Compliance Control | K8s Implementation |
|---|---|
| **SOC 2 CC6.1** Access Control | RBAC + OIDC + namespace isolation + audit logging |
| **SOC 2 CC6.7** Encryption | etcd encryption, TLS everywhere, Vault for secrets |
| **SOC 2 CC7.2** System Monitoring | Prometheus + Falco + audit logs to SIEM |
| **HIPAA** PHI Isolation | Dedicated node pools, NetworkPolicy, encrypted PVCs |
| **HIPAA** Audit Trails | K8s audit policy → CloudWatch/Stackdriver → WORM storage |
| **HIPAA** Access Logging | OIDC + RBAC audit + Falco runtime monitoring |
| **PCI-DSS 1.3** Network Segmentation | NetworkPolicy default deny, namespace isolation, mesh mTLS |
| **PCI-DSS 6.3** Vulnerability Management | Kyverno image verification, Trivy scanning in CI |
| **PCI-DSS 10.2** Audit Logging | K8s audit policy (RequestResponse level) + Falco |
| **FedRAMP** Boundary Protection | Air-gapped clusters, private API server, bastion access |
| **FedRAMP** Config Management | GitOps (immutable deployments), OPA policy enforcement |

### K8s Audit Policy

```yaml
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  # Log all secret access at RequestResponse level
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["secrets"]
  # Log all RBAC changes
  - level: RequestResponse
    resources:
      - group: "rbac.authorization.k8s.io"
        resources: ["roles", "rolebindings", "clusterroles", "clusterrolebindings"]
  # Log pod exec (compliance-critical)
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["pods/exec", "pods/portforward"]
  # Log all write operations at Request level
  - level: Request
    verbs: ["create", "update", "patch", "delete"]
  # Log everything else at Metadata level
  - level: Metadata
    omitStages: ["RequestReceived"]
```

---

## 16. Output Specification

### Tier 1 Output
- [ ] Deployment with resource requests/limits
- [ ] Service (ClusterIP)
- [ ] ConfigMap for non-sensitive configuration
- [ ] K8s Secret for sensitive values
- [ ] Namespace definition
- [ ] Basic Ingress or NodePort
- [ ] README with kubectl apply instructions

### Tier 2 Output (includes Tier 1 +)
- [ ] Namespace with ResourceQuota and LimitRange
- [ ] RBAC Role + RoleBinding (per namespace)
- [ ] Sealed Secrets (GitOps-safe)
- [ ] NetworkPolicy (default deny + explicit allows)
- [ ] HPA (Horizontal Pod Autoscaler)
- [ ] PDB (PodDisruptionBudget)
- [ ] Ingress with TLS (cert-manager)
- [ ] Pod Security Standards (restricted)
- [ ] Health checks (liveness, readiness, startup probes)
- [ ] Prometheus ServiceMonitor
- [ ] Helm chart or Kustomize base + overlays

### Tier 3 Output (includes Tier 2 +)
- [ ] Multi-namespace strategy with hierarchy
- [ ] Kyverno/OPA policies (images, resources, security)
- [ ] External Secrets + Vault integration
- [ ] Gateway API configuration
- [ ] Cilium NetworkPolicy (L7)
- [ ] ArgoCD Application + ApplicationSet
- [ ] GitOps repo structure (app-of-apps)
- [ ] kube-prometheus-stack with custom dashboards
- [ ] Loki + Promtail for log aggregation
- [ ] PrometheusRule for SLO alerting
- [ ] Velero backup schedules
- [ ] Topology spread constraints (multi-AZ)

### Tier 4 Output (includes Tier 3 +)
- [ ] Multi-cluster ArgoCD hub-spoke
- [ ] Istio/Linkerd service mesh configuration
- [ ] Cross-cluster service discovery
- [ ] Multi-region DNS failover (ExternalDNS)
- [ ] Thanos for federated metrics
- [ ] Vault HA with cross-cluster replication
- [ ] Argo Rollouts progressive delivery
- [ ] Cross-region Velero backup/restore
- [ ] Compliance audit policy
- [ ] Multi-cluster RBAC via OIDC federation

### Tier 5 Output (includes Tier 4 +)
- [ ] Fleet management configuration (Rancher/GKE Fleet)
- [ ] Cilium Cluster Mesh (eBPF networking)
- [ ] Crossplane compositions (infra-as-K8s)
- [ ] Custom operator scaffolding (Kubebuilder)
- [ ] Karpenter NodePool configurations
- [ ] Kubecost integration for FinOps
- [ ] Platform API (Backstage templates)
- [ ] Virtual clusters (vcluster) for tenant isolation
- [ ] Multi-tenant Vault with HSM
- [ ] SLSA provenance verification at admission
- [ ] eBPF-based runtime security (Tetragon)

---

## 17. Error Handling

| Scenario | Detection | Action |
|----------|-----------|--------|
| Pod stuck in CrashLoopBackOff | Events + container logs | Check liveness probe, resource limits, startup time |
| ImagePullBackOff | Events | Verify image exists, registry auth, image pull secret |
| Pending pod (unschedulable) | `kubectl describe pod` | Check node resources, taints/tolerations, affinity rules |
| OOMKilled | Container status | Increase memory limits, check for memory leaks |
| Evicted pod | Events | Node under disk/memory pressure — increase node pool |
| RBAC permission denied | API server 403 | Check Role/RoleBinding, verify subject name/group |
| NetworkPolicy blocking traffic | Connection timeout | Verify policy selectors, check DNS egress rule |
| Secret not found | Deployment events | Check secret name, namespace, external sync status |
| Ingress 502/503 | Ingress controller logs | Verify backend service, pod readiness, health checks |
| PDB blocking drain | Node drain timeout | Adjust PDB minAvailable/maxUnavailable, check replicas |
| ArgoCD sync failed | ArgoCD UI/events | Check manifest validation, RBAC, diff analysis |
| HPA not scaling | HPA status | Verify metrics-server, check metric availability |
| Vault secret sync failed | ESO events | Check VaultAuth, policy, secret path, ESO logs |
| cert-manager challenge failed | Certificate events | Verify DNS records, ACME issuer, rate limits |

---

## 18. Domain Standards

### Must Follow

- [ ] All workloads have resource requests AND limits
- [ ] All pods run as non-root (securityContext.runAsNonRoot: true)
- [ ] All containers have readOnly root filesystem where possible
- [ ] All containers drop ALL capabilities, add only needed
- [ ] All namespaces have ResourceQuota and LimitRange (Tier 2+)
- [ ] All namespaces have default-deny NetworkPolicy (Tier 2+)
- [ ] All secrets encrypted at rest (EncryptionConfiguration)
- [ ] All production images use digest references (not tags)
- [ ] All ingress uses TLS (no plaintext HTTP in production)
- [ ] All RBAC follows least-privilege principle
- [ ] Labels: app.kubernetes.io/name, app.kubernetes.io/version, app.kubernetes.io/component
- [ ] Pod topology spread constraints for HA (Tier 2+)
- [ ] PodDisruptionBudget for all production deployments
- [ ] Graceful shutdown handling (preStop hook + terminationGracePeriodSeconds)
- [ ] Health probes (liveness + readiness + startup for slow-starting apps)

### Must Avoid

- Running as root or with privileged: true
- Using `default` namespace for production workloads
- Hardcoding secrets in manifests (use Sealed Secrets / ESO / Vault)
- Using `latest` tag for images in production
- ClusterRoleBinding to `cluster-admin` for application workloads
- Missing NetworkPolicies (open cluster networking)
- No resource limits (leads to noisy neighbor / OOM)
- hostNetwork: true or hostPID: true without justification
- Storing sensitive data in ConfigMaps
- Missing PDB (rolling updates can take down all pods)
- Using NodePort or LoadBalancer per-service (use Ingress/Gateway)
- Committing unencrypted secrets to Git
- Skip pod security standards enforcement
- Using emptyDir for persistent data

---

## 19. Output Checklist

Before delivering any Kubernetes setup, verify ALL items:

### Architecture
- [ ] Tier appropriate for requirements
- [ ] Namespace strategy defined
- [ ] Resource packaging (Helm/Kustomize) consistent
- [ ] GitOps configured (Tier 3+)
- [ ] Multi-cluster strategy (Tier 4+)

### Security
- [ ] RBAC configured (least privilege)
- [ ] Pod Security Standards enforced
- [ ] NetworkPolicies applied (default deny + allow)
- [ ] Secrets management at appropriate tier
- [ ] Security contexts on all containers
- [ ] Policy engine rules (Tier 2+)
- [ ] Image verification (Tier 3+)
- [ ] Audit policy configured (Tier 3+)

### Reliability
- [ ] Resource requests AND limits on all containers
- [ ] Liveness, readiness, and startup probes
- [ ] PodDisruptionBudget for production workloads
- [ ] HPA configured with appropriate metrics
- [ ] Topology spread constraints (multi-AZ)
- [ ] Graceful shutdown (preStop + terminationGracePeriod)
- [ ] Backup strategy (Velero, Tier 2+)

### Observability
- [ ] Prometheus metrics exported (ServiceMonitor)
- [ ] Logging to stdout/stderr (collected by agent)
- [ ] Health check endpoints
- [ ] SLO/SLI alerting rules (Tier 3+)
- [ ] Dashboards provisioned (Tier 2+)

### Operations
- [ ] Labels and annotations consistent
- [ ] Deployment strategy defined (RollingUpdate/Canary)
- [ ] Environment-specific overlays (dev/staging/prod)
- [ ] Secret rotation documented
- [ ] Runbook / DR procedure documented
- [ ] Cost visibility configured (Tier 3+)

---

## 20. Skill Structure (For skill-creator-pro)

```
k8s-mastery/
├── SKILL.md                                ← <500 lines, workflow + decision trees
├── references/
│   ├── core-resources.md                   ← Deployment, Service, ConfigMap, StatefulSet, Jobs
│   ├── namespace-patterns.md               ← Namespace strategy, ResourceQuota, LimitRange, HNC
│   ├── rbac-patterns.md                    ← Roles, Bindings, OIDC, Aggregation, Cross-cluster
│   ├── secrets-management.md               ← K8s Secrets, Sealed Secrets, ESO, Vault, CSI Driver
│   ├── networking.md                       ← NetworkPolicy, Gateway API, Ingress, Service types
│   ├── service-mesh.md                     ← Istio, Linkerd, Cilium mesh, mTLS, traffic mgmt
│   ├── security.md                         ← Pod Security Standards, security context, Falco
│   ├── policy-engines.md                   ← Kyverno, OPA Gatekeeper, ValidatingAdmissionPolicy
│   ├── observability.md                    ← Prometheus, Grafana, Loki, Tempo, Thanos, SLOs
│   ├── gitops-patterns.md                  ← ArgoCD, Flux, app-of-apps, progressive delivery
│   ├── multi-cluster.md                    ← Federation, cross-cluster discovery, hub-spoke
│   ├── hyperscale-patterns.md              ← Fleet mgmt, Crossplane, custom operators, eBPF
│   ├── disaster-recovery.md                ← Velero, etcd backup, multi-region failover, DR tiers
│   ├── cost-optimization.md                ← VPA, Karpenter, spot instances, Kubecost, FinOps
│   ├── production-hardening.md             ← Full production checklist, compliance, audit
│   ├── helm-kustomize.md                   ← Helm chart patterns, Kustomize overlays, Timoni
│   └── anti-patterns.md                    ← 25+ common K8s mistakes with fixes
├── assets/templates/
│   ├── deployment_basic.yaml               ← Tier 1 complete deployment
│   ├── deployment_production.yaml          ← Tier 2 hardened deployment (all probes, PDB, HPA)
│   ├── namespace_enterprise.yaml           ← Tier 3 namespace with quota + limitrange + netpol
│   ├── helm_chart/                         ← Complete Helm chart skeleton
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   ├── values-prod.yaml
│   │   └── templates/
│   │       ├── deployment.yaml
│   │       ├── service.yaml
│   │       ├── ingress.yaml
│   │       ├── hpa.yaml
│   │       ├── pdb.yaml
│   │       ├── networkpolicy.yaml
│   │       ├── serviceaccount.yaml
│   │       ├── servicemonitor.yaml
│   │       └── _helpers.tpl
│   ├── kustomize_base/                     ← Kustomize base for microservices
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── kustomize_overlays/                 ← Per-environment overlays
│   │   ├── dev/kustomization.yaml
│   │   ├── staging/kustomization.yaml
│   │   └── prod/kustomization.yaml
│   ├── argocd_app_of_apps.yaml             ← ArgoCD root application
│   ├── argocd_applicationset.yaml          ← Multi-cluster ApplicationSet
│   ├── kyverno_policies.yaml               ← Production policy bundle
│   ├── external_secret.yaml                ← Vault integration template
│   ├── prometheus_rules.yaml               ← SLO alerting rules
│   ├── velero_schedule.yaml                ← Backup schedule template
│   ├── gateway_api.yaml                    ← Gateway + HTTPRoute template
│   └── karpenter_nodepool.yaml             ← Node autoscaling template
└── scripts/
    └── scaffold_k8s.py                     ← Project generator for all 5 tiers
        # Usage: python scaffold_k8s.py <name> --tier <1|2|3|4|5>
        #   --provider <eks|gke|aks|onprem>
        #   --packaging <helm|kustomize|raw>
        #   --gitops <argocd|flux|none>
        #   --mesh <none|istio|linkerd|cilium>
        #   --secrets <k8s|sealed|vault>
        #   --path <output-dir>
```

---

## 21. SDK/Tool Versions (February 2026)

| Tool | Version | Purpose |
|------|---------|---------|
| Kubernetes | 1.31+ | Orchestration platform |
| Helm | 3.16+ | Package management |
| Kustomize | 5.5+ | Manifest overlays |
| ArgoCD | 2.13+ | GitOps CD |
| Argo Rollouts | 1.7+ | Progressive delivery |
| Istio | 1.24+ | Service mesh |
| Linkerd | 2.16+ | Lightweight service mesh |
| Cilium | 1.16+ | eBPF CNI + mesh |
| Kyverno | 1.13+ | Policy engine |
| OPA Gatekeeper | 3.18+ | Policy engine |
| External Secrets | 0.12+ | Secret sync operator |
| HashiCorp Vault | 1.18+ | Secrets management |
| Sealed Secrets | 0.27+ | GitOps secrets encryption |
| Prometheus | 2.55+ | Metrics collection |
| Grafana | 11.3+ | Dashboards |
| Loki | 3.3+ | Log aggregation |
| Tempo | 2.6+ | Distributed tracing |
| Thanos | 0.37+ | Multi-cluster metrics |
| Velero | 1.15+ | Backup and restore |
| cert-manager | 1.16+ | Certificate management |
| Karpenter | 1.1+ | Node autoscaling |
| Crossplane | 1.18+ | Infrastructure as K8s |
| Kubecost | 2.5+ | Cost visibility |
| Falco | 0.39+ | Runtime security |
| Tetragon | 1.3+ | eBPF security observability |
| Kubebuilder | 4.3+ | Operator framework |

---

## 22. Official Documentation Links

| Resource | URL | Use For |
|----------|-----|---------|
| Kubernetes Docs | https://kubernetes.io/docs/ | Core reference |
| Kubernetes API Ref | https://kubernetes.io/docs/reference/kubernetes-api/ | API spec |
| Helm Docs | https://helm.sh/docs/ | Chart development |
| ArgoCD Docs | https://argo-cd.readthedocs.io/ | GitOps patterns |
| Argo Rollouts | https://argoproj.github.io/rollouts/ | Progressive delivery |
| Istio Docs | https://istio.io/latest/docs/ | Service mesh |
| Cilium Docs | https://docs.cilium.io/ | eBPF networking |
| Kyverno Docs | https://kyverno.io/docs/ | Policy engine |
| OPA Gatekeeper | https://open-policy-agent.github.io/gatekeeper/ | Policy engine |
| External Secrets | https://external-secrets.io/latest/ | Secret sync |
| Vault Docs | https://developer.hashicorp.com/vault/docs | Secrets management |
| Prometheus | https://prometheus.io/docs/ | Monitoring |
| Gateway API | https://gateway-api.sigs.k8s.io/ | Modern ingress |
| Karpenter | https://karpenter.sh/docs/ | Node scaling |
| Crossplane | https://docs.crossplane.io/ | Infrastructure |
| Velero | https://velero.io/docs/ | Backup/restore |
| cert-manager | https://cert-manager.io/docs/ | TLS certificates |
| Kubecost | https://docs.kubecost.com/ | Cost management |
| Falco | https://falco.org/docs/ | Runtime security |
| Tetragon | https://tetragon.io/docs/ | eBPF security |

---

*Spec version: 1.0 — February 2026*
*Target: skill-creator-pro → k8s-mastery skill*
*Standard: Google / Meta / Netflix / Uber / Stripe-grade infrastructure*
