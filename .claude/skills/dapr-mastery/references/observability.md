# Dapr Observability Reference

## Three Pillars of Dapr Observability

| Pillar | Dapr Feature | Backend |
|--------|-------------|---------|
| Distributed Tracing | OpenTelemetry / W3C TraceContext | Zipkin, Jaeger, Azure Monitor, Datadog |
| Metrics | Prometheus exposition | Prometheus + Grafana |
| Logging | Structured JSON | Loki, Elasticsearch, Splunk |

---

## Distributed Tracing

### Dapr Configuration (OpenTelemetry Collector)

```yaml
apiVersion: dapr.io/v1alpha1
kind: Configuration
metadata:
  name: tracing-config
  namespace: production
spec:
  tracing:
    samplingRate: "1"        # 1 = 100%, "0.1" = 10% for high traffic
    otel:
      endpointAddress: "otel-collector.observability:4317"
      isSecure: false
      protocol: grpc          # grpc or http
    # Legacy: Zipkin direct (alternative)
    # zipkin:
    #   endpointAddress: "http://zipkin.observability:9411/api/v2/spans"
```

### OpenTelemetry Collector Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: otel-collector
  namespace: observability
spec:
  replicas: 2
  selector:
    matchLabels:
      app: otel-collector
  template:
    spec:
      containers:
        - name: otel-collector
          image: otel/opentelemetry-collector-contrib:0.90.0
          args: ["--config=/conf/otel-collector-config.yaml"]
          ports:
            - containerPort: 4317   # gRPC OTLP
            - containerPort: 4318   # HTTP OTLP
            - containerPort: 55679  # zpages debug
          volumeMounts:
            - name: otel-config
              mountPath: /conf
      volumes:
        - name: otel-config
          configMap:
            name: otel-collector-config
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-collector-config
  namespace: observability
data:
  otel-collector-config.yaml: |
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318

    processors:
      batch:
        timeout: 5s
        send_batch_size: 1000
      memory_limiter:
        check_interval: 1s
        limit_mib: 512

    exporters:
      jaeger:
        endpoint: jaeger-collector.observability:14250
        tls:
          insecure: true
      prometheus:
        endpoint: "0.0.0.0:8889"
      logging:
        loglevel: warn

    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [memory_limiter, batch]
          exporters: [jaeger]
        metrics:
          receivers: [otlp]
          processors: [batch]
          exporters: [prometheus]
```

---

## Prometheus Metrics

### Dapr Exposes These Metric Categories

| Category | Examples |
|----------|----------|
| Service Invocation | `dapr_http_server_request_count`, `dapr_http_server_response_count` |
| State | `dapr_state_request_count`, `dapr_state_request_duration_ms` |
| Pub/Sub | `dapr_pubsub_publish_count`, `dapr_pubsub_incoming_message_count` |
| Actor | `dapr_actor_active_actors`, `dapr_actor_request_count`, `dapr_actor_timer_fired` |
| Workflow | `dapr_workflow_operation_count`, `dapr_workflow_request_latency_ms` |
| Runtime | `dapr_grpc_io_server_completed_rpcs`, `dapr_http_client_retry_count` |
| Circuit Breaker | `dapr_circuit_breaker_state` |

### Prometheus Scrape Config

```yaml
# prometheus.yml
scrape_configs:
  # Dapr sidecars
  - job_name: 'dapr-sidecars'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names: [production, staging]
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_dapr_io_enable_metrics]
        regex: "true"
        action: keep
      - source_labels: [__meta_kubernetes_pod_annotation_dapr_io_metrics_port]
        target_label: __port__
      - source_labels: [__meta_kubernetes_pod_ip, __port__]
        separator: ':'
        target_label: __address__
      - source_labels: [__meta_kubernetes_pod_annotation_dapr_io_app_id]
        target_label: app_id
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace

  # Dapr control plane
  - job_name: 'dapr-control-plane'
    static_configs:
      - targets:
          - dapr-operator.dapr-system:8080
          - dapr-placement-server.dapr-system:9090
          - dapr-sentry.dapr-system:9090
          - dapr-scheduler.dapr-system:9090
```

### Grafana Dashboard Import

```bash
# Import official Dapr Grafana dashboards
# Dashboard IDs (grafana.com):
# 12216 - Dapr System Components
# 17021 - Dapr Service Invocation
# 17000 - Dapr Pub/Sub
# 17001 - Dapr Actor
# 17002 - Dapr Workflow

kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: dapr-dashboards
  namespace: monitoring
  labels:
    grafana_dashboard: "1"    # Grafana sidecar auto-imports
data:
  dapr-system.json: |
    # Export from grafana.com/dashboards/12216
EOF
```

---

## Logging

### Dapr Log Format (JSON)

```json
{
  "time": "2025-01-15T10:30:00Z",
  "level": "info",
  "type": "log",
  "msg": "Invoked method getOrder successfully",
  "scope": "dapr.runtime",
  "instance": "order-service-pod-abc",
  "app_id": "order-service",
  "ver": "1.15.0"
}
```

### Log Aggregation with Loki

```yaml
# Promtail pipeline for Dapr log enrichment
pipelineStages:
  - json:
      expressions:
        app_id: app_id
        level: level
        scope: scope
  - labels:
      app_id:
      level:
      scope:
  - drop:
      source: level
      value: debug   # Drop debug logs in production
      drop_counter_reason: dapr_debug_drop
```

### Recommended Log Levels

| Environment | Level | Reason |
|-------------|-------|--------|
| Production | `warn` | Minimal noise, captures errors |
| Staging | `info` | Trace key flows |
| Development | `debug` | Full visibility |

```yaml
# Set via Helm or annotation
annotations:
  dapr.io/log-level: "warn"
  dapr.io/log-as-json: "true"
```

---

## Health Checks

### Dapr Sidecar Health API

```bash
# Dapr sidecar health (from within pod)
curl http://localhost:3500/v1.0/healthz         # 204 = healthy
curl http://localhost:3500/v1.0/healthz/outbound # Check component connectivity

# Dapr metadata
curl http://localhost:3500/v1.0/metadata
```

### App Health Probes

```yaml
# Application must expose these (Dapr uses them for health checks)
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
```

### Dapr App Health (v1.13+)

```yaml
# Dapr monitors app health and disables sidecar if app is unhealthy
annotations:
  dapr.io/enable-app-health-check: "true"
  dapr.io/app-health-check-path: "/healthz"
  dapr.io/app-health-probe-interval: "5"    # seconds
  dapr.io/app-health-probe-timeout: "500"   # milliseconds
  dapr.io/app-health-threshold: "3"          # failures before marking unhealthy
```

---

## Key Alerts (Prometheus Alert Rules)

```yaml
groups:
  - name: dapr.rules
    rules:
      # High error rate on service invocation
      - alert: DaprHighInvocationErrorRate
        expr: |
          rate(dapr_http_server_response_count{status_code=~"5.."}[5m])
          / rate(dapr_http_server_response_count[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High Dapr invocation error rate on {{ $labels.app_id }}"

      # Circuit breaker open
      - alert: DaprCircuitBreakerOpen
        expr: dapr_circuit_breaker_state == 1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Circuit breaker OPEN for {{ $labels.app_id }}"

      # Actor activation failures
      - alert: DaprActorActivationFailures
        expr: rate(dapr_actor_request_count{status="failed"}[5m]) > 10
        for: 5m
        labels:
          severity: warning

      # Pub/Sub message backlog
      - alert: DaprPubSubBacklog
        expr: dapr_pubsub_incoming_message_count - dapr_pubsub_process_message_count > 10000
        for: 10m
        labels:
          severity: warning

      # Sidecar memory near limit
      - alert: DaprSidecarHighMemory
        expr: |
          container_memory_usage_bytes{container="daprd"}
          / container_spec_memory_limit_bytes{container="daprd"} > 0.85
        for: 5m
        labels:
          severity: warning
```
