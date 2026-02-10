# Anti-Patterns

25+ common Kubernetes mistakes that compromise security, reliability, and cost -- with concrete fixes.

---

## Quick Reference Table

| # | Anti-Pattern | Problem | Fix |
|---|-------------|---------|-----|
| 1 | No resource limits | Noisy neighbor; OOMKilled cluster | Set requests AND limits on every container |
| 2 | Running as root | Container breakout = host root access | `runAsNonRoot: true`, `runAsUser: 65534` |
| 3 | Using :latest tag | Non-reproducible deploys, silent regressions | Pin version + digest: `image:v1.2.0@sha256:...` |
| 4 | No health probes | Traffic sent to dead pods, no auto-recovery | Add liveness, readiness, AND startup probes |
| 5 | No PDB | Node drain kills all replicas at once | Add PodDisruptionBudget with minAvailable |
| 6 | Hardcoded secrets | Secrets in YAML committed to git | Use External Secrets, Sealed Secrets, or Vault |
| 7 | No NetworkPolicy | All pods can talk to all pods (flat network) | Default deny + explicit allow per service |
| 8 | Single replica in prod | Zero availability during restarts/crashes | Min 3 replicas + PDB + topology spread |
| 9 | No RBAC | Every pod has cluster-admin equivalent | Namespace-scoped Roles, least privilege |
| 10 | No namespace isolation | Teams step on each other, no resource boundaries | Namespaces + RBAC + ResourceQuota + NetworkPolicy |
| 11 | No GitOps | Snowflake clusters, no audit trail | ArgoCD/Flux, all changes via reviewed PRs |
| 12 | Manual kubectl in prod | Undocumented changes, drift from desired state | GitOps only; kubectl read-only in prod |
| 13 | No monitoring | Blind to failures until customers report | Prometheus + Grafana + alerting on SLOs |
| 14 | No backup | Data loss on etcd/PV failure is unrecoverable | Velero schedules + etcd snapshots + tested restores |
| 15 | hostNetwork abuse | Bypasses NetworkPolicy, port conflicts | Use Services and Ingress; hostNetwork only for CNI/DaemonSets |
| 16 | Privileged containers | Full host kernel access, escape is trivial | `privileged: false`, drop ALL capabilities |
| 17 | Missing topology spread | All replicas on same node or zone | topologySpreadConstraints across zones and nodes |
| 18 | No graceful shutdown | Requests dropped during rollout/scale-down | preStop hook + SIGTERM handling + terminationGracePeriod |
| 19 | No resource quotas | Single namespace can consume entire cluster | ResourceQuota + LimitRange per namespace |
| 20 | Using default SA | Default SA token auto-mounted = lateral movement risk | `automountServiceAccountToken: false`, dedicated SAs |
| 21 | ConfigMap for secrets | Secrets stored base64 in ConfigMaps (no encryption) | Use Secret resources + encrypt at rest (KMS) |
| 22 | No Pod Security Standards | Any pod spec accepted, including privileged | PSS labels: enforce restricted/baseline |
| 23 | Missing labels | Cannot query, monitor, or cost-allocate workloads | Standard labels: app, version, team, env |
| 24 | No DNS policy | DNS resolution failures under load | Set dnsPolicy and dnsConfig with ndots:2 |
| 25 | No node affinity for stateful | Stateful pods scheduled far from their PVs | nodeAffinity or topology constraints matching PV zone |
| 26 | Giant monolith containers | 2GB+ images, slow pulls, wasted bandwidth | Multi-stage builds, distroless/scratch base images |
| 27 | No pod priority | Critical pods evicted before batch jobs | PriorityClass: system-critical > high > default > low |

---

## Detailed Anti-Patterns with Code

### 1. No Resource Limits

**Bad**:
```yaml
containers:
  - name: app
    image: myapp:v1
    # No resources block at all
```

**Good**:
```yaml
containers:
  - name: app
    image: myapp:v1
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 500m
        memory: 512Mi
```
**Why**: Without limits, a single container can consume all node resources, causing OOMKills and CPU starvation for every other pod on the node.

---

### 2. Running as Root

**Bad**:
```yaml
containers:
  - name: app
    image: myapp:v1
    # No securityContext = runs as root (UID 0)
```

**Good**:
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65534
  runAsGroup: 65534
  seccompProfile:
    type: RuntimeDefault
containers:
  - name: app
    image: myapp:v1
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop:
          - ALL
```
**Why**: Root in a container can exploit kernel vulnerabilities to escape to the host. Non-root with dropped capabilities limits blast radius.

---

### 3. Using :latest Tag

**Bad**:
```yaml
containers:
  - name: app
    image: myapp:latest
```

**Good**:
```yaml
containers:
  - name: app
    image: myregistry.io/myapp:v2.3.1@sha256:a1b2c3d4e5f6...
```
**Why**: `:latest` is mutable -- you cannot determine what is actually running. Digest pinning guarantees the exact binary across all environments and rollbacks.

---

### 4. No Health Probes

**Bad**:
```yaml
containers:
  - name: app
    image: myapp:v2.3.1
    # No probes = kubelet assumes pod is healthy forever
```

**Good**:
```yaml
containers:
  - name: app
    image: myapp:v2.3.1
    startupProbe:
      httpGet:
        path: /healthz
        port: 8080
      failureThreshold: 30
      periodSeconds: 10
    livenessProbe:
      httpGet:
        path: /healthz
        port: 8080
      periodSeconds: 10
    readinessProbe:
      httpGet:
        path: /readyz
        port: 8080
      periodSeconds: 5
```
**Why**: Without readiness probes, traffic routes to pods that are not ready. Without liveness probes, deadlocked pods are never restarted. Without startup probes, slow-starting apps are killed during initialization.

---

### 5. No PodDisruptionBudget

**Bad**: No PDB defined. A `kubectl drain` evicts all replicas simultaneously.

**Good**:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: myapp-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: myapp
```
**Why**: During voluntary disruptions (node upgrades, autoscaler scale-down), PDB ensures minimum availability is maintained.

---

### 6. Hardcoded Secrets

**Bad**:
```yaml
containers:
  - name: app
    env:
      - name: DB_PASSWORD
        value: "super-secret-password"    # In plain text, committed to git
```

**Good**:
```yaml
containers:
  - name: app
    env:
      - name: DB_PASSWORD
        valueFrom:
          secretKeyRef:
            name: db-credentials
            key: password
# Secret managed by External Secrets Operator syncing from AWS Secrets Manager
```
**Why**: Secrets in manifests end up in git history, etcd (base64 is not encryption), and CI logs. Use External Secrets Operator, Sealed Secrets, or Vault CSI.

---

### 7. No NetworkPolicy

**Bad**: No NetworkPolicy in namespace = default allow all.

**Good**:
```yaml
# Default deny all
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
---
# Allow specific traffic
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-to-db
spec:
  podSelector:
    matchLabels:
      app: postgres
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api
      ports:
        - port: 5432
```
**Why**: Without NetworkPolicy, a compromised pod can reach every other pod, including databases and internal services.

---

### 8. Single Replica in Production

**Bad**:
```yaml
spec:
  replicas: 1    # Any restart = downtime
```

**Good**:
```yaml
spec:
  replicas: 3
  # + PDB with minAvailable: 2
  # + topologySpreadConstraints across zones
```
**Why**: A single replica means any pod restart, node failure, or deployment rollout causes downtime.

---

### 9. No RBAC

**Bad**: Using default ServiceAccount which may have broad permissions, or granting `cluster-admin` to workloads.

**Good**:
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: myapp-role
  namespace: production
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
    resourceNames: ["myapp-config"]     # Scoped to specific resource
```
**Why**: Over-permissioned service accounts enable lateral movement. A compromised pod with cluster-admin can take over the entire cluster.

---

### 10. No Namespace Isolation

**Bad**: Everything deployed to `default` namespace.

**Good**: Dedicated namespaces per team/environment with:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: team-alpha
  labels:
    pod-security.kubernetes.io/enforce: restricted
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-alpha-quota
  namespace: team-alpha
spec:
  hard:
    requests.cpu: "50"
    requests.memory: 100Gi
    pods: "100"
```
**Why**: Without namespace isolation, teams share resource pools, RBAC boundaries, and network access indiscriminately.

---

### 11-12. No GitOps / Manual kubectl in Prod

**Bad**:
```bash
kubectl apply -f deployment.yaml          # No audit trail
kubectl set image deployment/app app=v2   # Who did this? When? Why?
```

**Good**: All changes via ArgoCD Application pointing to a git repo. Production kubectl access is read-only.
**Why**: Manual changes create configuration drift, lack audit trails, and cannot be reproduced or rolled back reliably.

---

### 18. No Graceful Shutdown

**Bad**:
```yaml
containers:
  - name: app
    image: myapp:v1
    # No preStop, no SIGTERM handling
    # terminationGracePeriodSeconds defaults to 30s
```

**Good**:
```yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: app
      image: myapp:v1
      lifecycle:
        preStop:
          exec:
            command:
              - /bin/sh
              - -c
              - |
                # Stop accepting new connections
                curl -X POST http://localhost:8080/drain
                # Wait for in-flight requests to complete
                sleep 15
```
**Why**: Without graceful shutdown, in-flight requests are dropped during rollouts. The preStop hook runs before SIGTERM, giving the app time to drain connections.

---

### 20. Using Default ServiceAccount

**Bad**:
```yaml
spec:
  # No serviceAccountName = uses "default" SA
  # automountServiceAccountToken defaults to true
  containers:
    - name: app
```

**Good**:
```yaml
spec:
  serviceAccountName: myapp-sa
  automountServiceAccountToken: false   # Unless the app needs K8s API access
  containers:
    - name: app
```
**Why**: The default SA token is mounted into every pod. If compromised, attackers can query the K8s API. Disable auto-mount and use dedicated SAs with minimal RBAC.

---

### 24. No DNS Policy

**Bad**: Default `dnsPolicy: ClusterFirst` with default ndots:5 causes 4 unnecessary DNS lookups per external domain query.

**Good**:
```yaml
spec:
  dnsPolicy: ClusterFirst
  dnsConfig:
    options:
      - name: ndots
        value: "2"
      - name: single-request-reopen
        value: ""
```
**Why**: With default `ndots:5`, resolving `api.example.com` first tries `api.example.com.production.svc.cluster.local`, then `.svc.cluster.local`, then `.cluster.local`, then `.example.com`, before finally the real query. Setting `ndots:2` skips the cluster search for any domain with 2+ dots.

---

### 25. No Node Affinity for Stateful Workloads

**Bad**:
```yaml
# StatefulSet with no affinity -- pods scheduled in different AZ than their PV
spec:
  template:
    spec:
      containers:
        - name: postgres
```

**Good**:
```yaml
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: topology.kubernetes.io/zone
                    operator: In
                    values:
                      - us-east-1a
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: postgres
```
**Why**: EBS/EFS volumes are zone-bound. If a pod is scheduled in a different AZ from its PV, it cannot attach the volume and enters a `Pending` state.

---

### 27. No Pod Priority

**Bad**: All pods have equal priority. Critical services evicted when nodes are under pressure.

**Good**:
```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: critical
value: 1000000
globalDefault: false
description: "For critical production services"
preemptionPolicy: PreemptLowerPriority
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: batch-low
value: 100
globalDefault: false
description: "For batch jobs that can be preempted"
preemptionPolicy: Never
---
# Usage in Deployment
spec:
  template:
    spec:
      priorityClassName: critical
```
**Why**: Without priority classes, the scheduler treats all pods equally. Under resource pressure, critical API pods may be evicted instead of batch jobs.
