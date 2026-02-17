# Anti-Patterns

## Architecture

| Anti-Pattern | Fix |
|-------------|-----|
| ZooKeeper in new deployments | KRaft mode only (Kafka 4.x) |
| Single broker in production | Min 3 brokers, RF=3 |
| Too many partitions | Start 6, scale by throughput formula |
| Topic per tenant | Key-based partitioning in shared topics |
| Kafka as database | Events in Kafka, materialize to DB for queries |
| Messages >1MB | Claim check: store in S3, send reference |

## Producer

| Anti-Pattern | Fix |
|-------------|-----|
| `acks=0/1` in prod | `acks=all` always |
| No idempotence | `enable.idempotence=true` |
| Fire-and-forget | Always register delivery callback |
| String serialization | Avro/Protobuf + Schema Registry |
| Hardcoded bootstrap | Config/env vars or DNS |
| `batch.size=0` | 65536 + `linger.ms=5` |

## Consumer

| Anti-Pattern | Fix |
|-------------|-----|
| `auto.commit=true` + processing | Manual commit after processing |
| Unbounded processing time | Stay within `max.poll.interval.ms` |
| No DLQ | DLQ after N retries for poison pills |
| `auto.offset.reset=latest` for processing | `earliest` for processing |
| Non-idempotent handlers | Dedup by event_id |

## Schema

| Anti-Pattern | Fix |
|-------------|-----|
| No schema | Schema Registry + Avro/Protobuf |
| `compatibility=NONE` in prod | BACKWARD or FULL |
| Removing required fields | Only remove optional fields |

## Operations

| Anti-Pattern | Fix |
|-------------|-----|
| No monitoring | Prometheus + JMX + alerting |
| Ignoring consumer lag | Alert on lag > threshold |
| `unclean.leader.election=true` | Always `false` in prod |
| No rack awareness | `broker.rack=az-1` |

## Security

| Anti-Pattern | Fix |
|-------------|-----|
| PLAINTEXT in prod | SASL_SSL or SSL |
| Credentials in code | Env vars or secret manager |
| No ACLs | Topic-prefixed ACLs per service |
| Shared credentials | Unique per service identity |

## Performance

| Anti-Pattern | Fix |
|-------------|-----|
| No compression | `compression.type=lz4` |
| RAID on Kafka disks | JBOD, multiple log.dirs |
| Swapping | `vm.swappiness=1` |
