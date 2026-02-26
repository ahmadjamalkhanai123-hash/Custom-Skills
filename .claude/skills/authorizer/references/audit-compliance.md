# Audit & Compliance — CIS, SOC 2, HIPAA, PCI-DSS, FedRAMP

## Kubernetes Audit Policy

### Production Audit Policy (CIS 1.2.x Compliant)

```yaml
# /etc/kubernetes/audit-policy.yaml
apiVersion: audit.k8s.io/v1
kind: Policy
omitStages:
  - "RequestReceived"   # Reduce log volume for non-sensitive requests
rules:
  # Log secret access at RequestResponse level
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["secrets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

  # Log authentication events
  - level: Metadata
    users: ["system:anonymous"]
    verbs: ["*"]

  # Log exec and portforward (high-risk)
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["pods/exec", "pods/portforward", "pods/attach"]

  # Log RBAC changes at RequestResponse
  - level: RequestResponse
    resources:
      - group: "rbac.authorization.k8s.io"
        resources: ["clusterroles", "clusterrolebindings", "roles", "rolebindings"]

  # Log admission webhook config changes
  - level: RequestResponse
    resources:
      - group: "admissionregistration.k8s.io"
        resources: ["validatingwebhookconfigurations", "mutatingwebhookconfigurations"]

  # Log cluster-level resource changes
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["namespaces", "persistentvolumes", "nodes"]
    verbs: ["create", "update", "patch", "delete"]

  # Log all workload changes (Metadata level for perf)
  - level: Metadata
    resources:
      - group: "apps"
        resources: ["deployments", "statefulsets", "daemonsets", "replicasets"]
      - group: "batch"
        resources: ["jobs", "cronjobs"]
    verbs: ["create", "update", "patch", "delete"]

  # Log ConfigMap changes (may contain sensitive data)
  - level: Request
    resources:
      - group: ""
        resources: ["configmaps"]
    verbs: ["create", "update", "patch", "delete"]

  # Default: Metadata for everything else
  - level: Metadata
    omitStages:
      - "RequestReceived"
```

---

## CIS Kubernetes Benchmark 1.9 Mappings

### Control Plane (Section 1)

| CIS Control | Check | YAML Fix |
|------------|-------|----------|
| 1.2.1 | Ensure `--anonymous-auth=false` | API server flag |
| 1.2.6 | Ensure `--authorization-mode=Node,RBAC` | API server flag |
| 1.2.7 | Ensure `--authorization-mode` does not include AlwaysAllow | API server flag |
| 1.2.9 | Ensure `--event-rate-limit-config` is set | EventRateLimit admission plugin |
| 1.2.13 | Ensure `--audit-log-path` is set | Audit policy file |
| 1.2.14 | Ensure `--audit-log-maxage=90` | API server flag |
| 1.2.24 | Ensure `--service-account-lookup=true` | API server flag |
| 1.2.33 | Ensure `--encryption-provider-config` is set | EncryptionConfiguration |

### RBAC + Service Accounts (Section 5)

| CIS Control | Check | Remediation |
|------------|-------|-------------|
| 5.1.1 | Ensure cluster-admin only to needed | Audit ClusterRoleBindings to cluster-admin |
| 5.1.2 | Minimize secret access to SA | Restrict secrets verbs in Roles |
| 5.1.3 | Minimize wildcard use in Roles | Grep for `verbs: ["*"]` |
| 5.1.4 | Create service accounts only when needed | `automountServiceAccountToken: false` |
| 5.1.5 | No SAs mounted in non-service pods | Default automount=false |
| 5.1.6 | No `system:masters` binding except admin | Audit ClusterRoleBindings |
| 5.2.1 | PSA: privileged namespace count | label `pod-security.kubernetes.io/enforce` |
| 5.2.2 | No privileged containers | Kyverno/OPA policy |
| 5.2.5 | No root containers | Kyverno `runAsNonRoot: true` |
| 5.2.6 | No host IPC | Kyverno `hostIPC: false` |
| 5.2.8 | No host path volumes | Kyverno disallow host-path |

### CIS Audit Commands

```bash
# Check cluster-admin bindings
kubectl get clusterrolebindings -o json | \
  jq '.items[] | select(.roleRef.name=="cluster-admin") | .subjects'

# Check for wildcard verbs
kubectl get clusterroles -o json | \
  jq '.items[].rules[] | select(.verbs[] == "*") | .'

# Check automountServiceAccountToken
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.automountServiceAccountToken != false) | .metadata.name'

# Check for privileged containers
kubectl get pods -A -o json | \
  jq '.items[].spec.containers[] | select(.securityContext.privileged == true)'
```

---

## SOC 2 Type II — K8s Controls

| SOC 2 Criterion | K8s Control | Implementation |
|----------------|-------------|----------------|
| CC6.1 — Logical access | RBAC + OIDC | `ClusterRoleBinding` per group |
| CC6.2 — Authentication | MFA via OIDC IdP | Keycloak/Okta MFA policy |
| CC6.3 — Access removal | JIT + expiry | Annotated temp RoleBindings |
| CC6.6 — Privileged access | No cluster-admin | Audit + Kyverno block |
| CC6.7 — Encryption in transit | mTLS | Istio STRICT / cert-manager |
| CC6.8 — Vulnerability mgmt | Image scanning | Trivy + Kyverno image verify |
| CC7.1 — System monitoring | Audit logs | Falco + OpenSearch |
| CC7.2 — Incident detection | SIEM alerts | Falco → Slack/PagerDuty |
| CC9.2 — Change management | GitOps | ArgoCD/Flux + PR approval |

---

## HIPAA Technical Safeguards — K8s Controls

| HIPAA Section | Requirement | K8s Implementation |
|--------------|-------------|-------------------|
| §164.312(a)(1) | Access Control | RBAC + OIDC with MFA |
| §164.312(a)(2)(i) | Unique User ID | Individual OIDC accounts |
| §164.312(a)(2)(iv) | Automatic logoff | OIDC token TTL ≤ 1h |
| §164.312(b) | Audit Controls | Audit policy + SIEM |
| §164.312(c)(1) | Integrity Controls | Kyverno + OPA admission |
| §164.312(d) | Person Authentication | OIDC + MFA |
| §164.312(e)(1) | Transmission Security | TLS 1.3 only, mTLS |
| §164.312(e)(2)(ii) | Encryption | cert-manager + K8s encryption-at-rest |

---

## PCI-DSS v4.0 — K8s Controls

| PCI Req | Requirement | K8s Implementation |
|---------|-------------|-------------------|
| 7.2 | Least-privilege access | RBAC minimal roles |
| 7.3 | JIT access management | Time-limited RoleBindings |
| 8.2 | Unique user accounts | OIDC individual emails |
| 8.3 | MFA for admin | OIDC + Duo/Okta MFA |
| 8.6 | System/app accounts | Dedicated SAs, no shared |
| 10.2 | Audit log generation | Full audit policy |
| 10.5 | Audit log protection | Immutable log storage (S3 + WORM) |
| 10.7 | Failure detection | Falco + alerting |
| 11.3 | Vulnerability scanning | Trivy in CI + runtime |

---

## FedRAMP — K8s Controls

| FedRAMP Control | K8s Implementation |
|----------------|-------------------|
| AC-2 Account Management | OIDC + automated deprovisioning |
| AC-3 Access Enforcement | RBAC + OPA deny-by-default |
| AC-6 Least Privilege | Scoped Roles, no cluster-admin |
| AC-17 Remote Access | VPN + kubeconfig OIDC only |
| AU-2 Auditable Events | Full audit policy (all writes) |
| AU-9 Audit Protection | Write-once S3 / CloudWatch |
| IA-2 Identification+Auth | OIDC/PIV with MFA |
| IA-5 Auth Management | Short-lived tokens, cert rotation |
| SC-8 Transmission Integrity | TLS 1.3, mTLS (Istio STRICT) |
| SC-28 Data at Rest | etcd encryption, Sealed Secrets |
| SI-2 Flaw Remediation | Kyverno disallow CVE images |

---

## Falco Runtime Security Rules (Audit Complement)

```yaml
# /etc/falco/rules.d/k8s-auth.yaml
- rule: K8s RBAC Change
  desc: Detect changes to RBAC resources
  condition: >
    ka.verb in (create, update, patch, delete) and
    ka.target.resource in (roles, rolebindings, clusterroles, clusterrolebindings)
  output: >
    K8s RBAC %ka.verb on %ka.target.name by %ka.user.name
    (namespace=%ka.target.namespace, user=%ka.user.name, ip=%ka.source.ip)
  priority: WARNING
  source: k8s_audit

- rule: K8s Secret Access
  desc: Secret read/write by non-system users
  condition: >
    ka.target.resource = secrets and
    not ka.user.name in (system:serviceaccount:kube-system:*)
  output: >
    Secret accessed: %ka.verb on %ka.target.name by %ka.user.name
  priority: WARNING
  source: k8s_audit

- rule: Exec into Pod
  desc: Detect exec/attach into pod
  condition: >
    ka.verb = create and
    ka.target.resource in (pods/exec, pods/attach)
  output: >
    Exec into pod %ka.target.name by %ka.user.name (ip=%ka.source.ip)
  priority: NOTICE
  source: k8s_audit
```
