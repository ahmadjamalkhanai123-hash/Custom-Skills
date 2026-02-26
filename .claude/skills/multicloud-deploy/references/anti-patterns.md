# Anti-Patterns Reference

25 documented multi-cloud mistakes and how to avoid them.

---

## Architecture Anti-Patterns

### 1. "Lift and Shift" to Multi-Cloud
**Problem**: Moving monolithic apps to multiple clouds without re-architecting for distributed systems.
**Symptoms**: Shared state via filesystem/NFS, hardcoded hostnames, no retry logic.
**Fix**: Re-architect for stateless services + external state (Redis, DB). Add distributed tracing, retries, circuit breakers before going multi-cloud.

### 2. Cloud-Specific SDK Calls Without Abstraction
**Problem**: Using `boto3.client('s3')` directly in app code, making it impossible to run on GCP/Azure.
**Symptoms**: App fails in DR cloud because AWS-specific API calls don't work.
**Fix**: Abstract storage/queue/compute behind interfaces:
```python
# Bad
s3 = boto3.client('s3')
s3.put_object(Bucket='mybucket', Key=key, Body=data)

# Good — cloud-agnostic blob storage abstraction
storage = BlobStorage.from_env()  # resolves to S3/GCS/Azure Blob based on env
storage.put(key, data)
```

### 3. Over-Federating (Managing Too Many Clusters Without Automation)
**Problem**: Adding more clusters than the team can manage operationally.
**Symptoms**: Inconsistent configs across clusters, delayed security patches, "snowflake" clusters.
**Fix**: Each cluster should be 100% GitOps-managed. Never allow manual `kubectl apply` in production. No cluster without ArgoCD/Flux sync.

### 4. No CIDR Plan Before Provisioning
**Problem**: Using same IP ranges across clouds (e.g., 10.0.0.0/16 everywhere).
**Symptoms**: VPN/interconnect fails, services can't route to each other, painful migration.
**Fix**: Plan CIDR allocation BEFORE first `terraform apply`. See CIDR table in `references/k8s-federation.md`.

### 5. Declaring "Multi-Cloud" Without Unified Observability
**Problem**: Each cloud has separate monitoring — no cross-cloud view of latency, errors, cost.
**Symptoms**: Incidents take 10x longer to diagnose. "We don't know which cloud has the problem."
**Fix**: Deploy OTel Collector → Thanos → Grafana on day 1. Multi-cloud without unified observability is not multi-cloud — it's multi-silo.

### 6. Active-Active Without Global Database
**Problem**: Running active-active traffic to multiple clouds but writing to single-master database.
**Symptoms**: All writes route to one cloud (negating active-active), high latency for cross-region writes.
**Fix**: Use CockroachDB (SURVIVE REGION FAILURE) or Cassandra (NetworkTopologyStrategy) for active-active. Or explicitly use active-passive if single-master is acceptable.

---

## Security Anti-Patterns

### 7. Static Credentials Across Cloud Boundaries
**Problem**: Storing AWS access keys / GCP service account keys as K8s secrets.
**Symptoms**: Key rotation is manual/rare. Credentials leaked in git history. CSPM findings.
**Fix**: IRSA (AWS), Workload Identity (GCP), Azure AD WIF everywhere. Use SPIFFE/SPIRE for zero-trust cross-cloud.

### 8. No mTLS Between Services
**Problem**: Services communicate over plain HTTP within cluster / across clusters.
**Symptoms**: Any compromised pod can impersonate any other service. No service-level audit trail.
**Fix**: Istio PeerAuthentication STRICT mode in all production namespaces. Takes <1 hour to configure.

### 9. Root Containers in Production
**Problem**: Containers run as root (UID 0), common when copying dev Dockerfiles to prod.
**Symptoms**: Container escape → node compromise. PCI/HIPAA/FedRAMP violations.
**Fix**: Kyverno policy: `runAsNonRoot: true` + `allowPrivilegeEscalation: false` enforced cluster-wide.

### 10. Secrets in ConfigMaps or Environment Variables (Plaintext)
**Problem**: `DB_PASSWORD=supersecret` in Deployment env vars or ConfigMaps.
**Symptoms**: Secrets visible in `kubectl get configmap -o yaml`. Rotated by recreating pods manually.
**Fix**: External Secrets Operator + HashiCorp Vault. Vault provides dynamic, short-lived secrets. ESO syncs to K8s secrets without storing in Git.

### 11. No Network Policies (Default: Allow All)
**Problem**: K8s default is allow-all networking — any pod can reach any other pod.
**Symptoms**: Lateral movement trivial after any pod compromise. PCI/HIPAA non-compliant.
**Fix**: Default-deny NetworkPolicy + Kyverno to enforce it:
```yaml
# Default deny all ingress/egress in every namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
```

### 12. Shared Cluster-Admin Credentials
**Problem**: Team shares single kubeconfig with cluster-admin privileges.
**Symptoms**: No audit trail for who did what. Cannot revoke individual access. Blast radius = entire cluster.
**Fix**: OIDC integration for human access (GitHub SSO, Google SSO). Each person gets their own RBAC binding. No shared credentials.

---

## Cost Anti-Patterns

### 13. Ignoring Data Egress Costs
**Problem**: Designing inter-cloud architecture without accounting for egress pricing.
**Symptoms**: Monthly bill 200% higher than compute cost due to cross-cloud data transfer.
**Fix**: Audit egress before designing architecture. Use private interconnect for high-bandwidth flows. Cache at edge. Colocate data-intensive services.

### 14. No Cost Tags from Day 1
**Problem**: Adding cost allocation tags "later" — impossible to retrofit retroactively.
**Symptoms**: Cloud bill shows $50k/month but nobody knows which team/service is responsible.
**Fix**: Enforce tags via Kyverno/OPA on day 1. Tags: `team`, `service`, `environment`, `cloud`, `tier`.

### 15. Paying for Idle DR Resources
**Problem**: Full production-sized standby cluster running 24/7 for DR.
**Symptoms**: DR costs 100% of production costs but handles 0% of traffic.
**Fix**: Use pilot light (minimal running resources, scale on failover) or warm standby (reduced replicas). Karpenter + scale-from-zero for DR clusters.

### 16. Over-Provisioned Node Pools
**Problem**: Requesting 4 CPU/16GB but using 0.5 CPU/2GB for most pods.
**Symptoms**: 70-80% idle compute. Kubecost shows "waste" in red.
**Fix**: Set resource requests accurately (use VPA recommendations). Enable Karpenter consolidation. Schedule cost review monthly.

---

## Operational Anti-Patterns

### 17. Manual `kubectl apply` in Production
**Problem**: Engineers SSH to clusters and apply manifests directly during incidents.
**Symptoms**: Config drift. "Works in AWS, broken in GCP" because someone applied a hotfix only to one cluster.
**Fix**: GitOps only. ArgoCD self-heal reverts manual changes. Treat manual applies as incidents to investigate.

### 18. Not Testing Failover Before Production
**Problem**: DR exists on paper but has never been tested. Velero backups exist but restore has never been run.
**Symptoms**: When real outage occurs, restore fails (schema mismatch, missing secrets, CIDR conflicts).
**Fix**: Run monthly failover drills. Chaos engineering (LitmusChaos) in staging before prod. Verify backup restore quarterly.

### 19. Config Drift Between Clusters
**Problem**: Clusters diverge over time due to manual changes, different Helm chart versions, skipped upgrades.
**Symptoms**: Debug sessions start with "Which cluster version is this? Why does it have this config?"
**Fix**: ArgoCD diff alert on any `OutOfSync` state. Kubernetes version parity policy (all clusters within 1 minor version).

### 20. No Runbook for Known Failure Modes
**Problem**: Incident occurs, team scrambles without documented procedure. 3 AM heroics.
**Symptoms**: RTO of 2hr instead of 15min because team is "figuring it out."
**Fix**: Write runbooks for every known failure mode before production launch. Test them in game days.

---

## Networking Anti-Patterns

### 21. Cross-Cloud Traffic on Public Internet
**Problem**: Services in AWS calling services in GCP via public internet IP.
**Symptoms**: High latency (100ms+ added), egress costs, traffic sniffable by ISPs, compliance failures.
**Fix**: Private interconnect (Equinix Fabric, Megaport), or cloud VPN (HA VPN + Transit Gateway).

### 22. Using Same Load Balancer Ports for Different Services
**Problem**: All services exposed on port 443 through the same LB with path-based routing only.
**Symptoms**: Single LB becomes SPOF. Difficult to add per-service circuit breakers.
**Fix**: One Kubernetes Service per microservice. Istio VirtualService for routing within mesh.

### 23. Not Setting Pod Disruption Budgets
**Problem**: No PodDisruptionBudget — Karpenter/cluster upgrades kill all pods simultaneously.
**Symptoms**: Rolling upgrade causes 100% downtime for services with <3 replicas.
**Fix**:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: checkout-api-pdb
spec:
  minAvailable: 2    # or maxUnavailable: 1
  selector:
    matchLabels:
      app: checkout-api
```

---

## Database Anti-Patterns

### 24. Database Split-Brain Without Conflict Resolution
**Problem**: Allowing writes to both clusters during network partition without conflict resolution strategy.
**Symptoms**: Data divergence when partition heals. "Which write wins?" — no answer.
**Fix**: Use consensus-based databases (CockroachDB uses Raft — no split-brain possible). Or explicitly choose conflict resolution policy (last-write-wins, application-resolved) before going multi-master.

### 25. Not Monitoring Replication Lag
**Problem**: Database replicas silently fall behind primary, making DR useless when needed.
**Symptoms**: "We have DR" but replica is 6 hours behind. Failover causes hours of data loss.
**Fix**: Alert on replication lag > 60s. Dashboard showing `pg_replication_lag` / CockroachDB `replication_lag_nanos`. PagerDuty alert if lag > RPO target.

---

## Quick Anti-Pattern Check

Before going to production, verify none of these are present:

- [ ] No static cloud credentials in K8s secrets or env vars
- [ ] No containers running as root in production namespaces
- [ ] No `kubectl apply` workflows (GitOps-only)
- [ ] No overlapping CIDRs across clouds
- [ ] No inter-cloud traffic on public internet
- [ ] No production cluster without Istio mTLS STRICT
- [ ] No cluster without cost allocation tags
- [ ] No DR that has never been tested
- [ ] No database without replication lag monitoring
- [ ] No service without PodDisruptionBudget
