# Logging Patterns
## Structured Logging, Aggregation, Cloud-Native Log Pipelines

---

## Structured Logging Principles

### Always JSON in Production
```python
# Python — structlog (recommended)
import structlog

log = structlog.get_logger()
log.info("order_created",
    order_id=order.id,
    user_id=user.id,
    amount=order.total,
    trace_id=get_current_trace_id(),
)
```

```typescript
// Node.js — pino (fastest JSON logger)
import pino from 'pino';
const log = pino({ level: 'info' });
log.info({ orderId, userId, amount }, 'order_created');
```

```go
// Go — slog (stdlib, 1.21+)
slog.Info("order_created",
    "order_id", order.ID,
    "user_id", user.ID,
    "trace_id", span.SpanContext().TraceID().String(),
)
```

### Mandatory Log Fields
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timestamp` | ISO 8601 | Yes | UTC timestamp with ms |
| `level` | string | Yes | DEBUG/INFO/WARN/ERROR/FATAL |
| `service.name` | string | Yes | Service identifier |
| `message` | string | Yes | Human-readable event summary |
| `trace_id` | string | Yes (if traced) | OTel trace ID (32 hex chars) |
| `span_id` | string | Yes (if traced) | OTel span ID (16 hex chars) |
| `environment` | string | Yes | dev/staging/production |
| `version` | string | Yes | Service version (semver) |
| `error` | object | When ERROR | {type, message, stack_trace} |

### Log Level Guidelines
| Level | When to Use | Production Rate |
|-------|-------------|-----------------|
| DEBUG | Detailed flow tracing | 0% (disabled) |
| INFO | Normal operations, state changes | Sampled |
| WARN | Unexpected but handled conditions | 100% |
| ERROR | Operation failed, requires attention | 100% |
| FATAL | Process cannot continue | 100% |

---

## Log Aggregation Backends

### Loki (Grafana — Recommended OSS)
**Design**: Index only labels (low cardinality); store log lines as-is
**Query language**: LogQL

```yaml
# promtail config — scrape Docker containers
scrape_configs:
  - job_name: containers
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        target_label: container
      - source_labels: ['__meta_docker_container_label_com_docker_compose_service']
        target_label: service
    pipeline_stages:
      - docker: {}
      - json:
          expressions:
            level: level
            trace_id: trace_id
      - labels:
          level:
          trace_id:
```

**LogQL examples**:
```logql
# Error logs for payment-service in last 1h
{service="payment-service"} |= "ERROR" | json | level="ERROR"

# Logs correlated to a trace
{service=~".+"} | json | trace_id="4bf92f3577b34da6a3ce929d0e0e4736"

# Log rate by service (metric query)
sum(rate({job="containers"}[5m])) by (service)
```

**Loki deployment config**:
```yaml
# loki config.yaml
auth_enabled: false
server:
  http_listen_port: 3100
ingester:
  chunk_idle_period: 3m
  max_chunk_age: 1h
schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h
storage_config:
  tsdb_shipper:
    active_index_directory: /loki/tsdb-index
    cache_location: /loki/tsdb-cache
  filesystem:
    directory: /loki/chunks
limits_config:
  retention_period: 30d
  ingestion_rate_mb: 16
  max_label_names_per_series: 20
```

---

### ELK Stack (Elasticsearch + Logstash + Kibana)
**Use when**: Full-text search on logs, complex log transformations, existing Elastic investment

```yaml
# Logstash pipeline
input {
  beats { port => 5044 }
}
filter {
  json { source => "message" }
  date { match => ["timestamp", "ISO8601"] target => "@timestamp" }
  if [level] == "ERROR" {
    mutate { add_tag => ["error"] }
  }
}
output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "logs-%{[service][name]}-%{+YYYY.MM.dd}"
    ilm_enabled => true
    ilm_rollover_alias => "logs"
    ilm_policy => "logs-policy"
  }
}
```

**Fluent Bit (lightweight forwarder — preferred over Logstash for K8s)**:
```yaml
# fluent-bit daemonset config
[INPUT]
    Name              tail
    Path              /var/log/containers/*.log
    Parser            docker
    Tag               kube.*
    Refresh_Interval  5

[FILTER]
    Name                kubernetes
    Match               kube.*
    Kube_URL            https://kubernetes.default.svc:443
    Merge_Log           On
    K8S-Logging.Parser  On

[OUTPUT]
    Name  es
    Match *
    Host  elasticsearch-master
    Port  9200
    Index fluent-bit
    Logstash_Format On
```

---

### Cloud-Native Log Services

#### AWS CloudWatch Logs
```yaml
# CloudWatch Agent config (EC2/ECS)
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/app/*.json",
            "log_group_name": "/app/production",
            "log_stream_name": "{instance_id}/{service}",
            "retention_in_days": 30
          }
        ]
      }
    }
  }
}
```

CloudWatch Logs Insights query:
```sql
fields @timestamp, level, service, message, trace_id
| filter level = "ERROR"
| stats count(*) as error_count by service
| sort error_count desc
```

#### GCP Cloud Logging
```python
# Structured logging to Cloud Logging (auto-detected in GKE/Cloud Run)
import google.cloud.logging
client = google.cloud.logging.Client()
client.setup_logging()

import logging
logging.info("order_created", extra={
    "json_fields": {
        "order_id": "ord-123",
        "trace": f"projects/{PROJECT}/traces/{trace_id}"
    }
})
```

Log Explorer query:
```
resource.type="k8s_container"
severity>=ERROR
jsonPayload.service="payment-service"
timestamp>="2026-02-25T00:00:00Z"
```

#### Azure Log Analytics (KQL)
```kql
// Errors per service in last 24h
ContainerLog
| where TimeGenerated > ago(24h)
| extend LogData = parse_json(LogEntry)
| where LogData.level == "ERROR"
| summarize ErrorCount = count() by Service = tostring(LogData['service.name'])
| order by ErrorCount desc
```

---

## Log Pipeline Architecture (OTel Collector as Universal Forwarder)

```yaml
# OTel Collector — log receiver + routing
receivers:
  filelog:
    include: [/var/log/apps/**/*.json]
    include_file_path: true
    operators:
      - type: json_parser
        timestamp:
          parse_from: attributes.timestamp
          layout: '%Y-%m-%dT%H:%M:%S.%fZ'
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  resource:
    attributes:
      - action: insert
        key: environment
        value: production
  attributes:
    actions:
      - action: delete   # Remove PII
        key: user.email

exporters:
  loki:
    endpoint: http://loki:3100/loki/api/v1/push
    labels:
      resource:
        service.name: service
        deployment.environment: environment
  awscloudwatchlogs:
    log_group_name: /app/production
    log_stream_name: otel-collector
    region: us-east-1
```

---

## Log Sampling Strategies

```python
# Sampling filter in OTel Collector
processors:
  filter/logs:
    logs:
      exclude:
        match_type: regexp
        bodies:
          - ".*health check.*"   # Drop health check noise
          - ".*GET /metrics.*"   # Drop scrape logs
    logs:
      include:
        match_type: strict
        severity_number:
          min: SEVERITY_NUMBER_WARN  # Only WARN+ in prod hot path
```

---

## Log Retention & Cost Optimization

| Tier | Hot (Fast Query) | Warm (Archive) | Cold (Compliance) |
|------|-----------------|----------------|-------------------|
| Loki | 7 days | 30 days (S3) | 90 days (Glacier) |
| CloudWatch | 7 days | Export to S3 | Glacier/IA |
| Elastic | 7 days (SSD) | 30 days (HDD) | S3 snapshot |

**Cost saving**: Enable log sampling for INFO-level in high-throughput services.
Sample rate 10% for INFO, 100% for WARN/ERROR. Can reduce log volume by 80%.

---

## Sensitive Data Masking

```yaml
# OTel Collector processor to redact PII
processors:
  redaction:
    allow_all_keys: false
    allowed_keys:
      - trace_id
      - span_id
      - service.name
      - level
      - message
      - environment
    blocked_values:
      - "[0-9]{4}[- ][0-9]{4}[- ][0-9]{4}[- ][0-9]{4}"  # Credit card
      - "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"  # Email
      - "Bearer [A-Za-z0-9\\-._~+/]+"                       # JWT/Bearer
    summary: debug
```
