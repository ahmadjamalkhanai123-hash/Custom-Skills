# Kafka Streams, Connect & Schema Registry

## Kafka Streams (Java)

```java
StreamsBuilder builder = new StreamsBuilder();
KStream<String, String> source = builder.stream("input-topic");

// Filter + Transform
KStream<String, String> filtered = source.filter((k, v) -> v != null).mapValues(v -> transform(v));

// KTable (changelog, upsert by key)
KTable<String, String> table = builder.table("state-topic");

// Join KStream-KTable
KStream<String, Enriched> enriched = source.join(table, (event, state) -> enrich(event, state));

// Windowed aggregation (5-min tumbling)
KTable<Windowed<String>, Long> counts = source.groupByKey()
    .windowedBy(TimeWindows.ofSizeWithNoGrace(Duration.ofMinutes(5)))
    .count(Materialized.as("counts-store"));

filtered.to("output-topic");
```

### Window Types

| Type | Config |
|------|--------|
| Tumbling | `TimeWindows.ofSizeWithNoGrace(5min)` |
| Hopping | `TimeWindows.ofSizeAndGrace(5min, 1min).advanceBy(1min)` |
| Sliding | `SlidingWindows.ofTimeDifferenceWithNoGrace(5min)` |
| Session | `SessionWindows.ofInactivityGapWithNoGrace(30min)` |

### Config: `application.id`, `processing.guarantee=exactly_once_v2`, `num.stream.threads=4`

## Kafka Connect

### Distributed Worker

```properties
group.id=connect-cluster
key.converter=io.confluent.connect.avro.AvroConverter
key.converter.schema.registry.url=http://schema-registry:8081
value.converter=io.confluent.connect.avro.AvroConverter
offset.storage.topic=connect-offsets
offset.storage.replication.factor=3
config.storage.topic=connect-configs
config.storage.replication.factor=3
status.storage.topic=connect-status
status.storage.replication.factor=3
```

### Debezium CDC (PostgreSQL)

```json
{
  "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
  "database.hostname": "postgres", "database.port": "5432",
  "database.user": "debezium", "database.password": "${env:DB_PASSWORD}",
  "database.dbname": "orders_db", "topic.prefix": "cdc",
  "table.include.list": "public.orders,public.customers",
  "plugin.name": "pgoutput",
  "transforms": "route",
  "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
  "transforms.route.regex": "cdc\\.public\\.(.*)",
  "transforms.route.replacement": "db.$1.changes.v1"
}
```

### Common SMTs: ExtractField, InsertField, ReplaceField, RegexRouter, TimestampConverter, Flatten

## Schema Registry

### Compatibility Modes

| Mode | Rule | Safe Changes |
|------|------|-------------|
| BACKWARD (default) | New reads old | Add optional, remove fields |
| FORWARD | Old reads new | Remove optional, add fields |
| FULL | Both | Add/remove optional only |
| NONE | No check | Dev only |

### Python Avro Producer

```python
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka import SerializingProducer

sr = SchemaRegistryClient({"url": "http://schema-registry:8081"})
serializer = AvroSerializer(sr, schema_str, to_dict=lambda obj, ctx: obj)
producer = SerializingProducer({"bootstrap.servers": "broker:9092",
    "key.serializer": StringSerializer(), "value.serializer": serializer})
producer.produce(topic="orders", key="order-1", value=order_dict)
```
