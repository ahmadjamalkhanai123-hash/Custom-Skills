# Kubernetes Label Strategy & Searching

Labels are the foundation of K8s — they drive selectors, NetworkPolicies, RBAC, cost attribution, and operations.

---

## Recommended Labels (K8s Standard)

Every resource MUST have these:

```yaml
metadata:
  labels:
    # Required (Kubernetes recommended)
    app.kubernetes.io/name: order-service        # App name
    app.kubernetes.io/instance: order-service-prod  # Unique instance
    app.kubernetes.io/version: "1.4.2"           # SemVer
    app.kubernetes.io/component: api             # Component role
    app.kubernetes.io/part-of: checkout-platform  # Parent system
    app.kubernetes.io/managed-by: helm           # Deployment tool

    # Business labels (custom)
    team: payments                    # Owning team
    environment: production           # dev/staging/production
    cost-center: cc-42               # FinOps attribution
    tier: critical                    # critical/standard/batch
```

### Label vs Annotation Decision

```
Need to SELECT or FILTER resources? → Label
Need to STORE metadata only?        → Annotation

Labels:  team, environment, app name, version, component
Annotations: git-sha, build-url, description, config-hash, last-deployed
```

---

## Label Taxonomy by Tier

### Tier 1-2: Basic

```yaml
labels:
  app.kubernetes.io/name: myapp
  app.kubernetes.io/version: "1.0.0"
  environment: dev
```

### Tier 3: Enterprise

```yaml
labels:
  app.kubernetes.io/name: order-service
  app.kubernetes.io/instance: order-service-prod
  app.kubernetes.io/version: "2.3.1"
  app.kubernetes.io/component: api
  app.kubernetes.io/part-of: checkout-platform
  app.kubernetes.io/managed-by: argocd
  team: payments
  environment: production
  cost-center: cc-42
  tier: critical
  compliance: pci-dss
```

### Tier 4-5: Fleet

```yaml
labels:
  # All of Tier 3 plus:
  cluster: us-east-1-prod
  region: us-east-1
  fleet: global-prod
  tenant: acme-corp          # Multi-tenant
  sla: platinum              # SLA tier
```

---

## Namespace Labels

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: checkout-prod
  labels:
    # K8s standard
    kubernetes.io/metadata.name: checkout-prod
    # Pod Security Standards
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
    # Business context
    domain: checkout
    environment: production
    team: payments
    cost-center: cc-42
    # Policy engine selectors
    kyverno.io/policy-group: production
```

---

## kubectl Label Searching

### Basic Selectors

```bash
# Equality-based
kubectl get pods -l app.kubernetes.io/name=order-service
kubectl get pods -l environment=production
kubectl get pods -l team=payments,environment=production

# Inequality
kubectl get pods -l 'environment!=production'

# Set-based
kubectl get pods -l 'environment in (staging, production)'
kubectl get pods -l 'tier in (critical, standard)'
kubectl get pods -l 'environment notin (dev)'

# Existence
kubectl get pods -l 'team'           # Has label 'team'
kubectl get pods -l '!experimental'  # Does NOT have label
```

### Advanced Queries

```bash
# Cross-resource: find all resources for a team
kubectl get all -l team=payments -A

# Show labels in output
kubectl get pods --show-labels -n checkout
kubectl get pods -L team,environment,tier -n checkout

# Custom columns with labels
kubectl get pods -o custom-columns=\
  NAME:.metadata.name,\
  TEAM:.metadata.labels.team,\
  ENV:.metadata.labels.environment,\
  VERSION:.metadata.labels.'app\.kubernetes\.io/version'

# Count pods per team
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.labels.team}{"\n"}{end}' | sort | uniq -c | sort -rn

# Find unlabeled pods (missing required label)
kubectl get pods -A -l '!team' --no-headers | wc -l

# Find all resources in a domain
kubectl get all -A -l 'app.kubernetes.io/part-of=checkout-platform'
```

### Operational Queries

```bash
# Find all critical-tier pods not running
kubectl get pods -A -l tier=critical --field-selector=status.phase!=Running

# Find all pods for a specific version (rollback check)
kubectl get pods -A -l 'app.kubernetes.io/version=1.4.2'

# Find pods managed by ArgoCD
kubectl get pods -A -l 'app.kubernetes.io/managed-by=argocd'

# List services with their selectors
kubectl get svc -A -o custom-columns=\
  NAMESPACE:.metadata.namespace,\
  NAME:.metadata.name,\
  SELECTOR:.spec.selector
```

---

## Label Cardinality Warnings

High-cardinality labels break Prometheus and increase etcd storage.

### SAFE Labels (Low Cardinality)

```yaml
# Finite, bounded values — safe for Prometheus metrics
team: payments           # ~10-50 teams
environment: production  # 3-5 environments
tier: critical           # 3-4 tiers
region: us-east-1        # ~10-20 regions
```

### DANGEROUS Labels (High Cardinality)

```yaml
# NEVER use as Prometheus label or matchLabels in ServiceMonitor
request-id: "abc-123-def"          # Infinite values
user-id: "user-98765"              # Millions of values
timestamp: "2026-02-09T10:30:00Z"  # Infinite values
session-hash: "sha256:abcdef..."   # Infinite values
```

### Rule of Thumb

```
Label cardinality < 100 values → Safe for metrics
Label cardinality 100-1000     → Use with caution, only in annotations
Label cardinality > 1000       → NEVER as label, use annotation only
```

---

## Kyverno Label Enforcement

```yaml
# Require standard labels on all Deployments
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-labels
spec:
  validationFailureAction: Enforce
  rules:
    - name: require-standard-labels
      match:
        any:
          - resources:
              kinds: [Deployment, StatefulSet, DaemonSet]
      validate:
        message: "Missing required labels: app.kubernetes.io/name, team, environment"
        pattern:
          metadata:
            labels:
              app.kubernetes.io/name: "?*"
              team: "?*"
              environment: "?*"
    - name: require-cost-center-in-prod
      match:
        any:
          - resources:
              kinds: [Namespace]
              selector:
                matchLabels:
                  environment: production
      validate:
        message: "Production namespaces must have cost-center label"
        pattern:
          metadata:
            labels:
              cost-center: "?*"
```

---

## Label-Based Cost Attribution

```yaml
# Kubecost allocation by label
# Configure Kubecost to group costs by team + environment
apiVersion: v1
kind: ConfigMap
metadata:
  name: kubecost-allocation
  namespace: kubecost
data:
  allocation.yaml: |
    labelConfig:
      enabled: true
      ownerLabel: team
      departmentLabel: cost-center
      environmentLabel: environment
      productLabel: app.kubernetes.io/part-of
```

```bash
# Query costs by team
kubectl cost namespace --show-labels -l team=payments

# Query costs by environment across all teams
kubectl cost namespace -l environment=production
```

