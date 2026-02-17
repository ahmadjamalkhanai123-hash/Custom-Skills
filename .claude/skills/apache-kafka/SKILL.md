---
name: apache-kafka
description: |
  Creates production-ready Apache Kafka architectures, configurations, and deployments
  from single-broker dev setups to global enterprise event streaming platforms with
  exactly-once semantics, multi-cluster replication, and cloud-native operations.
  This skill should be used when users want to build Kafka clusters, create
  producer/consumer applications, implement event-driven microservices, deploy
  Kafka Streams pipelines, configure Kafka Connect, set up schema registries,
  or architect enterprise-scale event streaming platforms.
---

# Apache Kafka

Build production-ready Apache Kafka event streaming platforms for any scale.

## What This Skill Does

- Creates Kafka cluster architectures (KRaft mode, Kafka 4.x — no ZooKeeper)
- Generates producer/consumer applications (Python, Java, Node.js, Go)
- Implements event-driven microservices (Event Sourcing, CQRS, Saga, Outbox)
- Builds Kafka Streams topologies (KStream, KTable, windowing, joins)
- Configures Kafka Connect pipelines (Debezium CDC, custom connectors, SMTs)
- Sets up Schema Registry (Avro, Protobuf, JSON Schema, compatibility modes)
- Deploys to Kubernetes (Strimzi operator), Docker Compose, or bare-metal
- Configures security (SASL/SCRAM, OAUTHBEARER, mTLS, ACLs, RBAC)
- Implements monitoring (Prometheus/Grafana, JMX, consumer lag, alerting)
- Architects multi-cluster (MirrorMaker 2, Cluster Linking, geo-replication)

## What This Skill Does NOT Do

- Manage Confluent Cloud accounts or billing
- Deploy to production infrastructure (generates configs, not deploys)
- Create custom Kafka protocol implementations (uses official clients)
- Handle ZooKeeper-based clusters (Kafka 4.x KRaft only)
- Monitor live clusters at runtime (generates monitoring configs)

---

## Before Implementation

Gather context to ensure successful implementation:

| Source | Gather |
|--------|--------|
| **Codebase** | Existing services, message formats, infra configs, language/framework |
| **Conversation** | User's scale requirements, use case, deployment target |
| **Skill References** | Domain patterns from `references/` (architecture, security, patterns) |
| **User Guidelines** | Team conventions, compliance requirements, cloud provider |

Ensure all required context is gathered before implementing.
Only ask user for THEIR specific requirements (Kafka domain expertise is in this skill).

---

## Required Clarifications

### Before Asking

1. Check conversation history for prior answers
2. Infer from existing project files (docker-compose, pom.xml, package.json, go.mod)
3. Only ask what cannot be determined from context

### Ask First

1. **Tier**: "What scale/complexity level?"

| Tier | Scope | Use Case |
|------|-------|----------|
| **1 — Dev** | Single broker, Docker Compose | Local development, prototyping |
| **2 — Production** | 3+ brokers, replication, security, monitoring | Single-team production |
| **3 — Microservices** | Event-driven architecture, CQRS, sagas, schema registry | Multi-service platform |
| **4 — Enterprise** | Multi-cluster, geo-replication, tiered storage, compliance | Global-scale systems |

2. **Use case**: "What are you building?"
   - Event streaming / real-time analytics
   - Microservices messaging / event-driven architecture
   - Data pipeline / CDC / ETL
   - Log aggregation / audit trail
   - AI agent event backbone

3. **Language**: "What's your primary language?"
   - Python (confluent-kafka / aiokafka)
   - Java (official client / Spring Kafka)
   - Node.js (kafkajs)
   - Go (confluent-kafka-go / segmentio)

### Ask If Needed

4. **Deployment target**: Kubernetes (Strimzi) / Docker Compose / Bare-metal / Cloud managed
5. **Security level**: None (dev) / SASL+TLS (prod) / mTLS+RBAC+encryption-at-rest (enterprise)
6. **Connect needs**: CDC (Debezium), S3 sink, Elasticsearch, JDBC, custom connectors

### Defaults (If Not Specified)

| Clarification | Default |
|---------------|---------|
| Tier | Infer from use case complexity |
| Language | Python (confluent-kafka) |
| Deployment | Docker Compose (Tier 1-2), Kubernetes (Tier 3-4) |
| Security | None (Tier 1), SASL/SCRAM+TLS (Tier 2+) |
| Schema Registry | Skip (Tier 1-2), Avro+BACKWARD (Tier 3-4) |
| Monitoring | None (Tier 1), Prometheus+Grafana (Tier 2+) |

---

## Workflow

```
Clarify → Architecture → Configure → Implement → Secure → Monitor → Validate
```

### Step 1: Determine Architecture

Select tier-appropriate architecture from `references/core-patterns.md`:

```
Tier 1: Single KRaft broker → Docker Compose → basic producer/consumer
Tier 2: 3-broker KRaft cluster → replication(3) + min.insync(2) → security + monitoring
Tier 3: Tier 2 + Schema Registry + Connect + Streams → event-driven microservices
Tier 4: Tier 3 + MirrorMaker 2 / Cluster Linking → multi-region active-active
```

### Step 2: Generate Cluster Configuration

**All tiers use KRaft mode (Kafka 4.x default — no ZooKeeper)**

Production broker defaults:

```properties
# === Broker server.properties ===
# Replication
default.replication.factor=3
min.insync.replicas=2
unclean.leader.election.enable=false

# Performance
compression.type=lz4
num.io.threads=8
num.network.threads=3
socket.send.buffer.bytes=102400
socket.receive.buffer.bytes=102400

# Retention
log.retention.hours=168
log.segment.bytes=1073741824
log.cleanup.policy=delete
```

Producer client config (NOT broker — set in application code):

```properties
# === Producer client config ===
acks=all
enable.idempotence=true
max.in.flight.requests.per.connection=5
batch.size=65536
linger.ms=5
compression.type=lz4
```

### Step 3: Implement Applications

Read `references/producer-consumer.md` for language-specific patterns.

**Producer essentials** (all languages):
- `acks=all` + `enable.idempotence=true` for exactly-once
- Batch tuning: `batch.size=65536`, `linger.ms=5`
- Compression: lz4 (speed) / zstd (ratio) / snappy (balanced)
- Error handling: retriable vs fatal, dead letter queue

**Consumer essentials** (all languages):
- Consumer groups with `cooperative-sticky` assignor
- `max.poll.records=500`, `session.timeout.ms=45000`
- Exactly-once: `isolation.level=read_committed` + transactional producer
- Offset strategy: `auto.offset.reset=earliest` for processing, `latest` for tailing

### Step 4: Configure Schema Registry (Tier 3-4)

Read `references/streams-connect.md` for schema patterns.

```
Compatibility modes:
  BACKWARD (default) — new schema can read old data (add optional fields)
  FORWARD — old schema can read new data (remove optional fields)
  FULL — both directions (safest for microservices)
  NONE — no compatibility check (dev only)
```

### Step 5: Implement Event Patterns (Tier 3-4)

Read `references/microservices-patterns.md` for:
- Event Sourcing — events as source of truth
- CQRS — separate read/write models
- Saga — orchestration (central coordinator) vs choreography (event chain)
- Transactional Outbox — atomically publish events with DB changes
- Dead Letter Queue — handle poison pills

### Step 6: Security Hardening (Tier 2+)

Read `references/security-operations.md`:

| Layer | Tier 2 | Tier 3 | Tier 4 |
|-------|--------|--------|--------|
| Auth | SASL/SCRAM-SHA-512 | + OAUTHBEARER | + mTLS |
| Encryption | TLS in-transit | + TLS inter-broker | + at-rest |
| Authorization | ACLs | + prefixed ACLs | + RBAC |
| Audit | Broker logs | + topic audit trail | + compliance logging |

### Step 7: Monitoring Stack (Tier 2+)

Read `references/deployment-monitoring.md`:
- JMX exporter → Prometheus → Grafana
- Key metrics: UnderReplicatedPartitions, ActiveControllerCount, consumer lag
- Alerting rules for broker health, ISR shrink, disk usage

### Step 8: Validate Output

Apply Output Checklist below.

---

## Partition Strategy

```
partitions = max(target_throughput / partition_throughput, consumer_count)

Rules:
- Start: 6 partitions per topic (most use cases)
- Scale: 12-30 for high throughput
- Max: ~4000 per broker (cluster limit)
- Key-based: ensure uniform key distribution
- Ordering: messages with same key → same partition → ordered
```

---

## Tier Quick Reference

| | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|--------|--------|--------|--------|
| Brokers | 1 | 3+ | 3+ | 3+ per region |
| KRaft Controllers | Combined | Combined | Dedicated 3 | Dedicated 3 per DC |
| Replication | 1 | 3 | 3 | 3 per cluster |
| Security | None | SASL+TLS | +ACLs+Schema | +mTLS+RBAC+audit |
| Schema Registry | No | Optional | Yes (Avro) | Yes (multi-region) |
| Connect | No | Optional | Yes | Yes (MM2/CL) |
| Streams | No | Optional | Yes | Yes |
| Monitoring | No | Prometheus | +Grafana+alerts | +cross-cluster |
| Deploy | Docker Compose | Docker/K8s | Kubernetes | Multi-K8s |
| Tiered Storage | No | No | Optional | Yes |

---

## MCP Server Tools

Context-optimized Kafka MCP server in `scripts/kafka_mcp_server.py`:

| Tool | Purpose |
|------|---------|
| `cluster_health` | Check broker status, controller, ISR |
| `topic_manage` | Create/describe/alter topics |
| `consumer_groups` | List groups, check lag, describe members |
| `config_audit` | Validate broker/topic configs against best practices |
| `schema_validate` | Validate Avro/Protobuf schemas, check compatibility |

Start: `python scripts/kafka_mcp_server.py` (stdio transport)

---

## Output Specification

Every generated Kafka project includes:

### Required Components
- [ ] KRaft cluster configuration (server.properties per broker)
- [ ] Producer/consumer code with error handling and serialization
- [ ] Docker Compose or K8s manifests for deployment
- [ ] Topic creation scripts with partition/replication strategy

### Tier 2+ Components
- [ ] TLS certificates setup (scripts or reference)
- [ ] SASL authentication configuration
- [ ] Prometheus JMX exporter + Grafana dashboards
- [ ] Health check and alerting rules

### Tier 3+ Components
- [ ] Schema Registry with compatibility mode
- [ ] Connect workers with connector configs
- [ ] Event-driven service patterns (chosen pattern)
- [ ] Dead letter queue handling

### Tier 4 Components
- [ ] Multi-cluster topology (active-active or active-passive)
- [ ] MirrorMaker 2 or Cluster Linking configuration
- [ ] Tiered storage configuration
- [ ] Compliance and audit logging

---

## Domain Standards

### Must Follow

- [ ] KRaft mode only (Kafka 4.x — no ZooKeeper)
- [ ] `acks=all` + `enable.idempotence=true` for any production producer
- [ ] `min.insync.replicas=2` with `replication.factor=3` for durability
- [ ] Consumer cooperative-sticky rebalancing (avoid stop-the-world)
- [ ] Schema evolution with compatibility modes (never NONE in prod)
- [ ] Dead letter queues for failed message handling
- [ ] Idempotent consumers (handle redelivery gracefully)
- [ ] Key-based partitioning for ordering guarantees
- [ ] Structured logging with correlation IDs across services
- [ ] Health checks on all broker and consumer group endpoints

### Must Avoid

- ZooKeeper-based deployment (deprecated in Kafka 4.x)
- `acks=0` or `acks=1` in production (data loss risk)
- `auto.commit.enable=true` with exactly-once requirements
- Unbounded consumer poll loops without backpressure
- String serialization for structured data (use Avro/Protobuf)
- Single partition topics for high-throughput workloads
- Hardcoded bootstrap servers (use config/env vars)
- Consumer group IDs without naming convention
- Ignoring consumer lag monitoring
- Fire-and-forget producer without error callbacks

---

## Output Checklist

Before delivering, verify:

- [ ] KRaft mode configured (no ZooKeeper references)
- [ ] Replication factor ≥3 for production topics
- [ ] min.insync.replicas = replication_factor - 1
- [ ] Producer idempotence enabled
- [ ] Consumer error handling with DLQ
- [ ] Security configured per tier
- [ ] Monitoring configured per tier
- [ ] Schema compatibility mode set (Tier 3+)
- [ ] Topic naming convention documented
- [ ] Partition strategy documented with formula
- [ ] Docker Compose or K8s manifests included
- [ ] Client configuration examples provided
- [ ] Anti-patterns from `references/anti-patterns.md` avoided

---

## Reference Files

| File | When to Read |
|------|--------------|
| `references/core-patterns.md` | Architecture, KRaft, broker configs, partition strategy |
| `references/producer-consumer.md` | Producer/consumer patterns in Python, Java, Node.js, Go |
| `references/streams-connect.md` | Kafka Streams topologies, Connect pipelines, Schema Registry |
| `references/microservices-patterns.md` | Event Sourcing, CQRS, Saga, Outbox, DLQ patterns |
| `references/security-operations.md` | SASL, mTLS, ACLs, RBAC, encryption, audit |
| `references/deployment-monitoring.md` | Strimzi K8s, Docker Compose, Prometheus, Grafana, alerting |
| `references/anti-patterns.md` | Common Kafka mistakes and fixes |

## Asset Templates

| Template | Purpose |
|----------|---------|
| `assets/templates/docker_compose_dev.yml` | Tier 1-2 local development stack |
| `assets/templates/python_producer_consumer.py` | Production Python producer/consumer |
| `assets/templates/kafka_streams_app.java` | Kafka Streams topology template |
| `assets/templates/strimzi_cluster.yaml` | Strimzi Kafka CR for Kubernetes |
| `assets/templates/monitoring_stack.yml` | Prometheus + Grafana + JMX exporter |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scaffold_kafka.py` | Generate complete project: `--tier 1\|2\|3\|4 --lang --security --monitoring` |
| `scripts/kafka_mcp_server.py` | Context-optimized MCP server for Kafka operations |

## Official Documentation

| Resource | URL | Use For |
|----------|-----|---------|
| Apache Kafka | https://kafka.apache.org/documentation/ | Core config, protocol, APIs |
| KRaft (KIP-500) | https://kafka.apache.org/documentation/#kraft | KRaft migration, controller config |
| Confluent Platform | https://docs.confluent.io/platform/current/overview.html | Schema Registry, ksqlDB, Connect |
| Strimzi Operator | https://strimzi.io/documentation/ | K8s deployment, CRDs, upgrades |
| Schema Registry | https://docs.confluent.io/platform/current/schema-registry/ | Avro/Protobuf, compatibility |
| Debezium CDC | https://debezium.io/documentation/ | CDC connectors, transforms |

Last verified: February 2026 (Kafka 3.9.x / 4.0, Strimzi 0.44, Confluent Platform 7.7).
When versions update: check references/core-patterns.md for config changes, update image tags in assets/templates/.
