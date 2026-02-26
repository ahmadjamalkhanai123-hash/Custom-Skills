# RBAC Patterns — Kubernetes Authorizer

## Core RBAC Objects

| Object | Scope | Purpose |
|--------|-------|---------|
| `Role` | Namespace | Grant access within a single namespace |
| `ClusterRole` | Cluster-wide | Grant cluster-scoped or cross-namespace access |
| `RoleBinding` | Namespace | Bind Role or ClusterRole to subjects in namespace |
| `ClusterRoleBinding` | Cluster-wide | Bind ClusterRole to subjects cluster-wide |

## Naming Convention (Industry Standard)

```
ClusterRole:  authorizer:<team>:<verb-group>-<resource>
  Examples:
    authorizer:platform:read-pods
    authorizer:app-team:write-deployments
    authorizer:monitoring:read-metrics
    authorizer:sre:admin-namespaces

Role:         <team>-<verb>-<resource>
  Examples:
    backend-read-secrets
    frontend-deploy-apps
```

## Least-Privilege Role Templates

### Read-Only (Viewer)
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: authorizer:global:viewer
  labels:
    rbac.authorizer.io/tier: "read-only"
    rbac.authorizer.io/managed: "true"
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "configmaps", "endpoints", "events"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
```

### Developer (Namespace-Scoped Write)
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: authorizer:dev:namespace-developer
  namespace: <NAMESPACE>
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "pods/exec", "services", "configmaps"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list"]  # No create/update on secrets for dev role
```

### SRE / Platform (Cross-Namespace, No Secrets Write)
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: authorizer:sre:platform-operator
rules:
  - apiGroups: [""]
    resources: ["namespaces", "nodes", "persistentvolumes"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch", "delete"]  # Can evict pods
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch", "update", "patch"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
```

### CI/CD Service Account (Deploy Only)
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: authorizer:cicd:deployer
  namespace: <NAMESPACE>
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch", "update", "patch"]
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
```

## Aggregated ClusterRoles (Kubernetes Built-in Extension)

```yaml
# Define an aggregatable role
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: authorizer:monitoring:metrics-reader
  labels:
    rbac.authorizer.io/aggregate-to-viewer: "true"  # Aggregate into viewer
rules:
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods", "nodes"]
    verbs: ["get", "list"]

# Aggregator ClusterRole that picks up labeled roles
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: authorizer:global:viewer
aggregationRule:
  clusterRoleSelectors:
    - matchLabels:
        rbac.authorizer.io/aggregate-to-viewer: "true"
rules: []  # Auto-populated by aggregation
```

## RoleBinding Patterns

### User → Namespace Role
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: bind-developer-alice
  namespace: team-backend
subjects:
  - kind: User
    name: alice@company.com   # OIDC sub claim
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: authorizer:dev:namespace-developer
  apiGroup: rbac.authorization.k8s.io
```

### Group → ClusterRole (read-only across cluster)
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: bind-sre-group
subjects:
  - kind: Group
    name: sre-team           # OIDC groups claim value
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: authorizer:sre:platform-operator
  apiGroup: rbac.authorization.k8s.io
```

### ServiceAccount → Role (same namespace)
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: bind-sa-backend-app
  namespace: team-backend
subjects:
  - kind: ServiceAccount
    name: backend-app-sa
    namespace: team-backend
roleRef:
  kind: Role
  name: authorizer:cicd:deployer
  apiGroup: rbac.authorization.k8s.io
```

## ABAC (Attribute-Based Access Control)

ABAC is legacy in Kubernetes (pre-1.8). Kept for on-prem clusters using `--authorization-mode=ABAC`.

### ABAC Policy File Format (`/etc/kubernetes/abac-policy.json`)
```json
{"apiVersion":"abac.authorization.kubernetes.io/v1beta1","kind":"Policy","spec":{"user":"alice","namespace":"team-backend","resource":"pods","readonly":true}}
{"apiVersion":"abac.authorization.kubernetes.io/v1beta1","kind":"Policy","spec":{"user":"admin","namespace":"*","resource":"*","apiGroup":"*"}}
```

**Recommendation**: Migrate all ABAC to RBAC. ABAC requires API server restart to update.

## SubjectAccessReview (Authorization Checks)

```bash
# Check if serviceaccount can list pods
kubectl auth can-i list pods \
  --as=system:serviceaccount:team-backend:backend-app-sa \
  --namespace=team-backend

# Check user permissions
kubectl auth can-i create deployments \
  --as=alice@company.com \
  --namespace=team-backend

# Full RBAC audit for a subject
kubectl auth can-i --list \
  --as=system:serviceaccount:team-backend:backend-app-sa \
  --namespace=team-backend
```

## RBAC Audit Tools

```bash
# rbac-lookup: list subjects and their access
kubectl rbac-lookup alice --kind user --output wide

# rakkess: matrix view of permissions
kubectl rakkess --sa team-backend:backend-app-sa

# rbac-tool: generate policies from access patterns
rbac-tool policy-rules -e -n team-backend

# audit2rbac: generate RBAC from audit logs
audit2rbac --filename audit.log --user alice@company.com
```

## Protected Resources (Always Restrict)

Resources that MUST never be exposed with write verbs to non-admin subjects:

```yaml
# Never grant these to non-cluster-admins:
- secrets (write/create)        # credential exfiltration
- clusterroles (write)          # privilege escalation
- clusterrolebindings (write)   # lateral movement
- validatingwebhookconfigurations (write)  # bypass admission
- mutatingwebhookconfigurations (write)    # code injection
- customresourcedefinitions (write)        # cluster-wide impact
- nodes (write)                 # host escape vector
- pods/exec (create)            # RCE vector — log all uses
- pods/portforward (create)     # network tunnel
```

## Ephemeral Access Patterns (JIT)

```yaml
# Time-limited RoleBinding via annotation (managed by controller)
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: temp-access-ops-incident
  namespace: production
  annotations:
    authorizer.io/expires-at: "2026-02-25T23:59:59Z"
    authorizer.io/reason: "P1 incident JIRA-1234"
    authorizer.io/approved-by: "security-team"
subjects:
  - kind: User
    name: ops-engineer@company.com
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: authorizer:sre:platform-operator
  apiGroup: rbac.authorization.k8s.io
```
