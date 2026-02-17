# Core Patterns — Kafka 4.x Architecture

## KRaft Mode (No ZooKeeper)

Kafka 4.x uses KRaft for metadata. ZooKeeper is removed.

| Mode | When | `process.roles` |
|------|------|------------------|
| Combined | Dev/Tier 1-2 | `broker,controller` |
| Dedicated | Prod/Tier 3-4 | Separate `controller` and `broker` nodes (3 controllers + N brokers) |

### Tier 1 — Single Broker

```properties
process.roles=broker,controller
node.id=1
controller.quorum.voters=1@localhost:9093
listeners=PLAINTEXT://:9092,CONTROLLER://:9093
num.partitions=1
default.replication.factor=1
```

### Tier 2+ — Production Cluster

```properties
process.roles=broker
controller.quorum.voters=100@ctrl-0:9093,101@ctrl-1:9093,102@ctrl-2:9093
listeners=SASL_SSL://:9092
default.replication.factor=3
min.insync.replicas=2
unclean.leader.election.enable=false
num.io.threads=8
num.network.threads=3
num.replica.fetchers=4
log.dirs=/var/kafka/data-1,/var/kafka/data-2
log.retention.hours=168
log.segment.bytes=1073741824
```

### Tier 4 — Tiered Storage

```properties
remote.log.storage.system.enable=true
log.local.retention.hours=24  # keep 24h local, rest in remote (S3/GCS/Azure)
```

## Partition Strategy

```
partitions = max(target_throughput_MB / per_partition_throughput_MB, consumer_count)
Benchmarks: Producer ~10 MB/s/partition, Consumer ~30 MB/s/partition
Rules: Start 6, scale 12-30, max ~4000/broker. Key-based for ordering.
```

## Topic Naming: `<domain>.<entity>.<event-type>.<version>`

Examples: `orders.order.created.v1`, `_dlq.orders.order.created.v1`

## Log Cleanup

| Strategy | Use | Config |
|----------|-----|--------|
| Delete | Event streams, logs | `cleanup.policy=delete`, `retention.ms=604800000` |
| Compact | State snapshots | `cleanup.policy=compact` |
| Both | Compacted with TTL | `cleanup.policy=compact,delete` |

## Compression

| Codec | Best For |
|-------|----------|
| lz4 | Low-latency, high-throughput (recommended default) |
| snappy | Balanced |
| zstd | Storage-constrained, batch |
| gzip | Maximum compression, cold data |
