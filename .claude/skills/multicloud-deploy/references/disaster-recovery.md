# Disaster Recovery Reference

## RTO/RPO Framework

### Definitions
- **RPO (Recovery Point Objective)**: Maximum acceptable data loss (time between last backup and failure)
- **RTO (Recovery Time Objective)**: Maximum acceptable downtime (time to restore service)

### DR Tiers

| Tier | RPO | RTO | Pattern | Annual Cost Premium |
|------|-----|-----|---------|---------------------|
| **A — Mission Critical** | < 1 min | < 5 min | Active-active, hot standby | 2–3x |
| **B — Business Critical** | < 15 min | < 1 hr | Active-passive, warm standby | 1.3–1.5x |
| **C — Standard** | < 4 hr | < 24 hr | Pilot light + backup restore | 1.1–1.2x |
| **D — Dev/Test** | < 24 hr | < 72 hr | Backup only, cold start | 1.0x |

### Choosing a Tier

| System Type | Recommended Tier |
|-------------|-----------------|
| Payment processing, real-time trading | A |
| Order management, customer portal | B |
| Internal tools, reporting | C |
| Dev/staging environments | D |

---

## Velero — Kubernetes Backup & Restore

Velero is the standard for backing up K8s resources + persistent volumes.

### Installation
```bash
velero install \
  --provider aws \
  --plugins velero/velero-plugin-for-aws:v1.8.0 \
  --bucket velero-backups-prod \
  --backup-location-config region=us-east-1 \
  --snapshot-location-config region=us-east-1 \
  --secret-file ./velero-credentials

# Verify
velero backup-location get
```

### Cross-Cloud Backup Configuration

```yaml
# Backup to AWS S3 from GKE cluster
apiVersion: velero.io/v1
kind: BackupStorageLocation
metadata:
  name: aws-s3-dr
  namespace: velero
spec:
  provider: aws
  objectStorage:
    bucket: velero-dr-prod-cross-cloud
    prefix: gcp-cluster/
  config:
    region: us-east-1
  credential:
    name: aws-cross-cloud-creds    # ESO-managed, not static
    key: cloud

---
# GCS primary backup + S3 DR copy
apiVersion: velero.io/v1
kind: BackupStorageLocation
metadata:
  name: gcs-primary
  namespace: velero
spec:
  provider: gcp
  objectStorage:
    bucket: velero-prod-gcs
  config:
    serviceAccount: velero@project.iam.gserviceaccount.com
```

### Automated Backup Schedule

```yaml
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: daily-full-backup
  namespace: velero
spec:
  schedule: "0 2 * * *"    # 2 AM daily
  template:
    ttl: 720h               # 30-day retention
    includedNamespaces:
      - payments
      - orders
      - users
    excludedResources:
      - events
      - events.events.k8s.io
    storageLocation: aws-s3-dr
    volumeSnapshotLocations:
      - aws-ebs-snapshots
    labelSelector:
      matchLabels:
        backup: "true"
    hooks:
      resources:
        - name: pre-backup-postgres-freeze
          includedNamespaces: [payments]
          labelSelector:
            matchLabels:
              app: postgresql
          pre:
            - exec:
                container: postgresql
                command: ["/bin/bash", "-c", "psql -c 'CHECKPOINT;'"]
                timeout: 30s

---
# Hourly incremental for critical namespaces
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: hourly-critical
  namespace: velero
spec:
  schedule: "0 * * * *"
  template:
    ttl: 48h
    includedNamespaces: [payments]
    storageLocation: aws-s3-dr
```

### Restore Procedure

```bash
# List available backups
velero backup get

# Restore specific backup to target cluster
velero restore create prod-restore-20260225 \
  --from-backup daily-full-backup-20260225020000 \
  --include-namespaces payments,orders \
  --namespace-mappings payments:payments-restored \
  --restore-volumes=true

# Monitor restore
velero restore describe prod-restore-20260225
velero restore logs prod-restore-20260225
```

---

## LitmusChaos — Chaos Engineering

Run chaos experiments in staging, then production to validate DR.

### Core Chaos Experiments for Multi-Cloud

```yaml
# Experiment 1: Kill random pods in payments namespace
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: pod-delete-payments
  namespace: payments
spec:
  appinfo:
    appns: payments
    applabel: "app=checkout-api"
    appkind: deployment
  chaosServiceAccount: litmus-admin
  experiments:
    - name: pod-delete
      spec:
        components:
          env:
            - name: TOTAL_CHAOS_DURATION
              value: "60"
            - name: CHAOS_INTERVAL
              value: "10"
            - name: FORCE
              value: "false"
            - name: PODS_AFFECTED_PERC
              value: "50"    # kill 50% of pods
```

```yaml
# Experiment 2: Simulate node failure (drain entire node)
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: node-drain
spec:
  experiments:
    - name: node-drain
      spec:
        components:
          env:
            - name: APP_NODE
              value: "ip-10-0-1-100.ec2.internal"
            - name: TOTAL_CHAOS_DURATION
              value: "120"
```

```yaml
# Experiment 3: Network partition between clusters
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: pod-network-loss
spec:
  experiments:
    - name: pod-network-loss
      spec:
        components:
          env:
            - name: NETWORK_INTERFACE
              value: "eth0"
            - name: NETWORK_PACKET_LOSS_PERCENTAGE
              value: "100"
            - name: DESTINATION_IPS
              value: "172.16.0.0/12"   # all GCP IPs
            - name: TOTAL_CHAOS_DURATION
              value: "300"             # 5-minute partition
```

### Chaos Test Plan (Minimum for Production)

| Test | Frequency | Expected Outcome |
|------|-----------|-----------------|
| Pod delete (50%) | Weekly | Zero user-visible errors |
| Node drain | Monthly | Karmada redistributes within 60s |
| Zone outage simulation | Quarterly | Cloudflare failovers within 30s |
| DB node kill (1 of 3) | Monthly | CockroachDB continues operating |
| Cross-cloud network loss (5 min) | Quarterly | Service degrades gracefully, no data loss |
| Full cloud region failure | Biannually | RTO/RPO targets met |

---

## DR Runbook Template

### Trigger Conditions
- Health check failures > 2 consecutive failures on primary
- Cloudflare LB marks primary pool as unhealthy
- PagerDuty alert: "Primary cluster unreachable"

### Phase 1: Assessment (0–5 min)

```bash
# Check cluster health
kubectl get nodes --context=aws-eks
kubectl get pods -A --context=aws-eks | grep -v Running

# Check Karmada federation status
kubectl get clusters -o wide --kubeconfig=~/.kube/karmada.config

# Check Velero backup status
velero backup get --context=gcp-gke | head -5
```

### Phase 2: Failover Decision (5–10 min)

| Situation | Action |
|-----------|--------|
| Single AZ down | Kubernetes reschedules automatically — no action |
| Full primary cluster down | Trigger DNS/LB failover to secondary |
| Database primary down | Trigger DB failover (CockroachDB auto-handles) |
| Region down | Activate DR runbook below |

### Phase 3: Failover Execution (10–30 min)

```bash
# Step 1: Verify secondary is healthy
kubectl get nodes --context=gcp-gke
kubectl get pods -n payments --context=gcp-gke

# Step 2: Scale up secondary (if warm standby)
kubectl scale deployment --replicas=10 checkout-api \
  --context=gcp-gke -n payments

# Step 3: Update Cloudflare LB to route 100% to secondary
# (If automated health checks haven't done this already)
cf api update-pool --disable-origin aws-us-east-1

# Step 4: Verify traffic routing
curl -H "Host: api.example.com" https://cf-trace.example.com/healthz

# Step 5: Restore from Velero backup if data needed
velero restore create emergency-restore \
  --from-backup $(velero backup get --output=json | jq -r '.[0].metadata.name') \
  --include-namespaces payments \
  --context=gcp-gke

# Step 6: Notify stakeholders
# Post to Slack #incidents and update status page
```

### Phase 4: Post-Incident (24–72 hr)

1. Root cause analysis document
2. Blameless postmortem within 48h
3. DR test report: did we meet RTO/RPO?
4. Action items to prevent recurrence
5. Update runbook based on lessons learned

---

## Database DR Patterns

### CockroachDB Multi-Region Failure

```sql
-- View replication zones
SHOW ZONE CONFIGURATION FOR DATABASE prod;

-- Set SURVIVE ZONE FAILURE (requires 3+ zones in region)
ALTER DATABASE prod CONFIGURE ZONE USING
  num_replicas = 5,
  constraints = '{+region=us-east1: 2, +region=us-central1: 2, +region=eastus: 1}',
  lease_preferences = '[[+region=us-east1]]';

-- SURVIVE REGION FAILURE (requires 3+ regions)
ALTER DATABASE prod SURVIVE REGION FAILURE;
```

No manual failover needed — CockroachDB Raft consensus handles it automatically.

### CloudNativePG Failover

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: prod-postgres
spec:
  instances: 3
  primaryUpdateStrategy: unsupervised   # auto-failover
  failoverDelay: 0                      # immediate failover

  backup:
    barmanObjectStore:
      destinationPath: "s3://postgres-backups-dr/prod"
      s3Credentials:
        accessKeyId:
          name: s3-creds
          key: ACCESS_KEY_ID
      wal:
        compression: gzip
      data:
        compression: gzip

  externalClusters:
    - name: gcp-replica
      connectionParameters:
        host: postgres-dr.gcp.internal
        user: streaming_replica
      password:
        name: replica-secret
        key: password
```

---

## Backup Verification (Critical — Often Skipped)

Untested backups are worthless. Verify monthly:

```bash
# Monthly restore test to isolated namespace
velero restore create monthly-verify-$(date +%Y%m) \
  --from-backup daily-full-backup-$(date +%Y%m%d)020000 \
  --include-namespaces payments \
  --namespace-mappings payments:verify-$(date +%Y%m) \
  --restore-volumes=true

# Verify data integrity
kubectl exec -n verify-$(date +%Y%m) postgres-0 -- \
  psql -c "SELECT count(*) FROM orders WHERE created_at > NOW() - INTERVAL '24 hours';"

# Clean up
kubectl delete namespace verify-$(date +%Y%m)
```

Schedule backup verification as a CronJob in your CI/CD pipeline.
