# Deployment & Monitoring

## Kubernetes — Strimzi Operator

```bash
kubectl create namespace kafka
kubectl apply -f https://strimzi.io/install/latest?namespace=kafka -n kafka
```

See `assets/templates/strimzi_cluster.yaml` for full Kafka CR. Key settings:
- `spec.kafka.replicas: 3+`, dedicated KRaft controllers
- Listeners: plain (internal), tls (inter-broker), external (LoadBalancer/Ingress)
- Storage: JBOD persistent volumes, rack awareness for AZ spread
- Strimzi also provides CRDs: KafkaTopic, KafkaUser, KafkaConnect, KafkaMirrorMaker2

### Strimzi Topic CRD

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: orders.order.created.v1
  labels: { strimzi.io/cluster: my-kafka }
spec:
  partitions: 12
  replicas: 3
  config: { retention.ms: "604800000", min.insync.replicas: "2", compression.type: lz4 }
```

## Monitoring — Critical Metrics

| Metric | Threshold | Severity |
|--------|-----------|----------|
| UnderReplicatedPartitions | > 0 for 5m | CRITICAL |
| ActiveControllerCount | != 1 | CRITICAL |
| OfflinePartitionsCount | > 0 | CRITICAL |
| ISRShrinkRate | sustained > 0 | WARNING |
| RequestHandlerAvgIdlePercent | < 0.3 | WARNING |
| consumer_lag | > threshold | WARNING |
| Disk usage | > 85% | WARNING |

### Prometheus Alerts

```yaml
- alert: KafkaUnderReplicatedPartitions
  expr: kafka_server_replica_manager_under_replicated_partitions > 0
  for: 5m
  labels: { severity: critical }
- alert: KafkaConsumerLag
  expr: kafka_consumergroup_lag > 10000
  for: 10m
  labels: { severity: warning }
```

### Grafana Panels: cluster overview, throughput (msg/s, bytes/s), latency (p50/p99), replication (ISR), consumer lag, disk, JVM

## Bare-Metal Tuning

```
Hardware: 24+ cores, 64GB+ RAM (page cache!), NVMe SSD JBOD, 10Gbps
OS: vm.swappiness=1, vm.dirty_ratio=80, ulimit -n 100000
JVM: -Xms6g -Xmx6g -XX:+UseG1GC -XX:MaxGCPauseMillis=20
```
