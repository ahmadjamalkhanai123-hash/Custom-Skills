# Observability Foundations
## OpenTelemetry, Signals, Pipelines, and Semantic Conventions

---

## The Four Observability Signals

### 1. Metrics
Numeric measurements aggregated over time. Low cardinality, high retention.
- **Types**: Counter, Gauge, Histogram, Summary (Prometheus types)
- **OTel types**: Sum, Gauge, Histogram, ExponentialHistogram, Summary
- **Best for**: Alerting, dashboards, SLOs, capacity planning
- **Cardinality rule**: Never use high-cardinality values (user_id, request_id) as label keys

### 2. Logs
Timestamped records of discrete events. High cardinality, moderate retention.
- **Format**: Always structured JSON in production
- **Required fields**: `timestamp`, `level`, `service.name`, `trace_id`, `span_id`, `environment`
- **Best for**: Debugging, audit trails, error details
- **Cost**: Most expensive observability signal by volume; always sample in production

### 3. Traces
Distributed context propagation through a system. Time-to-first-byte, latency breakdown.
- **Anatomy**: Trace → Spans → Span Events → Span Attributes
- **Propagation**: W3C `traceparent` header (trace-id, parent-id, trace-flags)
- **Best for**: Latency analysis, dependency mapping, failure root cause
- **Sampling**: Never 100% in production; use tail-based for error capture

### 4. Events (Profiling + Continuous Profiling)
Point-in-time occurrences that don't fit structured logs.
- **Examples**: Deployment events, alert firings, user actions, model predictions
- **OTel Events**: Span events (attached to traces) or standalone log events
- **Profiling**: CPU/memory flamegraphs (Pyroscope, Cloud Profiler, Datadog Continuous Profiler)

---

## OpenTelemetry Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     YOUR APPLICATION                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Python   │  │  Node.js │  │   Go     │  │  Java    │   │
│  │ OTel SDK │  │ OTel SDK │  │ OTel SDK │  │ OTel SDK │   │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘   │
└────────┼─────────────┼─────────────┼──────────────┼─────────┘
         │   OTLP/gRPC or OTLP/HTTP  │              │
         └──────────────┬────────────┘              │
                        ▼                           │
              ┌────────────────────┐                │
              │  OTel Collector    │◄───────────────┘
              │  ┌──────────────┐  │
              │  │  Receivers   │  │  ← OTLP, Prometheus, Jaeger, Zipkin, statsd
              │  │  Processors  │  │  ← Batch, Filter, AttributeTransform, Sampling
              │  │  Exporters   │  │  ← Prometheus, Jaeger, Loki, Tempo, OTLP, Datadog
              │  └──────────────┘  │
              └────────────────────┘
                   │         │
          ┌────────┘         └────────┐
          ▼                          ▼
   Metrics Backend           Traces Backend
   (Prometheus/Cloud)       (Tempo/Jaeger/Cloud)
          │
          ▼
   Logs Backend
   (Loki/EFK/Cloud)
```

---

## OTel Collector Configuration Patterns

### Minimal Collector (Local Dev)
```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    send_batch_size: 1000
    timeout: 1s
  memory_limiter:
    check_interval: 1s
    limit_mib: 512

exporters:
  prometheus:
    endpoint: "0.0.0.0:9090"
  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true
  loki:
    endpoint: http://loki:3100/loki/api/v1/push

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheus]
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/jaeger]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [loki]
```

### Tail-Based Sampling (Production)
```yaml
processors:
  tail_sampling:
    decision_wait: 10s
    num_traces: 100000
    expected_new_traces_per_sec: 1000
    policies:
      - name: errors-policy
        type: status_code
        status_code: {status_codes: [ERROR]}
      - name: slow-traces-policy
        type: latency
        latency: {threshold_ms: 1000}
      - name: probabilistic-policy
        type: probabilistic
        probabilistic: {sampling_percentage: 10}
```

---

## SDK Instrumentation — Language Reference

### Python (opentelemetry-sdk)
```python
import os
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

def setup_telemetry(service_name: str, otlp_endpoint: str):
    # Tracer
    provider = TracerProvider(
        resource=Resource.create({
            SERVICE_NAME: service_name,
            "deployment.environment": os.getenv("DEPLOYMENT_ENV", "dev"),
            "service.version": os.getenv("SERVICE_VERSION", "0.0.0"),
        })
    )
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=otlp_endpoint)
    ))
    trace.set_tracer_provider(provider)

    # Auto-instrument common libraries
    FastAPIInstrumentor.instrument()
    HTTPXClientInstrumentor.instrument()
    SQLAlchemyInstrumentor.instrument()
```

### Node.js (opentelemetry-js)
```typescript
import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-grpc';
import { PrometheusExporter } from '@opentelemetry/exporter-prometheus';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';

const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter({ url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT }),
  metricReader: new PrometheusExporter({ port: 9464 }),
  instrumentations: [getNodeAutoInstrumentations()],
  resource: new Resource({ [SEMRESATTRS_SERVICE_NAME]: 'my-service' }),
});
sdk.start();
```

### Go (go.opentelemetry.io/otel)
```go
func initTracer(ctx context.Context) (*sdktrace.TracerProvider, error) {
    exp, _ := otlptracegrpc.New(ctx,
        otlptracegrpc.WithEndpoint(os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")),
    )
    tp := sdktrace.NewTracerProvider(
        sdktrace.WithBatcher(exp),
        sdktrace.WithResource(resource.NewWithAttributes(
            semconv.SchemaURL,
            semconv.ServiceName(os.Getenv("SERVICE_NAME")),
        )),
    )
    otel.SetTracerProvider(tp)
    otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
        propagation.TraceContext{}, propagation.Baggage{},
    ))
    return tp, nil
}
```

---

## Semantic Conventions (Critical for Consistency)

| Attribute | Key | Example |
|-----------|-----|---------|
| Service name | `service.name` | `payment-service` |
| Environment | `deployment.environment` | `production` |
| Version | `service.version` | `1.4.2` |
| HTTP method | `http.request.method` | `GET` |
| HTTP status | `http.response.status_code` | `200` |
| DB system | `db.system` | `postgresql` |
| DB statement | `db.statement` | `SELECT * FROM users` |
| Message system | `messaging.system` | `kafka` |
| Cloud provider | `cloud.provider` | `aws` |
| K8s pod | `k8s.pod.name` | `api-7d4b9c-xvf2k` |
| LLM model | `gen_ai.request.model` | `claude-sonnet-4-6` |
| LLM tokens | `gen_ai.usage.input_tokens` | `1024` |

Full reference: https://opentelemetry.io/docs/specs/semconv/

---

## Correlation — The Glue Between Signals

Every log line and metric sample MUST carry trace context:

```json
{
  "timestamp": "2026-02-25T12:34:56.789Z",
  "level": "ERROR",
  "service.name": "order-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "message": "Payment processing failed",
  "error": "timeout connecting to payment-gateway",
  "environment": "production",
  "version": "1.4.2"
}
```

Exemplars link metrics to traces:
```yaml
# Prometheus histogram with exemplar
http_request_duration_seconds_bucket{le="0.1"} 24054 # {trace_id="4bf92f..."} 0.054
```
