# Kubernetes Security (4C Layer 2)

## API Server Hardening

```yaml
# kube-apiserver flags (kubeadm ClusterConfiguration)
apiServer:
  extraArgs:
    # Authentication
    anonymous-auth: "false"
    oidc-issuer-url: "https://accounts.google.com"
    oidc-client-id: "kubernetes"

    # Authorization
    authorization-mode: "Node,RBAC"

    # Admission Control
    enable-admission-plugins: >
      NodeRestriction,
      PodSecurity,
      ResourceQuota,
      LimitRanger,
      ServiceAccount,
      DefaultStorageClass,
      ValidatingAdmissionWebhook,
      MutatingAdmissionWebhook

    # Encryption at rest
    encryption-provider-config: "/etc/kubernetes/encryption/config.yaml"

    # Audit logging
    audit-log-path: "/var/log/kubernetes/audit.log"
    audit-log-maxage: "30"
    audit-log-maxbackup: "10"
    audit-log-maxsize: "100"
    audit-policy-file: "/etc/kubernetes/audit-policy.yaml"

    # TLS
    tls-min-version: "VersionTLS13"
    tls-cipher-suites: "TLS_AES_128_GCM_SHA256,TLS_AES_256_GCM_SHA384"

    # Misc hardening
    profiling: "false"
    request-timeout: "300s"
    service-account-lookup: "true"
```

## Encryption at Rest

```yaml
# /etc/kubernetes/encryption/config.yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
      - configmaps
    providers:
      - aescbc:                      # AES-CBC with PKCS#7 padding
          keys:
            - name: key1
              secret: c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLXN0cmluZw==
      - identity: {}                 # Fallback: unencrypted (for migration)
  - resources:
      - events                       # Don't encrypt events (performance)
    providers:
      - identity: {}
```

## Kubernetes Audit Policy

```yaml
# /etc/kubernetes/audit-policy.yaml
apiVersion: audit.k8s.io/v1
kind: Policy
omitStages:
  - RequestReceived               # Reduce noise

rules:
  # Log all secrets/configmaps at RequestResponse
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["secrets", "configmaps"]

  # Log pod creation/deletion at RequestResponse
  - level: RequestResponse
    verbs: ["create", "update", "delete", "patch"]
    resources:
      - group: ""
        resources: ["pods", "services", "persistentvolumeclaims"]

  # Log RBAC changes
  - level: RequestResponse
    resources:
      - group: "rbac.authorization.k8s.io"
        resources: ["roles", "rolebindings", "clusterroles", "clusterrolebindings"]

  # Log authentication (at Metadata only — no body)
  - level: Metadata
    verbs: ["get", "list", "watch"]
    resources:
      - group: ""
        resources: ["pods", "nodes", "services"]

  # Log everything else at Metadata level
  - level: Metadata
    omitStages:
      - RequestReceived
```

---

## RBAC: Least-Privilege Patterns

### ServiceAccount Per Workload

```yaml
# NEVER use default ServiceAccount
# Create a dedicated SA per deployment

apiVersion: v1
kind: ServiceAccount
metadata:
  name: payment-service
  namespace: payments
  labels:
    app: payment-service
automountServiceAccountToken: false   # Disable auto-mount; use projected token
---
# Mount as projected token with expiry
apiVersion: v1
kind: Pod
spec:
  serviceAccountName: payment-service
  volumes:
    - name: token
      projected:
        sources:
          - serviceAccountToken:
              path: token
              expirationSeconds: 3600    # 1-hour expiry
              audience: payment-api
  containers:
    - name: app
      volumeMounts:
        - name: token
          mountPath: /var/run/secrets/kubernetes.io/serviceaccount
          readOnly: true
```

### Minimal RBAC Roles

```yaml
# Role: read own ConfigMaps only
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: payment-service-role
  namespace: payments
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["payment-service-config"]   # Named resource restriction
    verbs: ["get", "watch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get"]                               # Own pod status only
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: payment-service-binding
  namespace: payments
subjects:
  - kind: ServiceAccount
    name: payment-service
    namespace: payments
roleRef:
  kind: Role
  apiVersion: rbac.authorization.k8s.io/v1
  name: payment-service-role
```

### RBAC Anti-Patterns to Avoid

```yaml
# DANGEROUS — never do this in production
# Bad: wildcard verbs
rules:
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["*"]

# Bad: cluster-admin for application workload
roleRef:
  kind: ClusterRole
  name: cluster-admin

# Bad: allow pod exec (enables container escape)
rules:
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]

# CORRECT: restrict exec to specific namespaces with justification
# and time-bound access via IAM condition
```

### RBAC Audit with kubectl-who-can

```bash
# Check who can exec into pods
kubectl who-can create pods/exec --all-namespaces

# Check who can read secrets
kubectl who-can get secrets --all-namespaces

# Check a specific service account's permissions
kubectl auth can-i --list --as=system:serviceaccount:payments:payment-service

# Detect cluster-admin bindings
kubectl get clusterrolebindings -o json | \
  jq '.items[] | select(.roleRef.name == "cluster-admin") | .subjects'
```

---

## Pod Security Standards (PSS) / Pod Security Admission (PSA)

### Namespace Labels for PSA

```yaml
# Enforce Restricted profile in production
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    # Enforce: reject violating pods
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: v1.32

    # Warn: log warnings for violating pods (audit period)
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: v1.32

    # Audit: record violating pods in audit log
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: v1.32
```

### PSS Profile Hierarchy

```
Privileged (no restrictions) — only for system namespaces (kube-system)
  ↓
Baseline (prevent known privilege escalations) — staging/dev workloads
  ↓
Restricted (maximum hardening) — ALL production workloads (default goal)
```

### Restricted Profile Requirements

```yaml
# A pod that satisfies PSS Restricted profile
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534              # nobody
    runAsGroup: 65534
    fsGroup: 65534
    seccompProfile:
      type: RuntimeDefault        # Or Localhost with custom profile

  containers:
    - name: app
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
          add: []                 # Only add NET_BIND_SERVICE if port < 1024
      resources:
        requests:
          memory: "64Mi"
          cpu: "100m"
        limits:
          memory: "256Mi"
          cpu: "500m"

  # No hostNetwork, hostPID, hostIPC
  # No hostPath volumes
  # No privileged containers
```

---

## NetworkPolicy: Zero-Trust Patterns

### Default-Deny All

```yaml
# Apply to every namespace before any allow rules
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: production
spec:
  podSelector: {}             # Matches ALL pods in namespace
  policyTypes:
    - Ingress
    - Egress
  # No ingress/egress rules = deny everything
```

### Allow DNS + System Services

```yaml
# Always allow DNS (required for service discovery)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
      to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
```

### Microservice Allow Pattern

```yaml
# payment-service: only allow ingress from order-service
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-service-ingress
  namespace: payments
spec:
  podSelector:
    matchLabels:
      app: payment-service
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: orders
          podSelector:
            matchLabels:
              app: order-service
      ports:
        - port: 8080
          protocol: TCP
---
# payment-service: only allow egress to database
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-service-egress
  namespace: payments
spec:
  podSelector:
    matchLabels:
      app: payment-service
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
          namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: databases
      ports:
        - port: 5432
    - to:                         # Allow metrics scraping by Prometheus
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
      ports:
        - port: 9090
```

---

## Resource Quotas and LimitRange

```yaml
# Namespace ResourceQuota — prevent noisy neighbor DoS
apiVersion: v1
kind: ResourceQuota
metadata:
  name: production-quota
  namespace: production
spec:
  hard:
    requests.cpu: "20"
    requests.memory: "40Gi"
    limits.cpu: "40"
    limits.memory: "80Gi"
    pods: "100"
    services: "20"
    persistentvolumeclaims: "10"
    count/secrets: "50"
    count/configmaps: "50"
---
# LimitRange — enforce default limits if not specified
apiVersion: v1
kind: LimitRange
metadata:
  name: production-limits
  namespace: production
spec:
  limits:
    - type: Container
      default:
        cpu: "500m"
        memory: "256Mi"
      defaultRequest:
        cpu: "100m"
        memory: "64Mi"
      max:
        cpu: "4"
        memory: "4Gi"
      min:
        cpu: "10m"
        memory: "16Mi"
```

---

## kube-bench CIS Audit

```bash
# Run CIS Kubernetes Benchmark L2
kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job.yaml
kubectl logs -l app=kube-bench

# Key CIS checks:
# 1.1.1  API server: --anonymous-auth=false
# 1.1.12 API server: encryption-provider-config set
# 1.1.19 API server: audit-policy-file configured
# 2.1.1  etcd: --cert-file, --key-file set
# 3.1.1  kubectl: use certificates (not credentials)
# 4.1.1  Worker nodes: kubelet --anonymous-auth=false
# 5.1.1  RBAC: no cluster-admin for service accounts
# 5.4.1  Secrets: not stored as environment variables
```
