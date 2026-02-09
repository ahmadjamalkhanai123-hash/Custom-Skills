# Observability

Production Docker workloads require structured logging, metrics, health checks,
tracing, and alerting. All patterns below are container-native with current tool versions.

---

## Logging

Containers must log to **stdout/stderr** in structured JSON. Never write log files
inside the container -- let the Docker logging driver handle persistence.

**Python (structlog):** `structlog.configure(processors=[TimeStamper(fmt="iso"), add_log_level, JSONRenderer()])`
**Node.js (pino):** `const log = pino({ level: "info", timestamp: pino.stdTimeFunctions.isoTime })`
**Go (zerolog):** `log.Info().Str("method","GET").Int("status",200).Msg("request_handled")`

Log format standard: every line must include `timestamp`, `level`, `msg`, `service`,
`trace_id` (when tracing enabled). Use lowercase_snake_case field names across languages.

```yaml
# Docker logging drivers
services:
  app:
    logging:
      driver: json-file                          # Default -- good for single-host
      options: { max-size: "50m", max-file: "5", tag: "{{.Name}}/{{.ID}}" }
    # Alt: Loki driver (install: docker plugin install grafana/loki-docker-driver:3.4.2)
    # logging:
    #   driver: loki
    #   options:
    #     loki-url: "http://loki:3100/loki/api/v1/push"
    #     loki-labels: "service={{.Name}},env=production"
    # Alt: Fluentd driver
    # logging:
    #   driver: fluentd
    #   options: { fluentd-address: "localhost:24224", tag: "docker.{{.Name}}" }
```

```yaml
# Centralized logging: Loki + Grafana
services:
  loki:
    image: grafana/loki:3.4.2
    command: -config.file=/etc/loki/local-config.yaml
    ports: ["127.0.0.1:3100:3100"]
    volumes: [loki-data:/loki]
    restart: unless-stopped
  grafana:
    image: grafana/grafana:11.5.1
    ports: ["127.0.0.1:3000:3000"]
    environment: { GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_PASSWORD:-admin}" }
    volumes: [grafana-data:/var/lib/grafana]
    depends_on: [loki]
    restart: unless-stopped
volumes: { loki-data: {}, grafana-data: {} }
```

---

## Metrics

```yaml
# cAdvisor for container metrics
services:
  cadvisor:
    image: gcr.io/cadvisor/cadvisor:v0.51.0
    ports: ["127.0.0.1:8080:8080"]
    volumes: ["/:/rootfs:ro", "/var/run:/var/run:ro", "/sys:/sys:ro", "/var/lib/docker/:/var/lib/docker:ro"]
    restart: unless-stopped
```

Key container metrics: `container_cpu_usage_seconds_total` (alert >80% limit),
`container_memory_usage_bytes` (alert >90% limit), `container_network_receive_bytes`,
`container_network_transmit_bytes`, `container_fs_reads_bytes_total`,
`container_fs_writes_bytes_total`, `container_restart_count` (alert >0 in window).

Custom Prometheus endpoint in app (Python example):
```python
from prometheus_client import Counter, Histogram, start_http_server
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["method", "path"])
start_http_server(9090)
```

Docker daemon metrics -- enable in `/etc/docker/daemon.json`:
`{ "metrics-addr": "127.0.0.1:9323", "experimental": true }`

```yaml
# Prometheus + Grafana stack
services:
  prometheus:
    image: prom/prometheus:v3.2.1
    ports: ["127.0.0.1:9090:9090"]
    volumes: ["./prometheus.yml:/etc/prometheus/prometheus.yml:ro", "prometheus-data:/prometheus"]
    command: ["--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.retention.time=30d"]
    restart: unless-stopped
  grafana:
    image: grafana/grafana:11.5.1
    ports: ["127.0.0.1:3000:3000"]
    environment: { GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_PASSWORD:-admin}" }
    volumes: [grafana-data:/var/lib/grafana]
    depends_on: [prometheus]
    restart: unless-stopped
volumes: { prometheus-data: {}, grafana-data: {} }
```

---

## Health Checks

Health checks tell Docker when a container is ready (startup) vs alive (liveness).

| Parameter        | Default | Purpose                                           |
|------------------|---------|---------------------------------------------------|
| `interval`       | 30s     | Time between consecutive checks                   |
| `timeout`        | 30s     | Max time a single check can take before failing    |
| `start_period`   | 0s      | Grace period during startup (failures not counted) |
| `start_interval` | 5s      | Interval during `start_period` (Compose v2.20+)   |
| `retries`        | 3       | Consecutive failures before marking unhealthy      |

Use `start_period` for slow-starting apps (JVM, ML models). `start_interval`
enables faster polling during startup for quicker readiness detection.

```yaml
# HTTP health check (web app) -- Compose (preferred over Dockerfile)
services:
  app:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 15s
      timeout: 5s
      start_period: 30s
      start_interval: 3s
      retries: 3
  # Database health checks
  postgres:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-postgres}"]
      interval: 10s
      timeout: 3s
      retries: 5
  # Redis health check
  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
  # Message queue health checks
  rabbitmq:
    image: rabbitmq:4.0-management-alpine
    healthcheck:
      test: ["CMD-SHELL", "rabbitmq-diagnostics -q check_running"]
      interval: 15s
      timeout: 10s
      start_period: 30s
      retries: 3
```

```dockerfile
# Dockerfile health check (overridden by Compose if both exist)
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
```

TCP health check for services without HTTP or CLI: `test: ["CMD-SHELL", "cat < /dev/tcp/localhost/5432 || exit 1"]`

Prefer Compose health checks over Dockerfile -- they are easier to tune per environment.

---

## Tracing

Distributed tracing tracks requests across container boundaries, revealing latency
bottlenecks and failure paths. Use OpenTelemetry as the standard.

```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.118.0
    command: ["--config=/etc/otelcol/config.yaml"]
    ports: ["127.0.0.1:4317:4317", "127.0.0.1:4318:4318"]  # gRPC + HTTP OTLP
    volumes: ["./otel-config.yaml:/etc/otelcol/config.yaml:ro"]
    restart: unless-stopped
  jaeger:
    image: jaegertracing/jaeger:2.4.0
    ports: ["127.0.0.1:16686:16686"]              # Jaeger UI
    environment: { COLLECTOR_OTLP_ENABLED: "true" }
    restart: unless-stopped
```

Auto-instrumentation env vars for app containers:
```yaml
  app:
    environment:
      OTEL_SERVICE_NAME: "my-service"
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
      OTEL_TRACES_SAMPLER: "parentbased_traceidratio"
      OTEL_TRACES_SAMPLER_ARG: "0.1"             # Sample 10% in production
      OTEL_RESOURCE_ATTRIBUTES: "deployment.environment=production"
```

Language SDKs: Python `opentelemetry-distro` + `opentelemetry-instrument`, Node.js
`@opentelemetry/auto-instrumentations-node`, Go `go.opentelemetry.io/contrib/instrumentation`.

Trace context propagation uses W3C `traceparent` / `tracestate` headers -- ensure
reverse proxies and API gateways forward them between containers.

---

## Alerting

```yaml
# alert-rules.yml -- Prometheus alerting rules
groups:
  - name: container_alerts
    rules:
      - alert: ContainerRestarting
        expr: increase(container_restart_count[5m]) > 0
        for: 1m
        labels: { severity: warning }
        annotations: { summary: "Container {{ $labels.name }} restarted" }
      - alert: ContainerHighCPU
        expr: (rate(container_cpu_usage_seconds_total[5m]) / container_spec_cpu_quota * container_spec_cpu_period) > 0.8
        for: 5m
        labels: { severity: warning }
        annotations: { summary: "Container {{ $labels.name }} CPU > 80%" }
      - alert: ContainerHighMemory
        expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9
        for: 5m
        labels: { severity: critical }
        annotations: { summary: "Container {{ $labels.name }} memory > 90%" }
```

```yaml
# Alertmanager service + config
services:
  alertmanager:
    image: prom/alertmanager:v0.28.1
    ports: ["127.0.0.1:9093:9093"]
    volumes: ["./alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro"]
    restart: unless-stopped
# alertmanager.yml
route: { receiver: "slack", group_by: ["alertname", "severity"], group_wait: 30s, repeat_interval: 4h }
receivers:
  - name: "slack"
    slack_configs:
      - api_url: "${SLACK_WEBHOOK_URL}"
        channel: "#alerts"
        title: '{{ .CommonAnnotations.summary }}'
```

---

## Dashboard Templates

Key Grafana panels for Docker monitoring:

| Panel                   | Query                                           | Visualization |
|-------------------------|-------------------------------------------------|---------------|
| Container Status        | `count by (state) (container_last_seen)`        | Stat / Table  |
| CPU Usage per Container | `rate(container_cpu_usage_seconds_total[5m])`   | Time series   |
| Memory Usage            | `container_memory_usage_bytes`                  | Time series   |
| Network RX/TX           | `rate(container_network_*_bytes_total[5m])`     | Time series   |
| Log Volume              | `sum(rate({job="docker"}[1m])) by (service)`    | Bar chart     |
| Health Check Status     | `engine_daemon_health_checks_failed_total`      | Stat          |
| Restart Count           | `increase(container_restart_count[1h])`         | Stat          |

Auto-provision dashboards by mounting JSON exports and a provisioning config:
```yaml
  grafana:
    volumes:
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
```
Place a `dashboards.yaml` in provisioning pointing to `/var/lib/grafana/dashboards`
with `disableDeletion: true` and `updateIntervalSeconds: 30`.
