#!/usr/bin/env python3
"""
Production Kafka Producer/Consumer — confluent-kafka
Replace {{PLACEHOLDERS}} with your values.

Dependencies: pip install confluent-kafka
"""

import json
import os
import signal
import sys
from confluent_kafka import Producer, Consumer, KafkaError

# ── Configuration ────────────────────────────────────────────────────────────

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC = "{{TOPIC_NAME}}"  # e.g., orders.order.created.v1

PRODUCER_CONFIG = {
    "bootstrap.servers": BOOTSTRAP,
    "acks": "all",
    "enable.idempotence": True,
    "max.in.flight.requests.per.connection": 5,
    "retries": 2147483647,
    "delivery.timeout.ms": 120000,
    "batch.size": 65536,
    "linger.ms": 5,
    "compression.type": "lz4",
    "client.id": "{{SERVICE_NAME}}-producer",
    # Uncomment for SASL/TLS (Tier 2+)
    # "security.protocol": "SASL_SSL",
    # "sasl.mechanism": "SCRAM-SHA-512",
    # "sasl.username": os.environ["KAFKA_USER"],
    # "sasl.password": os.environ["KAFKA_PASS"],
}

CONSUMER_CONFIG = {
    "bootstrap.servers": BOOTSTRAP,
    "group.id": "{{GROUP_ID}}",  # e.g., order-processor-group
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
    "max.poll.interval.ms": 300000,
    "session.timeout.ms": 45000,
    "heartbeat.interval.ms": 15000,
    "partition.assignment.strategy": "cooperative-sticky",
    "isolation.level": "read_committed",
    "client.id": "{{SERVICE_NAME}}-consumer",
}

# ── Producer ─────────────────────────────────────────────────────────────────

def create_producer() -> Producer:
    return Producer(PRODUCER_CONFIG)

def delivery_callback(err, msg):
    if err:
        print(f"DELIVERY FAILED: {err} | topic={msg.topic()} partition={msg.partition()}")
    else:
        print(f"DELIVERED: {msg.topic()}[{msg.partition()}]@{msg.offset()}")

def produce_event(producer: Producer, key: str, value: dict):
    producer.produce(
        topic=TOPIC,
        key=key.encode("utf-8"),
        value=json.dumps(value).encode("utf-8"),
        callback=delivery_callback,
    )
    producer.poll(0)

# ── Consumer ─────────────────────────────────────────────────────────────────

running = True

def shutdown(sig, frame):
    global running
    running = False
    print("\nShutting down consumer...")

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

def process_message(msg) -> bool:
    """Process a single message. Return True on success."""
    try:
        key = msg.key().decode("utf-8") if msg.key() else None
        value = json.loads(msg.value().decode("utf-8"))
        print(f"Processing: key={key} value={value}")
        # {{BUSINESS_LOGIC}}
        return True
    except Exception as e:
        print(f"Processing error: {e}")
        return False

def run_consumer():
    consumer = Consumer(CONSUMER_CONFIG)
    consumer.subscribe([TOPIC])
    dlq_producer = Producer(PRODUCER_CONFIG)

    try:
        while running:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    print(f"Consumer error: {msg.error()}")
                continue

            if process_message(msg):
                consumer.commit(message=msg)
            else:
                # Send to DLQ
                dlq_producer.produce(
                    topic=f"_dlq.{TOPIC}",
                    key=msg.key(),
                    value=msg.value(),
                    headers=[("error", b"processing_failed"), ("original-topic", TOPIC.encode())],
                )
                dlq_producer.poll(0)
                consumer.commit(message=msg)
    finally:
        consumer.close()
        dlq_producer.flush(timeout=10)
        print("Consumer closed.")

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "produce":
        p = create_producer()
        produce_event(p, "key-1", {"event": "test", "data": "hello"})
        p.flush(timeout=30)
    else:
        run_consumer()
