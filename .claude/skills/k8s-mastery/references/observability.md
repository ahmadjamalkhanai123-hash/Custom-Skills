# Kubernetes Observability Stack

Production-grade observability for Kubernetes: metrics, logs, traces, and alerting.

---

## Prometheus: kube-prometheus-stack

The kube-prometheus-stack Helm chart bundles Prometheus, Grafana, AlertManager, node-exporter,
and kube-state-metrics in a single deployment.

### Helm Values

```yaml
# values-prometheus-stack.yaml
kube-prometheus-stack:
  prometheus:
    prometheusSpec:
      replicas: 2
      retention: 15d
      retentionSize: "40GB"
      resources:
        requests:
          cpu: "1"
          memory: 4Gi
        limits:
          cpu: "2"
          memory: 8Gi
      storageSpec:
        volumeClaimTemplate:
          spec:
            storageClassName: gp3
            accessModes: ["ReadWriteOnce"]
            resources:
              requests:
                storage: 50Gi
      externalLabels:
        cluster: production-us-east-1
      # Scrape interval and evaluation
      scrapeInterval: 30s
      evaluationInterval: 30s
      # Remote write for long-term storage
      remoteWrite:
        - url: http://thanos-receive.monitoring:19291/api/v1/receive
          writeRelabelConfigs:
            - sourceLabels: [__name__]
              regex: "go_.*"
              action: drop
      # Pod anti-affinity for HA
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  app.kubernetes.io/name: prometheus
              topologyKey: kubernetes.io/hostname

  alertmanager:
    alertmanagerSpec:
      replicas: 3
      storage:
        volumeClaimTemplate:
          spec:
            storageClassName: gp3
            resources:
              requests:
                storage: 10Gi

  grafana:
    replicas: 2
    persistence:
      enabled: true
      size: 10Gi
    adminPassword: ""  # Use external secret
    envFromSecret: grafana-secrets
    sidecar:
      dashboards:
        enabled: true
        searchNamespace: ALL
      datasources:
        enabled: true
```

### ServiceMonitor

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: api-service-monitor
  namespace: monitoring
  labels:
    release: kube-prometheus-stack  # Must match Prometheus selector
spec:
  namespaceSelector:
    matchNames:
      - production
      - staging
  selector:
    matchLabels:
      app.kubernetes.io/name: api-server
  endpoints:
    - port: metrics
      path: /metrics
      interval: 15s
      scrapeTimeout: 10s
      metricRelabelings:
        - sourceLabels: [__name__]
          regex: "go_gc_.*"
          action: drop
        - sourceLabels: [__name__]
          regex: "http_request_duration_seconds.*"
          action: keep
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_label_version]
          targetLabel: version
```

### PodMonitor

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: envoy-sidecar-monitor
  namespace: monitoring
spec:
  namespaceSelector:
    matchNames:
      - production
  selector:
    matchLabels:
      sidecar.istio.io/inject: "true"
  podMetricsEndpoints:
    - port: http-envoy-prom
      path: /stats/prometheus
      interval: 30s
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_name]
          targetLabel: pod
        - sourceLabels: [__meta_kubernetes_namespace]
          targetLabel: namespace
```

---

## Grafana Configuration

### Dashboard Provisioning via ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboard-api-overview
  namespace: monitoring
  labels:
    grafana_dashboard: "1"  # Sidecar picks this up
data:
  api-overview.json: |
    {
      "dashboard": {
        "title": "API Service Overview",
        "uid": "api-overview-v1",
        "panels": [
          {
            "title": "Request Rate",
            "type": "timeseries",
            "targets": [{
              "expr": "sum(rate(http_requests_total{namespace=\"production\"}[5m])) by (service)",
              "legendFormat": "{{ service }}"
            }],
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
          },
          {
            "title": "Error Rate %",
            "type": "stat",
            "targets": [{
              "expr": "sum(rate(http_requests_total{status=~\"5..\"}[5m])) / sum(rate(http_requests_total[5m])) * 100"
            }],
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0}
          },
          {
            "title": "P99 Latency",
            "type": "timeseries",
            "targets": [{
              "expr": "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))",
              "legendFormat": "{{ service }}"
            }],
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 8}
          }
        ]
      }
    }
```

### Datasource Configuration

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-datasources
  namespace: monitoring
  labels:
    grafana_datasource: "1"
data:
  datasources.yaml: |
    apiVersion: 1
    datasources:
      - name: Prometheus
        type: prometheus
        access: proxy
        url: http://prometheus-operated.monitoring:9090
        isDefault: true
        jsonData:
          timeInterval: 15s
          httpMethod: POST
      - name: Loki
        type: loki
        access: proxy
        url: http://loki-gateway.monitoring:80
        jsonData:
          derivedFields:
            - datasourceUid: tempo
              matcherRegex: "traceID=(\\w+)"
              name: TraceID
              url: "$${__value.raw}"
      - name: Tempo
        type: tempo
        uid: tempo
        access: proxy
        url: http://tempo-query-frontend.monitoring:3100
        jsonData:
          tracesToLogs:
            datasourceUid: loki
            tags: ["service.name", "k8s.namespace.name"]
          nodeGraph:
            enabled: true
          serviceMap:
            datasourceUid: Prometheus
```

---

## AlertManager Configuration

### Routing Tree and Receivers

```yaml
apiVersion: monitoring.coreos.com/v1alpha1
kind: AlertmanagerConfig
metadata:
  name: production-alerts
  namespace: monitoring
spec:
  route:
    groupBy: ["alertname", "namespace", "service"]
    groupWait: 30s
    groupInterval: 5m
    repeatInterval: 4h
    receiver: default-slack
    routes:
      # Critical alerts -> PagerDuty immediately
      - matchers:
          - name: severity
            value: critical
        receiver: pagerduty-critical
        repeatInterval: 15m
        continue: false
      # Warning alerts -> Slack
      - matchers:
          - name: severity
            value: warning
        receiver: slack-warnings
        groupWait: 1m
        repeatInterval: 1h
      # SLO burn alerts -> OpsGenie
      - matchers:
          - name: alerttype
            value: slo_burn
        receiver: opsgenie-slo
        repeatInterval: 30m

  receivers:
    - name: default-slack
      slackConfigs:
        - apiURL:
            name: alertmanager-slack
            key: webhook-url
          channel: "#alerts-default"
          title: '[{{ .Status | toUpper }}] {{ .CommonLabels.alertname }}'
          text: >-
            *Cluster:* {{ .CommonLabels.cluster }}
            *Namespace:* {{ .CommonLabels.namespace }}
            *Description:* {{ .CommonAnnotations.description }}
          sendResolved: true

    - name: pagerduty-critical
      pagerdutyConfigs:
        - routingKey:
            name: alertmanager-pagerduty
            key: routing-key
          severity: critical
          description: '{{ .CommonLabels.alertname }} in {{ .CommonLabels.namespace }}'
          details:
            - key: cluster
              value: '{{ .CommonLabels.cluster }}'
            - key: runbook
              value: '{{ .CommonAnnotations.runbook_url }}'

    - name: opsgenie-slo
      opsgenieConfigs:
        - apiKey:
            name: alertmanager-opsgenie
            key: api-key
          message: 'SLO Burn: {{ .CommonLabels.alertname }}'
          priority: '{{ if eq .CommonLabels.severity "critical" }}P1{{ else }}P2{{ end }}'
          tags: "slo,kubernetes,{{ .CommonLabels.service }}"
```

---

## SLO/SLI Alerting with PrometheusRule

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: slo-alerts
  namespace: monitoring
  labels:
    release: kube-prometheus-stack
spec:
  groups:
    # --- Availability SLO: 99.9% success rate ---
    - name: slo.availability
      interval: 30s
      rules:
        # SLI: success rate over 5m
        - record: sli:http_availability:rate5m
          expr: |
            sum(rate(http_requests_total{status!~"5.."}[5m])) by (service, namespace)
            /
            sum(rate(http_requests_total[5m])) by (service, namespace)

        # Multi-window burn rate alerts (Google SRE approach)
        # Fast burn: 14.4x burn rate over 1h (consumes 2% budget in 1h)
        - alert: SLOAvailabilityBurnRateCritical
          expr: |
            (
              1 - sli:http_availability:rate5m
            ) > (14.4 * 0.001)
            and
            (
              1 - (
                sum(rate(http_requests_total{status!~"5.."}[1h])) by (service, namespace)
                /
                sum(rate(http_requests_total[1h])) by (service, namespace)
              )
            ) > (14.4 * 0.001)
          for: 2m
          labels:
            severity: critical
            alerttype: slo_burn
          annotations:
            summary: "High error budget burn rate for {{ $labels.service }}"
            description: "Service {{ $labels.service }} is burning error budget 14.4x faster than allowed. Current availability: {{ $value | humanizePercentage }}"
            runbook_url: "https://runbooks.example.com/slo-burn-critical"

        # Slow burn: 1x burn rate over 3d (on track to exhaust monthly budget)
        - alert: SLOAvailabilityBurnRateWarning
          expr: |
            (
              1 - (
                sum(rate(http_requests_total{status!~"5.."}[6h])) by (service, namespace)
                /
                sum(rate(http_requests_total[6h])) by (service, namespace)
              )
            ) > (1 * 0.001)
            and
            (
              1 - (
                sum(rate(http_requests_total{status!~"5.."}[3d])) by (service, namespace)
                /
                sum(rate(http_requests_total[3d])) by (service, namespace)
              )
            ) > (1 * 0.001)
          for: 1h
          labels:
            severity: warning
            alerttype: slo_burn
          annotations:
            summary: "Slow error budget burn for {{ $labels.service }}"
            description: "Service {{ $labels.service }} is on track to exhaust its monthly error budget."

    # --- Latency SLO: 99th percentile < 500ms ---
    - name: slo.latency
      interval: 30s
      rules:
        - record: sli:http_latency_p99:5m
          expr: |
            histogram_quantile(0.99,
              sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service, namespace)
            )

        - alert: SLOLatencyP99Critical
          expr: sli:http_latency_p99:5m > 0.5
          for: 5m
          labels:
            severity: critical
            alerttype: slo_burn
          annotations:
            summary: "P99 latency exceeds 500ms for {{ $labels.service }}"
            description: "P99 latency is {{ $value | humanizeDuration }} (SLO: 500ms)"

        # Error budget remaining
        - record: slo:error_budget_remaining:ratio
          expr: |
            1 - (
              (1 - sli:http_availability:rate5m) / 0.001
            )
```

---

## Loki: Log Aggregation

### Loki with Promtail

```yaml
# Loki Helm values
loki:
  auth_enabled: false
  commonConfig:
    replication_factor: 3
  schemaConfig:
    configs:
      - from: "2024-01-01"
        store: tsdb
        object_store: s3
        schema: v13
        index:
          prefix: loki_index_
          period: 24h
  storage:
    type: s3
    bucketNames:
      chunks: loki-chunks-prod
      ruler: loki-ruler-prod
    s3:
      region: us-east-1
      endpoint: null  # Use default AWS endpoint
  limits_config:
    retention_period: 30d
    max_query_length: 721h
    max_entries_limit_per_query: 10000
    ingestion_rate_mb: 16
    ingestion_burst_size_mb: 32

# Promtail Helm values
promtail:
  config:
    clients:
      - url: http://loki-gateway.monitoring/loki/api/v1/push
    snippets:
      pipelineStages:
        - cri: {}
        - json:
            expressions:
              level: level
              msg: msg
              trace_id: traceID
        - labels:
            level:
            trace_id:
        - timestamp:
            source: time
            format: RFC3339Nano
        - output:
            source: msg
```

### Fluent Bit Alternative

```yaml
# Fluent Bit Helm values
fluent-bit:
  config:
    inputs: |
      [INPUT]
          Name              tail
          Tag               kube.*
          Path              /var/log/containers/*.log
          Parser            cri
          DB                /var/log/flb_kube.db
          Mem_Buf_Limit     64MB
          Skip_Long_Lines   On
          Refresh_Interval  10

    filters: |
      [FILTER]
          Name                kubernetes
          Match               kube.*
          Kube_URL            https://kubernetes.default.svc:443
          Kube_Tag_Prefix     kube.var.log.containers.
          Merge_Log           On
          K8S-Logging.Parser  On
          K8S-Logging.Exclude Off

      [FILTER]
          Name    grep
          Match   kube.*
          Exclude log ^$

    outputs: |
      [OUTPUT]
          Name          loki
          Match         kube.*
          Host          loki-gateway.monitoring
          Port          80
          Labels        job=fluentbit, namespace=$kubernetes['namespace_name'], pod=$kubernetes['pod_name']
          Auto_Kubernetes_Labels Off
          Line_Format   json
```

### Key LogQL Queries

```
# Error logs by service
{namespace="production"} |= "error" | json | line_format "{{.service}}: {{.msg}}"

# Log volume by namespace
sum(rate({namespace=~".+"} [5m])) by (namespace)

# Slow requests (>1s) from structured logs
{namespace="production", app="api"} | json | latency_ms > 1000 | line_format "{{.method}} {{.path}} {{.latency_ms}}ms"

# Top 10 error messages
topk(10, sum(count_over_time({namespace="production"} |= "error" | json [1h])) by (msg))

# Correlate logs with trace ID
{namespace="production"} |= "traceID" | json | trace_id = "abc123def456"
```

---

## Tempo: Distributed Tracing

```yaml
# Tempo Helm values
tempo:
  traces:
    otlp:
      grpc:
        enabled: true
      http:
        enabled: true
    zipkin:
      enabled: true
    jaeger:
      thriftHttp:
        enabled: true
  storage:
    trace:
      backend: s3
      s3:
        bucket: tempo-traces-prod
        endpoint: s3.us-east-1.amazonaws.com
        region: us-east-1
      wal:
        path: /var/tempo/wal
      block:
        bloom_filter_false_positive: 0.05
        v2_index_downsample_bytes: 1000
        v2_encoding: zstd
  metricsGenerator:
    enabled: true
    remoteWriteUrl: http://prometheus-operated.monitoring:9090/api/v1/write
  overrides:
    defaults:
      metrics_generator:
        processors:
          - service-graphs
          - span-metrics
```

---

## Thanos: Multi-Cluster Metrics Federation

```yaml
# Thanos Sidecar (added to Prometheus)
kube-prometheus-stack:
  prometheus:
    prometheusSpec:
      thanos:
        objectStorageConfig:
          existingSecret:
            name: thanos-objstore-config
            key: objstore.yml

---
# Thanos object store secret
apiVersion: v1
kind: Secret
metadata:
  name: thanos-objstore-config
  namespace: monitoring
stringData:
  objstore.yml: |
    type: S3
    config:
      bucket: thanos-metrics-prod
      endpoint: s3.us-east-1.amazonaws.com
      region: us-east-1

---
# Thanos Query (central query layer)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: thanos-query
  namespace: monitoring
spec:
  replicas: 2
  selector:
    matchLabels:
      app: thanos-query
  template:
    metadata:
      labels:
        app: thanos-query
    spec:
      containers:
        - name: thanos-query
          image: quay.io/thanos/thanos:v0.35.0
          args:
            - query
            - --log.level=info
            - --query.replica-label=prometheus_replica
            - --query.auto-downsampling
            # Sidecar endpoints from each cluster
            - --endpoint=dnssrv+_grpc._tcp.thanos-sidecar-us-east.monitoring.svc
            - --endpoint=dnssrv+_grpc._tcp.thanos-sidecar-eu-west.monitoring.svc
            # Store gateway for historical data
            - --endpoint=dnssrv+_grpc._tcp.thanos-store-gateway.monitoring.svc
          ports:
            - name: http
              containerPort: 10902
            - name: grpc
              containerPort: 10901
          resources:
            requests:
              cpu: 500m
              memory: 1Gi

---
# Thanos Store Gateway (long-term S3 queries)
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: thanos-store-gateway
  namespace: monitoring
spec:
  replicas: 3
  selector:
    matchLabels:
      app: thanos-store
  template:
    metadata:
      labels:
        app: thanos-store
    spec:
      containers:
        - name: thanos-store
          image: quay.io/thanos/thanos:v0.35.0
          args:
            - store
            - --data-dir=/var/thanos/store
            - --objstore.config-file=/etc/thanos/objstore.yml
            - --index-cache-size=1GB
            - --chunk-pool-size=4GB
          volumeMounts:
            - name: data
              mountPath: /var/thanos/store
            - name: objstore-config
              mountPath: /etc/thanos
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        storageClassName: gp3
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 50Gi

---
# Thanos Compactor (downsampling + compaction)
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: thanos-compactor
  namespace: monitoring
spec:
  replicas: 1  # Must be singleton
  selector:
    matchLabels:
      app: thanos-compactor
  template:
    spec:
      containers:
        - name: thanos-compactor
          image: quay.io/thanos/thanos:v0.35.0
          args:
            - compact
            - --data-dir=/var/thanos/compact
            - --objstore.config-file=/etc/thanos/objstore.yml
            - --retention.resolution-raw=30d
            - --retention.resolution-5m=180d
            - --retention.resolution-1h=365d
            - --compact.concurrency=4
            - --downsample.concurrency=4
            - --wait
```

---

## OpenTelemetry Collector

```yaml
apiVersion: opentelemetry.io/v1beta1
kind: OpenTelemetryCollector
metadata:
  name: otel-collector
  namespace: monitoring
spec:
  mode: deployment
  replicas: 2
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: "1"
      memory: 2Gi
  config:
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318
      prometheus:
        config:
          scrape_configs:
            - job_name: otel-collector
              scrape_interval: 15s
              static_configs:
                - targets: ["0.0.0.0:8888"]
      k8s_events:
        auth_type: serviceAccount
        namespaces: [production, staging]

    processors:
      batch:
        send_batch_size: 1024
        send_batch_max_size: 2048
        timeout: 5s
      memory_limiter:
        check_interval: 1s
        limit_mib: 1536
        spike_limit_mib: 512
      resource:
        attributes:
          - key: cluster
            value: production-us-east-1
            action: upsert
      filter:
        error_mode: ignore
        traces:
          span:
            - 'attributes["http.target"] == "/healthz"'
            - 'attributes["http.target"] == "/readyz"'
      tail_sampling:
        decision_wait: 10s
        policies:
          - name: errors
            type: status_code
            status_code:
              status_codes: [ERROR]
          - name: slow-traces
            type: latency
            latency:
              threshold_ms: 1000
          - name: probabilistic
            type: probabilistic
            probabilistic:
              sampling_percentage: 10

    exporters:
      otlp/tempo:
        endpoint: tempo-distributor.monitoring:4317
        tls:
          insecure: true
      prometheusremotewrite:
        endpoint: http://prometheus-operated.monitoring:9090/api/v1/write
        resource_to_telemetry_conversion:
          enabled: true
      loki:
        endpoint: http://loki-gateway.monitoring:80/loki/api/v1/push
        default_labels_enabled:
          exporter: false
          job: true

    extensions:
      health_check:
        endpoint: 0.0.0.0:13133
      zpages:
        endpoint: 0.0.0.0:55679

    service:
      extensions: [health_check, zpages]
      pipelines:
        traces:
          receivers: [otlp]
          processors: [memory_limiter, resource, filter, tail_sampling, batch]
          exporters: [otlp/tempo]
        metrics:
          receivers: [otlp, prometheus]
          processors: [memory_limiter, resource, batch]
          exporters: [prometheusremotewrite]
        logs:
          receivers: [otlp, k8s_events]
          processors: [memory_limiter, resource, batch]
          exporters: [loki]
      telemetry:
        logs:
          level: info
        metrics:
          address: 0.0.0.0:8888
```

---

## Key Dashboards

### Cluster Overview Queries

```promql
# Node CPU utilization
1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) by (instance)

# Node memory utilization
1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)

# Cluster pod capacity
sum(kube_pod_info) / sum(kube_node_status_allocatable{resource="pods"}) * 100

# Cluster CPU allocation
sum(kube_pod_container_resource_requests{resource="cpu"}) / sum(kube_node_status_allocatable{resource="cpu"}) * 100
```

### Namespace Workloads Queries

```promql
# Pods not ready by namespace
sum(kube_pod_status_ready{condition="false"}) by (namespace)

# Deployment replicas mismatch
kube_deployment_spec_replicas != kube_deployment_status_ready_replicas

# Container restart rate
sum(rate(kube_pod_container_status_restarts_total[15m])) by (namespace, pod) > 0

# PVC usage percentage
kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes * 100
```

### Pod Resources Queries

```promql
# CPU throttling by pod
sum(rate(container_cpu_cfs_throttled_periods_total[5m])) by (pod, namespace)
/
sum(rate(container_cpu_cfs_periods_total[5m])) by (pod, namespace) * 100

# OOM kill events
kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}

# Pod CPU usage vs request
sum(rate(container_cpu_usage_seconds_total[5m])) by (pod, namespace)
/
sum(kube_pod_container_resource_requests{resource="cpu"}) by (pod, namespace)

# Pod memory usage vs limit
sum(container_memory_working_set_bytes) by (pod, namespace)
/
sum(kube_pod_container_resource_limits{resource="memory"}) by (pod, namespace)
```

---

## Production Checklist

| Component | Concern | Recommendation |
|-----------|---------|----------------|
| Prometheus | Retention | 15d local, Thanos for long-term |
| Prometheus | HA | 2 replicas with pod anti-affinity |
| AlertManager | HA | 3 replicas, gossip cluster |
| Grafana | Persistence | External PostgreSQL or PVC |
| Loki | Storage | S3/GCS with TSDB schema v13 |
| Tempo | Sampling | Tail sampling at collector, 10% baseline |
| Thanos | Compaction | Singleton compactor, retention policies |
| OTel Collector | Memory | memory_limiter processor always first |
| All | RBAC | Namespace-scoped ServiceMonitors, read-only Grafana for devs |
| All | Cost | Drop unnecessary metrics via relabeling, log retention limits |
