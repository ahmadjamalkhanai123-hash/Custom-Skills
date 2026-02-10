# Namespace Patterns

Namespace strategy, ResourceQuota, LimitRange, Hierarchical Namespace Controller, and virtual cluster isolation.

---

## Tier-Based Namespace Strategy

### Decision Tree

```
How many teams share the cluster?

Single developer / learning?
  -> Tier 1: default namespace

Single team, multiple environments?
  -> Tier 2: Per-environment (dev, staging, prod)

Multiple teams, compliance requirements?
  -> Tier 3: Per-team+env (team-payments-prod) with quotas

Large org, deep hierarchy, delegated admin?
  -> Tier 4: Hierarchical Namespace Controller (HNC)

Multi-tenant SaaS, full isolation required?
  -> Tier 5: vcluster (virtual clusters)
```

---

## Tier 1: Default Namespace

For learning and single-workload development only.

```yaml
# No namespace manifest needed; use default
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  # namespace: default (implicit)
```

**When to move beyond Tier 1:** As soon as you have more than one workload or any production traffic.

---

## Tier 2: Per-Environment Namespaces

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: dev
  labels:
    env: dev
    team: platform
    cost-center: engineering
    kubernetes.io/metadata.name: dev
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/warn: restricted
---
apiVersion: v1
kind: Namespace
metadata:
  name: staging
  labels:
    env: staging
    team: platform
    cost-center: engineering
    kubernetes.io/metadata.name: staging
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
---
apiVersion: v1
kind: Namespace
metadata:
  name: prod
  labels:
    env: prod
    team: platform
    cost-center: engineering
    kubernetes.io/metadata.name: prod
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
```

### Tier 2 ResourceQuota (per environment)

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: dev-quota
  namespace: dev
spec:
  hard:
    requests.cpu: "8"
    requests.memory: 16Gi
    limits.cpu: "16"
    limits.memory: 32Gi
    pods: "50"
    services: "20"
    persistentvolumeclaims: "10"
    requests.storage: 100Gi
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: prod-quota
  namespace: prod
spec:
  hard:
    requests.cpu: "32"
    requests.memory: 64Gi
    limits.cpu: "64"
    limits.memory: 128Gi
    pods: "200"
    services: "50"
    persistentvolumeclaims: "50"
    requests.storage: 500Gi
    count/deployments.apps: "50"
    count/statefulsets.apps: "20"
    count/jobs.batch: "100"
    count/cronjobs.batch: "20"
```

### Tier 2 LimitRange

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: dev
spec:
  limits:
    - type: Container
      default:               # applied when no limits set
        cpu: 500m
        memory: 256Mi
      defaultRequest:        # applied when no requests set
        cpu: 100m
        memory: 128Mi
      min:
        cpu: 50m
        memory: 64Mi
      max:
        cpu: "4"
        memory: 4Gi
    - type: Pod
      max:
        cpu: "8"
        memory: 8Gi
    - type: PersistentVolumeClaim
      min:
        storage: 1Gi
      max:
        storage: 50Gi
```

---

## Tier 3: Per-Team+Environment Namespaces

Naming convention: `{team}-{service}-{env}` or `{team}-{env}`.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: payments-prod
  labels:
    team: payments
    env: prod
    cost-center: payments-bu
    compliance: pci-dss
    kubernetes.io/metadata.name: payments-prod
    pod-security.kubernetes.io/enforce: restricted
    istio-injection: enabled
  annotations:
    owner: "payments-team@company.com"
    oncall: "payments-oncall"
    slack: "#payments-alerts"
---
apiVersion: v1
kind: Namespace
metadata:
  name: payments-staging
  labels:
    team: payments
    env: staging
    cost-center: payments-bu
    kubernetes.io/metadata.name: payments-staging
    pod-security.kubernetes.io/enforce: restricted
---
apiVersion: v1
kind: Namespace
metadata:
  name: orders-prod
  labels:
    team: orders
    env: prod
    cost-center: orders-bu
    kubernetes.io/metadata.name: orders-prod
    pod-security.kubernetes.io/enforce: restricted
    istio-injection: enabled
```

### Tier 3 ResourceQuota (team-scoped)

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: payments-prod-quota
  namespace: payments-prod
spec:
  hard:
    requests.cpu: "16"
    requests.memory: 32Gi
    limits.cpu: "32"
    limits.memory: 64Gi
    pods: "100"
    services: "30"
    persistentvolumeclaims: "20"
    requests.storage: 200Gi
    count/deployments.apps: "30"
    count/statefulsets.apps: "10"
    count/jobs.batch: "50"
    count/configmaps: "100"
    count/secrets: "100"
  scopeSelector:
    matchExpressions:
      - scopeName: PriorityClass
        operator: In
        values: ["high", "medium"]
```

### Tier 3 LimitRange (production-grade)

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: payments-prod-limits
  namespace: payments-prod
spec:
  limits:
    - type: Container
      default:
        cpu: "1"
        memory: 512Mi
      defaultRequest:
        cpu: 250m
        memory: 256Mi
      min:
        cpu: 100m
        memory: 128Mi
      max:
        cpu: "4"
        memory: 8Gi
      maxLimitRequestRatio:
        cpu: "4"              # limit can be max 4x request
        memory: "2"           # limit can be max 2x request
    - type: Pod
      max:
        cpu: "16"
        memory: 32Gi
    - type: PersistentVolumeClaim
      min:
        storage: 1Gi
      max:
        storage: 200Gi
```

### Default-Deny NetworkPolicy per Namespace

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: payments-prod
spec:
  podSelector: {}             # matches all pods
  policyTypes:
    - Ingress
    - Egress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: payments-prod
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to: []
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

---

## Tier 4: Hierarchical Namespace Controller (HNC)

HNC enables parent-child namespace trees with policy inheritance.

### Install HNC

```bash
kubectl apply -f https://github.com/kubernetes-sigs/hierarchical-namespaces/releases/latest/download/default.yaml
```

### Parent Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: payments
  labels:
    team: payments
    hnc.x-k8s.io/included-namespace: "true"
```

### SubnamespaceAnchor (creates child namespace)

```yaml
apiVersion: hnc.x-k8s.io/v1alpha2
kind: SubnamespaceAnchor
metadata:
  name: payments-prod
  namespace: payments        # parent
---
apiVersion: hnc.x-k8s.io/v1alpha2
kind: SubnamespaceAnchor
metadata:
  name: payments-staging
  namespace: payments
---
apiVersion: hnc.x-k8s.io/v1alpha2
kind: SubnamespaceAnchor
metadata:
  name: payments-dev
  namespace: payments
```

### HNC Config (propagation rules)

```yaml
apiVersion: hnc.x-k8s.io/v1alpha2
kind: HNCConfiguration
metadata:
  name: config
spec:
  resources:
    - resource: secrets
      mode: Propagate          # copy secrets from parent to children
    - resource: roles
      mode: Propagate
    - resource: rolebindings
      mode: Propagate
    - resource: networkpolicies
      mode: Propagate
    - resource: limitranges
      mode: Propagate
    - resource: resourcequotas
      mode: Remove             # children define their own quotas
    - resource: configmaps
      mode: Propagate
```

**Inherited flow:** Define a Role or NetworkPolicy in the parent `payments` namespace and it automatically propagates to `payments-prod`, `payments-staging`, and `payments-dev`.

### Verify Hierarchy

```bash
kubectl hns tree payments
# payments
# ├── payments-dev
# ├── payments-staging
# └── payments-prod

kubectl hns describe payments-prod
```

---

## Tier 5: vcluster (Virtual Clusters)

Full Kubernetes API per tenant, running inside a host namespace.

### Install vcluster CLI

```bash
curl -L -o vcluster "https://github.com/loft-sh/vcluster/releases/latest/download/vcluster-linux-amd64"
chmod +x vcluster && sudo mv vcluster /usr/local/bin/
```

### Create vcluster via Helm

```yaml
# vcluster-values.yaml
syncer:
  extraArgs:
    - --tls-san=tenant-a.example.com
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: "1"
      memory: 1Gi

sync:
  nodes:
    enabled: true
    syncAllNodes: false
  persistentvolumes:
    enabled: true
  ingresses:
    enabled: true
  networkpolicies:
    enabled: true

isolation:
  enabled: true
  namespace: null
  podSecurityStandard: restricted
  resourceQuota:
    enabled: true
    quota:
      requests.cpu: "10"
      requests.memory: 20Gi
      limits.cpu: "20"
      limits.memory: 40Gi
      pods: "100"
      services: "40"
      persistentvolumeclaims: "20"
  limitRange:
    enabled: true
    default:
      cpu: 500m
      memory: 256Mi
    defaultRequest:
      cpu: 100m
      memory: 128Mi
  networkPolicy:
    enabled: true
```

```bash
# Create virtual cluster in host namespace
vcluster create tenant-a \
  --namespace tenant-a-host \
  --values vcluster-values.yaml

# Connect to vcluster
vcluster connect tenant-a --namespace tenant-a-host

# Tenant gets full admin inside their vcluster
kubectl get nodes   # sees synced nodes
kubectl create ns my-app  # full control
```

### vcluster vs HNC Decision

```
Need delegated admin within same cluster?
  -> HNC (lighter, policy inheritance)

Need full K8s API isolation per tenant?
  -> vcluster (heavier, complete isolation)

Multi-tenant SaaS where tenants run their own workloads?
  -> vcluster

Internal teams sharing infrastructure?
  -> HNC
```

---

## Namespace Label Conventions

### Standard Labels

| Label | Purpose | Example |
|-------|---------|---------|
| `team` | Owning team | `payments` |
| `env` | Environment | `prod`, `staging`, `dev` |
| `cost-center` | Billing | `payments-bu` |
| `compliance` | Regulatory | `pci-dss`, `hipaa` |
| `pod-security.kubernetes.io/enforce` | PSS level | `restricted` |
| `istio-injection` | Mesh sidecar | `enabled` |
| `kubernetes.io/metadata.name` | Namespace name (for NetworkPolicy) | `payments-prod` |

### Labels Used by NetworkPolicy

```yaml
# Allow ingress only from the "gateway" namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-from-gateway
  namespace: payments-prod
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: gateway
```

### Labels Used by Gateway API

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: main-gateway
  namespace: gateway
spec:
  gatewayClassName: istio
  listeners:
    - name: https
      port: 443
      protocol: HTTPS
      allowedRoutes:
        namespaces:
          from: Selector
          selector:
            matchLabels:
              env: prod          # only prod namespaces can attach routes
```

---

## Namespace Provisioning Automation

### Kyverno Policy: Auto-Create Resources on New Namespace

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: namespace-defaults
spec:
  rules:
    - name: generate-limit-range
      match:
        any:
          - resources:
              kinds: ["Namespace"]
              selector:
                matchLabels:
                  env: prod
      generate:
        apiVersion: v1
        kind: LimitRange
        name: default-limits
        namespace: "{{request.object.metadata.name}}"
        synchronize: true
        data:
          spec:
            limits:
              - type: Container
                default:
                  cpu: "1"
                  memory: 512Mi
                defaultRequest:
                  cpu: 250m
                  memory: 256Mi
    - name: generate-network-policy
      match:
        any:
          - resources:
              kinds: ["Namespace"]
              selector:
                matchLabels:
                  env: prod
      generate:
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        name: default-deny-all
        namespace: "{{request.object.metadata.name}}"
        synchronize: true
        data:
          spec:
            podSelector: {}
            policyTypes:
              - Ingress
              - Egress
    - name: generate-resource-quota
      match:
        any:
          - resources:
              kinds: ["Namespace"]
              selector:
                matchLabels:
                  env: prod
      generate:
        apiVersion: v1
        kind: ResourceQuota
        name: default-quota
        namespace: "{{request.object.metadata.name}}"
        synchronize: true
        data:
          spec:
            hard:
              requests.cpu: "16"
              requests.memory: 32Gi
              limits.cpu: "32"
              limits.memory: 64Gi
              pods: "100"
```

### ArgoCD ApplicationSet for Namespace Provisioning

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: namespace-provisioner
  namespace: argocd
spec:
  generators:
    - git:
        repoURL: https://github.com/org/platform-config.git
        revision: main
        directories:
          - path: "namespaces/*"
  template:
    metadata:
      name: "ns-{{path.basename}}"
    spec:
      project: platform
      source:
        repoURL: https://github.com/org/platform-config.git
        targetRevision: main
        path: "namespaces/{{path.basename}}"
      destination:
        server: https://kubernetes.default.svc
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

---

## Best Practices

1. **Never use `default` namespace for production** -- it lacks quotas and has permissive RBAC
2. **Always add ResourceQuota + LimitRange** to every non-system namespace (Tier 2+)
3. **Always add default-deny NetworkPolicy** before deploying workloads
4. **Use label conventions consistently** -- they drive NetworkPolicy, Gateway API, cost attribution
5. **Automate namespace provisioning** with Kyverno generate rules or ArgoCD ApplicationSets
6. **Set Pod Security Standards** via namespace labels (enforce + warn + audit)
7. **Include annotations for ownership** -- owner email, oncall, Slack channel
8. **Monitor quota usage** -- alert at 80% utilization to prevent scheduling failures
9. **Prefer HNC for internal teams** and vcluster for tenant isolation
10. **Delete unused namespaces** -- orphaned namespaces accumulate stale resources and secrets
