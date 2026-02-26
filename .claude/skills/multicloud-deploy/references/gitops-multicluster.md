# GitOps Multi-Cluster Reference

## ArgoCD ApplicationSets (Recommended)

ApplicationSets dynamically generate ArgoCD Applications from templates.
The cluster generator auto-discovers and deploys to all registered clusters.

### Installation

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f \
  https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Install ApplicationSet controller (included in ArgoCD v2.3+)
# Register clusters
argocd cluster add aws-eks --kubeconfig ~/.kube/eks.config
argocd cluster add gcp-gke --kubeconfig ~/.kube/gke.config
argocd cluster add azure-aks --kubeconfig ~/.kube/aks.config
```

### Cluster Generator (Deploy to All Clusters)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: microservices-all-clusters
  namespace: argocd
spec:
  generators:
    - clusters:
        selector:
          matchLabels:
            environment: production   # only production clusters
  template:
    metadata:
      name: "{{name}}-microservices"   # {{name}} = cluster name
    spec:
      project: production
      source:
        repoURL: https://github.com/org/platform-gitops
        targetRevision: main
        path: "clusters/{{name}}/microservices"   # per-cluster overrides
      destination:
        server: "{{server}}"    # cluster API server URL
        namespace: microservices
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
          - ServerSideApply=true
        retry:
          limit: 5
          backoff:
            duration: 5s
            factor: 2
            maxDuration: 3m
```

### Matrix Generator (Cross Cloud × Environments)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: services-matrix
  namespace: argocd
spec:
  generators:
    - matrix:
        generators:
          - clusters:
              selector:
                matchLabels:
                  environment: production
          - list:
              elements:
                - service: checkout-api
                  namespace: payments
                - service: inventory-api
                  namespace: orders
                - service: user-service
                  namespace: users
  template:
    metadata:
      name: "{{name}}-{{service}}"
    spec:
      source:
        repoURL: https://github.com/org/services
        path: "{{service}}/helm"
        helm:
          valueFiles:
            - values-production.yaml
            - "values-{{metadata.labels.cloud}}.yaml"
      destination:
        server: "{{server}}"
        namespace: "{{namespace}}"
```

### App of Apps Pattern (Multi-Cluster Bootstrap)

```yaml
# Root application bootstraps all cluster configurations
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: platform-root
  namespace: argocd
spec:
  project: platform
  source:
    repoURL: https://github.com/org/platform-gitops
    targetRevision: main
    path: bootstrap/
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

```
bootstrap/
├── aws-eks.yaml        # ApplicationSet for AWS cluster
├── gcp-gke.yaml        # ApplicationSet for GCP cluster
├── azure-aks.yaml      # ApplicationSet for Azure cluster
└── shared/             # Cross-cluster shared resources
    ├── rbac.yaml
    └── monitoring.yaml
```

### Secrets Management with ArgoCD

Never store secrets in Git. Use External Secrets Operator + Vault:

```yaml
# ExternalSecret pulls from Vault, creates K8s secret
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: database-credentials
  namespace: payments
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: database-credentials
    creationPolicy: Owner
  data:
    - secretKey: password
      remoteRef:
        key: payments/database
        property: password
    - secretKey: username
      remoteRef:
        key: payments/database
        property: username
```

```yaml
# Vault-backed ClusterSecretStore (per cluster)
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "https://vault.prod.internal"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes-aws-eks"
          role: "payments-reader"
```

---

## Flux Multi-Cluster

Flux is an alternative GitOps engine (CNCF Graduated). Better for large-scale fleet.

### Multi-Cluster Setup with Kustomize

```yaml
# aws-eks/kustomization.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: microservices
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: platform-repo
  path: ./clusters/aws-eks
  prune: true
  wait: true
  timeout: 2m
  postBuild:
    substitute:
      CLOUD: "aws"
      REGION: "us-east-1"
      CLUSTER_NAME: "aws-eks-prod"
```

### Image Automation (Auto-Deploy New Versions)

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: checkout-api
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: checkout-api
  policy:
    semver:
      range: ">=1.0.0 <2.0.0"   # only patch/minor updates auto-deploy

---
# ImageUpdateAutomation commits updated image tags to Git
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageUpdateAutomation
metadata:
  name: auto-deploy
  namespace: flux-system
spec:
  interval: 10m
  sourceRef:
    kind: GitRepository
    name: platform-repo
  git:
    commit:
      author:
        email: fluxbot@company.com
        name: Flux Bot
      messageTemplate: "chore: update {{range .Updated.Images}}{{println .}}{{end}}"
    push:
      branch: main
  update:
    path: ./clusters
    strategy: Setters
```

---

## GitOps Repository Structure (Recommended)

```
platform-gitops/
├── bootstrap/                    # Cluster bootstrap (ArgoCD/Flux install)
│   ├── aws-eks/
│   ├── gcp-gke/
│   └── azure-aks/
├── clusters/                     # Per-cluster configurations
│   ├── aws-eks/
│   │   ├── kustomization.yaml
│   │   ├── values-aws.yaml       # Cloud-specific Helm overrides
│   │   └── namespaces/
│   ├── gcp-gke/
│   │   ├── kustomization.yaml
│   │   └── values-gcp.yaml
│   └── azure-aks/
│       ├── kustomization.yaml
│       └── values-azure.yaml
├── apps/                         # Service definitions (cloud-agnostic)
│   ├── checkout-api/
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── values-production.yaml
│   └── inventory-api/
├── infrastructure/               # Shared infra (Istio, Prometheus, etc.)
│   ├── istio/
│   ├── monitoring/
│   └── security/
└── environments/                 # Environment-level configs
    ├── production/
    └── staging/
```

---

## Progressive Delivery (Argo Rollouts Multi-Cluster)

Deploy progressively across clusters — AWS first, then GCP, then Azure:

```yaml
# 1. Deploy to aws-eks with canary analysis
# 2. If 30min metrics are healthy, promote to gcp-gke
# 3. If healthy, promote to azure-aks

# Implemented via ApplicationSet with progressive sync waves
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: progressive-delivery
spec:
  generators:
    - list:
        elements:
          - cluster: aws-eks
            server: https://aws-eks.example.com
            wave: "1"
          - cluster: gcp-gke
            server: https://gcp-gke.example.com
            wave: "2"
          - cluster: azure-aks
            server: https://azure-aks.example.com
            wave: "3"
  template:
    metadata:
      name: "checkout-api-{{cluster}}"
      annotations:
        argocd.argoproj.io/sync-wave: "{{wave}}"
    spec:
      source:
        path: apps/checkout-api/helm
      destination:
        server: "{{server}}"
        namespace: payments
```

---

## Drift Detection and Self-Healing

ArgoCD self-heal detects drift (manual kubectl applies) and reverts.

```yaml
syncPolicy:
  automated:
    prune: true        # delete resources removed from Git
    selfHeal: true     # revert manual changes
```

**Drift Alerting** (Prometheus metric from ArgoCD):
```promql
# Alert when any app is out of sync for > 5 minutes
argocd_app_info{sync_status="OutOfSync"} == 1
```

```yaml
# Alert rule
- alert: ArgoCDApplicationOutOfSync
  expr: argocd_app_info{sync_status="OutOfSync"} == 1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "ArgoCD app {{ $labels.name }} is out of sync"
```

---

## Multi-Cloud GitOps Decision: ArgoCD vs Flux

| Factor | ArgoCD | Flux |
|--------|--------|------|
| **UI** | Rich web UI | CLI-first |
| **Multi-cluster** | ApplicationSets | Kustomize + multi-tenancy |
| **Secret management** | Plugin-based (AVP, ESO) | Built-in SOPS + ESO |
| **Image automation** | Limited (Argo Image Updater) | Native ImageUpdateAutomation |
| **Scale (clusters)** | Best for <100 clusters | Best for 100+ clusters (pull-based) |
| **Learning curve** | Medium | Medium |
| **Community** | CNCF Graduated | CNCF Graduated |

**Use ArgoCD for:** Most enterprise deployments with UI requirement, ApplicationSet power.
**Use Flux for:** Large fleet (100+ clusters), GitOps purists, image automation needs.
