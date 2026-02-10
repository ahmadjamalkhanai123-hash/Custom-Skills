# Kubernetes Security Hardening

> Production security controls: Pod Security Standards, seccomp, AppArmor, Falco, Tetragon, image verification, audit policy.

---

## Pod Security Standards

Kubernetes Pod Security Admission (PSA) enforces three levels. Apply via namespace labels.

### Restricted (Production Default)

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: latest
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: latest
```

Restricted requires: `runAsNonRoot`, no privilege escalation, drop ALL capabilities, seccomp RuntimeDefault, no hostNetwork/hostPID/hostIPC, read-only root filesystem is recommended.

### Baseline (Staging)

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: staging
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: latest
```

Baseline prevents known privilege escalations but is less strict than restricted. Warn on restricted violations to prepare for promotion.

### Privileged (System Namespaces Only)

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: kube-system
  labels:
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/enforce-version: latest
```

Only for system components (CNI, CSI drivers, monitoring agents) that genuinely need host access.

---

## Security Context: Hardened Pod Template

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-server
  template:
    metadata:
      labels:
        app: api-server
    spec:
      automountServiceAccountToken: false  # Disable unless needed
      serviceAccountName: api-server
      securityContext:
        runAsNonRoot: true
        runAsUser: 65534          # nobody
        runAsGroup: 65534
        fsGroup: 65534
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: api
          image: ghcr.io/myorg/api-server:v2.1.0@sha256:abc123...
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
            # Add specific capabilities ONLY if absolutely required:
            # capabilities:
            #   add:
            #     - NET_BIND_SERVICE  # For binding to ports < 1024
          ports:
            - containerPort: 8080
              protocol: TCP
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            - name: cache
              mountPath: /var/cache
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: "1"
              memory: 512Mi
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 100Mi
        - name: cache
          emptyDir:
            sizeLimit: 200Mi
```

Key patterns:
- `readOnlyRootFilesystem: true` — mount `emptyDir` for `/tmp` and writable paths.
- `automountServiceAccountToken: false` — only mount when the pod needs Kubernetes API access.
- Pin images by digest (`@sha256:...`) to prevent tag mutation attacks.

---

## Seccomp Profiles

### RuntimeDefault (Recommended Baseline)

```yaml
securityContext:
  seccompProfile:
    type: RuntimeDefault
```

RuntimeDefault blocks dangerous syscalls (e.g., `ptrace`, `mount`, `reboot`) while allowing standard application syscalls.

### Custom Seccomp Profile

Deploy custom profiles via a DaemonSet or use `SeccompProfile` resources (requires seccomp operator).

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    {
      "names": [
        "accept4", "bind", "clone", "close", "connect",
        "epoll_create1", "epoll_ctl", "epoll_wait",
        "exit", "exit_group", "fcntl", "fstat",
        "futex", "getpid", "getsockname", "getsockopt",
        "listen", "mmap", "mprotect", "munmap",
        "nanosleep", "openat", "read", "recvfrom",
        "rt_sigaction", "rt_sigprocmask", "sendto",
        "setsockopt", "socket", "write"
      ],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

Reference in pod spec:

```yaml
securityContext:
  seccompProfile:
    type: Localhost
    localhostProfile: profiles/api-server.json
```

The profile file must exist at `/var/lib/kubelet/seccomp/profiles/api-server.json` on each node.

---

## AppArmor Profiles

AppArmor confines processes to a limited set of resources. Available on Ubuntu/Debian nodes.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: api-server
  annotations:
    container.apparmor.security.beta.kubernetes.io/api: runtime/default
spec:
  containers:
    - name: api
      image: ghcr.io/myorg/api-server:v2.1.0
```

### Custom AppArmor Profile

Load on nodes via a DaemonSet:

```
#include <tunables/global>

profile k8s-api-server flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  #include <abstractions/nameservice>

  # Allow network access
  network inet tcp,
  network inet udp,
  network inet6 tcp,
  network inet6 udp,

  # Allow reading application files
  /app/** r,
  /app/bin/api-server ix,

  # Allow writing to tmp and logs
  /tmp/** rw,
  /var/log/app/** rw,

  # Deny everything else
  deny /etc/shadow r,
  deny /proc/*/mem rw,
  deny /sys/** w,
}
```

Reference the custom profile:

```yaml
annotations:
  container.apparmor.security.beta.kubernetes.io/api: localhost/k8s-api-server
```

---

## Falco Runtime Detection

Falco detects anomalous behavior at runtime using kernel syscall monitoring.

### Installation

```bash
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm install falco falcosecurity/falco \
  --namespace falco --create-namespace \
  --set falcosidekick.enabled=true \
  --set falcosidekick.config.slack.webhookurl="https://hooks.slack.com/..." \
  --set driver.kind=ebpf
```

### Custom Falco Rules

```yaml
# falco-rules.yaml (ConfigMap or Helm values)
customRules:
  production-rules.yaml: |-
    - rule: Shell Spawned in Container
      desc: Detect shell execution inside a container
      condition: >
        spawned_process and container and
        proc.name in (bash, sh, zsh, dash, ash) and
        not container.image.repository in (allowed_shell_images)
      output: >
        Shell spawned in container
        (user=%user.name container=%container.name image=%container.image.repository
         shell=%proc.name parent=%proc.pname cmdline=%proc.cmdline)
      priority: WARNING
      tags: [container, shell, mitre_execution]

    - rule: Sensitive File Read in Container
      desc: Detect reading of sensitive files
      condition: >
        open_read and container and
        fd.name in (/etc/shadow, /etc/sudoers, /root/.ssh/authorized_keys,
                     /root/.bash_history, /run/secrets/kubernetes.io/serviceaccount/token)
      output: >
        Sensitive file read in container
        (user=%user.name file=%fd.name container=%container.name image=%container.image.repository)
      priority: ERROR
      tags: [container, filesystem, mitre_credential_access]

    - rule: Crypto Mining Detected
      desc: Detect cryptocurrency mining processes
      condition: >
        spawned_process and container and
        (proc.name in (xmrig, minerd, cpuminer, ethminer) or
         proc.cmdline contains "stratum+tcp://")
      output: >
        Crypto miner detected (process=%proc.name cmdline=%proc.cmdline
        container=%container.name image=%container.image.repository)
      priority: CRITICAL
      tags: [container, crypto, mitre_execution]

    - rule: Unexpected Outbound Connection
      desc: Detect outbound connections to non-standard ports
      condition: >
        outbound and container and
        fd.sport > 1024 and
        not fd.rport in (53, 80, 443, 5432, 6379, 8080, 8443, 9090) and
        not container.image.repository in (known_network_images)
      output: >
        Unexpected outbound connection
        (container=%container.name image=%container.image.repository
         connection=%fd.name port=%fd.rport)
      priority: WARNING
      tags: [container, network, mitre_exfiltration]
```

---

## Tetragon eBPF Security Observability

Tetragon provides deep kernel-level security observability and enforcement using eBPF.

### Installation

```bash
helm repo add cilium https://helm.cilium.io
helm install tetragon cilium/tetragon \
  --namespace kube-system \
  --set tetragon.enableProcessCred=true \
  --set tetragon.enableProcessNs=true
```

### TracingPolicy: File Access Monitoring

```yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: sensitive-file-access
spec:
  kprobes:
    - call: fd_install
      syscall: false
      return: false
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
                - /etc/passwd
                - /run/secrets
                - /var/run/secrets/kubernetes.io
          matchNamespaces:
            - namespace: Pid
              operator: NotIn
              values:
                - "host_ns"
          matchActions:
            - action: Post
```

### TracingPolicy: Network Monitoring

```yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: network-monitoring
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
              operator: DPort
              values:
                - "22"    # SSH
                - "4444"  # Common reverse shell
                - "1337"  # Suspicious
          matchActions:
            - action: Sigkill  # Kill the process immediately
```

### TracingPolicy: Privilege Escalation Detection

```yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: privilege-escalation
spec:
  kprobes:
    - call: __x64_sys_setuid
      syscall: true
      args:
        - index: 0
          type: int
      selectors:
        - matchArgs:
            - index: 0
              operator: Equal
              values:
                - "0"  # setuid(0) = become root
          matchNamespaces:
            - namespace: Pid
              operator: NotIn
              values:
                - "host_ns"
          matchActions:
            - action: Sigkill
            - action: Post
```

---

## Image Verification: Cosign + Kyverno

### Sign Images with Cosign

```bash
# Generate key pair
cosign generate-key-pair

# Sign image
cosign sign --key cosign.key ghcr.io/myorg/api-server:v2.1.0

# Verify
cosign verify --key cosign.pub ghcr.io/myorg/api-server:v2.1.0
```

### Kyverno verifyImages Policy

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-image-signatures
spec:
  validationFailureAction: Enforce
  webhookTimeoutSeconds: 30
  rules:
    - name: verify-cosign-signature
      match:
        any:
          - resources:
              kinds:
                - Pod
              namespaces:
                - production
                - staging
      verifyImages:
        - imageReferences:
            - "ghcr.io/myorg/*"
          attestors:
            - entries:
                - keys:
                    publicKeys: |-
                      -----BEGIN PUBLIC KEY-----
                      MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...
                      -----END PUBLIC KEY-----
          mutateDigest: true      # Replace tags with digests
          verifyDigest: true
          required: true
```

---

## Kubernetes Audit Policy

### Comprehensive Audit Policy

```yaml
apiVersion: audit.k8s.io/v1
kind: Policy
metadata:
  name: production-audit-policy
rules:
  # Log no action for read-only requests to system endpoints
  - level: None
    resources:
      - group: ""
        resources: ["endpoints", "services", "services/status"]
    verbs: ["get", "watch", "list"]

  # Log no action for kubelet and system:node health checks
  - level: None
    users: ["system:kube-proxy", "kubelet", "system:apiserver"]
    verbs: ["get"]
    resources:
      - group: ""
        resources: ["nodes/status", "pods/status"]

  # Full request+response for secrets, configmaps, RBAC changes
  - level: RequestResponse
    resources:
      - group: ""
        resources: ["secrets", "configmaps"]
      - group: "rbac.authorization.k8s.io"
        resources: ["clusterroles", "clusterrolebindings", "roles", "rolebindings"]
    omitStages:
      - RequestReceived

  # Full request+response for authentication-related events
  - level: RequestResponse
    resources:
      - group: "authentication.k8s.io"
        resources: ["tokenreviews"]
      - group: "authorization.k8s.io"
        resources: ["subjectaccessreviews"]

  # Log request body for write operations on workloads
  - level: Request
    resources:
      - group: ""
        resources: ["pods", "services"]
      - group: "apps"
        resources: ["deployments", "statefulsets", "daemonsets"]
      - group: "batch"
        resources: ["jobs", "cronjobs"]
    verbs: ["create", "update", "patch", "delete"]
    omitStages:
      - RequestReceived

  # Metadata-only for everything else
  - level: Metadata
    omitStages:
      - RequestReceived
```

### API Server Configuration

```yaml
# In kube-apiserver flags (or kubeadm ClusterConfiguration)
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
apiServer:
  extraArgs:
    audit-policy-file: /etc/kubernetes/audit-policy.yaml
    audit-log-path: /var/log/kubernetes/audit.log
    audit-log-maxage: "30"
    audit-log-maxbackup: "10"
    audit-log-maxsize: "100"
    # Or send to a webhook:
    # audit-webhook-config-file: /etc/kubernetes/audit-webhook.yaml
  extraVolumes:
    - name: audit-policy
      hostPath: /etc/kubernetes/audit-policy.yaml
      mountPath: /etc/kubernetes/audit-policy.yaml
      readOnly: true
      pathType: File
    - name: audit-log
      hostPath: /var/log/kubernetes
      mountPath: /var/log/kubernetes
      pathType: DirectoryOrCreate
```

---

## Quick Reference: Security Checklist

| Control | Implementation | Priority |
|---|---|---|
| Pod Security Standards | `restricted` namespace labels | P0 |
| Drop ALL capabilities | `capabilities.drop: [ALL]` | P0 |
| Non-root user | `runAsNonRoot: true`, `runAsUser: 65534` | P0 |
| Read-only root filesystem | `readOnlyRootFilesystem: true` + emptyDir mounts | P0 |
| No privilege escalation | `allowPrivilegeEscalation: false` | P0 |
| Seccomp profile | `seccompProfile.type: RuntimeDefault` | P0 |
| Image digest pinning | `image: repo@sha256:...` | P1 |
| Image signature verification | Cosign + Kyverno `verifyImages` | P1 |
| Disable service account automount | `automountServiceAccountToken: false` | P1 |
| Audit logging | Audit Policy with RequestResponse for secrets/RBAC | P1 |
| Runtime detection | Falco or Tetragon | P2 |
| AppArmor profiles | `runtime/default` or custom | P2 |
| Network policy default deny | NetworkPolicy `podSelector: {}` deny all | P0 |
