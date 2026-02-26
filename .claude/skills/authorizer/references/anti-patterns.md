# Authorization Anti-Patterns — 25 Common Mistakes

## Critical (Immediate Risk)

### AP-01: cluster-admin Bindings for Non-Admins
```yaml
# BAD — service account with cluster-admin
subjects:
  - kind: ServiceAccount
    name: my-app
roleRef:
  kind: ClusterRole
  name: cluster-admin   # NEVER for app SAs
```
**Risk**: Full cluster compromise if SA token stolen. CVE-2018-1002105 (privilege escalation)
**Fix**: Scope to specific resources with minimal verbs

### AP-02: Wildcard Verbs in Roles
```yaml
# BAD
rules:
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["*"]         # Equivalent to cluster-admin
```
**Fix**: Enumerate exact resources and verbs needed

### AP-03: Secrets with Broad Access
```yaml
# BAD — any pod can read all secrets
rules:
  - resources: ["secrets"]
    verbs: ["get", "list", "watch"]  # list reveals all secret names
```
**Fix**: Restrict to specific secret names using `resourceNames`
```yaml
rules:
  - resources: ["secrets"]
    resourceNames: ["my-app-config"]   # Specific secret only
    verbs: ["get"]
```

### AP-04: automountServiceAccountToken Not Disabled
```yaml
# BAD — default mounts SA token in every pod
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-app
# Missing: automountServiceAccountToken: false
```
**Risk**: Lateral movement if pod compromised. Token persists until SA deleted.
**Fix**: `automountServiceAccountToken: false` on SA; use projected tokens explicitly

### AP-05: Long-Lived Tokens (Static Secret Tokens)
```bash
# BAD — legacy token (no expiry)
kubectl create serviceaccount my-app
kubectl create token my-app   # Without --duration
```
**Fix**: Use projected ServiceAccount tokens with `expirationSeconds: 3600`

### AP-06: pod/exec Access for Non-Operators
```yaml
# BAD — application SA can exec into pods
rules:
  - resources: ["pods/exec"]
    verbs: ["create"]   # RCE vector
```
**Risk**: Remote code execution in any pod. Audit all uses via Falco.
**Fix**: Remove from all non-operator roles; log all exec events

### AP-07: Sharing ServiceAccounts Across Teams
```yaml
# BAD — shared SA for multiple microservices
apiVersion: v1
kind: ServiceAccount
metadata:
  name: shared-backend-sa   # Backend + frontend + worker all use this
```
**Risk**: If one service compromised, attacker has access as all services
**Fix**: One SA per distinct workload; name `<app>-<component>-sa`

---

## High Risk

### AP-08: No NetworkPolicy (Flat Network)
```bash
# BAD — any pod can reach any other pod
kubectl get networkpolicies -A  # Returns nothing
```
**Risk**: Lateral movement after pod compromise; no blast radius containment
**Fix**: Default-deny-all + explicit allow-list per namespace

### AP-09: PSA Not Enforced
```yaml
# BAD — namespace with no PSA labels
apiVersion: v1
kind: Namespace
metadata:
  name: production
  # Missing pod-security.kubernetes.io/enforce label
```
**Fix**: All production namespaces must have `enforce: restricted`

### AP-10: OIDC Without Group Claims
```bash
# BAD — OIDC configured without groups
--oidc-username-claim=email
# Missing: --oidc-groups-claim=groups
```
**Risk**: All users individually bound; no group management; stale bindings
**Fix**: Configure groups claim; bind ClusterRoles to Groups not Users

### AP-11: Permissive Istio mTLS Mode
```yaml
# BAD — PERMISSIVE allows plain-text traffic
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
spec:
  mtls:
    mode: PERMISSIVE   # Any non-mTLS traffic allowed
```
**Fix**: `STRICT` in production; `PERMISSIVE` only during migration period

### AP-12: No Expiry on Temporary Access
```yaml
# BAD — "temporary" RoleBinding with no expiry
kind: RoleBinding
metadata:
  name: temp-access-alice-production  # Forgotten, never removed
```
**Fix**: Controller-managed RoleBindings with `authorizer.io/expires-at` annotation

### AP-13: ClusterRoles Without Namespace Scope
```yaml
# BAD — ClusterRole bound with ClusterRoleBinding to developer
subjects:
  - kind: User
    name: alice@company.com
roleRef:
  kind: ClusterRole
  name: developer-role
```
**Risk**: Developer accesses all namespaces
**Fix**: Use RoleBinding (namespace-scoped) instead of ClusterRoleBinding for developers

### AP-14: Verbose Audit Policy (or No Audit)
```yaml
# BAD — audit everything at RequestResponse
rules:
  - level: RequestResponse   # 10x log volume, massive storage
# OR — no audit policy at all
```
**Fix**: Tiered audit policy: `RequestResponse` for secrets/RBAC, `Metadata` for others

---

## Medium Risk

### AP-15: Node IAM Profile with Broad Permissions (Cloud)
**Risk**: All pods on node share IAM role; any pod can call AWS APIs
**Fix**: Use IRSA or EKS Pod Identity; restrict node IAM to EC2 metadata only

### AP-16: Lack of RBAC for CRDs
```yaml
# BAD — CRD deployed with no accompanying RBAC
# Any authenticated user can read/write ExternalSecrets
```
**Fix**: Define ClusterRoles for CRD resources; restrict to specific namespaces/SAs

### AP-17: Wildcard Namespace in RoleBinding
```yaml
# BAD (conceptually) — using ClusterRoleBinding when RoleBinding suffices
kind: ClusterRoleBinding   # Instead of per-namespace RoleBinding
```
**Fix**: Prefer RoleBinding within specific namespaces; only use ClusterRoleBinding when cluster-wide access is genuinely needed

### AP-18: No Image Signature Verification
```yaml
# BAD — pulling any image without signature check
containers:
  - image: registry.company.com/backend:latest  # Unsigned, potentially tampered
```
**Fix**: Kyverno `verifyImages` with Cosign public key or Notation

### AP-19: Secrets in Environment Variables
```yaml
# BAD — secret as env var (visible in process list)
env:
  - name: DB_PASSWORD
    value: "plaintext-password"
```
**Fix**: Use `secretKeyRef` → ExternalSecrets → Vault Agent injection

### AP-20: No Egress NetworkPolicy for Sensitive Workloads
```yaml
# BAD — payment processor pod can reach any internet host
# No egress NetworkPolicy in namespace
```
**Risk**: Data exfiltration, command-and-control callbacks
**Fix**: Default-deny egress; explicit allow to specific IPs/domains

---

## Operational Mistakes

### AP-21: Bypassing Admission with Direct etcd Access
**Risk**: Policy engines (OPA/Kyverno) bypass; unreviewed objects created
**Fix**: mTLS on etcd; no etcd access except kube-apiserver; rotate etcd certs

### AP-22: Testing with Production Credentials
**Risk**: Developer tests with prod kubeconfig → accidental production impact
**Fix**: Separate kubeconfig per environment; CI/CD uses scoped SAs with short tokens

### AP-23: Single Point of Failure for cluster-admin
```bash
# BAD — only one cluster-admin user
kubectl get clusterrolebindings | grep cluster-admin
# Only admin@company.com — what if they leave?
```
**Fix**: At least 2 break-glass accounts; emergency access procedure documented

### AP-24: Not Rotating Certificates
```bash
# BAD — cert approaching expiry
kubeadm certs check-expiration
# apiserver: 10 days remaining
```
**Fix**: cert-manager with auto-renewal; alert at 30d expiry; annual kubeadm cert renewal

### AP-25: Using Default Service Accounts in Workloads
```yaml
# BAD — using default SA (has cluster-wide scope via default binding)
spec:
  serviceAccountName: default   # Never use default SA
```
**Fix**: Create dedicated SA per app; never use `default`; set `automountServiceAccountToken: false` on `default` SA in all namespaces

---

## Quick Audit Script

```bash
#!/bin/bash
# Quick auth audit — run this first on any cluster

echo "=== cluster-admin bindings ==="
kubectl get clusterrolebindings -o json | \
  jq -r '.items[] | select(.roleRef.name=="cluster-admin") | "\(.metadata.name): \(.subjects[].name)"'

echo "=== Wildcard roles ==="
kubectl get clusterroles -o json | \
  jq -r '.items[] | select(.rules[]?.verbs[]? == "*") | .metadata.name' | \
  grep -v "system:"

echo "=== SAs with automount enabled ==="
kubectl get sa -A -o json | \
  jq -r '.items[] | select(.automountServiceAccountToken != false) | "\(.metadata.namespace)/\(.metadata.name)"'

echo "=== Namespaces without PSA ==="
kubectl get namespaces -o json | \
  jq -r '.items[] | select(.metadata.labels["pod-security.kubernetes.io/enforce"] == null) | .metadata.name'

echo "=== Namespaces without NetworkPolicy ==="
for ns in $(kubectl get namespaces -o name | cut -d/ -f2); do
  count=$(kubectl get networkpolicies -n $ns --no-headers 2>/dev/null | wc -l)
  [ "$count" -eq 0 ] && echo "$ns: NO NetworkPolicy"
done
```
