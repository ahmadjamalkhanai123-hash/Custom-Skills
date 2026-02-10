# RBAC Patterns

Multi-layer Role-Based Access Control covering authentication, authorization tiers, aggregated roles, cross-cluster federation, service accounts, impersonation, and auditing.

---

## Authentication Layer

### Decision Tree

```
How do users authenticate to the cluster?

Cloud-managed cluster (EKS, GKE, AKS)?
  -> Cloud IAM integration (IRSA, Workload Identity, AAD)

Self-managed / on-prem?
  -> OIDC provider (Dex, Keycloak, Okta)

CI/CD pipelines and automation?
  -> ServiceAccount tokens (short-lived, bound)

Emergency / break-glass?
  -> Client certificates (rotate regularly)
```

### OIDC with Dex (self-managed clusters)

```yaml
# kube-apiserver flags
apiVersion: v1
kind: Pod
metadata:
  name: kube-apiserver
  namespace: kube-system
spec:
  containers:
    - name: kube-apiserver
      command:
        - kube-apiserver
        - --oidc-issuer-url=https://dex.example.com
        - --oidc-client-id=kubernetes
        - --oidc-username-claim=email
        - --oidc-groups-claim=groups
        - --oidc-username-prefix="oidc:"
        - --oidc-groups-prefix="oidc:"
```

### AWS IRSA (EKS — IAM Roles for Service Accounts)

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: s3-reader
  namespace: data-pipeline
  annotations:
    eks.amazonaws.com/role-arn: "arn:aws:iam::123456789012:role/s3-reader-role"
---
# Pod using this SA gets temporary AWS credentials injected
apiVersion: apps/v1
kind: Deployment
metadata:
  name: etl-worker
  namespace: data-pipeline
spec:
  template:
    spec:
      serviceAccountName: s3-reader
      automountServiceAccountToken: true   # needed for IRSA
      containers:
        - name: etl
          image: registry.example.com/etl@sha256:etl123...
          # AWS SDK auto-discovers credentials from projected token
```

### GKE Workload Identity

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: gcs-writer
  namespace: analytics
  annotations:
    iam.gke.io/gcp-service-account: "gcs-writer@project-id.iam.gserviceaccount.com"
```

```bash
# Bind K8s SA to GCP SA
gcloud iam service-accounts add-iam-policy-binding \
  gcs-writer@project-id.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:project-id.svc.id.goog[analytics/gcs-writer]"
```

---

## Tier 1: cluster-admin (Development Only)

For local development and learning. Never use in production.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: dev-admin
subjects:
  - kind: User
    name: developer@example.com
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cluster-admin          # built-in, full access
  apiGroup: rbac.authorization.k8s.io
```

**Risk:** Full cluster access. Replace with scoped roles immediately for any shared cluster.

---

## Tier 2: Namespace-Scoped Roles

### Developer Role (read/write workloads, read-only secrets)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer
  namespace: payments-dev
rules:
  # Workload management
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  # Core resources
  - apiGroups: [""]
    resources: ["pods", "pods/log", "pods/exec", "services", "configmaps", "endpoints"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  # Secrets: read-only (no create/delete)
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "watch"]
  # Events and status
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["get", "list", "watch"]
  # HPA
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  # Ingress
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: developer-binding
  namespace: payments-dev
subjects:
  - kind: Group
    name: "oidc:payments-developers"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: developer
  apiGroup: rbac.authorization.k8s.io
```

### SRE Role (full namespace access including secrets and RBAC)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: sre
  namespace: payments-prod
rules:
  # Full workload management
  - apiGroups: ["", "apps", "batch", "autoscaling", "policy"]
    resources: ["*"]
    verbs: ["*"]
  # Network resources
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["*"]
  # RBAC within namespace
  - apiGroups: ["rbac.authorization.k8s.io"]
    resources: ["roles", "rolebindings"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  # Monitoring
  - apiGroups: ["monitoring.coreos.com"]
    resources: ["servicemonitors", "prometheusrules", "podmonitors"]
    verbs: ["*"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: sre-binding
  namespace: payments-prod
subjects:
  - kind: Group
    name: "oidc:platform-sre"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: sre
  apiGroup: rbac.authorization.k8s.io
```

### Read-Only Role (auditors, on-call)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: readonly
  namespace: payments-prod
rules:
  - apiGroups: ["", "apps", "batch", "autoscaling", "networking.k8s.io", "policy"]
    resources: ["*"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get", "list"]
  # Explicitly deny secrets access for readonly
  # (omitting secrets from resources means no access)
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: readonly-binding
  namespace: payments-prod
subjects:
  - kind: Group
    name: "oidc:payments-oncall"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: readonly
  apiGroup: rbac.authorization.k8s.io
```

### Readonly with Secrets (for SRE on-call)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: readonly-with-secrets
  namespace: payments-prod
rules:
  - apiGroups: ["", "apps", "batch", "autoscaling", "networking.k8s.io", "policy"]
    resources: ["*"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/log", "pods/exec"]
    verbs: ["get", "list", "create"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list"]
```

---

## Tier 3: Aggregated ClusterRoles

Aggregated ClusterRoles compose multiple roles via label selectors. Adding a new role with the matching label automatically extends the aggregate.

### Base Fragment Roles

```yaml
# Fragment: view workloads
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: workload-viewer
  labels:
    rbac.example.com/aggregate-to-developer: "true"
    rbac.example.com/aggregate-to-sre: "true"
    rbac.example.com/aggregate-to-readonly: "true"
rules:
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
---
# Fragment: manage workloads
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: workload-manager
  labels:
    rbac.example.com/aggregate-to-developer: "true"
    rbac.example.com/aggregate-to-sre: "true"
rules:
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
    verbs: ["create", "update", "patch", "delete"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["create", "update", "patch", "delete"]
---
# Fragment: manage secrets
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: secret-manager
  labels:
    rbac.example.com/aggregate-to-sre: "true"
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
# Fragment: manage monitoring
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: monitoring-manager
  labels:
    rbac.example.com/aggregate-to-sre: "true"
    rbac.example.com/aggregate-to-developer: "true"
rules:
  - apiGroups: ["monitoring.coreos.com"]
    resources: ["servicemonitors", "prometheusrules", "podmonitors"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
```

### Aggregated ClusterRoles

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: aggregate-developer
aggregationRule:
  clusterRoleSelectors:
    - matchLabels:
        rbac.example.com/aggregate-to-developer: "true"
rules: []  # auto-filled by aggregation controller
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: aggregate-sre
aggregationRule:
  clusterRoleSelectors:
    - matchLabels:
        rbac.example.com/aggregate-to-sre: "true"
rules: []
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: aggregate-readonly
aggregationRule:
  clusterRoleSelectors:
    - matchLabels:
        rbac.example.com/aggregate-to-readonly: "true"
rules: []
```

### Bind Aggregated Role to Namespace

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: payments-developers
  namespace: payments-prod
subjects:
  - kind: Group
    name: "oidc:payments-developers"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole            # reference the ClusterRole
  name: aggregate-developer    # but bind it to a namespace
  apiGroup: rbac.authorization.k8s.io
```

---

## Tier 4-5: Cross-Cluster OIDC Federation

### Centralized OIDC Provider (Keycloak) with Group Mapping

```yaml
# Keycloak client configuration (simplified)
# Each cluster registers as an OIDC client
# Groups in Keycloak map to K8s RBAC groups

# Cluster A kube-apiserver config:
# --oidc-issuer-url=https://keycloak.example.com/realms/kubernetes
# --oidc-client-id=cluster-us-east-1
# --oidc-groups-claim=groups
# --oidc-groups-prefix="oidc:"

# Cluster B kube-apiserver config:
# --oidc-issuer-url=https://keycloak.example.com/realms/kubernetes
# --oidc-client-id=cluster-eu-west-1
# --oidc-groups-claim=groups
# --oidc-groups-prefix="oidc:"
```

### Cross-Cluster RoleBinding (applied to each cluster)

```yaml
# Same RoleBinding deployed to all clusters via GitOps
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: global-sre-team
subjects:
  - kind: Group
    name: "oidc:global-sre"       # same OIDC group in all clusters
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: aggregate-sre
  apiGroup: rbac.authorization.k8s.io
---
# Per-region team binding
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: us-payments-team
  namespace: payments-prod
subjects:
  - kind: Group
    name: "oidc:us-payments-team"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: aggregate-developer
  apiGroup: rbac.authorization.k8s.io
```

### Fleet-Level RBAC (Tier 5 — Rancher)

```yaml
# Rancher GlobalRole — applies across all downstream clusters
apiVersion: management.cattle.io/v3
kind: GlobalRole
metadata:
  name: fleet-readonly
rules:
  - apiGroups: [""]
    resources: ["namespaces", "pods", "services"]
    verbs: ["get", "list", "watch"]
---
apiVersion: management.cattle.io/v3
kind: GlobalRoleBinding
metadata:
  name: fleet-readonly-auditors
globalRoleName: fleet-readonly
subjects:
  - kind: Group
    name: "oidc:compliance-auditors"
    apiGroup: rbac.authorization.k8s.io
```

---

## ServiceAccount for Workloads

### Least-Privilege Service Account

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: api-server
  namespace: payments-prod
  labels:
    app.kubernetes.io/name: api-server
automountServiceAccountToken: false    # default off
---
# Only create Role if the workload needs K8s API access
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: api-server-role
  namespace: payments-prod
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "watch"]
    resourceNames: ["api-server-config"]   # specific resource only
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: api-server-binding
  namespace: payments-prod
subjects:
  - kind: ServiceAccount
    name: api-server
    namespace: payments-prod
roleRef:
  kind: Role
  name: api-server-role
  apiGroup: rbac.authorization.k8s.io
```

### Service Account Decision Tree

```
Does the workload need K8s API access?
  NO  -> automountServiceAccountToken: false, no Role needed
  YES -> What does it need?
    Read own ConfigMap/Secret?
      -> Role with get/watch on specific resourceNames
    List pods (leader election)?
      -> Role with get/list/watch on pods, create/update on leases
    Operator managing CRDs?
      -> ClusterRole with CRD-specific verbs
    ArgoCD/CI deploying manifests?
      -> Role with create/update/patch on target resources
```

---

## Impersonation (Admin Debugging)

Impersonation lets admins test RBAC as another user without switching credentials.

```yaml
# ClusterRole allowing impersonation
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: impersonator
rules:
  - apiGroups: [""]
    resources: ["users", "groups", "serviceaccounts"]
    verbs: ["impersonate"]
  - apiGroups: [""]
    resources: ["userextras/scopes"]
    verbs: ["impersonate"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: admin-impersonator
subjects:
  - kind: Group
    name: "oidc:platform-admins"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: impersonator
  apiGroup: rbac.authorization.k8s.io
```

```bash
# Test as a developer
kubectl auth can-i create deployments \
  --as=developer@example.com \
  --as-group=oidc:payments-developers \
  -n payments-prod
# yes/no

# Run a command as another user
kubectl get pods -n payments-prod \
  --as=developer@example.com \
  --as-group=oidc:payments-developers
```

---

## RBAC Audit Queries

### Built-in kubectl auth

```bash
# Can user X do action Y in namespace Z?
kubectl auth can-i create deployments -n payments-prod --as=developer@example.com

# What can I do in a namespace?
kubectl auth can-i --list -n payments-prod

# What can a ServiceAccount do?
kubectl auth can-i --list -n payments-prod \
  --as=system:serviceaccount:payments-prod:api-server
```

### rbac-lookup (kubectl plugin)

```bash
# Install
kubectl krew install rbac-lookup

# Find all bindings for a user
kubectl rbac-lookup developer@example.com

# Find all bindings in a namespace
kubectl rbac-lookup --kind=rolebinding -n payments-prod

# Find who has cluster-admin
kubectl rbac-lookup --kind=clusterrolebinding | grep cluster-admin
```

### who-can (kubectl plugin)

```bash
# Install
kubectl krew install who-can

# Who can delete pods in payments-prod?
kubectl who-can delete pods -n payments-prod

# Who can create secrets cluster-wide?
kubectl who-can create secrets --all-namespaces

# Who can exec into pods?
kubectl who-can create pods/exec -n payments-prod
```

### Audit Log Query for RBAC Denials

```bash
# Find RBAC denials in audit logs
kubectl logs -n kube-system -l component=kube-apiserver | \
  grep "RBAC DENY" | jq '.user.username, .objectRef'

# Structured audit policy to capture RBAC events
```

```yaml
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  - level: RequestResponse
    resources:
      - group: "rbac.authorization.k8s.io"
        resources: ["roles", "rolebindings", "clusterroles", "clusterrolebindings"]
    verbs: ["create", "update", "patch", "delete"]
  - level: Metadata
    nonResourceURLs: ["/apis/*", "/api/*"]
    verbs: ["get"]
    users: ["system:anonymous"]
```

---

## Least-Privilege Decision Tree

```
Step 1: Does the app need K8s API access at all?
  NO  -> automountServiceAccountToken: false, DONE
  YES -> continue

Step 2: Does it need cluster-wide access?
  NO  -> Use Role (namespace-scoped)
  YES -> Use ClusterRole (justify in PR)

Step 3: What resources does it need?
  -> List specific apiGroups + resources (never use "*")

Step 4: What verbs does it need?
  -> List specific verbs (never use "*")
  -> Read-only: get, list, watch
  -> Read-write: get, list, watch, create, update, patch
  -> Full: get, list, watch, create, update, patch, delete

Step 5: Can you restrict to specific resource names?
  YES -> Add resourceNames field
  NO  -> Allow all resources of that type

Step 6: Review with who-can
  -> kubectl who-can <verb> <resource> -n <namespace>
  -> Ensure no unexpected subjects have access
```

---

## Common RBAC Anti-Patterns

| Anti-Pattern | Risk | Fix |
|--------------|------|-----|
| `cluster-admin` for apps | Full cluster takeover | Scoped Role with specific verbs |
| `rules: [{apiGroups: ["*"], resources: ["*"], verbs: ["*"]}]` | God mode | Enumerate specific resources and verbs |
| `automountServiceAccountToken: true` (default) | Token exposed to all containers | Set `false`, mount only when needed |
| ClusterRoleBinding for namespace workloads | Access beyond namespace | RoleBinding referencing ClusterRole |
| Same SA for multiple workloads | Blast radius | One SA per workload |
| Long-lived SA tokens | Token theft | Use TokenRequestAPI (bound, short-lived) |
| No RBAC review process | Privilege creep | Quarterly audit with rbac-lookup |

---

## Developer vs Admin/SRE Persona Roles

### Developer Role (Namespace-Scoped)

Developers deploy apps, check logs, port-forward — never manage cluster infra.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer
  namespace: "{{NAMESPACE}}"
rules:
  # Workload management
  - apiGroups: ["apps"]
    resources: [deployments, replicasets, statefulsets]
    verbs: [get, list, watch, create, update, patch]
  # Pod operations (logs, exec, port-forward)
  - apiGroups: [""]
    resources: [pods, pods/log, pods/portforward, pods/exec]
    verbs: [get, list, watch, create]
  # Config and secrets (read only — secrets created by pipeline)
  - apiGroups: [""]
    resources: [configmaps]
    verbs: [get, list, watch, create, update, patch]
  - apiGroups: [""]
    resources: [secrets]
    verbs: [get, list, watch]
  # Services
  - apiGroups: [""]
    resources: [services, endpoints]
    verbs: [get, list, watch, create, update, patch]
  # Events (troubleshooting)
  - apiGroups: [""]
    resources: [events]
    verbs: [get, list, watch]
  # HPA (self-service scaling)
  - apiGroups: [autoscaling]
    resources: [horizontalpodautoscalers]
    verbs: [get, list, watch, create, update, patch]
  # CronJobs
  - apiGroups: [batch]
    resources: [jobs, cronjobs]
    verbs: [get, list, watch, create, delete]
  # NOT allowed: Namespace, Node, ClusterRole, PV, NetworkPolicy
```

### Admin/SRE Role (Cluster-Scoped)

Admins manage cluster infra, policies, nodes, RBAC, networking.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: platform-admin
rules:
  # Cluster operations
  - apiGroups: [""]
    resources: [nodes, namespaces, persistentvolumes]
    verbs: ["*"]
  # RBAC management
  - apiGroups: [rbac.authorization.k8s.io]
    resources: [roles, rolebindings, clusterroles, clusterrolebindings]
    verbs: ["*"]
  # Networking + policies
  - apiGroups: [networking.k8s.io]
    resources: [networkpolicies, ingresses]
    verbs: ["*"]
  - apiGroups: [kyverno.io]
    resources: [clusterpolicies, policies]
    verbs: ["*"]
  # Storage
  - apiGroups: [storage.k8s.io]
    resources: [storageclasses]
    verbs: ["*"]
  # CRDs (operators, mesh, etc.)
  - apiGroups: [apiextensions.k8s.io]
    resources: [customresourcedefinitions]
    verbs: [get, list, watch, create, update]
  # ArgoCD applications
  - apiGroups: [argoproj.io]
    resources: [applications, applicationsets, appprojects]
    verbs: ["*"]
```

### Persona Permission Matrix

| Action | Developer | Team Lead | SRE/Admin |
|--------|-----------|-----------|-----------|
| Deploy workloads | Own namespace | Team namespaces | All namespaces |
| View logs/events | Own namespace | Team namespaces | Cluster-wide |
| kubectl exec | Own pods | Team pods | All pods |
| Port-forward | Own services | Team services | All services |
| Create secrets | No (pipeline only) | Own namespace | All |
| Manage RBAC | No | No | Yes |
| Manage NetworkPolicy | No | No | Yes |
| Manage nodes | No | No | Yes |
| Access ArgoCD | View own apps | Sync team apps | Full admin |
| Manage Kyverno | No | No | Yes |
| Break-glass admin | No | Request | Execute |

---

## Best Practices Summary

1. **Default deny:** `automountServiceAccountToken: false` on all ServiceAccounts
2. **One SA per workload:** Never share ServiceAccounts between deployments
3. **Namespace-scoped first:** Use Role + RoleBinding unless cluster access is justified
4. **Aggregated ClusterRoles:** Compose roles from fragments for maintainability
5. **OIDC groups, not users:** Bind to groups so team changes are handled in IdP
6. **resourceNames when possible:** Restrict to specific ConfigMaps, Secrets by name
7. **Audit quarterly:** Use rbac-lookup and who-can to find privilege creep
8. **Impersonation for debugging:** Never share admin credentials
9. **GitOps for RBAC:** All Role/RoleBinding changes go through PR review
10. **Break-glass procedure:** Document emergency admin access with audit trail
