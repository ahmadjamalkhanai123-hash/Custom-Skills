# Cost Optimization

Resource right-sizing, autoscaling, spot instances, and FinOps patterns for Kubernetes.

---

## VerticalPodAutoscaler (VPA)

### Recommendation Mode (Safe -- Read-Only)

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: api-gateway-vpa
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-gateway
  updatePolicy:
    updateMode: "Off"               # Recommendation only, no changes applied
  resourcePolicy:
    containerPolicies:
      - containerName: api-gateway
        minAllowed:
          cpu: 100m
          memory: 128Mi
        maxAllowed:
          cpu: "4"
          memory: 4Gi
        controlledResources:
          - cpu
          - memory
```

### Auto Mode (Apply Recommendations)

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: worker-vpa
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: worker
  updatePolicy:
    updateMode: "Auto"              # Evict and recreate with new resources
    minReplicas: 2                  # Keep at least 2 during VPA updates
  resourcePolicy:
    containerPolicies:
      - containerName: worker
        minAllowed:
          cpu: 250m
          memory: 256Mi
        maxAllowed:
          cpu: "8"
          memory: 8Gi
        controlledResources:
          - cpu
          - memory
        controlledValues: RequestsAndLimits
      # Exclude sidecar from VPA control
      - containerName: istio-proxy
        mode: "Off"
```

**VPA Modes**:
- `Off`: Recommendations only (view with `kubectl describe vpa <name>`).
- `Initial`: Apply recommendations only at pod creation (no eviction).
- `Auto`: Evict and recreate pods when recommendations change significantly.
- Never combine VPA and HPA on the same CPU/memory metric -- they conflict.

---

## HorizontalPodAutoscaler (HPA)

### CPU and Memory Scaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-gateway-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-gateway
  minReplicas: 3
  maxReplicas: 50
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
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Percent
          value: 100                # Double pods
          periodSeconds: 60
        - type: Pods
          value: 10                 # Or add 10 pods
          periodSeconds: 60
      selectPolicy: Max             # Use whichever adds more pods
    scaleDown:
      stabilizationWindowSeconds: 300   # Wait 5 min before scaling down
      policies:
        - type: Percent
          value: 10                 # Remove 10% at a time
          periodSeconds: 60
      selectPolicy: Min             # Use conservative scale-down
```

### Custom Metrics Scaling (Prometheus)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: queue-worker-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: queue-worker
  minReplicas: 2
  maxReplicas: 100
  metrics:
    # Scale based on queue depth (from Prometheus via prometheus-adapter)
    - type: External
      external:
        metric:
          name: rabbitmq_queue_messages
          selector:
            matchLabels:
              queue: orders
        target:
          type: AverageValue
          averageValue: "30"        # 30 messages per worker
    # Also scale on request latency
    - type: Pods
      pods:
        metric:
          name: http_request_duration_seconds_p99
        target:
          type: AverageValue
          averageValue: "500m"      # 500ms p99 target
```

---

## Karpenter (Node Autoscaling)

### NodePool

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: general
spec:
  template:
    metadata:
      labels:
        team: platform
        tier: general
    spec:
      requirements:
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64", "arm64"]    # Include Graviton for cost savings
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand"]
        - key: karpenter.k8s.aws/instance-category
          operator: In
          values: ["c", "m", "r"]       # Compute, general, memory optimized
        - key: karpenter.k8s.aws/instance-generation
          operator: Gt
          values: ["5"]                  # 6th gen+ only
        - key: karpenter.k8s.aws/instance-size
          operator: In
          values: ["large", "xlarge", "2xlarge", "4xlarge"]
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: default
      expireAfter: 720h               # Replace nodes every 30 days
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 1m               # Consolidate quickly
  limits:
    cpu: "1000"                        # Max 1000 vCPUs across all nodes
    memory: 2000Gi
  weight: 50                           # Lower priority than critical pool
```

### EC2NodeClass

```yaml
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: default
spec:
  amiSelectorTerms:
    - alias: bottlerocket@latest        # Bottlerocket for security
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: my-cluster
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: my-cluster
  instanceProfile: KarpenterNodeInstanceProfile-my-cluster
  blockDeviceMappings:
    - deviceName: /dev/xvda
      ebs:
        volumeSize: 100Gi
        volumeType: gp3
        iops: 3000
        throughput: 125
        encrypted: true
        deleteOnTermination: true
  tags:
    Environment: production
    ManagedBy: karpenter
```

### Spot-Optimized NodePool (Cost Priority)

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: spot-workers
spec:
  template:
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot"]              # Spot only
        - key: kubernetes.io/arch
          operator: In
          values: ["arm64"]             # Graviton = cheapest
        - key: karpenter.k8s.aws/instance-category
          operator: In
          values: ["c", "m"]
        - key: karpenter.k8s.aws/instance-size
          operator: In
          values: ["xlarge", "2xlarge", "4xlarge", "8xlarge"]
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: default
      # Taint so only tolerating workloads schedule here
      taints:
        - key: karpenter.sh/capacity-type
          value: spot
          effect: NoSchedule
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 30s
  limits:
    cpu: "500"
  weight: 100                          # Prefer spot over on-demand
```

---

## Spot Instance Interruption Handling

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-processor
  namespace: production
spec:
  replicas: 10
  selector:
    matchLabels:
      app: batch-processor
  template:
    metadata:
      labels:
        app: batch-processor
    spec:
      tolerations:
        - key: karpenter.sh/capacity-type
          value: spot
          effect: NoSchedule
      terminationGracePeriodSeconds: 120   # 2 min for graceful shutdown
      containers:
        - name: processor
          image: myregistry/batch-processor:v1.5.0
          lifecycle:
            preStop:
              exec:
                command:
                  - /bin/sh
                  - -c
                  - |
                    # Checkpoint current work
                    curl -X POST http://localhost:8080/checkpoint
                    # Drain in-flight requests
                    sleep 10
          resources:
            requests:
              cpu: "1"
              memory: 2Gi
            limits:
              cpu: "2"
              memory: 4Gi
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: batch-processor
```

---

## Resource Right-Sizing Workflow

### Goldilocks Operator (VPA Recommendations Dashboard)

```yaml
# Install via Helm
# helm install goldilocks fairwinds-stable/goldilocks -n goldilocks-system
# Enable per namespace:
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    goldilocks.fairwinds.com/enabled: "true"
# Goldilocks creates a VPA in "Off" mode for every Deployment and
# exposes a dashboard showing current vs recommended requests/limits.
```

### Right-Sizing Process

1. Deploy VPA in `Off` mode for all workloads.
2. Wait 7 days to collect steady-state + peak usage data.
3. Review recommendations: `kubectl describe vpa -n production`.
4. Compare current requests vs VPA `target` (ideal) and `upperBound` (safety margin).
5. Set requests to VPA `target`, limits to VPA `upperBound`.
6. Repeat quarterly.

---

## Kubecost for Cost Allocation

```yaml
# values.yaml for Kubecost Helm chart
kubecostProductConfigs:
  clusterName: production-us-east-1
  currencyCode: USD
  # Team-based cost allocation
  labelMappedFields:
    team: "team"
    environment: "env"
    product: "product"
  # Alert on cost anomalies
  alerts:
    - type: budget
      threshold: 10000              # $10k monthly budget
      window: monthly
      aggregation: namespace
      filter: production
    - type: spendChange
      threshold: 0.3                # 30% increase triggers alert
      window: 1d
      baselineWindow: 7d
  # Savings recommendations
  savings:
    enabled: true
    # Detect workloads with <10% CPU utilization for 7 days
    idleThreshold: 0.1
    idleWindow: 168h
```

---

## Karpenter vs Cluster Autoscaler Decision

| Factor | Karpenter | Cluster Autoscaler |
|--------|-----------|-------------------|
| Speed | Provisions in seconds | Minutes (ASG-based) |
| Instance diversity | Any instance type | Fixed per node group |
| Spot handling | Native, capacity-optimized | Requires mixed instances policy |
| Consolidation | Built-in, aggressive | None (only scale-down) |
| Graviton/ARM | First-class support | Separate node groups |
| Cloud support | AWS (primary), Azure (preview) | AWS, GCP, Azure, all clouds |
| Complexity | Lower (no ASGs) | Higher (ASG management) |

**Use Karpenter** when: AWS-only, need fast scaling, want spot optimization, diverse instance types.
**Use Cluster Autoscaler** when: multi-cloud, GKE/AKS, simpler requirements, established ASG patterns.

---

## Budget Alerts and FinOps Dashboard

### PrometheusRule for Cost Alerts

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: cost-alerts
  namespace: monitoring
spec:
  groups:
    - name: cost-optimization
      interval: 1h
      rules:
        # Alert when namespace cost exceeds budget
        - alert: NamespaceCostExceeded
          expr: |
            sum by (namespace) (
              rate(container_cpu_usage_seconds_total[1h]) * 0.032  +
              container_memory_working_set_bytes / 1073741824 * 0.004
            ) * 730 > 5000
          for: 6h
          labels:
            severity: warning
          annotations:
            summary: "Namespace {{ $labels.namespace }} projected cost exceeds $5000/month"

        # Alert on idle pods (< 5% CPU for 24h)
        - alert: IdlePodDetected
          expr: |
            avg_over_time(
              rate(container_cpu_usage_seconds_total{container!=""}[5m])[24h:5m]
            ) / on(namespace, pod, container)
            kube_pod_container_resource_requests{resource="cpu"} < 0.05
          for: 24h
          labels:
            severity: info
          annotations:
            summary: "Pod {{ $labels.pod }} in {{ $labels.namespace }} is idle"

        # Alert when requests >> actual usage (over-provisioned)
        - alert: OverProvisionedWorkload
          expr: |
            avg_over_time(
              rate(container_cpu_usage_seconds_total{container!=""}[5m])[7d:1h]
            ) / on(namespace, pod, container)
            kube_pod_container_resource_requests{resource="cpu"} < 0.2
          for: 7d
          labels:
            severity: warning
          annotations:
            summary: "{{ $labels.pod }} uses <20% of requested CPU for 7 days"
```

### ResourceQuota for Budget Enforcement

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-budget
  namespace: team-alpha
spec:
  hard:
    requests.cpu: "100"
    requests.memory: 200Gi
    limits.cpu: "200"
    limits.memory: 400Gi
    persistentvolumeclaims: "50"
    services.loadbalancers: "5"
    # Count-based quotas
    pods: "200"
    services: "50"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: team-alpha
spec:
  limits:
    - type: Container
      default:
        cpu: 500m
        memory: 512Mi
      defaultRequest:
        cpu: 100m
        memory: 128Mi
      min:
        cpu: 50m
        memory: 64Mi
      max:
        cpu: "8"
        memory: 16Gi
    - type: PersistentVolumeClaim
      min:
        storage: 1Gi
      max:
        storage: 100Gi
```
