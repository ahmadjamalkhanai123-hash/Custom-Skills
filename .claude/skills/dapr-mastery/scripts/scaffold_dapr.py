#!/usr/bin/env python3
"""
scaffold_dapr.py — Dapr Project Scaffolder
==========================================
Generates production-ready Dapr project structure for any tier.

Usage:
    python scaffold_dapr.py --name myapp --tier 2 --lang python --actors --workflows
    python scaffold_dapr.py --name ecommerce --tier 3 --lang dotnet --actors --workflows --pubsub kafka
    python scaffold_dapr.py --name platform --tier 4 --lang python --all

Options:
    --name        Project name (required)
    --tier        1=Dev, 2=Production, 3=Microservices, 4=Enterprise (default: 2)
    --lang        python | dotnet | java | go (default: python)
    --actors      Include Actor service
    --workflows   Include Workflow service
    --pubsub      Pub/Sub broker: redis | kafka | rabbitmq | servicebus (default: redis)
    --state       State store: redis | postgres | cosmos | dynamodb (default: redis)
    --secrets     Secret store: kubernetes | vault | azurekeyvault (default: kubernetes)
    --tracing     Tracing backend: zipkin | jaeger | otel (default: otel)
    --cloud       Cloud provider: aws | azure | gcp | local (default: local)
    --all         Include all features (actors, workflows, full observability)
    --out         Output directory (default: ./dapr-<name>)
"""

import argparse
import os
import sys
from pathlib import Path
from textwrap import dedent


# ── Color Output ──────────────────────────────────────────────────────────────

GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def info(msg): print(f"{BLUE}[INFO]{RESET} {msg}")
def success(msg): print(f"{GREEN}[OK]{RESET} {msg}")
def warn(msg): print(f"{YELLOW}[WARN]{RESET} {msg}")
def error(msg): print(f"{RED}[ERROR]{RESET} {msg}", file=sys.stderr)


# ── File Writer ────────────────────────────────────────────────────────────────

def write_file(base: Path, relative: str, content: str, overwrite: bool = False):
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        warn(f"  Skipping (exists): {relative}")
        return
    path.write_text(dedent(content).lstrip())
    success(f"  Created: {relative}")


# ── Component YAML Generators ──────────────────────────────────────────────────

def state_store_yaml(store: str, namespace: str, scopes: list[str]) -> str:
    scope_str = "\n".join(f"  - {s}" for s in scopes)
    if store == "redis":
        return f"""
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: statestore
  namespace: {namespace}
spec:
  type: state.redis
  version: v1
  metadata:
    - name: redisHost
      secretKeyRef: {{name: redis-secret, key: host}}
    - name: redisPassword
      secretKeyRef: {{name: redis-secret, key: password}}
    - name: enableTLS
      value: "true"
    - name: ttlInSeconds
      value: "86400"
scopes:
{scope_str}
"""
    elif store == "postgres":
        return f"""
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: statestore
  namespace: {namespace}
spec:
  type: state.postgresql/v2
  version: v1
  metadata:
    - name: connectionString
      secretKeyRef: {{name: pg-secret, key: connectionString}}
    - name: tablePrefix
      value: "{namespace}_"
scopes:
{scope_str}
"""
    elif store == "cosmos":
        return f"""
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: statestore
  namespace: {namespace}
spec:
  type: state.azure.cosmosdb
  version: v1
  metadata:
    - name: url
      secretKeyRef: {{name: cosmos-secret, key: url}}
    - name: masterKey
      secretKeyRef: {{name: cosmos-secret, key: key}}
    - name: database
      value: "daprDB"
    - name: collection
      value: "daprState"
    - name: partitionKey
      value: "partitionKey"
scopes:
{scope_str}
"""
    return ""


def pubsub_yaml(broker: str, namespace: str, scopes: list[str]) -> str:
    scope_str = "\n".join(f"  - {s}" for s in scopes)
    if broker == "redis":
        return f"""
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: pubsub
  namespace: {namespace}
spec:
  type: pubsub.redis
  version: v1
  metadata:
    - name: redisHost
      secretKeyRef: {{name: redis-secret, key: host}}
    - name: redisPassword
      secretKeyRef: {{name: redis-secret, key: password}}
scopes:
{scope_str}
"""
    elif broker == "kafka":
        return f"""
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: pubsub
  namespace: {namespace}
spec:
  type: pubsub.kafka
  version: v1
  metadata:
    - name: brokers
      secretKeyRef: {{name: kafka-secret, key: brokers}}
    - name: consumerGroup
      value: "{namespace}-consumer-group"
    - name: authType
      value: "none"    # Change to "certificate" in production
    - name: initialOffset
      value: "newest"
scopes:
{scope_str}
"""
    return ""


def secret_store_yaml(store: str, namespace: str) -> str:
    if store == "kubernetes":
        return f"""
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: secretstore
  namespace: {namespace}
spec:
  type: secretstores.kubernetes
  version: v1
"""
    elif store == "vault":
        return f"""
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: secretstore
  namespace: {namespace}
spec:
  type: secretstores.hashicorp.vault
  version: v1
  metadata:
    - name: vaultAddr
      value: "https://vault.internal:8200"
    - name: vaultTokenMountPath
      value: "/var/run/secrets/vault/token"
    - name: enginePath
      value: "secret"
    - name: vaultKVVersion
      value: "v2"
"""
    return ""


def dapr_config_yaml(namespace: str, has_actors: bool, tier: int) -> str:
    sampling = "1" if tier <= 1 else "0.01"
    actor_section = ""
    if has_actors:
        actor_section = """
  entities:
    - "$(APP_NAME)Actor"
  actorIdleTimeout: 1h
  actorScanInterval: 30s
  drainOngoingCallTimeout: 60s
  drainRebalancedActors: true
  reentrancy:
    enabled: true
    maxStackDepth: 32
  remindersStoragePartitions: 7"""

    return f"""
apiVersion: dapr.io/v1alpha1
kind: Configuration
metadata:
  name: app-config
  namespace: {namespace}
spec:
  tracing:
    samplingRate: "{sampling}"
    otel:
      endpointAddress: "otel-collector.observability:4317"
      isSecure: false
      protocol: grpc
  metric:
    enabled: true
  accessControl:
    defaultAction: {"allow" if tier <= 1 else "deny"}
    trustDomain: "cluster.local"{actor_section}
  features:
    - name: SchedulerReminders
      enabled: true
"""


def resiliency_yaml(namespace: str) -> str:
    return f"""
apiVersion: dapr.io/v1alpha1
kind: Resiliency
metadata:
  name: app-resiliency
  namespace: {namespace}
spec:
  policies:
    retries:
      default-retry:
        policy: exponential
        initialInterval: 500ms
        randomizationFactor: 0.5
        multiplier: 1.5
        maxInterval: 30s
        maxRetries: 3
    timeouts:
      standard: {{duration: 10s}}
      fast: {{duration: 3s}}
    circuitBreakers:
      standard-cb:
        maxRequests: 1
        interval: 10s
        timeout: 60s
        trip: consecutiveFailures > 5
  targets:
    components:
      statestore:
        outbound:
          timeout: standard
          retry: default-retry
          circuitBreaker: standard-cb
      pubsub:
        outbound:
          timeout: standard
          retry: default-retry
"""


def k8s_deployment_yaml(app_name: str, namespace: str, port: int,
                          has_actors: bool = False) -> str:
    config_name = "actor-config" if has_actors else "app-config"
    memory_limit = "512Mi" if has_actors else "256Mi"
    cpu_limit = "500m" if has_actors else "300m"
    return f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
  namespace: {namespace}
  labels:
    app: {app_name}
spec:
  replicas: 3
  selector:
    matchLabels:
      app: {app_name}
  template:
    metadata:
      labels:
        app: {app_name}
      annotations:
        dapr.io/enabled: "true"
        dapr.io/app-id: "{app_name}"
        dapr.io/app-port: "{port}"
        dapr.io/sidecar-cpu-request: "100m"
        dapr.io/sidecar-cpu-limit: "{cpu_limit}"
        dapr.io/sidecar-memory-request: "128Mi"
        dapr.io/sidecar-memory-limit: "{memory_limit}"
        dapr.io/env: "GOMEMLIMIT={int(int(memory_limit[:-2])*0.9)}MiB"
        dapr.io/enable-metrics: "true"
        dapr.io/enable-api-logging: "true"
        dapr.io/log-level: "warn"
        dapr.io/config: "{config_name}"
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: {app_name}
          image: myregistry/{app_name}:latest
          ports:
            - containerPort: {port}
          resources:
            requests: {{cpu: "200m", memory: "256Mi"}}
            limits: {{cpu: "1000m", memory: "512Mi"}}
          livenessProbe:
            httpGet: {{path: /healthz, port: {port}}}
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet: {{path: /healthz/ready, port: {port}}}
            initialDelaySeconds: 5
            periodSeconds: 10
"""


def helm_values_yaml() -> str:
    return """
# Dapr Helm Values — Production
# helm upgrade --install dapr dapr/dapr -n dapr-system --values helm-values.yaml

global:
  logLevel: warn
  logAsJson: true
  prometheus:
    enabled: true
    port: 9090
  mtls:
    enabled: true
    workloadCertTTL: 24h
    allowedClockSkew: 15m

dapr_operator:
  replicaCount: 3
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
  resources:
    requests: {cpu: "100m", memory: "128Mi"}
    limits: {cpu: "500m", memory: "512Mi"}

dapr_sidecar_injector:
  replicaCount: 3
  podDisruptionBudget:
    enabled: true
    minAvailable: 2

dapr_placement:
  replicaCount: 3
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
  resources:
    requests: {cpu: "250m", memory: "256Mi"}
    limits: {cpu: "500m", memory: "512Mi"}

dapr_sentry:
  replicaCount: 3
  resources:
    requests: {cpu: "100m", memory: "128Mi"}
    limits: {cpu: "300m", memory: "256Mi"}

dapr_scheduler:
  replicaCount: 3
  resources:
    requests: {cpu: "100m", memory: "256Mi"}
    limits: {cpu: "500m", memory: "1Gi"}
"""


def docker_compose_yaml(has_redis: bool, has_kafka: bool, has_zipkin: bool) -> str:
    services = {"version": "3.9", "services": {}}
    content = "version: '3.9'\nservices:\n"

    if has_redis:
        content += """
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --requirepass devpassword
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "devpassword", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
"""

    if has_kafka:
        content += """
  kafka:
    image: confluentinc/cp-kafka:7.6.0
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    depends_on: [zookeeper]

  zookeeper:
    image: confluentinc/cp-zookeeper:7.6.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
"""

    if has_zipkin:
        content += """
  zipkin:
    image: openzipkin/zipkin:latest
    ports:
      - "9411:9411"
"""

    return content


def python_main_app(app_name: str) -> str:
    return f'''"""
{app_name} — Dapr-integrated FastAPI Service
"""
from fastapi import FastAPI, HTTPException
from dapr.clients import DaprClient
from pydantic import BaseModel
import logging
import json

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = FastAPI(title="{app_name}")


class OrderRequest(BaseModel):
    customer_id: str
    items: list[dict]
    total: float


@app.get("/healthz")
async def health():
    return {{"status": "ok"}}


@app.get("/healthz/ready")
async def ready():
    return {{"status": "ready"}}


@app.post("/orders")
async def create_order(request: OrderRequest):
    """Create order — save state and publish event."""
    with DaprClient() as d:
        order_id = f"order-{{request.customer_id}}-001"

        # Save state
        d.save_state(
            store_name="statestore",
            key=order_id,
            value=json.dumps(request.dict()),
            state_metadata={{"contentType": "application/json"}}
        )

        # Publish event
        d.publish_event(
            pubsub_name="pubsub",
            topic_name="orders.created",
            data=json.dumps({{"orderId": order_id, **request.dict()}}),
            data_content_type="application/json"
        )

    return {{"orderId": order_id, "status": "created"}}


@app.get("/orders/{{order_id}}")
async def get_order(order_id: str):
    """Get order from state store."""
    with DaprClient() as d:
        state = d.get_state(store_name="statestore", key=order_id)
        if not state.data:
            raise HTTPException(status_code=404, detail="Order not found")
        return json.loads(state.data)


@app.post("/events/orders-subscriber")
async def handle_order_event(event: dict):
    """Handle orders.created pub/sub events."""
    logger.info(f"Received order event: {{event.get('orderId')}}")
    # Process event...
    return {{"status": "SUCCESS"}}
'''


# ── Main Scaffold Logic ────────────────────────────────────────────────────────

def scaffold(args):
    name = args.name.lower().replace(" ", "-")
    tier = args.tier
    lang = args.lang
    namespace = name
    out = Path(args.out or f"dapr-{name}")

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Dapr Project Scaffolder — {name.upper()}{RESET}")
    print(f"  Tier: {tier} | Lang: {lang} | Dir: {out}")
    print(f"{BOLD}{'='*60}{RESET}\n")

    services = ["api-service"]
    if args.actors or args.all:
        services.append("actor-service")
    if args.workflows or args.all:
        services.append("workflow-service")

    # ── Directory Structure ────────────────────────────────────────────────────
    info("Creating project structure...")

    # Components
    write_file(out, "components/statestore.yaml",
               state_store_yaml(args.state, namespace, services))
    write_file(out, "components/pubsub.yaml",
               pubsub_yaml(args.pubsub, namespace, services))
    write_file(out, "components/secretstore.yaml",
               secret_store_yaml(args.secrets, namespace))
    write_file(out, "components/dapr-config.yaml",
               dapr_config_yaml(namespace, has_actors=(args.actors or args.all), tier=tier))

    if tier >= 2:
        write_file(out, "components/resiliency.yaml", resiliency_yaml(namespace))

    # Multi-app run (Tier 1 only)
    if tier == 1:
        write_file(out, "docker-compose.yml",
                   docker_compose_yaml(
                       has_redis=(args.state == "redis" or args.pubsub == "redis"),
                       has_kafka=(args.pubsub == "kafka"),
                       has_zipkin=True
                   ))
        dapr_yaml_content = "version: 1\napps:\n"
        port = 8001
        for svc in services:
            dapr_yaml_content += f"""  - appID: {svc}\n    appDirPath: ./services/{svc}\n    appPort: {port}\n    command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}"]\n    daprHTTPPort: {3500 + (port - 8000)}\n    resourcesPath: ../../components\n    configFilePath: ../../components/dapr-config.yaml\n\n"""
            port += 1
        write_file(out, "dapr.yaml", dapr_yaml_content)

    # Kubernetes manifests (Tier 2+)
    if tier >= 2:
        port = 8001
        for svc in services:
            is_actor = "actor" in svc
            write_file(out, f"k8s/{svc}/deployment.yaml",
                       k8s_deployment_yaml(svc, namespace, port, is_actor))
            write_file(out, f"k8s/{svc}/service.yaml", f"""
apiVersion: v1
kind: Service
metadata:
  name: {svc}
  namespace: {namespace}
spec:
  selector:
    app: {svc}
  ports:
    - port: 80
      targetPort: {port}
""")
            port += 1

        write_file(out, "k8s/namespace.yaml", f"""
apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    dapr-enabled: "true"
""")

    # Helm (Tier 2+)
    if tier >= 2:
        write_file(out, "helm/dapr-values.yaml", helm_values_yaml())

    # Application Code
    if lang == "python":
        write_file(out, "services/api-service/main.py", python_main_app("api-service"))
        write_file(out, "services/api-service/requirements.txt",
                   "dapr\ndapr-ext-fastapi\nfastapi\nuvicorn[standard]\npydantic\n")

        if args.actors or args.all:
            # Copy actor template reference
            write_file(out, "services/actor-service/requirements.txt",
                       "dapr\ndapr-ext-fastapi\nfastapi\nuvicorn[standard]\n")
            write_file(out, "services/actor-service/README.md",
                       "# Actor Service\n\nSee `.claude/skills/dapr-mastery/assets/actor_service_python.py` for template.\n")

        if args.workflows or args.all:
            write_file(out, "services/workflow-service/requirements.txt",
                       "dapr\ndapr-ext-workflow\nfastapi\nuvicorn[standard]\n")
            write_file(out, "services/workflow-service/README.md",
                       "# Workflow Service\n\nSee `.claude/skills/dapr-mastery/assets/workflow_saga_python.py` for template.\n")

    # Observability (Tier 3+)
    if tier >= 3 or args.all:
        write_file(out, "observability/prometheus-rules.yaml", """
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: dapr-alerts
  namespace: monitoring
spec:
  groups:
    - name: dapr.rules
      rules:
        - alert: DaprHighErrorRate
          expr: rate(dapr_http_server_response_count{status_code=~"5.."}[5m]) > 0.05
          for: 5m
          labels:
            severity: critical
""")

    # Makefile
    write_file(out, "Makefile", f"""
.PHONY: dev install-dapr validate deploy-k8s

install-dapr:
\tdapr init --runtime-version 1.15.0
\t@echo "Dapr initialized"

dev:
\tdapr run -f dapr.yaml

validate:
\tdapr components -k -n {namespace}
\tdapr status -k

deploy-k8s:
\tkubectl apply -f k8s/namespace.yaml
\tkubectl apply -f components/ -n {namespace}
\tkubectl apply -f k8s/ -n {namespace} --recursive

deploy-dapr-control-plane:
\thelm upgrade --install dapr dapr/dapr \\
\t\t--namespace dapr-system --create-namespace \\
\t\t--version 1.15.x \\
\t\t--values helm/dapr-values.yaml \\
\t\t--wait
""")

    # Summary
    file_count = sum(1 for _ in out.rglob("*") if _.is_file())
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{GREEN}{BOLD}  Project scaffolded successfully!{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    print(f"  Location : {out.absolute()}")
    print(f"  Files    : {file_count}")
    print(f"  Services : {', '.join(services)}")
    print(f"\n{BOLD}  Next Steps:{RESET}")
    print(f"    1. cd {out}")
    if tier == 1:
        print(f"    2. docker-compose up -d")
        print(f"    3. dapr run -f dapr.yaml")
    else:
        print(f"    2. make deploy-dapr-control-plane")
        print(f"    3. make deploy-k8s")
        print(f"    4. kubectl get pods -n {namespace}")
    print(f"\n  References: .claude/skills/dapr-mastery/references/")
    print(f"  Templates : .claude/skills/dapr-mastery/assets/\n")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scaffold a production-ready Dapr project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--name", required=True, help="Project name")
    parser.add_argument("--tier", type=int, default=2, choices=[1, 2, 3, 4])
    parser.add_argument("--lang", default="python",
                        choices=["python", "dotnet", "java", "go"])
    parser.add_argument("--actors", action="store_true")
    parser.add_argument("--workflows", action="store_true")
    parser.add_argument("--pubsub", default="redis",
                        choices=["redis", "kafka", "rabbitmq", "servicebus"])
    parser.add_argument("--state", default="redis",
                        choices=["redis", "postgres", "cosmos", "dynamodb"])
    parser.add_argument("--secrets", default="kubernetes",
                        choices=["kubernetes", "vault", "azurekeyvault"])
    parser.add_argument("--tracing", default="otel",
                        choices=["otel", "zipkin", "jaeger"])
    parser.add_argument("--cloud", default="local",
                        choices=["aws", "azure", "gcp", "local"])
    parser.add_argument("--all", action="store_true", help="Include all features")
    parser.add_argument("--out", default=None, help="Output directory")

    args = parser.parse_args()
    scaffold(args)
