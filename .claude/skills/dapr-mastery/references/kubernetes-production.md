# Dapr Kubernetes Production Reference

## Dapr Control Plane Architecture

```
dapr-system namespace:
├── dapr-operator          # Manages Dapr CRDs, component lifecycle
├── dapr-sidecar-injector  # Mutating webhook: injects sidecar
├── dapr-placement         # Actor placement service (stateful)
├── dapr-sentry            # Certificate Authority (mTLS)
└── dapr-scheduler         # Job/reminder scheduler (v1.14+ stable in v1.15)
```

## Production Helm Deployment

```bash
helm repo add dapr https://dapr.github.io/helm-charts/
helm repo update

helm upgrade --install dapr dapr/dapr \
  --namespace dapr-system \
  --create-namespace \
  --version 1.15.x \
  --values dapr-production-values.yaml \
  --wait
```

### Production Helm Values (`dapr-production-values.yaml`)

```yaml
global:
  logLevel: warn             # Use "info" for debug, "warn" for production
  logAsJson: true            # Structured JSON logs
  prometheus:
    enabled: true
    port: 9090
  mtls:
    enabled: true
    workloadCertTTL: 24h
    allowedClockSkew: 15m
  imagePullPolicy: IfNotPresent

dapr_operator:
  replicaCount: 3            # HA: 3 replicas
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
  resources:
    requests: { cpu: "100m", memory: "128Mi" }
    limits: { cpu: "500m", memory: "512Mi" }
  nodeSelector:
    kubernetes.io/os: linux
  tolerations: []
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - topologyKey: kubernetes.io/hostname

dapr_sidecar_injector:
  replicaCount: 3
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
  resources:
    requests: { cpu: "100m", memory: "128Mi" }
    limits: { cpu: "500m", memory: "256Mi" }
  webhookFailurePolicy: Fail   # Fail if injector is down (safe default)

dapr_placement:
  replicaCount: 3             # HA: 3 replicas (required for actors)
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
  resources:
    requests: { cpu: "250m", memory: "256Mi" }
    limits: { cpu: "500m", memory: "512Mi" }
  # Placement uses Raft consensus — needs odd number of replicas (3 or 5)

dapr_sentry:
  replicaCount: 3
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
  resources:
    requests: { cpu: "100m", memory: "128Mi" }
    limits: { cpu: "300m", memory: "256Mi" }

dapr_scheduler:
  replicaCount: 3            # HA for job/reminder scheduling (v1.15+)
  resources:
    requests: { cpu: "100m", memory: "256Mi" }
    limits: { cpu: "500m", memory: "1Gi" }
  # Scheduler uses etcd embedded — needs persistent storage
  volumeClaimTemplates:
    - metadata:
        name: scheduler-data
      spec:
        accessModes: [ReadWriteOnce]
        storageClassName: fast-ssd
        resources:
          requests:
            storage: 10Gi
```

---

## Application Deployment with Dapr Sidecar

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: production
  labels:
    app: order-service
    version: v1
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
        version: v1
      annotations:
        # ── Required Dapr Annotations ──────────────────────────
        dapr.io/enabled: "true"
        dapr.io/app-id: "order-service"
        dapr.io/app-port: "8080"
        dapr.io/app-protocol: "http"     # or "grpc", "https", "grpcs"

        # ── Production Resource Limits ─────────────────────────
        dapr.io/sidecar-cpu-request: "100m"
        dapr.io/sidecar-cpu-limit: "300m"
        dapr.io/sidecar-memory-request: "128Mi"
        dapr.io/sidecar-memory-limit: "256Mi"
        dapr.io/env: "GOMEMLIMIT=230MiB"  # 90% of memory limit

        # ── Observability ──────────────────────────────────────
        dapr.io/enable-metrics: "true"
        dapr.io/metrics-port: "9090"
        dapr.io/enable-api-logging: "true"
        dapr.io/log-level: "warn"
        dapr.io/config: "production-config"     # Dapr Configuration name

        # ── Security ───────────────────────────────────────────
        dapr.io/api-token-secret: "dapr-api-token"  # K8s secret name

        # ── Performance ────────────────────────────────────────
        dapr.io/http-max-request-size: "4"    # MB
        dapr.io/http-read-buffer-size: "4"    # KB
        dapr.io/max-concurrency: "0"           # 0 = unlimited

    spec:
      serviceAccountName: order-service
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: order-service
          image: myregistry/order-service:v1.2.3
          imagePullPolicy: Always
          ports:
            - containerPort: 8080
          resources:
            requests: { cpu: "200m", memory: "256Mi" }
            limits: { cpu: "1000m", memory: "512Mi" }
          env:
            - name: DAPR_HTTP_ENDPOINT
              value: "http://localhost:3500"
            - name: APP_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: dapr-api-token
                  key: token
          livenessProbe:
            httpGet: { path: /healthz, port: 8080 }
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet: { path: /readyz, port: 8080 }
            initialDelaySeconds: 5
            periodSeconds: 10
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: order-service
```

---

## Actor Service Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-actor-service
  namespace: production
spec:
  replicas: 3            # Actor placement requires ≥2 for HA
  selector:
    matchLabels:
      app: order-actor-service
  template:
    metadata:
      annotations:
        dapr.io/enabled: "true"
        dapr.io/app-id: "order-actor-service"
        dapr.io/app-port: "8080"
        dapr.io/sidecar-memory-limit: "512Mi"     # Actors need more memory
        dapr.io/sidecar-cpu-limit: "500m"
        dapr.io/config: "actor-config"             # Config with actor settings
      labels:
        app: order-actor-service
    spec:
      # Graceful shutdown: allow reminders/timers to drain
      terminationGracePeriodSeconds: 90
      containers:
        - name: order-actor-service
          image: myregistry/order-actor:v1.0.0
          ports:
            - containerPort: 8080
          # Actor host endpoints required
          # GET  /healthz/ready
          # GET  /dapr/config (actor type registration)
          # PUT  /actors/{actorType}/{actorId}/method/{method}
          # PUT  /actors/{actorType}/{actorId}/reminders/{name}
          # DELETE /actors/{actorType}/{actorId}/reminders/{name}
```

---

## Workflow Service Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: workflow-service
  namespace: production
spec:
  replicas: 3             # Minimum 2 for HA, scale with load
  template:
    metadata:
      annotations:
        dapr.io/enabled: "true"
        dapr.io/app-id: "workflow-service"
        dapr.io/app-port: "8080"
        dapr.io/sidecar-memory-limit: "512Mi"   # Workflow needs more
        dapr.io/sidecar-cpu-limit: "500m"
        dapr.io/max-concurrency: "10"            # Limit concurrent workflows
    spec:
      terminationGracePeriodSeconds: 120  # Allow in-flight workflows to complete
      containers:
        - name: workflow-service
          image: myregistry/workflow-service:v1.0.0
```

---

## Namespace Organization

```
cluster/
├── dapr-system/          # Dapr control plane (managed separately)
│   ├── dapr-operator
│   ├── dapr-sidecar-injector
│   ├── dapr-placement
│   ├── dapr-sentry
│   └── dapr-scheduler
├── production/           # Production workloads
│   ├── Components (statestore, pubsub, secrets)
│   ├── Resiliency policies
│   ├── Dapr Configurations
│   └── Application Deployments
├── staging/              # Staging (separate components)
└── development/          # Development
```

---

## Horizontal Pod Autoscaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: order-service-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: order-service
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 70
    # KEDA: scale on Kafka consumer lag (for pub/sub services)
    # type: External → kafka_consumer_lag metric
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300   # 5 min before scaling down
      policies:
        - type: Percent
          value: 25
          periodSeconds: 60
```

---

## Multi-Cluster Setup

```yaml
# Cluster A (Primary) — components shared via external backends
# Cluster B (Secondary/DR) — same component configs, different namespaces

# State store (both clusters point to same Redis Cluster or Cosmos DB)
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: global-statestore
spec:
  type: state.azure.cosmosdb    # Global distribution built-in
  metadata:
    - name: url
      secretKeyRef: { name: cosmos-global, key: url }
    - name: consistencyLevel
      value: "Session"           # Or "Strong" for cross-region consistency

# Pub/Sub (use globally replicated broker)
spec:
  type: pubsub.azure.servicebus.topics  # Azure SB is globally replicated
  # OR: Kafka MirrorMaker 2 for cross-cluster replication
```

---

## Dapr Upgrade Strategy

```bash
# 1. Check current version
dapr --version
kubectl get pods -n dapr-system -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].image}{"\n"}{end}'

# 2. Upgrade control plane (rolling)
helm upgrade dapr dapr/dapr \
  --namespace dapr-system \
  --version 1.15.x \
  --values dapr-production-values.yaml \
  --wait

# 3. Restart application pods to get new sidecar version
kubectl rollout restart deployment -n production

# 4. Verify
dapr status -k
```

---

## Production Readiness Checklist

### Control Plane
- [ ] All control plane components: 3+ replicas
- [ ] PodDisruptionBudgets configured
- [ ] Node anti-affinity (spread across nodes)
- [ ] Persistent storage for Scheduler (etcd)
- [ ] Control plane resource limits set

### Applications
- [ ] All sidecar resource limits set (CPU + memory)
- [ ] `GOMEMLIMIT` set to 90% of sidecar memory limit
- [ ] `terminationGracePeriodSeconds` ≥ 60 for actors/workflows
- [ ] Health endpoints: `/healthz/ready`, `/healthz/live`
- [ ] HPA configured for all production services

### Networking
- [ ] NetworkPolicy restricts cross-namespace access
- [ ] Ingress TLS terminated at load balancer
- [ ] Service mesh (optional but recommended: Istio/Linkerd)

### Operations
- [ ] GitOps pipeline for component YAML (ArgoCD/Flux)
- [ ] Helm chart version pinned (not `latest`)
- [ ] Upgrade runbook documented
- [ ] DR tested (simulate Placement service failure)
