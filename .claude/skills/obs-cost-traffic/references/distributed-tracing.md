# Distributed Tracing
## Trace Context Propagation, Sampling Strategies, and Backend Reference

---

## Trace Anatomy

```
Trace (single request across all services)
└── Root Span: api-gateway POST /order (total: 245ms)
    ├── Child Span: auth-service validate_token (12ms)
    ├── Child Span: order-service create_order (180ms)
    │   ├── Child Span: db.postgresql INSERT orders (35ms)
    │   │   └── Span Event: query_slow (threshold exceeded)
    │   └── Child Span: kafka publish order.created (8ms)
    └── Child Span: notification-service send_email (45ms)
        └── Span Event: smtp_error (retrying)
```

**Span attributes**:
- `name`: Operation name (HTTP method + route, or function name)
- `trace_id`: 128-bit unique ID (shared across all spans in a trace)
- `span_id`: 64-bit ID for this span
- `parent_span_id`: Links to parent span (none for root)
- `start_time` + `end_time`: Nanosecond timestamps
- `status`: OK / ERROR / UNSET
- `kind`: SERVER / CLIENT / PRODUCER / CONSUMER / INTERNAL
- `attributes`: Key-value pairs following semantic conventions

---

## W3C Trace Context (The Standard)

All modern tracing uses W3C `traceparent` header:
```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^ ^^
             version  trace-id (128-bit hex)      parent-id (64b)  flags
```

`tracestate` for vendor-specific data:
```
tracestate: datadog=s:1,dd.p.dm=-0;_dd.p.tid=66df4ce800000000
```

**Propagation in HTTP clients**:
```python
# Python httpx — automatic with OTel instrumentation
import httpx
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
HTTPXClientInstrumentor().instrument()  # Injects traceparent automatically

# Manual propagation
from opentelemetry.propagate import inject
headers = {}
inject(headers)  # Injects W3C traceparent
response = httpx.get("http://other-service/api", headers=headers)
```

**Propagation in Kafka (async)**:
```python
from opentelemetry.propagate import inject, extract
from confluent_kafka import Producer, Consumer

# Producer — inject trace context into message headers
producer = Producer({'bootstrap.servers': 'kafka:9092'})
headers = {}
inject(headers)  # Injects traceparent into dict
producer.produce('orders', value=payload, headers=list(headers.items()))

# Consumer — extract and continue the trace
msg = consumer.poll(1.0)
context = extract({k: v.decode() for k, v in (msg.headers() or [])})
with tracer.start_as_current_span("process_order", context=context):
    process(msg.value())
```

---

## Sampling Strategies

### Head-Based Sampling (Decision at trace start)
```python
# Probabilistic sampler — simple, predictable
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

sampler = TraceIdRatioBased(0.1)  # 10% sample rate

# ParentBased — respect upstream sampling decision
from opentelemetry.sdk.trace.sampling import ParentBased
sampler = ParentBased(root=TraceIdRatioBased(0.1))
```

### Tail-Based Sampling (Decision after trace completes)
Best for ensuring ALL errors and slow traces are captured:

```yaml
# OTel Collector tail_sampling processor
processors:
  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    expected_new_traces_per_sec: 500
    policies:
      # Always keep errors
      - name: keep-errors
        type: status_code
        status_code: {status_codes: [ERROR]}
      # Keep slow traces (>2s)
      - name: keep-slow
        type: latency
        latency: {threshold_ms: 2000}
      # Keep 5% of all other traces
      - name: probabilistic
        type: probabilistic
        probabilistic: {sampling_percentage: 5}
      # Always keep traces for critical services
      - name: keep-payment
        type: string_attribute
        string_attribute:
          key: service.name
          values: [payment-service, fraud-detection]
```

### Adaptive Sampling (Rate-Limiting)
```yaml
# OTel Collector probabilistic_sampler
processors:
  probabilistic_sampler:
    sampling_percentage: 10
    # Or rate-limiting:
    # hash_seed: 22  # For consistent sampling across collectors
```

---

## Tracing Backends

### Grafana Tempo (Recommended OSS — Pairs with Loki/Grafana)
- **Storage**: Object storage (S3, GCS, Azure Blob, or local filesystem)
- **Scale**: Petabyte-scale with distributed mode
- **Integration**: Direct Grafana datasource, Prometheus exemplars

```yaml
# tempo.yaml — minimal config
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318
    jaeger:
      protocols:
        thrift_http:
          endpoint: 0.0.0.0:14268

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/blocks
    wal:
      path: /tmp/tempo/wal

compactor:
  compaction:
    block_retention: 168h  # 7 days

query_frontend:
  search:
    duration_slo: 5s
    throughput_bytes_slo: 1.073741824e+09
```

### Jaeger (Standalone Tracing — Battle-Tested)
- All-in-one mode for dev, distributed for production
- Cassandra or Elasticsearch backend

```yaml
# jaeger all-in-one (dev)
services:
  jaeger:
    image: jaegertracing/all-in-one:1.55
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
```

---

## Cloud-Native Tracing

### AWS X-Ray
```python
# Lambda / ECS instrumentation
from aws_xray_sdk.core import xray_recorder, patch_all
patch_all()  # Auto-instrument boto3, requests, httplib

@xray_recorder.capture('process_order')
def process_order(order_id: str):
    # Creates X-Ray subsegment automatically
    return order_service.get(order_id)
```

OTel → X-Ray bridge (recommended for greenfield):
```yaml
# ADOT Collector exporter config
exporters:
  awsxray:
    region: us-east-1
    indexed_attributes:
      - aws.operation
      - http.response.status_code
      - db.statement
```

### Google Cloud Trace
```python
# Cloud Trace auto-integration via OTel
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider.add_span_processor(
    BatchSpanProcessor(CloudTraceSpanExporter(project_id=PROJECT_ID))
)
```

Cloud Trace query (Cloud Console):
```
# Find all traces with errors for a service
resource.type="k8s_container"
resource.labels.container_name="payment-service"
status_code="ERROR"
latency>2s
```

### Azure Application Insights
```python
# OTel → App Insights via Azure Monitor exporter
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

provider.add_span_processor(
    BatchSpanProcessor(AzureMonitorTraceExporter(
        connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    ))
)
```

---

## Enterprise APM — Feature Comparison

| Feature | Datadog APM | New Relic | Dynatrace |
|---------|-------------|-----------|-----------|
| Auto-instrumentation | Yes (ddtrace) | Yes (agent) | Yes (OneAgent) |
| Distributed tracing | Yes | Yes | Yes (PurePath) |
| Service map | Yes | Yes | Yes (Smartscape) |
| AI/LLM tracing | Yes (LLM Observability) | Yes | Yes |
| Anomaly detection | ML-based | ML-based | AI-powered |
| Cost | Per host + per APM host | Usage-based | Per host |
| Correlation to logs | Yes | Yes | Yes |
| Root cause analysis | AI-assisted | Yes | AI-assisted |

---

## Trace-Based SLOs (Linking Tracing to Reliability)

```yaml
# Prometheus recording rule from trace-derived metrics
# (OTel Collector generates metrics from spans)
- record: service:request_duration_seconds:p99
  expr: |
    histogram_quantile(0.99,
      sum(rate(traces_spanmetrics_duration_milliseconds_bucket[5m])) by (service, le)
    ) / 1000

- alert: ServiceLatencySLOBreach
  expr: service:request_duration_seconds:p99 > 0.5
  for: 5m
  labels:
    severity: warning
    slo: latency
  annotations:
    summary: "{{ $labels.service }} p99 latency exceeding 500ms SLO"
```

**Span Metrics Connector** (OTel Collector — converts traces to metrics):
```yaml
connectors:
  spanmetrics:
    histogram:
      explicit:
        buckets: [5ms, 10ms, 25ms, 50ms, 75ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s]
    dimensions:
      - name: http.method
      - name: http.status_code
      - name: service.name
    exemplars:
      enabled: true  # Links metrics back to trace IDs

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/jaeger, spanmetrics]
    metrics/spanmetrics:
      receivers: [spanmetrics]
      exporters: [prometheus]
```

---

## Async and Event-Driven Tracing Patterns

```python
# Message queue correlation pattern
class TracedMessageHandler:
    def handle(self, message: Message):
        # Extract trace context from message
        carrier = {h.key: h.value.decode() for h in message.headers}
        ctx = extract(carrier)

        # Create span linked to producing trace
        with tracer.start_as_current_span(
            "consume_order_event",
            context=ctx,
            kind=SpanKind.CONSUMER,
            attributes={
                "messaging.system": "kafka",
                "messaging.destination": "orders.created",
                "messaging.operation": "receive",
            }
        ) as span:
            self.process(message)
```

**Database tracing best practices**:
- Capture `db.statement` for slow queries only (>100ms) to avoid data leakage
- Use `db.operation` + `db.name` always
- Never capture bind parameters that may contain PII
