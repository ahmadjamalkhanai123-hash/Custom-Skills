# Metrics & Alerting
## Prometheus, Grafana, SLOs/SLIs, Alertmanager, Golden Signals

---

## The Four Golden Signals (Google SRE Book)

| Signal | What It Measures | Primary Metric |
|--------|-----------------|----------------|
| **Latency** | Time to serve a request (separate successful vs. failed) | `http_request_duration_seconds` histogram |
| **Traffic** | Volume of demand on the system | `http_requests_total` counter |
| **Errors** | Rate of failed requests (5xx, timeouts, wrong results) | `http_requests_total{http_status_code=~"5.."}` (OTel semconv) |
| **Saturation** | How full is the service? (CPU, memory, queue depth) | `process_cpu_seconds_total`, `container_memory_usage_bytes` |

---

## Prometheus Metrics Reference

### Metric Types
```python
# Counter — only increases (requests, errors, bytes sent)
from prometheus_client import Counter
requests_total = Counter('http_requests_total',
    'Total HTTP requests',
    ['method', 'path', 'status_code']
)
requests_total.labels(method='GET', path='/api/orders', status_code='200').inc()

# Gauge — can go up or down (queue depth, active connections, temperature)
from prometheus_client import Gauge
active_connections = Gauge('active_connections', 'Current active connections')
active_connections.set(42)

# Histogram — samples with configurable buckets (latency, request size)
from prometheus_client import Histogram
request_duration = Histogram('http_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'path'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)
with request_duration.labels(method='POST', path='/order').time():
    process_order()
```

### Prometheus Scrape Config
```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'kubernetes-pods'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod

  - job_name: 'kubernetes-services'
    kubernetes_sd_configs:
      - role: service
    metrics_path: /metrics
```

### Remote Write (Long-Term Storage)
```yaml
remote_write:
  - url: "https://prometheus-remote-write.grafana.net/api/prom/push"
    basic_auth:
      username: "12345"
      password: "${GRAFANA_API_KEY}"
    write_relabel_configs:
      - source_labels: [__name__]
        regex: "go_.*|process_.*"
        action: drop  # Drop low-value Go runtime metrics
```

---

## SLO/SLI Framework

### Defining SLIs
```yaml
# SLI: The metric that measures user happiness
# Example SLIs for an order service:

availability_sli:
  # Label: OTel semconv = http_status_code; legacy prometheus_client = status or code
  numerator: "sum(rate(http_requests_total{job='order-service',http_status_code!~'5..'}[5m]))"
  denominator: "sum(rate(http_requests_total{job='order-service'}[5m]))"

latency_sli:
  # % of requests faster than 300ms
  numerator: "sum(rate(http_request_duration_seconds_bucket{job='order-service',le='0.3'}[5m]))"
  denominator: "sum(rate(http_request_duration_seconds_count{job='order-service'}[5m]))"
```

### Recording Rules for SLOs
```yaml
# prometheus-rules.yaml
groups:
  - name: slo.order-service
    interval: 30s
    rules:
      # Short-window burn rate
      - record: job:slo_availability:ratio_rate5m
        expr: |
          sum(rate(http_requests_total{job="order-service",http_status_code!~"5.."}[5m]))
          / sum(rate(http_requests_total{job="order-service"}[5m]))

      # Medium-window burn rate
      - record: job:slo_availability:ratio_rate1h
        expr: |
          sum(rate(http_requests_total{job="order-service",http_status_code!~"5.."}[1h]))
          / sum(rate(http_requests_total{job="order-service"}[1h]))

      # Long-window burn rate
      - record: job:slo_availability:ratio_rate30d
        expr: |
          sum(rate(http_requests_total{job="order-service",http_status_code!~"5.."}[30d]))
          / sum(rate(http_requests_total{job="order-service"}[30d]))

      # Error budget remaining (target: 99.9%)
      - record: job:slo_error_budget_remaining:ratio
        expr: |
          1 - (1 - job:slo_availability:ratio_rate30d) / (1 - 0.999)
```

### Multi-Window Burn Rate Alerts (Google SRE Book Method)
```yaml
  - name: slo.alerts.order-service
    rules:
      # Critical: 2% budget burned in 1h (14.4x burn rate)
      - alert: SLOHighBurnRateCritical
        expr: |
          (job:slo_availability:ratio_rate1h < (1 - 14.4 * (1 - 0.999)))
          and
          (job:slo_availability:ratio_rate5m < (1 - 14.4 * (1 - 0.999)))
        for: 2m
        labels:
          severity: critical
          slo: availability
          team: platform
        annotations:
          summary: "{{ $labels.job }} burning error budget at 14.4x rate"
          description: "Will exhaust 30-day budget in 2 hours if sustained"
          runbook: "https://wiki.internal/runbooks/slo-high-burn-rate"

      # Warning: 5% budget burned in 6h (6x burn rate)
      - alert: SLOHighBurnRateWarning
        expr: |
          (job:slo_availability:ratio_rate1h < (1 - 6 * (1 - 0.999)))
          and
          (job:slo_availability:ratio_rate5m < (1 - 6 * (1 - 0.999)))
        for: 15m
        labels:
          severity: warning
          slo: availability
```

---

## Alertmanager Configuration

```yaml
# alertmanager.yaml
global:
  resolve_timeout: 5m
  slack_api_url: "${SLACK_WEBHOOK_URL}"
  pagerduty_url: "https://events.pagerduty.com/v2/enqueue"

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    # Critical alerts → PagerDuty
    - match:
        severity: critical
      receiver: pagerduty
      continue: true  # Also send to Slack

    # SLO alerts → dedicated channel
    - match:
        slo: availability
      receiver: slo-channel

    # Business hours only
    - match:
        severity: warning
      receiver: slack-warning
      active_time_intervals:
        - business_hours

receivers:
  - name: pagerduty
    pagerduty_configs:
      - routing_key: "${PAGERDUTY_KEY}"
        severity: "{{ .CommonLabels.severity }}"
        description: "{{ .CommonAnnotations.summary }}"

  - name: slo-channel
    slack_configs:
      - channel: '#slo-alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: slack-warning
    slack_configs:
      - channel: '#platform-warnings'

inhibit_rules:
  # Critical inhibits warning for the same service
  - source_match:
      severity: critical
    target_match:
      severity: warning
    equal: ['alertname', 'service']

time_intervals:
  - name: business_hours
    time_intervals:
      - weekdays: ['monday:friday']
        times:
          - start_time: '09:00'
            end_time: '17:00'
```

---

## Grafana Dashboard Patterns

### Golden Signals Row (PromQL)
```
# Traffic (requests/sec)
sum(rate(http_requests_total{job=~"$service"}[5m])) by (method)

# Error rate (%)
sum(rate(http_requests_total{job=~"$service",status=~"5.."}[5m]))
/ sum(rate(http_requests_total{job=~"$service"}[5m])) * 100

# p50/p95/p99 Latency
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket{job=~"$service"}[5m])) by (le)
)

# Saturation — CPU usage
sum(rate(container_cpu_usage_seconds_total{namespace=~"$namespace"}[5m]))
  / sum(kube_pod_container_resource_limits{resource="cpu",namespace=~"$namespace"}) * 100
```

### Service Map (Dependency Graph)
- Grafana plugin: **grafana-k6-app** or **Grafana Service Graph** (from Tempo)
- Built from trace span metrics with `calls_total` and `duration_milliseconds`

```yaml
# span-metrics generates service graph metrics automatically
connectors:
  servicegraph:
    metrics_flush_interval: 15s
    dimensions:
      - http.method
      - http.status_code
    store:
      ttl: 2s
      max_items: 1000
```

---

## Kubernetes Cluster Monitoring

### kube-prometheus-stack (Helm — recommended)
```yaml
# values.yaml for kube-prometheus-stack
prometheus:
  prometheusSpec:
    retention: 15d
    retentionSize: "50GB"
    resources:
      requests:
        memory: 2Gi
        cpu: 500m
      limits:
        memory: 4Gi
    storageSpec:
      volumeClaimTemplate:
        spec:
          storageClassName: gp3
          resources:
            requests:
              storage: 100Gi

grafana:
  adminPassword: "${GRAFANA_ADMIN_PASSWORD}"
  persistence:
    enabled: true
    size: 10Gi
  dashboardProviders:
    dashboardproviders.yaml:
      providers:
        - name: default
          folder: Production
          type: file
          options:
            path: /var/lib/grafana/dashboards

alertmanager:
  config:
    global:
      slack_api_url: "${SLACK_WEBHOOK}"
```

### Key Kubernetes Alerts
```yaml
- alert: PodCrashLooping
  expr: rate(kube_pod_container_status_restarts_total[15m]) > 0
  for: 5m
  labels: {severity: warning}

- alert: NodeMemoryPressure
  expr: |
    (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100 < 10
  for: 5m
  labels: {severity: critical}

- alert: PVCUsageHigh
  expr: |
    kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes * 100 > 85
  for: 10m
  labels: {severity: warning}

- alert: DeploymentReplicaMismatch
  expr: |
    kube_deployment_spec_replicas != kube_deployment_status_available_replicas
  for: 15m
  labels: {severity: warning}
```

---

## Cardinality Management (Critical for Cost)

**High cardinality = exponential metric storage cost**

```yaml
# Bad — user_id creates millions of time series
http_requests_total{method="GET", user_id="usr_12345"}

# Good — user cohort or status only
http_requests_total{method="GET", plan="premium"}

# OTel Collector — drop high-cardinality attributes
processors:
  attributes:
    actions:
      - key: user.id
        action: delete
      - key: request.id
        action: delete
      - key: session.id
        action: delete

  # Limit metric dimensions
  transform:
    error_mode: ignore
    metric_statements:
      - context: datapoint
        statements:
          - delete_key(attributes, "user.id")
```

**Cardinality analysis**:
```promql
# Find metrics with highest cardinality
topk(10, count by (__name__)({__name__=~".+"}))

# Count unique label combinations
count(count by (service, path) (http_requests_total))
```
