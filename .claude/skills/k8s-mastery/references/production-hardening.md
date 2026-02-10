# Production Hardening

Comprehensive production readiness checklist, compliance mapping, security enforcement, and incident response for Kubernetes.

---

## Production Readiness Checklist (40+ Items)

### Compute and Scheduling
- [ ] All containers have CPU and memory requests AND limits
- [ ] VPA or Goldilocks deployed for right-sizing recommendations
- [ ] HPA configured for all user-facing workloads
- [ ] Topology spread constraints configured for multi-AZ
- [ ] PodDisruptionBudgets for all production Deployments/StatefulSets
- [ ] Node affinity rules for stateful workloads (same AZ as volumes)
- [ ] Preemption priority classes defined (system-critical, high, default, low)
- [ ] terminationGracePeriodSeconds set appropriately (not default 30s for long tasks)

### Security
- [ ] Pod Security Standards enforced (restricted or baseline per namespace)
- [ ] No containers running as root
- [ ] No privileged containers
- [ ] Read-only root filesystem where possible
- [ ] SecurityContext: runAsNonRoot, allowPrivilegeEscalation=false
- [ ] All images from private registry with digest pinning
- [ ] Image signing with Cosign, verified at admission
- [ ] SBOM generated for all images
- [ ] NetworkPolicies: default deny ingress + egress per namespace
- [ ] RBAC: no cluster-admin for workloads, least privilege per namespace
- [ ] Secrets encrypted at rest (KMS provider)
- [ ] No default ServiceAccount tokens auto-mounted
- [ ] Falco or Tetragon for runtime security monitoring

### Networking
- [ ] Ingress TLS termination with cert-manager auto-renewal
- [ ] Rate limiting at ingress level
- [ ] NetworkPolicy default deny in every namespace
- [ ] Service mesh mTLS (Istio/Linkerd) for east-west traffic
- [ ] DNS policy set appropriately for pods
- [ ] ExternalDNS for automatic DNS management

### Observability
- [ ] Prometheus + Grafana for metrics
- [ ] Loki or Elasticsearch for centralized logging
- [ ] Distributed tracing (Jaeger/Tempo) with OpenTelemetry
- [ ] Alerting rules for SLOs (latency, error rate, availability)
- [ ] On-call rotation configured in PagerDuty/Opsgenie
- [ ] Dashboards for all critical services
- [ ] Kubernetes events exported to logging system

### Reliability
- [ ] Liveness, readiness, and startup probes on all containers
- [ ] Velero backup schedules for all namespaces
- [ ] etcd snapshots automated and tested
- [ ] DR runbook written and tested quarterly
- [ ] Chaos engineering tests (Litmus/Chaos Mesh) run periodically
- [ ] Circuit breakers for external dependencies

### Deployment
- [ ] GitOps (ArgoCD/Flux) -- no manual kubectl apply in production
- [ ] Progressive rollout strategy (canary/blue-green via Argo Rollouts)
- [ ] Rollback procedure documented and tested
- [ ] Pre-deploy and post-deploy smoke tests automated
- [ ] Resource quotas and limit ranges per namespace
- [ ] Namespace isolation with RBAC and NetworkPolicy

### Compliance
- [ ] Audit logging enabled and shipped to SIEM
- [ ] Pod security admission enforced
- [ ] OPA/Kyverno policies for organizational standards
- [ ] Image vulnerability scanning in CI/CD pipeline
- [ ] Secrets rotation automated
- [ ] Access reviews documented quarterly

---

## Compliance Mapping

### SOC 2

| Control | K8s Implementation |
|---------|-------------------|
| CC6.1 Logical access | RBAC with namespace isolation, OIDC authentication |
| CC6.3 Access removal | Automated RBAC via GitOps, IdP group sync |
| CC7.1 Detect threats | Falco runtime monitoring, audit logs to SIEM |
| CC7.2 Monitor infrastructure | Prometheus alerts, node/pod/container metrics |
| CC8.1 Change management | GitOps (ArgoCD), all changes via reviewed PRs |
| CC9.1 Risk mitigation | PDB, multi-AZ topology, DR tested quarterly |

### HIPAA

| Requirement | K8s Implementation |
|------------|-------------------|
| Access control (164.312a) | RBAC, namespace isolation, OIDC + MFA |
| Audit controls (164.312b) | K8s audit policy at RequestResponse level |
| Integrity (164.312c) | Image signing (Cosign), admission webhook verification |
| Encryption in transit (164.312e) | Service mesh mTLS, ingress TLS |
| Encryption at rest | etcd encryption (KMS), PV encryption (CSI) |
| BAA compliance | Node isolation for PHI namespaces, dedicated node pools |

### PCI-DSS

| Requirement | K8s Implementation |
|------------|-------------------|
| Req 1: Firewall | NetworkPolicy default deny, segmented namespaces |
| Req 2: No defaults | No default SA tokens, custom security contexts |
| Req 3: Protect data | Encrypted PVs, sealed secrets, vault integration |
| Req 6: Secure apps | Image scanning (Trivy), admission control (OPA/Kyverno) |
| Req 7: Restrict access | RBAC least privilege, namespace-scoped roles |
| Req 8: Authentication | OIDC + MFA, short-lived tokens |
| Req 10: Logging | Audit logs, access logs, SIEM integration |
| Req 11: Testing | Chaos engineering, penetration testing |

### FedRAMP

| Control | K8s Implementation |
|---------|-------------------|
| AC-2 Account mgmt | OIDC + IdP integration, automated offboarding |
| AU-2 Auditable events | K8s audit policy, API server audit logging |
| CM-2 Baseline config | GitOps, OPA/Kyverno policy enforcement |
| IA-2 MFA | OIDC provider with MFA enforcement |
| SC-7 Boundary protection | NetworkPolicy, ingress/egress controls |
| SC-28 Data at rest | KMS-backed etcd encryption, encrypted PVs |
| SI-4 Monitoring | Falco, Prometheus, SIEM integration |

---

## Kubernetes Audit Policy

```yaml
apiVersion: audit.k8s.io/v1
kind: Policy
metadata:
  name: production-audit-policy
rules:
  # Do not log requests to the following API endpoints
  - level: None
    users: ["system:kube-proxy"]
    verbs: ["watch"]
    resources:
      - group: ""
        resources: ["endpoints", "services", "services/status"]

  # Do not log healthcheck and readiness probes
  - level: None
    nonResourceURLs:
      - /healthz*
      - /readyz*
      - /livez*
      - /metrics

  # Do not log authenticated requests to certain non-resource URLs
  - level: None
    userGroups: ["system:authenticated"]
    nonResourceURLs:
      - /api*
      - /version

  # Log Secret and TokenReview access at RequestResponse level
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["secrets", "configmaps"]
      - group: "authentication.k8s.io"
        resources: ["tokenreviews"]
    omitStages:
      - RequestReceived

  # Log all RBAC changes at RequestResponse level
  - level: RequestResponse
    resources:
      - group: "rbac.authorization.k8s.io"
        resources:
          - roles
          - rolebindings
          - clusterroles
          - clusterrolebindings
    omitStages:
      - RequestReceived

  # Log pod exec/attach/portforward at RequestResponse
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["pods/exec", "pods/attach", "pods/portforward"]
    omitStages:
      - RequestReceived

  # Log all namespace and node changes
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["namespaces", "nodes"]
    verbs: ["create", "update", "patch", "delete"]
    omitStages:
      - RequestReceived

  # Log all write operations at Request level
  - level: Request
    verbs: ["create", "update", "patch", "delete", "deletecollection"]
    omitStages:
      - RequestReceived

  # Log read operations at Metadata level
  - level: Metadata
    verbs: ["get", "list", "watch"]
    omitStages:
      - RequestReceived

  # Catch-all at Metadata level
  - level: Metadata
    omitStages:
      - RequestReceived
```

---

## Pod Security Standards Enforcement

```yaml
# Namespace labels to enforce Pod Security Standards
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    # Enforce restricted (strictest) -- reject non-compliant pods
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: latest
    # Warn on restricted violations (shows warnings but allows)
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: latest
    # Audit restricted violations (logged in audit log)
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: latest
---
# Baseline for staging (less strict)
apiVersion: v1
kind: Namespace
metadata:
  name: staging
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: latest
---
# Privileged for system namespaces only
apiVersion: v1
kind: Namespace
metadata:
  name: kube-system
  labels:
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/enforce-version: latest
```

### Compliant Pod (Restricted Profile)

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: compliant-pod
  namespace: production
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534
    runAsGroup: 65534
    fsGroup: 65534
    seccompProfile:
      type: RuntimeDefault
  automountServiceAccountToken: false
  containers:
    - name: app
      image: myregistry/app:v1.2.0@sha256:abc123...
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
      resources:
        requests:
          cpu: 100m
          memory: 128Mi
        limits:
          cpu: 500m
          memory: 512Mi
      volumeMounts:
        - name: tmp
          mountPath: /tmp
  volumes:
    - name: tmp
      emptyDir:
        sizeLimit: 100Mi
```

---

## Runtime Security

### Falco Rules

```yaml
# falco-custom-rules.yaml
customRules:
  custom-rules.yaml: |-
    - rule: Detect Shell in Container
      desc: Alert when a shell is spawned inside a container
      condition: >
        spawned_process and container and
        proc.name in (bash, sh, zsh, dash, ksh) and
        not proc.pname in (cron, crond, supervisord)
      output: >
        Shell spawned in container
        (user=%user.name container=%container.name image=%container.image.repository
        shell=%proc.name parent=%proc.pname cmdline=%proc.cmdline)
      priority: WARNING
      tags: [container, shell, mitre_execution]

    - rule: Detect Crypto Mining
      desc: Alert on known crypto mining pool connections
      condition: >
        outbound and fd.sip.name in
        (pool.minergate.com, xmr.pool.minergate.com,
         pool.supportxmr.com, mining.pool.example.com)
      output: >
        Crypto mining pool connection detected
        (user=%user.name container=%container.name image=%container.image.repository
        dest=%fd.sip.name:%fd.sport)
      priority: CRITICAL
      tags: [container, network, crypto]

    - rule: Detect Sensitive File Read
      desc: Alert when sensitive files are read in containers
      condition: >
        open_read and container and
        fd.name in (/etc/shadow, /etc/passwd, /etc/kubernetes/admin.conf,
                     /var/run/secrets/kubernetes.io/serviceaccount/token)
      output: >
        Sensitive file read in container
        (user=%user.name file=%fd.name container=%container.name
        image=%container.image.repository)
      priority: WARNING
      tags: [container, filesystem, mitre_credential_access]

    - rule: Detect Package Manager Execution
      desc: Alert when package managers run in production containers
      condition: >
        spawned_process and container and
        proc.name in (apt, apt-get, yum, dnf, apk, pip, npm) and
        k8s.ns.name = "production"
      output: >
        Package manager executed in production
        (user=%user.name proc=%proc.name container=%container.name
        namespace=%k8s.ns.name)
      priority: ERROR
      tags: [container, process, mitre_execution]
```

### Tetragon TracingPolicy

```yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: sensitive-file-access
spec:
  kprobes:
    - call: fd_install
      syscall: false
      args:
        - index: 0
          type: int
        - index: 1
          type: file
      selectors:
        - matchArgs:
            - index: 1
              operator: Prefix
              values:
                - /etc/shadow
                - /etc/kubernetes
                - /var/run/secrets
          matchActions:
            - action: Sigkill      # Kill the process immediately
            - action: Post         # Also send event to log
---
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: network-egress-monitor
spec:
  kprobes:
    - call: tcp_connect
      syscall: false
      args:
        - index: 0
          type: sock
      selectors:
        - matchArgs:
            - index: 0
              operator: NotDAddr
              values:
                - 10.0.0.0/8       # Allow cluster CIDR
                - 172.16.0.0/12
          matchNamespaces:
            - namespace: production
              operator: In
          matchActions:
            - action: Post
              rateLimit: "1m"
```

---

## Supply Chain Security

### Cosign Image Signing and Verification

```yaml
# Kyverno policy to verify image signatures
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-image-signature
spec:
  validationFailureAction: Enforce
  background: false
  webhookTimeoutSeconds: 30
  rules:
    - name: verify-cosign-signature
      match:
        any:
          - resources:
              kinds:
                - Pod
      verifyImages:
        - imageReferences:
            - "myregistry.io/*"
          attestors:
            - entries:
                - keyless:
                    subject: "https://github.com/myorg/*"
                    issuer: "https://token.actions.githubusercontent.com"
                    rekor:
                      url: https://rekor.sigstore.dev
          mutateDigest: true
          verifyDigest: true
          required: true
---
# SBOM attestation verification
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-sbom
spec:
  validationFailureAction: Enforce
  rules:
    - name: check-sbom-attestation
      match:
        any:
          - resources:
              kinds:
                - Pod
      verifyImages:
        - imageReferences:
            - "myregistry.io/*"
          attestations:
            - type: https://spdx.dev/Document
              attestors:
                - entries:
                    - keyless:
                        subject: "https://github.com/myorg/*"
                        issuer: "https://token.actions.githubusercontent.com"
              conditions:
                - all:
                    - key: "{{ creationInfo.created }}"
                      operator: NotEquals
                      value: ""
```

---

## Incident Response

### Escalation Matrix

```
Severity | Response Time | Who           | Channel
---------|---------------|---------------|------------------
SEV1     | 5 min         | On-call + Mgr | #war-room (Slack)
SEV2     | 15 min        | On-call       | #incidents
SEV3     | 1 hour        | Team lead     | #ops-alerts
SEV4     | Next bus day   | Assigned eng  | Jira ticket
```

### Production Deployment Checklist

**Pre-Deploy**:
- [ ] All CI checks passing (lint, test, security scan)
- [ ] Image signed and pushed to production registry
- [ ] Changelog reviewed and approved
- [ ] Feature flags configured for gradual rollout
- [ ] Rollback procedure confirmed
- [ ] Monitoring dashboards open

**During Deploy**:
- [ ] Deploy via GitOps merge (never manual kubectl)
- [ ] Watch rollout: `kubectl rollout status deployment/<name> -n production`
- [ ] Monitor error rates, latency, and 5xx in Grafana
- [ ] Check pod health: `kubectl get pods -n production -l app=<name>`
- [ ] Verify canary metrics (if canary deployment)

**Post-Deploy**:
- [ ] Run smoke tests against production
- [ ] Verify no increase in error rate (compare to baseline)
- [ ] Check resource usage (CPU/memory) is within bounds
- [ ] Confirm logs flowing to centralized logging
- [ ] Update deployment tracker / release notes
- [ ] Remove feature flag after full rollout confirmed

### Network Segmentation Strategy

```yaml
# Default deny all traffic in namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
---
# Allow only specific ingress
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-ingress
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api-gateway
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              network-zone: dmz
          podSelector:
            matchLabels:
              app: ingress-nginx
      ports:
        - protocol: TCP
          port: 8080
---
# Allow DNS egress for all pods
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-egress
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```
