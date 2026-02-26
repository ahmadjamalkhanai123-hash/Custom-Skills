# Service Mesh Federation Reference

## Istio Multi-Cluster

Istio supports cross-cluster service discovery and mTLS federation.
Two primary topologies: **multi-primary** (each cluster has control plane)
vs **primary-remote** (one control plane manages all).

### Multi-Primary (Recommended for Production)

Each cluster runs its own Istio control plane. East-west gateways bridge clusters.

```
Cluster AWS-EKS                    Cluster GCP-GKE
┌─────────────────────┐            ┌─────────────────────┐
│  istiod             │            │  istiod             │
│  Pods (east-west GW)│◄──mTLS────►│  Pods (east-west GW)│
│  Services           │            │  Services           │
└─────────────────────┘            └─────────────────────┘
```

#### Step 1: Install Istio with Multi-Cluster Config

```bash
# Cluster 1 (AWS)
istioctl install -f - <<EOF
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
spec:
  values:
    global:
      meshID: mesh1
      multiCluster:
        clusterName: aws-eks
      network: network-aws
EOF

# Cluster 2 (GCP) — same meshID, different clusterName + network
istioctl install -f - <<EOF
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
spec:
  values:
    global:
      meshID: mesh1
      multiCluster:
        clusterName: gcp-gke
      network: network-gcp
EOF
```

#### Step 2: Deploy East-West Gateways

```bash
# Install east-west gateway on each cluster
samples/multicluster/gen-eastwest-gateway.sh \
  --mesh mesh1 \
  --cluster aws-eks \
  --network network-aws | istioctl install --context=aws-eks -y -f -

samples/multicluster/gen-eastwest-gateway.sh \
  --mesh mesh1 \
  --cluster gcp-gke \
  --network network-gcp | istioctl install --context=gcp-gke -y -f -
```

#### Step 3: Expose Services Through East-West Gateway

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: Gateway
metadata:
  name: cross-network-gateway
  namespace: istio-system
spec:
  selector:
    istio: eastwestgateway
  servers:
    - port:
        number: 15443
        name: tls
        protocol: TLS
      tls:
        mode: AUTO_PASSTHROUGH
      hosts:
        - "*.local"
```

#### Step 4: Enable Endpoint Discovery

```bash
# Share service discovery between clusters
istioctl create-remote-secret \
  --context=aws-eks \
  --name=aws-eks | kubectl apply --context=gcp-gke -f -

istioctl create-remote-secret \
  --context=gcp-gke \
  --name=gcp-gke | kubectl apply --context=aws-eks -f -
```

### Service Discovery Across Clusters

Once configured, services are automatically discoverable across clusters:
```yaml
# payment-service in AWS reaches inventory-service in GCP
# No code change needed — Istio handles routing transparently
# Call: http://inventory-service.orders.svc.cluster.local
```

### Global mTLS Enforcement

```yaml
# Apply to all namespaces — enforce STRICT mTLS
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-system    # applies cluster-wide
spec:
  mtls:
    mode: STRICT
```

### Traffic Locality (Prefer Local Cluster)

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: checkout-api
spec:
  host: checkout-api.payments.svc.cluster.local
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
    outlierDetection:
      consecutive5xxErrors: 3
      interval: 10s
      baseEjectionTime: 30s
    loadBalancer:
      localityLbSetting:
        enabled: true
        failover:
          - from: us-east1        # AWS region
            to: us-central1       # GCP region (failover)
          - from: us-central1
            to: eastus            # Azure (last resort)
```

### AuthorizationPolicy (Zero-Trust)

```yaml
# Allow specific service-to-service communication only
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: payments-policy
  namespace: payments
spec:
  selector:
    matchLabels:
      app: checkout-api
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/orders/sa/order-processor"
              - "cluster.local/ns/frontend/sa/web-frontend"
      to:
        - operation:
            methods: ["POST", "GET"]
            paths: ["/api/v1/*"]
```

---

## Cilium Cluster Mesh

Layer 3/4 federation using eBPF. Complements or replaces Istio for network-layer policies.

### Setup (already covered in k8s-federation.md)

Key benefit over Istio: **no sidecar overhead** — policies enforced in eBPF kernel.

### Mutual Authentication (mTLS via Cilium)

```yaml
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: cross-cluster-mtls
spec:
  endpointSelector:
    matchLabels:
      app: payment-service
  ingress:
    - fromEndpoints:
        - matchLabels:
            app: order-service
      authentication:
        mode: "required"    # enforces mTLS via SPIFFE
```

---

## Consul Connect (HashiCorp)

Use when: existing HashiCorp Vault stack, hybrid cloud + on-prem, multi-platform.

### Federated Datacenters

```hcl
# Primary datacenter config
datacenter = "aws-us-east-1"
primary_datacenter = "aws-us-east-1"

# Secondary datacenter config
datacenter = "gcp-us-central1"
primary_datacenter = "aws-us-east-1"  # same primary

retry_join_wan = ["aws-consul-server.example.com"]
```

```yaml
# Service mesh intention (Consul equivalent of AuthorizationPolicy)
apiVersion: consul.hashicorp.com/v1alpha1
kind: ServiceIntentions
metadata:
  name: checkout-allows-order
spec:
  destination:
    name: checkout-api
  sources:
    - name: order-service
      action: allow
    - name: "*"
      action: deny     # deny all others (default-deny)
```

---

## Service Mesh Decision Matrix

| Factor | Istio | Cilium Cluster Mesh | Consul Connect |
|--------|-------|---------------------|----------------|
| **Performance overhead** | 5-10ms (sidecar) | <1ms (eBPF) | 2-5ms (sidecar) |
| **mTLS** | Envoy proxy | SPIFFE kernel | Envoy proxy |
| **L7 policies** | Full (routes, retries, timeouts) | Limited | Full |
| **Multi-cloud** | Excellent | Excellent | Excellent |
| **Hybrid (bare metal)** | Good | Good | Best |
| **Learning curve** | High | Medium | High |
| **Ecosystem** | CNCF Graduated | CNCF Graduated | HashiCorp (BSL) |
| **Recommended for** | L7 traffic management | High-throughput, low-latency | Vault-heavy stacks |

**For most Tier 2+ deployments: Istio (L7) + Cilium (L3/4)** together.

---

## Traffic Management (Istio VirtualService)

### Weighted Routing (Canary + DR)

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: checkout-api
spec:
  hosts:
    - checkout-api
  http:
    - match:
        - headers:
            x-canary:
              exact: "true"
      route:
        - destination:
            host: checkout-api
            subset: canary
          weight: 100
    - route:
        - destination:
            host: checkout-api
            subset: stable
          weight: 95
        - destination:
            host: checkout-api
            subset: canary
          weight: 5
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: "5xx,reset,connect-failure"
      timeout: 10s
      fault:
        delay:
          percentage:
            value: 0.1    # 0.1% artificial delay for testing
          fixedDelay: 5s
```

### Circuit Breaker

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: checkout-circuit-breaker
spec:
  host: checkout-api
  trafficPolicy:
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 10s
      baseEjectionTime: 30s
      maxEjectionPercent: 50    # never eject more than 50% of replicas
    connectionPool:
      tcp:
        maxConnections: 100
        connectTimeout: 30ms
      http:
        h2UpgradePolicy: UPGRADE
        idleTimeout: 90s
        http2MaxRequests: 1000
        maxRequestsPerConnection: 10
```

---

## Observability (Distributed Tracing Across Clusters)

All services must propagate W3C trace context headers:
```
traceparent: 00-{traceId}-{spanId}-{flags}
```

Configure OTel Collector on each cluster to forward spans to Tempo/Jaeger:
```yaml
# istio telemetry config
apiVersion: telemetry.istio.io/v1alpha1
kind: Telemetry
metadata:
  name: tracing
  namespace: istio-system
spec:
  tracing:
    - providers:
        - name: otel-tracing
      randomSamplingPercentage: 10.0    # 10% sampling in production
```
