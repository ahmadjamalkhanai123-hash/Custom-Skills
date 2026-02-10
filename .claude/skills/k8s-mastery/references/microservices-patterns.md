# Kubernetes Microservices Patterns

Patterns for orchestrating 2 to 500+ services on Kubernetes.

---

## Service Communication Matrix

### Synchronous (Request-Response)

```yaml
# Pattern: HTTP/gRPC between services via ClusterIP
# Service A → Service B
apiVersion: v1
kind: Service
metadata:
  name: payment-service
  namespace: payments
  labels:
    app.kubernetes.io/name: payment-service
    app.kubernetes.io/part-of: checkout-platform
spec:
  selector:
    app.kubernetes.io/name: payment-service
  ports:
    - name: http
      port: 8080
      targetPort: http
    - name: grpc
      port: 9090
      targetPort: grpc
---
# Internal DNS: payment-service.payments.svc.cluster.local
# Short form (same namespace): payment-service
# Cross-namespace: payment-service.payments
```

### Asynchronous (Event-Driven)

```yaml
# Pattern: NATS/Kafka/RabbitMQ for decoupled communication
# Deploy message broker as StatefulSet
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: nats
  namespace: messaging
spec:
  serviceName: nats
  replicas: 3
  selector:
    matchLabels:
      app.kubernetes.io/name: nats
  template:
    spec:
      containers:
        - name: nats
          image: nats:2.10-alpine
          ports:
            - containerPort: 4222
              name: client
            - containerPort: 6222
              name: cluster
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
```

### Communication Decision Guide

```
Between 2 services?
├── Need immediate response? → HTTP REST or gRPC (ClusterIP Service)
├── Fire-and-forget? → Message queue (NATS, RabbitMQ)
├── Event streaming? → Kafka (StatefulSet, 3+ brokers)
├── Large file transfer? → S3-compatible (MinIO) + event notification
└── Real-time bidirectional? → gRPC streaming or WebSocket
```

---

## Service Dependency Management

### Dependency Graph Template

```yaml
# ConfigMap documenting service dependencies (for ops visibility)
apiVersion: v1
kind: ConfigMap
metadata:
  name: service-dependency-map
  namespace: platform
  labels:
    app.kubernetes.io/component: documentation
data:
  dependencies.yaml: |
    services:
      api-gateway:
        depends_on: [auth-service, user-service, product-service]
        type: synchronous
        criticality: critical

      order-service:
        depends_on: [inventory-service, payment-service, notification-service]
        sync_deps: [inventory-service, payment-service]
        async_deps: [notification-service]
        criticality: critical

      notification-service:
        depends_on: [email-provider, sms-provider]
        type: asynchronous
        criticality: low
        degradation: graceful  # App works without notifications
```

### Init Container Dependencies

```yaml
# Wait for dependent services before starting
spec:
  initContainers:
    - name: wait-for-db
      image: busybox:1.36
      command: ['sh', '-c', 'until nc -z postgres.database 5432; do echo waiting for db; sleep 2; done']
    - name: wait-for-cache
      image: busybox:1.36
      command: ['sh', '-c', 'until nc -z redis.cache 6379; do echo waiting for cache; sleep 2; done']
  containers:
    - name: app
      # App starts only after db and cache are ready
```

---

## Multi-Service Deployment Patterns

### Namespace-per-Domain Strategy

```
# For 20+ microservices, organize by business domain
namespaces/
├── checkout/          # order-svc, payment-svc, cart-svc
├── catalog/           # product-svc, search-svc, inventory-svc
├── identity/          # auth-svc, user-svc, profile-svc
├── messaging/         # notification-svc, email-svc, sms-svc
├── observability/     # prometheus, grafana, loki, tempo
├── ingress/           # nginx/gateway controller
└── platform/          # shared infra (databases, caches, queues)
```

### ArgoCD App-of-Apps for Microservices

```yaml
# Root application that manages all microservice apps
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: microservices-platform
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/k8s-manifests.git
    targetRevision: main
    path: apps/
  destination:
    server: https://kubernetes.default.svc
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
---
# Each file in apps/ is an Application pointing to a service
# apps/checkout/order-service.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: order-service
  namespace: argocd
  labels:
    domain: checkout
    tier: critical
spec:
  project: checkout
  source:
    repoURL: https://github.com/org/k8s-manifests.git
    path: services/order-service/overlays/prod
  destination:
    server: https://kubernetes.default.svc
    namespace: checkout
```

### ApplicationSet for Multi-Service Matrix

```yaml
# Deploy all services across all environments
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: microservices
  namespace: argocd
spec:
  generators:
    - matrix:
        generators:
          - git:
              repoURL: https://github.com/org/k8s-manifests.git
              directories:
                - path: services/*
          - list:
              elements:
                - env: dev
                  cluster: dev-cluster
                - env: staging
                  cluster: staging-cluster
                - env: prod
                  cluster: prod-cluster
  template:
    metadata:
      name: '{{path.basename}}-{{env}}'
    spec:
      source:
        repoURL: https://github.com/org/k8s-manifests.git
        path: '{{path}}/overlays/{{env}}'
      destination:
        server: '{{cluster}}'
        namespace: '{{path.basename}}'
```

---

## Resilience Patterns

### Circuit Breaker (Istio)

```yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: payment-service
  namespace: checkout
spec:
  host: payment-service
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        h2UpgradePolicy: DEFAULT
        http1MaxPendingRequests: 100
        http2MaxRequests: 1000
        maxRequestsPerConnection: 10
        maxRetries: 3
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
```

### Retry + Timeout Budgets

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: payment-service
  namespace: checkout
spec:
  hosts:
    - payment-service
  http:
    - route:
        - destination:
            host: payment-service
      timeout: 5s
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: 5xx,reset,connect-failure,retriable-4xx
```

### Rate Limiting (Gateway API + Envoy)

```yaml
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: BackendTrafficPolicy
metadata:
  name: rate-limit-api
  namespace: ingress
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: api-route
  rateLimit:
    type: Global
    global:
      rules:
        - clientSelectors:
            - headers:
                - name: x-api-key
                  type: Distinct
          limit:
            requests: 100
            unit: Minute
```

---

## Distributed Tracing Setup

### OpenTelemetry Collector for Microservices

```yaml
apiVersion: opentelemetry.io/v1beta1
kind: OpenTelemetryCollector
metadata:
  name: otel-collector
  namespace: observability
spec:
  mode: deployment
  config:
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
        send_batch_size: 1024
      # Add service graph processor for dependency visualization
      servicegraph:
        metrics_exporter: prometheus
        latency_histogram_buckets: [1, 2, 5, 10, 50, 100, 500]
    exporters:
      otlp/tempo:
        endpoint: tempo.observability:4317
        tls:
          insecure: true
      prometheus:
        endpoint: 0.0.0.0:8889
    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [batch]
          exporters: [otlp/tempo]
        metrics:
          receivers: [otlp]
          processors: [batch, servicegraph]
          exporters: [prometheus]
```

### Trace Context Propagation

```yaml
# Sidecar injection for auto-instrumentation
apiVersion: opentelemetry.io/v1alpha1
kind: Instrumentation
metadata:
  name: auto-instrumentation
  namespace: checkout
spec:
  propagators:
    - tracecontext
    - baggage
    - b3
  sampler:
    type: parentbased_traceidratio
    argument: "0.1"  # 10% sampling in prod
  python:
    image: ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-python:latest
  java:
    image: ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:latest
  nodejs:
    image: ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-nodejs:latest
```

```yaml
# Add annotation to pods for auto-instrumentation
metadata:
  annotations:
    instrumentation.opentelemetry.io/inject-python: "true"
    # or inject-java, inject-nodejs, inject-dotnet
```

---

## API Gateway Pattern

### Gateway API for Microservices Routing

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: platform-routes
  namespace: ingress
spec:
  parentRefs:
    - name: main-gateway
  rules:
    # Route by path prefix to different services/namespaces
    - matches:
        - path:
            type: PathPrefix
            value: /api/v1/orders
      backendRefs:
        - name: order-service
          namespace: checkout
          port: 8080
    - matches:
        - path:
            type: PathPrefix
            value: /api/v1/products
      backendRefs:
        - name: product-service
          namespace: catalog
          port: 8080
    - matches:
        - path:
            type: PathPrefix
            value: /api/v1/users
      backendRefs:
        - name: user-service
          namespace: identity
          port: 8080
    # Canary: split traffic for new version
    - matches:
        - path:
            type: PathPrefix
            value: /api/v2/orders
      backendRefs:
        - name: order-service-v2
          namespace: checkout
          port: 8080
          weight: 10
        - name: order-service
          namespace: checkout
          port: 8080
          weight: 90
```

---

## Cross-Namespace NetworkPolicy for Microservices

```yaml
# Allow checkout domain services to talk to each other
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-checkout-domain
  namespace: checkout
spec:
  podSelector: {}  # All pods in checkout namespace
  policyTypes: [Ingress, Egress]
  ingress:
    # Allow from same domain
    - from:
        - namespaceSelector:
            matchLabels:
              domain: checkout
    # Allow from API gateway
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress
          podSelector:
            matchLabels:
              app.kubernetes.io/name: gateway
  egress:
    # Allow to same domain
    - to:
        - namespaceSelector:
            matchLabels:
              domain: checkout
    # Allow to shared platform (databases, caches)
    - to:
        - namespaceSelector:
            matchLabels:
              domain: platform
    # Allow DNS
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - protocol: UDP
          port: 53
    # Allow to messaging (async events)
    - to:
        - namespaceSelector:
            matchLabels:
              domain: messaging
```

---

## Scaling Strategy for Microservices

### Per-Service HPA with Custom Metrics

```yaml
# Scale order-service on queue depth (KEDA)
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: order-service-scaler
  namespace: checkout
spec:
  scaleTargetRef:
    name: order-service
  minReplicaCount: 2
  maxReplicaCount: 50
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.observability:9090
        metricName: http_requests_per_second
        query: sum(rate(http_requests_total{service="order-service"}[2m]))
        threshold: "100"  # Scale at 100 RPS per replica
    - type: rabbitmq
      metadata:
        host: amqp://rabbitmq.messaging:5672
        queueName: orders
        queueLength: "50"  # Scale when queue > 50 per replica
```

---

## Health Check Strategy for Microservices

```yaml
# Standardized health endpoints across all services
containers:
  - name: app
    livenessProbe:
      httpGet:
        path: /healthz          # Is process alive?
        port: http
      initialDelaySeconds: 15
      periodSeconds: 20
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz           # Can it serve traffic?
        port: http
      initialDelaySeconds: 5
      periodSeconds: 10
      failureThreshold: 3
    startupProbe:
      httpGet:
        path: /healthz
        port: http
      initialDelaySeconds: 10
      periodSeconds: 5
      failureThreshold: 30      # 150s max startup time
```

### Health Endpoint Contract

```
GET /healthz → 200 if process alive (liveness)
GET /readyz  → 200 if ready to serve (readiness)
  - Checks: DB connection, cache connection, required config loaded
  - Does NOT check: downstream services (avoid cascading failures)
GET /readyz/dependencies → 200 with dependency status (for dashboards only)
  {
    "postgres": "up",
    "redis": "up",
    "payment-provider": "degraded"
  }
```

---

## Microservices Anti-Patterns on K8s

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Readiness checks downstream deps | Cascading failures — one service down takes all | Only check local deps (DB, cache) |
| All services in one namespace | No isolation, RBAC nightmare | Namespace per domain |
| No resource limits | Noisy neighbor, one service OOMs the node | Set requests AND limits on everything |
| Synchronous chains >3 deep | Latency multiplies, reliability drops | Use async (events) for deep chains |
| Shared database across services | Tight coupling, migration hell | Database per service |
| No circuit breaker | Retry storms overwhelm failing service | Istio DestinationRule outlierDetection |
| No distributed tracing | Can't debug cross-service issues | OpenTelemetry + Tempo/Jaeger |
| Manual deployment order | "Deploy A before B" breaks automation | Init containers + readiness gates |
| Hardcoded service URLs | Breaks across environments | Use K8s DNS: `svc.namespace.svc.cluster.local` |
| No PDB per service | Rolling updates take down entire domain | PDB with minAvailable on all prod services |

