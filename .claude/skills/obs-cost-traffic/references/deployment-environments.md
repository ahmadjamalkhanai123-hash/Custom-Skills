# Deployment Environments
## Environment-Specific Observability, Traffic, and Cost Configurations

---

## Environment Matrix

| Aspect | Local Dev | VPS/Self-Hosted | Cloud (Single) | Multi-Cloud Enterprise |
|--------|-----------|-----------------|----------------|------------------------|
| **Orchestration** | Docker Compose | Docker + Systemd | EKS/GKE/AKS | Multi-cluster K8s |
| **Collector** | otelcol-contrib | otelcol-contrib | ADOT/OTel Operator | OTel Operator + DD Agent |
| **Metrics** | Prometheus | Prometheus | Cloud Metrics + Prom | Datadog / New Relic |
| **Logs** | Loki | Loki | Cloud Logging | Datadog Logs / Splunk |
| **Traces** | Tempo | Tempo/Jaeger | Cloud Trace | Datadog APM |
| **Dashboards** | Grafana OSS | Grafana OSS | Grafana OSS/Cloud | Grafana Enterprise / DD |
| **Traffic** | Traefik | NGINX + HAProxy | Cloud LB + Mesh | Cloudflare + Istio |
| **Cost Tools** | Infracost | Manual + OpenCost | Kubecost + Cloud | CloudHealth + FOCUS |

---

## Tier 1: Local Development

### Docker Compose Observability Stack
```yaml
# docker-compose.observability.yml
services:
  # OTel Collector — central telemetry hub
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.116.0
    command: ["--config=/etc/otelcol-contrib/otelcol-config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otelcol-contrib/otelcol-config.yaml
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
      - "8889:8889"   # Prometheus metrics (self)
    depends_on:
      - loki
      - tempo
      - prometheus

  # Prometheus — metrics storage
  prometheus:
    image: prom/prometheus:v2.51.0
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=7d
      - --web.enable-remote-write-receiver
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"

  # Loki — log aggregation
  loki:
    image: grafana/loki:3.1.0
    command: -config.file=/etc/loki/local-config.yaml
    volumes:
      - loki_data:/loki
    ports:
      - "3100:3100"

  # Promtail — log collector (Docker logs)
  promtail:
    image: grafana/promtail:3.1.0
    command: -config.file=/etc/promtail/promtail.yaml
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /var/log:/var/log
      - ./promtail-config.yaml:/etc/promtail/promtail.yaml

  # Tempo — distributed tracing
  tempo:
    image: grafana/tempo:2.4.1
    command: ["-config.file=/etc/tempo.yaml"]
    volumes:
      - ./tempo.yaml:/etc/tempo.yaml
      - tempo_data:/tmp/tempo
    ports:
      - "3200:3200"   # Tempo API
      - "9411:9411"   # Zipkin (optional)

  # Grafana — unified dashboards
  grafana:
    image: grafana/grafana:11.1.0
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
      - loki
      - tempo

  # Traefik — local load balancer / reverse proxy
  traefik:
    image: traefik:v3.0
    command:
      - --api.insecure=true
      - --providers.docker
      - --entrypoints.web.address=:80
      - --metrics.prometheus=true
      - --metrics.prometheus.buckets=0.1,0.3,1.2,5.0
      - --tracing.otlp=true
      - --tracing.otlp.grpc.endpoint=otel-collector:4317
      - --tracing.otlp.grpc.insecure=true
    ports:
      - "80:80"
      - "8080:8080"   # Traefik dashboard
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro

volumes:
  prometheus_data:
  loki_data:
  tempo_data:
  grafana_data:
```

### Local Grafana Provisioning
```yaml
# grafana/provisioning/datasources/datasources.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true

  - name: Loki
    type: loki
    url: http://loki:3100
    jsonData:
      derivedFields:
        - name: TraceID
          matcherRegex: '"trace_id":"(\w+)"'
          url: "$${__value.raw}"
          datasourceUid: tempo

  - name: Tempo
    type: tempo
    uid: tempo
    url: http://tempo:3200
    jsonData:
      tracesToLogsV2:
        datasourceUid: loki
        filterByTraceID: true
      serviceMap:
        datasourceUid: prometheus
```

---

## Tier 2: VPS / Self-Hosted

### Prometheus + Alertmanager on VPS (Systemd)
```ini
# /etc/systemd/system/prometheus.service
[Unit]
Description=Prometheus
After=network.target

[Service]
Type=simple
User=prometheus
ExecStart=/usr/local/bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --storage.tsdb.retention.time=15d \
  --storage.tsdb.retention.size=50GB \
  --web.console.templates=/etc/prometheus/consoles \
  --web.console.libraries=/etc/prometheus/console_libraries \
  --web.listen-address=0.0.0.0:9090 \
  --web.external-url=https://prometheus.internal.company.com

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### HAProxy + Keepalived (VIP Failover)
```bash
# Keepalived for VIP between two HAProxy nodes
# /etc/keepalived/keepalived.conf (MASTER node)
vrrp_instance VI_1 {
    state MASTER
    interface eth0
    virtual_router_id 51
    priority 101
    advert_int 1
    authentication {
        auth_type PASS
        auth_pass secret123
    }
    virtual_ipaddress {
        10.0.1.100/24   # VIP — clients connect here
    }
    track_script {
        chk_haproxy
    }
}

vrrp_script chk_haproxy {
    script "killall -0 haproxy"
    interval 2
    weight 2
}
```

---

## Tier 3: AWS Cloud

### EKS Observability Setup
```bash
# AWS Distro for OpenTelemetry (ADOT) Operator
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm install adot-operator open-telemetry/opentelemetry-operator \
  --namespace opentelemetry-operator-system \
  --create-namespace

# Container Insights
aws eks create-addon \
  --cluster-name production \
  --addon-name amazon-cloudwatch-observability \
  --configuration-values '{"containerLogs":{"enabled":true}}'
```

```yaml
# OpenTelemetryCollector CR (AWS → Prometheus + CloudWatch)
apiVersion: opentelemetry.io/v1alpha1
kind: OpenTelemetryCollector
metadata:
  name: aws-collector
  namespace: monitoring
spec:
  config: |
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
    exporters:
      awsxray:
        region: us-east-1
      awscloudwatchlogs:
        log_group_name: /eks/production/otel
        region: us-east-1
      prometheus:
        endpoint: "0.0.0.0:8889"
    service:
      pipelines:
        traces:
          receivers: [otlp]
          exporters: [awsxray]
        logs:
          receivers: [otlp]
          exporters: [awscloudwatchlogs]
        metrics:
          receivers: [otlp]
          exporters: [prometheus]
```

### GKE Observability Setup
```bash
# Enable GKE managed Prometheus
gcloud container clusters update production \
  --enable-managed-prometheus \
  --region us-central1

# Workload metrics collection
kubectl apply -f - <<EOF
apiVersion: monitoring.googleapis.com/v1
kind: PodMonitoring
metadata:
  name: order-service
  namespace: production
spec:
  selector:
    matchLabels:
      app: order-service
  endpoints:
    - port: metrics
      interval: 30s
EOF
```

### AKS Observability Setup
```bash
# Enable Azure Monitor Container Insights
az aks enable-addons \
  --resource-group myResourceGroup \
  --name production \
  --addons monitoring \
  --workspace-resource-id /subscriptions/{id}/resourceGroups/{rg}/providers/Microsoft.OperationalInsights/workspaces/{name}

# Deploy OTel Operator
helm install otel-operator open-telemetry/opentelemetry-operator \
  --namespace opentelemetry-operator-system \
  --create-namespace \
  --set "manager.collectorImage.repository=otel/opentelemetry-collector-contrib"
```

---

## Tier 4: Enterprise Multi-Cloud

### Datadog Unified Observability
```yaml
# Datadog Agent (K8s DaemonSet via Helm)
# datadog-values.yaml
datadog:
  apiKey: "${DD_API_KEY}"
  appKey: "${DD_APP_KEY}"
  clusterName: "production-us"
  site: "datadoghq.com"

  logs:
    enabled: true
    containerCollectAll: true
  apm:
    portEnabled: true
    enabled: true
  otlp:
    receiver:
      protocols:
        grpc:
          enabled: true
          endpoint: "0.0.0.0:4317"  # Accept OTel traces
  processAgent:
    enabled: true
  networkMonitoring:
    enabled: true
  universalServiceMonitoring:
    enabled: true
  containerExcllude:
    - "name:datadog-agent"

agents:
  tolerations:
    - operator: Exists

clusterAgent:
  enabled: true
  metricsProvider:
    enabled: true

# LLM Observability
llmObservability:
  enabled: true
  agentlessEnabled: true   # For serverless / Cloud Run
```

### Multi-Cluster Unified View
```yaml
# Thanos for multi-cluster Prometheus federation
# (sidecar on each Prometheus, querier aggregates)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: thanos-querier
spec:
  template:
    spec:
      containers:
        - name: thanos-querier
          image: quay.io/thanos/thanos:v0.36.0
          args:
            - query
            - --http-address=0.0.0.0:9090
            - --grpc-address=0.0.0.0:10901
            - --store=thanos-sidecar-us-east:10901
            - --store=thanos-sidecar-eu-west:10901
            - --store=thanos-sidecar-ap-south:10901
            - --query.replica-label=cluster
```

---

## Environment-Specific Cost Considerations

| Environment | Key Cost Drivers | Optimization |
|-------------|-----------------|--------------|
| **Local Dev** | Engineer time, laptop resources | Docker resource limits, efficient compose |
| **VPS** | VM cost, bandwidth, storage | Reserved VPS, S3 for log archival |
| **AWS** | EC2/EKS nodes, data transfer, CloudWatch | Savings Plans, Kubecost, log filtering |
| **GCP** | GKE nodes, logging ingestion, data egress | CUDs, GKE Autopilot, Log exclusions |
| **Azure** | AKS nodes, Log Analytics ingestion, egress | Reserved, Hybrid Benefit, Log sampling |
| **Multi-Cloud** | Egress costs dominate | CDN, regional data locality, FOCUS analysis |

### Cross-Cloud Egress Cost Reference
| Traffic Type | Approx Cost |
|-------------|-------------|
| Same region, same AZ | Free |
| Same region, cross AZ | $0.01/GB (AWS) |
| Same region, cross VPC | $0.01/GB |
| Internet egress (first 10TB) | $0.09/GB (AWS), $0.085/GB (GCP) |
| Cross-cloud (AWS → GCP) | $0.09/GB + $0.085/GB |
| Cloudflare CDN (cached) | $0 (free tier) |
