# Disaster Recovery

Comprehensive DR patterns for Kubernetes clusters: backup/restore, multi-region failover, and high availability.

---

## DR Tier Model

| Tier | Strategy | RPO | RTO | Use Case |
|------|----------|-----|-----|----------|
| T2 | Backup/Restore | 24h | 4-8h | Dev/staging, non-critical workloads |
| T3 | Multi-AZ with Backups | 1h | 1-2h | Standard production |
| T4 | Active-Passive Cross-Region | 15m | 15-30m | Business-critical apps |
| T5 | Active-Active Multi-Region | ~0 (seconds) | ~0 | Financial, healthcare, SaaS platforms |

---

## Velero Backup Infrastructure

### BackupStorageLocation (S3)

```yaml
apiVersion: velero.io/v1
kind: BackupStorageLocation
metadata:
  name: default
  namespace: velero
spec:
  provider: aws
  objectStorage:
    bucket: my-cluster-backups
    prefix: velero
  config:
    region: us-east-1
    s3ForcePathStyle: "false"
  credential:
    name: cloud-credentials
    key: cloud
```

### VolumeSnapshotLocation

```yaml
apiVersion: velero.io/v1
kind: VolumeSnapshotLocation
metadata:
  name: default
  namespace: velero
spec:
  provider: aws
  config:
    region: us-east-1
```

### Daily Full Cluster Backup

```yaml
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: daily-full-backup
  namespace: velero
spec:
  schedule: "0 2 * * *"           # 2 AM daily
  template:
    ttl: 720h0m0s                  # Retain 30 days
    includedNamespaces:
      - "*"
    excludedNamespaces:
      - kube-system
      - velero
    storageLocation: default
    volumeSnapshotLocations:
      - default
    defaultVolumesToFsBackup: false  # Use CSI snapshots when available
    snapshotMoveData: true           # Move snapshots to object storage
    metadata:
      labels:
        backup-type: daily-full
```

### Hourly Critical Namespace Backup

```yaml
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: hourly-critical
  namespace: velero
spec:
  schedule: "0 * * * *"           # Every hour
  template:
    ttl: 168h0m0s                  # Retain 7 days
    includedNamespaces:
      - production
      - payments
      - auth
    storageLocation: default
    volumeSnapshotLocations:
      - default
    defaultVolumesToFsBackup: true  # File-level backup for stateful sets
    orderedResources:
      # Backup secrets and configmaps first
      v1/Secret: "production/db-credentials,payments/stripe-keys"
      v1/ConfigMap: "production/app-config"
    metadata:
      labels:
        backup-type: hourly-critical
```

---

## Restore Procedures

### Full Cluster Restore

```yaml
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: full-cluster-restore
  namespace: velero
spec:
  backupName: daily-full-backup-20260209020000
  includedNamespaces:
    - "*"
  restorePVs: true
  preserveNodePorts: true
  existingResourcePolicy: update    # Overwrite existing resources
```

### Single Namespace Restore

```yaml
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: restore-payments
  namespace: velero
spec:
  backupName: hourly-critical-20260209150000
  includedNamespaces:
    - payments
  restorePVs: true
  namespaceMapping:
    payments: payments              # Same namespace (or remap)
  existingResourcePolicy: none      # Skip existing resources
```

### Single Resource Restore

```yaml
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: restore-single-deployment
  namespace: velero
spec:
  backupName: hourly-critical-20260209150000
  includedNamespaces:
    - production
  includedResources:
    - deployments
  labelSelector:
    matchLabels:
      app: api-gateway
  restorePVs: false
```

---

## etcd Snapshot and Restore

### Automated etcd Snapshot CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: etcd-snapshot
  namespace: kube-system
spec:
  schedule: "0 */6 * * *"          # Every 6 hours
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: etcd-snapshot
              image: registry.k8s.io/etcd:3.5.12-0
              command:
                - /bin/sh
                - -c
                - |
                  SNAPSHOT_NAME="snapshot-$(date +%Y%m%d-%H%M%S).db"
                  etcdctl snapshot save /snapshots/${SNAPSHOT_NAME} \
                    --endpoints=https://127.0.0.1:2379 \
                    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
                    --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
                    --key=/etc/kubernetes/pki/etcd/healthcheck-client.key
                  # Verify snapshot
                  etcdctl snapshot status /snapshots/${SNAPSHOT_NAME} --write-out=table
                  # Prune old snapshots (keep last 10)
                  ls -t /snapshots/snapshot-*.db | tail -n +11 | xargs rm -f
              volumeMounts:
                - name: etcd-certs
                  mountPath: /etc/kubernetes/pki/etcd
                  readOnly: true
                - name: snapshots
                  mountPath: /snapshots
          restartPolicy: OnFailure
          hostNetwork: true
          nodeSelector:
            node-role.kubernetes.io/control-plane: ""
          tolerations:
            - key: node-role.kubernetes.io/control-plane
              effect: NoSchedule
          volumes:
            - name: etcd-certs
              hostPath:
                path: /etc/kubernetes/pki/etcd
            - name: snapshots
              persistentVolumeClaim:
                claimName: etcd-snapshots-pvc
```

---

## Multi-Region Failover

### ExternalDNS with Health Checks

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api-gateway
  namespace: production
  annotations:
    # ExternalDNS annotations for Route53
    external-dns.alpha.kubernetes.io/hostname: api.example.com
    external-dns.alpha.kubernetes.io/ttl: "60"
    # Failover routing policy
    external-dns.alpha.kubernetes.io/set-identifier: us-east-1-primary
    external-dns.alpha.kubernetes.io/aws-failover: PRIMARY
    # Health check
    external-dns.alpha.kubernetes.io/aws-health-check-id: "hc-abc123"
spec:
  type: LoadBalancer
  selector:
    app: api-gateway
  ports:
    - port: 443
      targetPort: 8443
---
# Secondary region Service (deployed to us-west-2 cluster)
apiVersion: v1
kind: Service
metadata:
  name: api-gateway
  namespace: production
  annotations:
    external-dns.alpha.kubernetes.io/hostname: api.example.com
    external-dns.alpha.kubernetes.io/ttl: "60"
    external-dns.alpha.kubernetes.io/set-identifier: us-west-2-secondary
    external-dns.alpha.kubernetes.io/aws-failover: SECONDARY
spec:
  type: LoadBalancer
  selector:
    app: api-gateway
  ports:
    - port: 443
      targetPort: 8443
```

---

## Topology Spread Constraints for HA

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-gateway
  namespace: production
spec:
  replicas: 6
  selector:
    matchLabels:
      app: api-gateway
  template:
    metadata:
      labels:
        app: api-gateway
    spec:
      topologySpreadConstraints:
        # Spread evenly across availability zones
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api-gateway
        # Spread across nodes within each zone
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: api-gateway
      affinity:
        # Avoid co-location with other critical services
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: app
                      operator: In
                      values:
                        - api-gateway
                topologyKey: kubernetes.io/hostname
      containers:
        - name: api-gateway
          image: myregistry/api-gateway:v2.1.0
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: "2"
              memory: 1Gi
```

---

## PodDisruptionBudget Patterns

### minAvailable (Guarantee Minimum Running)

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-gateway-pdb
  namespace: production
spec:
  minAvailable: 2                   # At least 2 pods must always be running
  selector:
    matchLabels:
      app: api-gateway
```

### maxUnavailable (Allow Maximum Disruption)

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: worker-pdb
  namespace: production
spec:
  maxUnavailable: "25%"             # At most 25% can be down during disruption
  selector:
    matchLabels:
      app: worker
```

### StatefulSet PDB (Database Clusters)

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-pdb
  namespace: production
spec:
  minAvailable: 2                   # Maintain quorum (3-node cluster)
  selector:
    matchLabels:
      app: postgres
      role: replica
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-primary-pdb
  namespace: production
spec:
  maxUnavailable: 0                 # Never disrupt the primary
  selector:
    matchLabels:
      app: postgres
      role: primary
```

**PDB Decision Guide**:
- Use `minAvailable` when you have a fixed minimum for quorum or capacity.
- Use `maxUnavailable` when you want percentage-based rolling tolerance.
- Use `maxUnavailable: 0` for single-instance critical workloads (prevents voluntary evictions).
- Never set `minAvailable` equal to replicas count -- it blocks all voluntary disruptions including node drains.

---

## DR Runbook Template

```yaml
# dr-runbook.yaml -- store alongside your manifests
apiVersion: v1
kind: ConfigMap
metadata:
  name: dr-runbook
  namespace: platform
  labels:
    type: runbook
data:
  runbook.md: |
    # DR Runbook: [Service Name]

    ## Severity Levels
    - SEV1: Complete service outage (page on-call + leadership)
    - SEV2: Degraded service (page on-call)
    - SEV3: Single component failure (Slack alert)

    ## Scenario 1: Single AZ Failure
    1. Verify pods rescheduled via topology spread constraints
    2. Check PDB status: kubectl get pdb -n production
    3. Confirm load balancer health checks passing
    4. Monitor: kubectl top nodes; kubectl get events --sort-by=.lastTimestamp

    ## Scenario 2: Full Cluster Loss
    1. Provision new cluster (Terraform / IaC -- estimated 15m)
    2. Install Velero: helm install velero vmware-tanzu/velero ...
    3. Configure BSL to point to backup bucket
    4. Restore: velero restore create --from-backup daily-full-backup-YYYYMMDD
    5. Verify: kubectl get pods -A; run smoke tests
    6. Update DNS to point to new cluster

    ## Scenario 3: etcd Corruption
    1. Stop kube-apiserver on all control plane nodes
    2. Restore etcd: etcdctl snapshot restore /snapshots/latest.db
    3. Restart etcd, then kube-apiserver
    4. Verify: kubectl get cs; kubectl get nodes

    ## Scenario 4: Region Failure (T4/T5)
    1. ExternalDNS health check fails -- automatic failover to secondary
    2. Verify secondary cluster receiving traffic
    3. Confirm data replication lag (check DB replication status)
    4. If active-active: no action needed, traffic auto-routes

    ## Post-Incident
    - Run backup verification: velero backup describe <name> --details
    - Confirm all PVCs restored: kubectl get pvc -A
    - Execute integration test suite
    - Update incident timeline and write post-mortem

    ## Contacts
    - On-call: PagerDuty rotation "k8s-platform"
    - Escalation: #incident-response Slack channel
    - Backup owner: platform-team@example.com
```

---

## Backup Verification CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: backup-verification
  namespace: velero
spec:
  schedule: "0 6 * * 1"            # Every Monday at 6 AM
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: velero
          containers:
            - name: verify
              image: bitnami/kubectl:1.30
              command:
                - /bin/sh
                - -c
                - |
                  set -e
                  echo "=== Backup Verification Report ==="
                  echo "Date: $(date -u)"

                  # Check latest backup status
                  LATEST=$(kubectl get backup -n velero \
                    --sort-by=.status.startTimestamp -o name | tail -1)
                  STATUS=$(kubectl get ${LATEST} -n velero \
                    -o jsonpath='{.status.phase}')

                  if [ "$STATUS" != "Completed" ]; then
                    echo "ALERT: Latest backup status is ${STATUS}"
                    exit 1
                  fi

                  echo "Latest backup: ${LATEST} -- Status: ${STATUS}"

                  # Check backup age
                  COMPLETED=$(kubectl get ${LATEST} -n velero \
                    -o jsonpath='{.status.completionTimestamp}')
                  echo "Completed at: ${COMPLETED}"

                  # Verify BSL is available
                  BSL_STATUS=$(kubectl get bsl default -n velero \
                    -o jsonpath='{.status.phase}')
                  echo "BSL status: ${BSL_STATUS}"

                  if [ "$BSL_STATUS" != "Available" ]; then
                    echo "ALERT: Backup storage location unavailable"
                    exit 1
                  fi

                  echo "=== All checks passed ==="
          restartPolicy: OnFailure
```
