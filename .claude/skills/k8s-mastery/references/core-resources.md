# Core Kubernetes Resources

Production-ready patterns for Deployments, StatefulSets, Jobs, DaemonSets, Services, ConfigMaps, Secrets, and health probes.

---

## Deployment (apps/v1)

### Production Deployment with Rolling Update

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  namespace: payments
  labels:
    app.kubernetes.io/name: api-server
    app.kubernetes.io/version: "1.4.2"
    app.kubernetes.io/component: backend
    app.kubernetes.io/part-of: payments-platform
    app.kubernetes.io/managed-by: helm
spec:
  replicas: 3
  revisionHistoryLimit: 5
  selector:
    matchLabels:
      app.kubernetes.io/name: api-server
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1          # one extra pod during rollout
      maxUnavailable: 0     # zero downtime
  template:
    metadata:
      labels:
        app.kubernetes.io/name: api-server
        app.kubernetes.io/version: "1.4.2"
        app.kubernetes.io/component: backend
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: api-server
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 45
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: api-server
          image: registry.example.com/api-server@sha256:abc123...
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          env:
            - name: DB_HOST
              valueFrom:
                configMapKeyRef:
                  name: api-server-config
                  key: db-host
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: api-server-secrets
                  key: db-password
          envFrom:
            - configMapRef:
                name: api-server-env
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            - name: config
              mountPath: /etc/app/config.yaml
              subPath: config.yaml
              readOnly: true
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 10
            periodSeconds: 5
            failureThreshold: 30    # 30 * 5s = 150s max startup
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 10"]  # drain in-flight
      volumes:
        - name: tmp
          emptyDir: {}
        - name: config
          configMap:
            name: api-server-config
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: api-server
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: api-server
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: app.kubernetes.io/name
                      operator: In
                      values: ["api-server"]
                topologyKey: kubernetes.io/hostname
```

### Rolling Update Strategy Decision Tree

```
What is the workload type?

Stateless web/API (zero downtime required)?
  -> maxSurge: 1, maxUnavailable: 0

Stateless worker (some downtime OK)?
  -> maxSurge: 0, maxUnavailable: 1

Fast rollout (large replicas, capacity to spare)?
  -> maxSurge: 25%, maxUnavailable: 25%

Single replica (dev/staging)?
  -> Recreate strategy (type: Recreate)
```

### PodDisruptionBudget

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-server
  namespace: payments
spec:
  minAvailable: 2          # or use maxUnavailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: api-server
```

### HorizontalPodAutoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server
  namespace: payments
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
  minReplicas: 3
  maxReplicas: 20
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Percent
          value: 50
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Pods
          value: 1
          periodSeconds: 120
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

---

## StatefulSet (apps/v1)

### Database StatefulSet with Persistent Storage

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: data
  labels:
    app.kubernetes.io/name: postgres
    app.kubernetes.io/component: database
spec:
  serviceName: postgres-headless    # required headless service
  replicas: 3
  podManagementPolicy: OrderedReady  # sequential start: 0, 1, 2
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: postgres
  template:
    metadata:
      labels:
        app.kubernetes.io/name: postgres
        app.kubernetes.io/component: database
    spec:
      serviceAccountName: postgres
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 120
      securityContext:
        runAsNonRoot: true
        runAsUser: 999
        fsGroup: 999
        seccompProfile:
          type: RuntimeDefault
      initContainers:
        - name: init-permissions
          image: busybox:1.36
          command: ["sh", "-c", "chown -R 999:999 /var/lib/postgresql/data"]
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
          securityContext:
            runAsUser: 0
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
              add: ["CHOWN", "FOWNER"]
      containers:
        - name: postgres
          image: postgres:16.2-alpine@sha256:def456...
          ports:
            - name: tcp-pg
              containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: appdb
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-credentials
                  key: username
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-credentials
                  key: password
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: "2"
              memory: 2Gi
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
            - name: tmp
              mountPath: /tmp
            - name: run
              mountPath: /var/run/postgresql
          livenessProbe:
            exec:
              command: ["pg_isready", "-U", "$(POSTGRES_USER)", "-d", "$(POSTGRES_DB)"]
            initialDelaySeconds: 30
            periodSeconds: 15
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "$(POSTGRES_USER)", "-d", "$(POSTGRES_DB)"]
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 3
          startupProbe:
            exec:
              command: ["pg_isready", "-U", "$(POSTGRES_USER)", "-d", "$(POSTGRES_DB)"]
            periodSeconds: 10
            failureThreshold: 30
      volumes:
        - name: tmp
          emptyDir: {}
        - name: run
          emptyDir: {}
  volumeClaimTemplates:
    - metadata:
        name: data
        labels:
          app.kubernetes.io/name: postgres
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: gp3-encrypted
        resources:
          requests:
            storage: 50Gi
```

### Headless Service for StatefulSet

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-headless
  namespace: data
  labels:
    app.kubernetes.io/name: postgres
spec:
  type: ClusterIP
  clusterIP: None           # headless: no cluster IP
  publishNotReadyAddresses: true
  ports:
    - name: tcp-pg
      port: 5432
      targetPort: tcp-pg
  selector:
    app.kubernetes.io/name: postgres
# DNS: postgres-0.postgres-headless.data.svc.cluster.local
```

---

## Jobs and CronJobs (batch/v1)

### One-Shot Job

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration-v1-4-2
  namespace: payments
  labels:
    app.kubernetes.io/name: db-migration
    app.kubernetes.io/version: "1.4.2"
spec:
  backoffLimit: 3                # retry up to 3 times on failure
  activeDeadlineSeconds: 600     # kill after 10 minutes total
  ttlSecondsAfterFinished: 86400 # auto-cleanup after 24h
  template:
    metadata:
      labels:
        app.kubernetes.io/name: db-migration
    spec:
      restartPolicy: Never       # job controller handles retries
      serviceAccountName: db-migration
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: migrate
          image: registry.example.com/db-migrate@sha256:mig789...
          command: ["python", "manage.py", "migrate", "--noinput"]
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: api-server-secrets
                  key: database-url
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
```

### CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: report-generator
  namespace: analytics
  labels:
    app.kubernetes.io/name: report-generator
    app.kubernetes.io/component: batch
spec:
  schedule: "0 2 * * *"          # daily at 02:00 UTC
  timeZone: "UTC"
  concurrencyPolicy: Forbid      # skip if previous still running
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  startingDeadlineSeconds: 300    # skip if missed by 5 min
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 3600  # max 1 hour
      ttlSecondsAfterFinished: 172800
      template:
        metadata:
          labels:
            app.kubernetes.io/name: report-generator
        spec:
          restartPolicy: OnFailure
          serviceAccountName: report-generator
          automountServiceAccountToken: false
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
            seccompProfile:
              type: RuntimeDefault
          containers:
            - name: report
              image: registry.example.com/reports@sha256:rpt012...
              command: ["python", "generate_report.py"]
              resources:
                requests:
                  cpu: 500m
                  memory: 512Mi
                limits:
                  cpu: "1"
                  memory: 1Gi
              securityContext:
                allowPrivilegeEscalation: false
                readOnlyRootFilesystem: true
                capabilities:
                  drop: ["ALL"]
```

### ConcurrencyPolicy Decision

```
Allow   -> multiple job instances can run in parallel
Forbid  -> skip new run if previous still active (most common)
Replace -> kill running job and start new one
```

---

## DaemonSet (apps/v1)

### Node-Level Agent

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentbit
  namespace: observability
  labels:
    app.kubernetes.io/name: fluentbit
    app.kubernetes.io/component: logging
spec:
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: fluentbit
  template:
    metadata:
      labels:
        app.kubernetes.io/name: fluentbit
    spec:
      serviceAccountName: fluentbit
      automountServiceAccountToken: true   # needs API access
      tolerations:
        - operator: Exists                 # run on ALL nodes
      priorityClassName: system-node-critical
      securityContext:
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: fluentbit
          image: fluent/fluent-bit:3.1@sha256:fb345...
          ports:
            - name: http-metrics
              containerPort: 2020
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: varlog
              mountPath: /var/log
              readOnly: true
            - name: containers
              mountPath: /var/lib/docker/containers
              readOnly: true
            - name: config
              mountPath: /fluent-bit/etc/
              readOnly: true
          livenessProbe:
            httpGet:
              path: /api/v1/health
              port: http-metrics
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /api/v1/health
              port: http-metrics
            periodSeconds: 15
      volumes:
        - name: varlog
          hostPath:
            path: /var/log
        - name: containers
          hostPath:
            path: /var/lib/docker/containers
        - name: config
          configMap:
            name: fluentbit-config
```

---

## Services (v1)

### ClusterIP (default, internal)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api-server
  namespace: payments
  labels:
    app.kubernetes.io/name: api-server
spec:
  type: ClusterIP
  ports:
    - name: http
      port: 80
      targetPort: http       # named port on container
      protocol: TCP
  selector:
    app.kubernetes.io/name: api-server
```

### LoadBalancer (external, cloud)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api-public
  namespace: payments
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
    service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"
    service.beta.kubernetes.io/aws-load-balancer-cross-zone-load-balancing-enabled: "true"
    service.beta.kubernetes.io/aws-load-balancer-ssl-cert: "arn:aws:acm:us-east-1:123456789:certificate/abc"
    service.beta.kubernetes.io/aws-load-balancer-ssl-ports: "443"
spec:
  type: LoadBalancer
  externalTrafficPolicy: Local   # preserve client IP
  ports:
    - name: https
      port: 443
      targetPort: http
      protocol: TCP
  selector:
    app.kubernetes.io/name: api-server
```

### NodePort (bare metal, testing)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api-nodeport
  namespace: payments
spec:
  type: NodePort
  ports:
    - name: http
      port: 80
      targetPort: http
      nodePort: 30080       # fixed port (30000-32767)
  selector:
    app.kubernetes.io/name: api-server
```

### ExternalName (alias to external service)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: external-db
  namespace: payments
spec:
  type: ExternalName
  externalName: mydb.us-east-1.rds.amazonaws.com
# Access as: external-db.payments.svc.cluster.local
```

### Service Type Decision Tree

```
Is the service internal only?
  YES -> ClusterIP (default)
  NO  -> Needs external access?
    Cloud LB available?
      YES -> LoadBalancer (with NLB annotations)
    Bare metal / testing?
      YES -> NodePort
    Pointing to external service?
      YES -> ExternalName
    Need stable DNS for StatefulSet pods?
      YES -> Headless (clusterIP: None)
```

---

## ConfigMap and Secret (v1)

### ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: api-server-config
  namespace: payments
  labels:
    app.kubernetes.io/name: api-server
data:
  db-host: "postgres-0.postgres-headless.data.svc.cluster.local"
  log-level: "info"
  config.yaml: |
    server:
      port: 8080
      read_timeout: 30s
      write_timeout: 30s
    cache:
      ttl: 300
      max_size: 1000
```

### Secret (Opaque)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: api-server-secrets
  namespace: payments
  labels:
    app.kubernetes.io/name: api-server
type: Opaque
stringData:                      # use stringData (plain text input)
  db-password: "REPLACE_IN_CI"   # never commit real values
  api-key: "REPLACE_IN_CI"
# Note: stringData is auto-encoded to base64 in data on apply
```

### Mounting Patterns

```yaml
# As environment variables (individual keys)
env:
  - name: DB_HOST
    valueFrom:
      configMapKeyRef:
        name: api-server-config
        key: db-host

# As environment variables (all keys)
envFrom:
  - configMapRef:
      name: api-server-env
  - secretRef:
      name: api-server-secrets

# As volume (file mount, preferred for secrets)
volumes:
  - name: config
    configMap:
      name: api-server-config
      items:
        - key: config.yaml
          path: config.yaml
  - name: secrets
    secret:
      secretName: api-server-secrets
      defaultMode: 0400       # read-only for owner
```

---

## Health Probe Patterns

### Probe Type Decision Tree

```
Is there an HTTP health endpoint?
  YES -> httpGet probe (most common)
  NO  -> Can you run a CLI command?
    YES -> exec probe (databases, custom checks)
    NO  -> Is the service TCP only?
      YES -> tcpSocket probe (Redis, Kafka)

Which probe types to use?
  startupProbe  -> slow-starting apps (JVM, ML models, DB init)
  readinessProbe -> always (controls Service traffic)
  livenessProbe  -> always (detects deadlocks, hangs)
```

### HTTP Probe (most common)

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: http
    httpHeaders:              # optional auth header
      - name: Authorization
        value: Bearer internal-health-token
  initialDelaySeconds: 15
  periodSeconds: 20
  timeoutSeconds: 5
  successThreshold: 1
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 3
  successThreshold: 1
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /healthz
    port: http
  initialDelaySeconds: 10
  periodSeconds: 5
  failureThreshold: 30       # 30 * 5s = 150s max startup time
```

### Exec Probe (databases)

```yaml
livenessProbe:
  exec:
    command:
      - pg_isready
      - -U
      - postgres
  periodSeconds: 15
  failureThreshold: 3
```

### TCP Socket Probe (Redis, Kafka)

```yaml
readinessProbe:
  tcpSocket:
    port: 6379
  periodSeconds: 10
  failureThreshold: 3
```

### gRPC Probe (gRPC services)

```yaml
readinessProbe:
  grpc:
    port: 50051
    service: ""               # empty = overall health
  periodSeconds: 10
  failureThreshold: 3
```

### Probe Timing Best Practices

| Setting | Liveness | Readiness | Startup |
|---------|----------|-----------|---------|
| initialDelaySeconds | 15-30 | 5-10 | 0-10 |
| periodSeconds | 15-30 | 5-10 | 5-10 |
| timeoutSeconds | 3-5 | 3-5 | 3-5 |
| failureThreshold | 3 | 3 | 20-60 |
| successThreshold | 1 | 1-2 | 1 |

### Graceful Shutdown Pattern

```yaml
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: app
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 10"]
            # Sleep allows endpoint removal to propagate
            # before SIGTERM stops accepting new requests
```

---

## Resource Sizing Guidelines

| Workload Type | CPU Request | CPU Limit | Memory Request | Memory Limit |
|---------------|-------------|-----------|----------------|--------------|
| Web/API (light) | 100m | 500m | 128Mi | 256Mi |
| Web/API (medium) | 250m | 1000m | 256Mi | 512Mi |
| Web/API (heavy) | 500m | 2000m | 512Mi | 1Gi |
| Worker/Consumer | 250m | 1000m | 256Mi | 512Mi |
| Database (small) | 500m | 2000m | 1Gi | 2Gi |
| Database (large) | 2000m | 4000m | 4Gi | 8Gi |
| Cache (Redis) | 100m | 500m | 256Mi | 512Mi |
| Batch Job | 500m | 2000m | 512Mi | 1Gi |

**Rules:**
- Always set requests AND limits
- Memory limit = 1.5x to 2x request (avoid OOMKilled)
- CPU limit = 2x to 4x request (allow bursting)
- Use VPA recommendations in production to right-size
- For Java/JVM: set -Xmx to 75% of memory limit
