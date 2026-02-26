# Database Replication Reference

## Database Selection Matrix

| Database | Type | Multi-Cloud Support | Consistency | Best For |
|----------|------|---------------------|------------|----------|
| **CockroachDB** | Distributed SQL | Excellent | Strong (Raft) | Global OLTP, financial |
| **Cloud Spanner** | Distributed SQL | GCP-native | External consistency | GCP-primary, high scale |
| **Cassandra** | Wide-column NoSQL | Excellent | Tunable | Time-series, IoT, high write |
| **CloudNativePG** | Postgres | Good (via replication) | Strong (streaming) | Postgres workloads |
| **CockroachDB** | Distributed SQL | Excellent | Strong | Most use cases |
| **Redis Cluster** | In-memory KV | Good | Eventual | Cache, sessions, leaderboard |
| **MongoDB Atlas** | Document | Multi-cloud native | Tunable | JSON document workloads |

---

## CockroachDB Multi-Region (Recommended for Global SQL)

CockroachDB distributes data across clouds with Raft consensus.
No single point of failure — survives node, zone, and region failures.

### Installation (Kubernetes via CockroachDB Operator)

```yaml
# CockroachDB Operator on each cluster
helm repo add cockroachdb https://charts.cockroachdb.com/
helm install cockroachdb cockroachdb/cockroachdb \
  --namespace cockroachdb --create-namespace \
  --set statefulset.replicas=3 \
  --set conf.locality="region=us-east1,cloud=aws" \
  --set tls.enabled=true \
  --set tls.certs.selfSigner.enabled=true
```

### Multi-Region Cluster (Across Clouds)

```sql
-- Add regions (connect to any node)
ALTER DATABASE prod ADD REGION "us-east1";   -- AWS EKS
ALTER DATABASE prod ADD REGION "us-central1"; -- GCP GKE
ALTER DATABASE prod ADD REGION "eastus";      -- Azure AKS

-- Set primary region (most reads/writes)
ALTER DATABASE prod SET PRIMARY REGION "us-east1";

-- Survival goal: survive full region failure (requires 3+ regions)
ALTER DATABASE prod SURVIVE REGION FAILURE;
```

### Multi-Region Table Optimizations

```sql
-- Global table: read anywhere, updated everywhere (config data)
CREATE TABLE config (
  key STRING PRIMARY KEY,
  value JSONB,
  updated_at TIMESTAMPTZ DEFAULT now()
) LOCALITY GLOBAL;

-- Regional table: pinned to user's home region
CREATE TABLE orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID,
  region crdb_internal_region,     -- auto-set based on gateway
  status STRING,
  total DECIMAL(12,2),
  created_at TIMESTAMPTZ DEFAULT now()
) LOCALITY REGIONAL BY ROW;

-- Regional table: all data in one region (fixed-location data)
CREATE TABLE audit_logs (
  id UUID PRIMARY KEY,
  event JSONB,
  created_at TIMESTAMPTZ
) LOCALITY REGIONAL IN "us-east1";
```

### Monitoring CockroachDB

```bash
# Prometheus metrics endpoint (every node)
# cockroachdb.prometheus.io/scrape: "true"
# cockroachdb.prometheus.io/port: "8080"

# Key metrics to alert on:
# - sql_query_latency_bucket  (p99 < 100ms)
# - ranges_unavailable         (must be 0)
# - replication_lag_nanos      (< 60s)
# - node_liveness_live_count   (== total_nodes)
```

---

## Cassandra Multi-Datacenter

Cassandra's NetworkTopologyStrategy replicates across datacenters (clouds).
Each cloud = one Cassandra datacenter.

### Deployment (K8s Operator)

```yaml
apiVersion: cassandra.datastax.com/v1beta1
kind: CassandraDatacenter
metadata:
  name: dc-aws
  namespace: cassandra
spec:
  clusterName: prod-cluster
  serverType: cassandra
  serverVersion: "4.1.0"
  managementApiAuth:
    insecure: {}
  size: 3
  storageConfig:
    cassandraDataVolumeClaimSpec:
      storageClassName: gp3
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 500Gi
  config:
    cassandra-yaml:
      num_tokens: 256
      endpoint_snitch: GossipingPropertyFileSnitch
    jvm-server-options:
      max_heap_size: "8G"
      initial_heap_size: "8G"
  racks:
    - name: rack1
    - name: rack2
    - name: rack3
```

### Keyspace with Multi-DC Replication

```cql
-- Create keyspace with 3 replicas per datacenter
CREATE KEYSPACE payments
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc-aws': 3,        -- 3 replicas in AWS
  'dc-gcp': 3,        -- 3 replicas in GCP
  'dc-azure': 2       -- 2 replicas in Azure (read replica)
} AND durable_writes = true;

-- Consistency levels for multi-DC
-- Write: LOCAL_QUORUM (writes to local DC before returning)
-- Read: LOCAL_QUORUM (reads from local DC, fastest)
-- For critical operations: EACH_QUORUM (all DCs must ack)
```

### Consistency Level Guide

| Operation | Consistency Level | Trade-off |
|-----------|------------------|-----------|
| Normal writes | LOCAL_QUORUM | Fast, survives minority DC failure |
| Financial writes | EACH_QUORUM | Slow, guarantees all DCs |
| Normal reads | LOCAL_QUORUM | Fast, local DC |
| Stale-tolerant reads | LOCAL_ONE | Fastest, may return stale data |
| Cross-DC reads | QUORUM | Balances consistency + perf |

---

## CloudNativePG — Postgres Multi-Cloud

CloudNativePG (CNPG) manages Postgres clusters on K8s.
For true multi-cloud, use streaming replication to standby clusters.

### Primary Cluster (AWS EKS)

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: prod-primary
  namespace: postgres
spec:
  instances: 3
  primaryUpdateStrategy: unsupervised

  postgresql:
    parameters:
      max_connections: "500"
      wal_level: "logical"         # for logical replication
      max_replication_slots: "10"
      wal_keep_size: "1GB"

  storage:
    size: 100Gi
    storageClass: gp3

  backup:
    barmanObjectStore:
      destinationPath: "s3://postgres-backups/primary"
      s3Credentials:
        accessKeyId:
          name: s3-backup-creds
          key: ACCESS_KEY_ID
        secretAccessKey:
          name: s3-backup-creds
          key: SECRET_ACCESS_KEY
      wal:
        compression: gzip
        maxParallel: 8
      data:
        compression: gzip
        immediateCheckpoint: true
    retentionPolicy: "30d"
```

### Standby Cluster (GCP GKE) — Bootstrapped from S3

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: prod-standby-gcp
  namespace: postgres
spec:
  instances: 2

  # Bootstrap as replica from primary's backup
  bootstrap:
    recovery:
      source: primary-aws
      recoveryTarget:
        targetTime: ""    # recover to latest

  # Streaming replication from primary
  externalClusters:
    - name: primary-aws
      connectionParameters:
        host: prod-primary-rw.postgres.svc.cluster.local
        user: streaming_replica
        dbname: postgres
        sslmode: verify-full
      sslCert:
        name: primary-tls
        key: tls.crt
      sslKey:
        name: primary-tls
        key: tls.key
      sslRootCert:
        name: primary-ca
        key: ca.crt
      password:
        name: streaming-replica-secret
        key: password
      barmanObjectStore:
        destinationPath: "s3://postgres-backups/primary"
        s3Credentials:
          accessKeyId:
            name: s3-backup-creds
            key: ACCESS_KEY_ID
```

### Switchover / Failover (CNPG)

```bash
# Planned switchover (no data loss)
kubectl cnpg promote prod-standby-gcp prod-standby-gcp-2 -n postgres

# Check replication lag
kubectl cnpg status prod-primary -n postgres | grep "Replication slots"

# Manual failover after primary loss
kubectl cnpg promote prod-standby-gcp --force -n postgres
```

---

## Redis Multi-Cloud (Session Store, Cache)

### Redis Cluster Across Clouds (Redis Enterprise)

Redis Enterprise supports Active-Active geo-distributed clusters:

```yaml
# Redis Enterprise Operator
apiVersion: app.redislabs.com/v1alpha1
kind: RedisEnterpriseCluster
metadata:
  name: prod-redis
spec:
  nodes: 3
  redisEnterpriseNodeResources:
    limits:
      cpu: "4"
      memory: 8Gi
  uiServiceType: LoadBalancer
```

### Open-Source Redis Cluster (Alternative)

Use ValKey (Redis OSS fork) or Redis 7.x with Kubernetes operator:

```yaml
# Deploy Redis Cluster (6 nodes: 3 primary + 3 replica)
helm install redis bitnami/redis-cluster \
  --set cluster.nodes=6 \
  --set cluster.replicas=1 \
  --set auth.enabled=true \
  --set persistence.size=10Gi

# For cross-cloud: use Redis with CRDB (Active-Active)
# or use Redis as pure cache with independent clusters per cloud
# (cache misses are acceptable — just slower)
```

### Cache Strategy for Multi-Cloud

For cache consistency across clouds:
1. **Each cloud has independent cache** — simplest, cache misses go to DB
2. **Write-through on DB write** — write to all caches on DB update (complex)
3. **Cache invalidation via Kafka** — DB write → Kafka event → all caches invalidate

Option 1 is recommended unless strict cache consistency is required.

---

## Data Sovereignty Considerations

When deploying across clouds in different countries:

| Requirement | Solution |
|-------------|----------|
| EU data stays in EU (GDPR) | Regional tables in CockroachDB; EU-only clusters |
| US gov data (FedRAMP) | AWS GovCloud or Azure Government only |
| Healthcare (HIPAA) | Encrypted at rest + in transit; audit logging enabled |
| PCI cardholder data | Isolated namespaces + network policy; no cross-region card data |

```sql
-- CockroachDB: pin EU user data to EU region
CREATE TABLE users (
  id UUID PRIMARY KEY,
  region crdb_internal_region NOT NULL,
  email STRING,
  created_at TIMESTAMPTZ DEFAULT now()
) LOCALITY REGIONAL BY ROW;

-- EU users automatically stored in eu-west1 region
-- US users automatically stored in us-east1 region
```

---

## Database Observability

### Key Metrics Per Database

**CockroachDB:**
```promql
# Replication lag
max(replication_lag_nanos) by (store_id) / 1e9

# Query latency p99
histogram_quantile(0.99, sql_service_latency_bucket)
```

**Cassandra:**
```promql
# Read/write latency p99
histogram_quantile(0.99, cassandra_read_latency_bucket)
histogram_quantile(0.99, cassandra_write_latency_bucket)

# Pending compactions (alert if > 15)
cassandra_pending_compactions
```

**CloudNativePG (Postgres):**
```promql
# Replication lag (seconds)
pg_replication_lag

# Active connections
pg_stat_activity_count{state="active"}

# Database size growth
pg_database_size_bytes
```
