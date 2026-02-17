#!/usr/bin/env python3
"""
Apache Kafka — Project Scaffolder

Generates a complete Kafka project based on tier, language, and options.

Usage:
    python scaffold_kafka.py <name> --tier <1|2|3|4> --lang <python|java|node|go>
        --path <output-dir> [--security <none|sasl|mtls>]
        [--monitoring] [--connect] [--schema-registry] [--streams]

Examples:
    python scaffold_kafka.py myapp --tier 1 --lang python --path ./myapp
    python scaffold_kafka.py orders --tier 2 --lang python --path ./orders --security sasl --monitoring
    python scaffold_kafka.py platform --tier 3 --lang java --path ./platform --connect --schema-registry --streams
    python scaffold_kafka.py global --tier 4 --lang python --path ./global --security mtls --monitoring --connect
"""

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path

# ── Docker Compose Templates ────────────────────────────────────────────────

COMPOSE_TIER1 = textwrap.dedent("""\
    # Kafka Dev Stack — Tier 1 (Single Broker, KRaft)
    services:
      kafka:
        image: apache/kafka:3.9.0
        ports: ["9092:9092", "9093:9093"]
        environment:
          KAFKA_NODE_ID: 1
          KAFKA_PROCESS_ROLES: broker,controller
          KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
          KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
          KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
          KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
          KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
          KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
          KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
          KAFKA_NUM_PARTITIONS: 6
          KAFKA_AUTO_CREATE_TOPICS_ENABLE: "false"
          CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk
        volumes: ["kafka-data:/var/lib/kafka/data"]
        healthcheck:
          test: ["CMD-SHELL", "kafka-broker-api-versions.sh --bootstrap-server localhost:9092 || exit 1"]
          interval: 10s
          timeout: 5s
          retries: 5

      kafka-ui:
        image: provectuslabs/kafka-ui:latest
        ports: ["8080:8080"]
        depends_on:
          kafka:
            condition: service_healthy
        environment:
          KAFKA_CLUSTERS_0_NAME: local
          KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9092

    volumes:
      kafka-data:
""")

COMPOSE_MONITORING = textwrap.dedent("""\

      prometheus:
        image: prom/prometheus:v2.53.0
        ports: ["9090:9090"]
        volumes: ["./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml"]

      grafana:
        image: grafana/grafana:11.1.0
        ports: ["3000:3000"]
        environment:
          GF_SECURITY_ADMIN_PASSWORD: admin
""")

COMPOSE_SCHEMA_REGISTRY = textwrap.dedent("""\

      schema-registry:
        image: confluentinc/cp-schema-registry:7.7.0
        depends_on:
          kafka:
            condition: service_healthy
        ports: ["8081:8081"]
        environment:
          SCHEMA_REGISTRY_HOST_NAME: schema-registry
          SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS: kafka:9092
""")

# ── Python Templates ────────────────────────────────────────────────────────

PYTHON_PRODUCER = textwrap.dedent("""\
    #!/usr/bin/env python3
    \"\"\"Production Kafka Producer for {name}.\"\"\"
    import json, os
    from confluent_kafka import Producer, KafkaError

    config = {{
        "bootstrap.servers": os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092"),
        "acks": "all",
        "enable.idempotence": True,
        "batch.size": 65536,
        "linger.ms": 5,
        "compression.type": "lz4",
        "client.id": "{name}-producer",
    }}

    producer = Producer(config)

    def delivery_cb(err, msg):
        if err:
            print(f"FAILED: {{err}}")
        else:
            print(f"OK: {{msg.topic()}}[{{msg.partition()}}]@{{msg.offset()}}")

    def produce(topic: str, key: str, value: dict):
        producer.produce(topic, key=key.encode(), value=json.dumps(value).encode(), callback=delivery_cb)
        producer.poll(0)

    if __name__ == "__main__":
        produce("{name}.events.v1", "test-key", {{"event": "test", "source": "{name}"}})
        producer.flush(30)
""")

PYTHON_CONSUMER = textwrap.dedent("""\
    #!/usr/bin/env python3
    \"\"\"Production Kafka Consumer for {name}.\"\"\"
    import json, os, signal
    from confluent_kafka import Consumer, KafkaError

    config = {{
        "bootstrap.servers": os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092"),
        "group.id": "{name}-group",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "session.timeout.ms": 45000,
        "partition.assignment.strategy": "cooperative-sticky",
        "isolation.level": "read_committed",
    }}

    running = True
    def _shutdown(sig, frame):
        global running
        running = False
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    def process(msg) -> bool:
        try:
            value = json.loads(msg.value().decode())
            print(f"Processing: {{value}}")
            return True
        except Exception as e:
            print(f"Error: {{e}}")
            return False

    if __name__ == "__main__":
        consumer = Consumer(config)
        consumer.subscribe(["{name}.events.v1"])
        try:
            while running:
                msg = consumer.poll(1.0)
                if msg is None: continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        print(f"Error: {{msg.error()}}")
                    continue
                if process(msg):
                    consumer.commit(message=msg)
        finally:
            consumer.close()
""")

PYTHON_REQUIREMENTS = textwrap.dedent("""\
    confluent-kafka>=2.6.0
    python-dotenv>=1.0.0
""")

# ── Topic Creation Script ───────────────────────────────────────────────────

TOPIC_SCRIPT = textwrap.dedent("""\
    #!/bin/bash
    # Create topics for {name}
    BOOTSTRAP="${{KAFKA_BOOTSTRAP:-localhost:9092}}"
    RF={rf}

    topics=(
        "{name}.events.v1"
        "_dlq.{name}.events.v1"
    )

    for topic in "${{topics[@]}}"; do
        echo "Creating topic: $topic"
        kafka-topics.sh --bootstrap-server "$BOOTSTRAP" --create \\
            --topic "$topic" --partitions {partitions} --replication-factor $RF \\
            --config min.insync.replicas={isr} \\
            --config retention.ms=604800000 \\
            --config compression.type=lz4 \\
            --if-not-exists
    done
    echo "Done."
""")

# ── Prometheus Config ────────────────────────────────────────────────────────

PROMETHEUS_YML = textwrap.dedent("""\
    global:
      scrape_interval: 15s
    scrape_configs:
      - job_name: kafka-exporter
        static_configs:
          - targets: ['kafka-exporter:9308']
""")

# ── .env Template ────────────────────────────────────────────────────────────

ENV_TEMPLATE = textwrap.dedent("""\
    KAFKA_BOOTSTRAP=localhost:9092
    # KAFKA_USER=
    # KAFKA_PASS=
    # SCHEMA_REGISTRY_URL=http://localhost:8081
""")


def scaffold(args):
    base = Path(args.path)
    name = args.name
    tier = args.tier

    # Tier-based defaults
    rf = 1 if tier == 1 else 3
    partitions = 6 if tier <= 2 else 12
    isr = 1 if tier == 1 else 2

    # Create directories
    dirs = [base / "src", base / "scripts"]
    if args.monitoring:
        dirs.append(base / "monitoring")
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Docker Compose
    compose = COMPOSE_TIER1
    if args.schema_registry or tier >= 3:
        compose += COMPOSE_SCHEMA_REGISTRY
    if args.monitoring or tier >= 2:
        compose += COMPOSE_MONITORING
    (base / "docker-compose.yml").write_text(compose)

    # Source files (language-specific)
    if args.lang == "python":
        (base / "src" / "producer.py").write_text(PYTHON_PRODUCER.format(name=name))
        (base / "src" / "consumer.py").write_text(PYTHON_CONSUMER.format(name=name))
        (base / "requirements.txt").write_text(PYTHON_REQUIREMENTS)
    else:
        print(f"WARNING: '{args.lang}' source templates not yet implemented. "
              f"Only docker-compose and topic scripts generated. Use --lang python for full scaffolding.",
              file=sys.stderr)

    # Security configuration
    if args.security == "sasl":
        sec_dir = base / "config" / "security"
        sec_dir.mkdir(parents=True, exist_ok=True)
        (sec_dir / "sasl_jaas.conf").write_text(textwrap.dedent("""\
            KafkaServer {
                org.apache.kafka.common.security.scram.ScramLoginModule required
                username="admin"
                password="${KAFKA_ADMIN_PASSWORD}";
            };
        """))
        (sec_dir / "client.properties").write_text(textwrap.dedent("""\
            security.protocol=SASL_SSL
            sasl.mechanism=SCRAM-SHA-512
            sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required \\
                username="${KAFKA_USER}" \\
                password="${KAFKA_PASS}";
        """))
    elif args.security == "mtls":
        sec_dir = base / "config" / "security"
        sec_dir.mkdir(parents=True, exist_ok=True)
        (sec_dir / "generate-certs.sh").write_text(textwrap.dedent("""\
            #!/bin/bash
            # Generate TLS certificates for mTLS Kafka
            PASS="${CERT_PASSWORD:-changeit}"
            # CA
            openssl req -new -x509 -keyout ca-key -out ca-cert -days 365 -subj "/CN=KafkaCA" -passout pass:$PASS
            # Broker keystore
            keytool -keystore broker.keystore.p12 -storetype PKCS12 -alias broker -genkey -keyalg RSA \\
                -storepass $PASS -keypass $PASS -dname "CN=kafka-broker"
            # Sign broker cert
            keytool -keystore broker.keystore.p12 -alias broker -certreq -file broker-csr -storepass $PASS
            openssl x509 -req -CA ca-cert -CAkey ca-key -in broker-csr -out broker-signed -days 365 -passin pass:$PASS
            # Import CA + signed cert
            keytool -keystore broker.keystore.p12 -alias CARoot -importcert -file ca-cert -storepass $PASS -noprompt
            keytool -keystore broker.keystore.p12 -alias broker -importcert -file broker-signed -storepass $PASS
            # Truststore
            keytool -keystore truststore.p12 -storetype PKCS12 -alias CARoot -importcert -file ca-cert -storepass $PASS -noprompt
            echo "Certs generated. Configure ssl.keystore/truststore in server.properties."
        """))
        os.chmod(sec_dir / "generate-certs.sh", 0o755)
        (sec_dir / "client.properties").write_text(textwrap.dedent("""\
            security.protocol=SSL
            ssl.keystore.location=./client.keystore.p12
            ssl.keystore.type=PKCS12
            ssl.keystore.password=${CERT_PASSWORD}
            ssl.truststore.location=./truststore.p12
            ssl.truststore.type=PKCS12
            ssl.truststore.password=${CERT_PASSWORD}
        """))

    # Connect configuration
    if args.connect:
        connect_dir = base / "config" / "connect"
        connect_dir.mkdir(parents=True, exist_ok=True)
        (connect_dir / "connect-distributed.properties").write_text(textwrap.dedent(f"""\
            bootstrap.servers=localhost:9092
            group.id={name}-connect
            key.converter=io.confluent.connect.avro.AvroConverter
            key.converter.schema.registry.url=http://schema-registry:8081
            value.converter=io.confluent.connect.avro.AvroConverter
            value.converter.schema.registry.url=http://schema-registry:8081
            offset.storage.topic={name}-connect-offsets
            offset.storage.replication.factor={rf}
            config.storage.topic={name}-connect-configs
            config.storage.replication.factor={rf}
            status.storage.topic={name}-connect-status
            status.storage.replication.factor={rf}
        """))
        (connect_dir / "debezium-postgres.json").write_text(json.dumps({
            "name": f"{name}-cdc-postgres",
            "config": {
                "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
                "database.hostname": "postgres", "database.port": "5432",
                "database.user": "debezium", "database.password": "${env:DB_PASSWORD}",
                "database.dbname": f"{name}_db", "topic.prefix": "cdc",
                "plugin.name": "pgoutput",
            }
        }, indent=2))

    # Streams app skeleton
    if args.streams:
        streams_dir = base / "streams"
        streams_dir.mkdir(parents=True, exist_ok=True)
        (streams_dir / "streams.properties").write_text(textwrap.dedent(f"""\
            application.id={name}-streams
            bootstrap.servers=localhost:9092
            processing.guarantee=exactly_once_v2
            num.stream.threads=4
            default.key.serde=org.apache.kafka.common.serialization.Serdes$StringSerde
            default.value.serde=org.apache.kafka.common.serialization.Serdes$StringSerde
        """))

    # Topic creation script
    (base / "scripts" / "create-topics.sh").write_text(
        TOPIC_SCRIPT.format(name=name, rf=rf, partitions=partitions, isr=isr)
    )
    os.chmod(base / "scripts" / "create-topics.sh", 0o755)

    # Monitoring
    if args.monitoring or tier >= 2:
        (base / "monitoring").mkdir(parents=True, exist_ok=True)
        (base / "monitoring" / "prometheus.yml").write_text(PROMETHEUS_YML)

    # .env
    (base / ".env").write_text(ENV_TEMPLATE)
    (base / ".gitignore").write_text(".env\nnode_modules/\n__pycache__/\n*.pyc\n")

    print(f"""
=== {name} — Kafka Tier {tier} Project ===

Created at: {base.resolve()}

Structure:
  docker-compose.yml    Kafka cluster + services
  src/producer.py       Production producer
  src/consumer.py       Production consumer
  scripts/create-topics.sh  Topic creation
  .env                  Environment config
  {"monitoring/          Prometheus config" if args.monitoring or tier >= 2 else ""}

Quick Start:
  cd {base}
  docker compose up -d
  pip install -r requirements.txt
  bash scripts/create-topics.sh
  python src/producer.py
  python src/consumer.py
""")


def main():
    parser = argparse.ArgumentParser(description="Apache Kafka Project Scaffolder")
    parser.add_argument("name", help="Project name")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], required=True)
    parser.add_argument("--lang", choices=["python", "java", "node", "go"], default="python")
    parser.add_argument("--path", required=True, help="Output directory")
    parser.add_argument("--security", choices=["none", "sasl", "mtls"], default="none")
    parser.add_argument("--monitoring", action="store_true")
    parser.add_argument("--connect", action="store_true")
    parser.add_argument("--schema-registry", action="store_true")
    parser.add_argument("--streams", action="store_true")
    args = parser.parse_args()
    scaffold(args)


if __name__ == "__main__":
    main()
