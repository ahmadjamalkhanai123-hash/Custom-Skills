# Multi-Cluster Authorization Patterns

## Multi-Cluster Identity Models

| Model | Tool | Identity Scope |
|-------|------|----------------|
| Hub-Spoke | GKE Hub / ACM | Central identity, spoke policies |
| Peer-to-Peer | Submariner / Skupper | Federated identities |
| GitOps Federation | ArgoCD + App-of-Apps | Git-sourced RBAC per cluster |
| Service Mesh Federation | Istio / Linkerd | SPIFFE cross-cluster trust domain |

---

## ArgoCD: Multi-Cluster RBAC

### Register Remote Cluster

```bash
# Add cluster to ArgoCD (creates service account in target)
argocd cluster add production-cluster --name production \
  --in-cluster=false

# Verify
argocd cluster list
```

### ArgoCD RBAC (ConfigMap `argocd-rbac-cm`)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-rbac-cm
  namespace: argocd
data:
  policy.default: role:readonly
  policy.csv: |
    # Platform team: full access to all apps and clusters
    p, role:platform-admin, applications, *, */*, allow
    p, role:platform-admin, clusters, *, *, allow
    p, role:platform-admin, repositories, *, *, allow
    p, role:platform-admin, projects, *, *, allow

    # App team: only their project and assigned clusters
    p, role:app-team-backend, applications, get, team-backend/*, allow
    p, role:app-team-backend, applications, sync, team-backend/*, allow
    p, role:app-team-backend, applications, update, team-backend/*, allow
    p, role:app-team-backend, logs, get, team-backend/*, allow

    # SRE: read-only across all, can sync in production
    p, role:sre, applications, get, */*, allow
    p, role:sre, applications, sync, production/*, allow
    p, role:sre, clusters, get, *, allow

    # Group bindings (from OIDC groups claim)
    g, oidc:platform-engineers, role:platform-admin
    g, oidc:backend-team, role:app-team-backend
    g, oidc:sre-team, role:sre

  scopes: '[groups, email]'
```

### ArgoCD AppProject: Cluster + Namespace Scoping

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: team-backend
  namespace: argocd
spec:
  description: "Backend team project"
  sourceRepos:
    - "https://github.com/company/backend-gitops"
  destinations:
    - namespace: "team-backend"
      server: "https://production-cluster.example.com"
    - namespace: "team-backend"
      server: "https://staging-cluster.example.com"
  clusterResourceWhitelist:
    - group: ""
      kind: Namespace
  namespaceResourceBlacklist:
    - group: ""
      kind: ResourceQuota    # Prevent quota overrides
  roles:
    - name: backend-developer
      description: "Backend developers can sync apps"
      policies:
        - p, proj:team-backend:backend-developer, applications, get, team-backend/*, allow
        - p, proj:team-backend:backend-developer, applications, sync, team-backend/*, allow
      groups:
        - oidc:backend-team
```

---

## Flux: Multi-Cluster GitOps Auth

### Multi-Cluster Kustomization

```yaml
# Hub cluster: push configs to spoke clusters via Kustomization
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: production-rbac
  namespace: flux-system
spec:
  interval: 10m
  path: "./clusters/production/auth"
  prune: true
  sourceRef:
    kind: GitRepository
    name: gitops-repo
  kubeConfig:
    secretRef:
      name: production-cluster-kubeconfig
```

```yaml
# Secret with kubeconfig for spoke cluster
apiVersion: v1
kind: Secret
metadata:
  name: production-cluster-kubeconfig
  namespace: flux-system
type: Opaque
data:
  value: <base64-encoded-kubeconfig>
```

---

## GKE Hub / Anthos Config Management (ACM)

```yaml
# ConfigSync (ACM) — sync RBAC from Git
apiVersion: configsync.gke.io/v1beta1
kind: RootSync
metadata:
  name: root-sync
  namespace: config-management-system
spec:
  sourceFormat: hierarchy
  git:
    repo: https://github.com/company/k8s-config
    branch: main
    dir: "/"
    auth: token
    secretRef:
      name: git-creds
```

```yaml
# Fleet RBAC — central ClusterRole across all member clusters
# Applied via ACM to all registered clusters
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: authorizer:fleet:platform-viewer
  annotations:
    configmanagement.gke.io/cluster-selector: "all-clusters"
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "nodes"]
    verbs: ["get", "list", "watch"]
```

---

## Cluster API: Multi-Cluster Identity

```yaml
# CAPI cluster SA for management operations
apiVersion: v1
kind: ServiceAccount
metadata:
  name: capi-controller-manager
  namespace: capi-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: authorizer:capi:manager
rules:
  - apiGroups: ["cluster.x-k8s.io"]
    resources: ["clusters", "machines", "machinesets", "machinedeployments"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: [""]
    resources: ["secrets", "configmaps", "events"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
```

---

## Cross-Cluster SPIFFE Trust Federation

```yaml
# SPIRE Server: federate with remote cluster trust domain
# server.conf additions for federation
federation {
  bundle_endpoint {
    address = "0.0.0.0"
    port = 8443
  }
  federates_with "remote-company.com" {
    bundle_endpoint_url = "https://spire-remote.remote-company.com:8443"
    bundle_endpoint_profile "https_spiffe" {
      endpoint_spiffe_id = "spiffe://remote-company.com/spire/server"
    }
  }
}
```

```bash
# Register cross-cluster workload entry
kubectl exec -n spire spire-server-0 -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://company.com/ns/team-backend/sa/backend-app-sa \
  -federatesWith spiffe://remote-company.com \
  -parentID spiffe://company.com/k8s-workload-registrar/production/node \
  -selector k8s:ns:team-backend \
  -selector k8s:sa:backend-app-sa
```

---

## SubjectAccessReview: Cross-Cluster Auth Check

```bash
# Check if remote SA has permissions on local cluster
kubectl create -f - <<EOF
apiVersion: authorization.k8s.io/v1
kind: SubjectAccessReview
spec:
  user: "system:serviceaccount:team-backend:backend-app-sa"
  groups: ["system:serviceaccounts", "system:serviceaccounts:team-backend"]
  resourceAttributes:
    namespace: "team-backend"
    verb: "get"
    resource: "pods"
EOF
```

## Multi-Cluster Auth Anti-Patterns

| Anti-Pattern | Risk | Fix |
|-------------|------|-----|
| Single kubeconfig with cluster-admin for all clusters | Full compromise if leaked | Per-cluster, scoped kubeconfigs |
| Same SA across dev/staging/prod | Prod access via staging breach | Separate SAs per environment |
| No RBAC on hub cluster | Hub compromise → all spokes | Treat hub as most sensitive cluster |
| Manual kubeconfig distribution | Rotation difficult, secrets sprawl | Use ArgoCD/Flux cluster secrets with SOPS |
| No cross-cluster audit trail | Cannot trace cross-cluster actions | Centralize audit logs (e.g., OpenSearch) |
