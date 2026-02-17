# Producer & Consumer Patterns

## Python — confluent-kafka

### Producer

```python
from confluent_kafka import Producer
import json, os

producer = Producer({
    "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"],
    "acks": "all", "enable.idempotence": True,
    "max.in.flight.requests.per.connection": 5,
    "retries": 2147483647, "delivery.timeout.ms": 120000,
    "batch.size": 65536, "linger.ms": 5, "compression.type": "lz4",
    # SASL: "security.protocol": "SASL_SSL", "sasl.mechanism": "SCRAM-SHA-512",
})

def delivery_cb(err, msg):
    if err: print(f"FAILED: {err}")

def produce(topic, key, value):
    producer.produce(topic, key=key.encode(), value=json.dumps(value).encode(), callback=delivery_cb)
    producer.poll(0)
# producer.flush(30) on shutdown
```

### Consumer

```python
from confluent_kafka import Consumer, KafkaError
import json, os, signal

consumer = Consumer({
    "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"],
    "group.id": "my-group", "auto.offset.reset": "earliest",
    "enable.auto.commit": False, "session.timeout.ms": 45000,
    "partition.assignment.strategy": "cooperative-sticky",
    "isolation.level": "read_committed",
})

running = True
def _shutdown(sig, frame):
    global running
    running = False
signal.signal(signal.SIGTERM, _shutdown)
consumer.subscribe(["topic"])
try:
    while running:
        msg = consumer.poll(1.0)
        if msg is None: continue
        if msg.error():
            if msg.error().code() != KafkaError._PARTITION_EOF: print(f"Error: {msg.error()}")
            continue
        if process(msg): consumer.commit(message=msg)
        else: produce_to_dlq(msg)  # DLQ on failure, then commit
finally:
    consumer.close()
```

### Transactional Producer (Exactly-Once)

```python
config["transactional.id"] = "txn-1"
producer = Producer(config)
producer.init_transactions()
producer.begin_transaction()
producer.produce("output", key=b"k", value=b"v")
producer.send_offsets_to_transaction(consumer.position(consumer.assignment()), consumer.consumer_group_metadata())
producer.commit_transaction()  # or abort_transaction() on error
```

## Python — aiokafka (Async)

```python
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

producer = AIOKafkaProducer(bootstrap_servers="localhost:9092", acks="all",
    enable_idempotence=True, compression_type="lz4",
    value_serializer=lambda v: json.dumps(v).encode())
await producer.start()
await producer.send_and_wait("topic", value={"k": "v"}, key=b"key")

consumer = AIOKafkaConsumer("topic", bootstrap_servers="localhost:9092",
    group_id="grp", enable_auto_commit=False, isolation_level="read_committed")
await consumer.start()
async for msg in consumer:
    process(msg); await consumer.commit()
```

## Java

```java
// Producer: acks=all, idempotence=true, batch=65536, linger=5, compression=lz4
// Consumer: group.id, auto.commit=false, isolation=read_committed, cooperative-sticky
// See assets/templates for full Java examples
```

## Node.js — kafkajs

```javascript
const { Kafka } = require("kafkajs");
const kafka = new Kafka({ brokers: ["broker:9092"] });
const producer = kafka.producer({ idempotent: true });
await producer.send({ topic: "t", messages: [{ key: "k", value: JSON.stringify(data) }] });
const consumer = kafka.consumer({ groupId: "g" });
await consumer.subscribe({ topic: "t" });
await consumer.run({ eachMessage: async ({ message }) => process(message) });
```
