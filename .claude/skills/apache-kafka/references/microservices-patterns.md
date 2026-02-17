# Microservices Event-Driven Patterns

## Event Sourcing

Store state as event sequence, rebuild by replay. Use compacted KTable for snapshots.

```python
def append_event(producer, topic, aggregate_id, event_type, data, version):
    producer.produce(topic, key=aggregate_id.encode(), value=json.dumps({
        "aggregate_id": aggregate_id, "event_type": event_type,
        "data": data, "version": version, "timestamp": datetime.utcnow().isoformat(),
    }).encode())
```

## CQRS

```
Commands → Kafka command topic → Validator → Event topic → Read Model Projector → Query DB
```

```python
async def project(consumer):
    async for msg in consumer:
        event = json.loads(msg.value())
        match event["event_type"]:
            case "OrderCreated": await db.execute("INSERT INTO order_view ...", event["data"])
            case "OrderUpdated": await db.execute("UPDATE order_view SET ...", event["data"])
        await consumer.commit()
```

## Saga — Choreography (Event Chain)

```
OrderService → order.created → PaymentService → payment.processed → InventoryService → stock.reserved
Compensation: payment.failed → OrderService cancels, InventoryService releases
```

## Saga — Orchestration (Coordinator)

```python
STEPS = [
    {"svc": "payment", "cmd": "process", "comp": "refund"},
    {"svc": "inventory", "cmd": "reserve", "comp": "release"},
]
for step in STEPS:
    produce(f"{step['svc']}.commands.v1", {"saga_id": id, "command": step["cmd"]})
    result = await wait_reply(id, step["svc"])
    if result["status"] == "failed":
        for done in reversed(completed):
            produce(f"{done['svc']}.commands.v1", {"command": done["comp"]})
        break
    completed.append(step)
```

## Transactional Outbox

```sql
-- Atomic: write to DB + outbox in same transaction
INSERT INTO orders (id, ...) VALUES (...);
INSERT INTO outbox (aggregate_type, aggregate_id, event_type, payload) VALUES (...);
-- Debezium CDC watches outbox table → auto-publishes to Kafka
```

## Dead Letter Queue

```python
MAX_RETRIES = 3
try: process(msg); consumer.commit(message=msg)
except RetriableError:
    retries = int(dict(msg.headers() or []).get("retry-count", b"0"))
    if retries < MAX_RETRIES:
        producer.produce(f"_retry.{msg.topic()}", key=msg.key(), value=msg.value(),
            headers=[("retry-count", str(retries+1).encode())])
    else:
        producer.produce(f"_dlq.{msg.topic()}", key=msg.key(), value=msg.value())
    consumer.commit(message=msg)
```

## AI Agent Event Backbone

```
agents.task.submitted.v1   → new task (each agent type = consumer group)
agents.task.completed.v1   → results
agents.task.failed.v1      → retry/escalate
agents.audit.trail.v1      → compacted log of all actions
```
