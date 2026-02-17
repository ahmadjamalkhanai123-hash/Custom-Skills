# Security & Operations

## Authentication

### SASL/SCRAM-SHA-512 (Tier 2+)

```properties
# Broker
listeners=SASL_SSL://:9092
sasl.enabled.mechanisms=SCRAM-SHA-512
sasl.mechanism.inter.broker.protocol=SCRAM-SHA-512
```

```bash
# Create users
kafka-configs.sh --bootstrap-server broker:9092 --alter \
  --add-config 'SCRAM-SHA-512=[password=secret]' --entity-type users --entity-name admin
```

### OAUTHBEARER (Tier 3+): `sasl.enabled.mechanisms=OAUTHBEARER` + token endpoint config

### mTLS (Tier 4): `ssl.client.auth=required` + keystore/truststore per client, TLSv1.3

## TLS (In-Transit)

```properties
ssl.keystore.location=/etc/kafka/certs/broker.keystore.p12
ssl.keystore.type=PKCS12
ssl.truststore.location=/etc/kafka/certs/truststore.p12
ssl.enabled.protocols=TLSv1.3
```

## ACLs

```bash
# Producer ACL (prefix-based)
kafka-acls.sh --bootstrap-server broker:9092 --add \
  --allow-principal User:order-service --operation Write,Describe \
  --topic orders.order --resource-pattern-type prefixed

# Consumer ACL
kafka-acls.sh --add --allow-principal User:payment-service \
  --operation Read,Describe --topic orders.order --resource-pattern-type prefixed \
  --group payment-processor --resource-pattern-type prefixed
```

### RBAC: ClusterAdmin (all), TopicAdmin (create/delete), Producer (write prefix), Consumer (read prefix), Monitor (describe-only)

## Encryption at Rest: LUKS/dm-crypt on log.dirs, or cloud KMS (EBS/CMEK)

## Rolling Restart (Zero Downtime)

```
For each broker (one at a time):
1. Stop → 2. Verify ISR ≥ min.insync.replicas → 3. Start → 4. Wait until caught up → 5. Next
```

## Multi-Cluster — MirrorMaker 2

```properties
clusters=us-east, eu-west
us-east.bootstrap.servers=us-broker:9092
eu-west.bootstrap.servers=eu-broker:9092
us-east->eu-west.enabled=true
us-east->eu-west.topics=orders\..*,payments\..*
replication.factor=3
emit.heartbeats.enabled=true
emit.checkpoints.enabled=true
```

Active-Active: Each region has local topics + replicated topics (prefixed with source cluster name). Consumer subscribes to both. Dedup by event_id header.
