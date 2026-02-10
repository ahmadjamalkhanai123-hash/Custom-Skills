# Kubernetes Service Mesh Patterns

> Production service mesh patterns: Istio, Linkerd, Cilium Service Mesh — mTLS, traffic management, observability.

---

## Istio

### Installation Profiles

```bash
# Minimal: Istiod only, no ingress gateway
istioctl install --set profile=minimal -y

# Default: Istiod + ingress gateway
istioctl install --set profile=default -y

# Demo: All features enabled (never use in production)
istioctl install --set profile=demo -y

# Production recommendation: minimal + Gateway API integration
istioctl install --set profile=minimal \
  --set values.pilot.env.PILOT_ENABLE_GATEWAY_API=true \
  --set meshConfig.accessLogFile=/dev/stdout \
  --set meshConfig.enableAutoMtls=true -y
```

Enable sidecar injection per namespace:

```bash
kubectl label namespace production istio-injection=enabled
```

### PeerAuthentication (Strict mTLS)

```yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: strict-mtls
  namespace: production
spec:
  mtls:
    mode: STRICT
---
# Mesh-wide strict mTLS (apply to istio-system namespace)
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: mesh-wide-strict
  namespace: istio-system
spec:
  mtls:
    mode: STRICT
```

### AuthorizationPolicy (L7 RBAC)

```yaml
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: api-server-authz
  namespace: production
spec:
  selector:
    matchLabels:
      app: api-server
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/production/sa/frontend"
      to:
        - operation:
            methods: ["GET", "POST"]
            paths: ["/api/v2/*"]
    - from:
        - source:
            principals:
              - "cluster.local/ns/monitoring/sa/prometheus"
      to:
        - operation:
            methods: ["GET"]
            paths: ["/metrics"]
---
# Default deny all in namespace
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: deny-all
  namespace: production
spec: {}
```

### VirtualService (Traffic Routing)

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: api-server
  namespace: production
spec:
  hosts:
    - api-server
  http:
    - match:
        - headers:
            x-canary:
              exact: "true"
      route:
        - destination:
            host: api-server
            subset: canary
    - route:
        - destination:
            host: api-server
            subset: stable
          weight: 95
        - destination:
            host: api-server
            subset: canary
          weight: 5
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: 5xx,reset,connect-failure
      timeout: 10s
      fault:
        delay:
          percentage:
            value: 0.1
          fixedDelay: 5s  # Chaos: 0.1% of requests get 5s delay
```

### DestinationRule

```yaml
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: api-server
  namespace: production
spec:
  host: api-server
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        h2UpgradePolicy: DEFAULT
        http1MaxPendingRequests: 100
        http2MaxRequests: 1000
        maxRequestsPerConnection: 10
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
    tls:
      mode: ISTIO_MUTUAL
  subsets:
    - name: stable
      labels:
        version: v2
    - name: canary
      labels:
        version: v3
```

### Traffic Splitting (Canary)

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: canary-rollout
  namespace: production
spec:
  hosts:
    - api-server
  http:
    - route:
        - destination:
            host: api-server
            subset: stable
          weight: 90
        - destination:
            host: api-server
            subset: canary
          weight: 10
```

Progression: 10% -> 25% -> 50% -> 100%. Use Flagger or Argo Rollouts to automate weight changes based on metrics.

---

## Linkerd

### Installation

```bash
# Install CLI
curl --proto '=https' --tlsv1.2 -sSfL https://run.linkerd.io/install | sh

# Pre-checks
linkerd check --pre

# Install CRDs + control plane
linkerd install --crds | kubectl apply -f -
linkerd install | kubectl apply -f -

# Verify
linkerd check

# Enable injection per namespace
kubectl annotate namespace production linkerd.io/inject=enabled
```

Linkerd automatically enables mTLS for all meshed pods with zero configuration.

### ServiceProfile (Per-Route Metrics + Retries)

```yaml
apiVersion: linkerd.io/v1alpha2
kind: ServiceProfile
metadata:
  name: api-server.production.svc.cluster.local
  namespace: production
spec:
  routes:
    - name: GET /api/v2/users
      condition:
        method: GET
        pathRegex: /api/v2/users(/[^/]+)?
      responseClasses:
        - condition:
            status:
              min: 500
              max: 599
          isFailure: true
      isRetryable: true
      timeout: 5s
    - name: POST /api/v2/orders
      condition:
        method: POST
        pathRegex: /api/v2/orders
      isRetryable: false  # Non-idempotent
      timeout: 10s
  retryBudget:
    retryRatio: 0.2       # Max 20% of requests are retries
    minRetriesPerSecond: 10
    ttl: 10s
```

### TrafficSplit (SMI)

```yaml
apiVersion: split.smi-spec.io/v1alpha2
kind: TrafficSplit
metadata:
  name: api-server-canary
  namespace: production
spec:
  service: api-server        # Apex service
  backends:
    - service: api-server-stable
      weight: 900             # 90%
    - service: api-server-canary
      weight: 100             # 10%
```

### Linkerd AuthorizationPolicy

```yaml
apiVersion: policy.linkerd.io/v1beta3
kind: Server
metadata:
  name: api-server-http
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api-server
  port: 8080
  proxyProtocol: HTTP/2
---
apiVersion: policy.linkerd.io/v1beta3
kind: AuthorizationPolicy
metadata:
  name: allow-frontend
  namespace: production
spec:
  targetRef:
    group: policy.linkerd.io
    kind: Server
    name: api-server-http
  requiredAuthenticationRefs:
    - name: frontend-identity
      kind: MeshTLSAuthentication
      group: policy.linkerd.io
---
apiVersion: policy.linkerd.io/v1alpha1
kind: MeshTLSAuthentication
metadata:
  name: frontend-identity
  namespace: production
spec:
  identities:
    - "*.production.serviceaccount.identity.linkerd.cluster.local"
```

---

## Cilium Service Mesh

Cilium provides service mesh capabilities using eBPF — no sidecars required. Networking, observability, and security run in the kernel.

### Enable Service Mesh Features

```bash
# Install Cilium with service mesh
helm upgrade --install cilium cilium/cilium \
  --namespace kube-system \
  --set kubeProxyReplacement=true \
  --set envoy.enabled=true \
  --set loadBalancer.algorithm=maglev \
  --set encryption.enabled=true \
  --set encryption.type=wireguard \
  --set hubble.enabled=true \
  --set hubble.relay.enabled=true \
  --set hubble.ui.enabled=true
```

### CiliumEnvoyConfig (L7 Traffic Management)

```yaml
apiVersion: cilium.io/v2
kind: CiliumEnvoyConfig
metadata:
  name: api-server-l7
  namespace: production
spec:
  services:
    - name: api-server
      namespace: production
  backendServices:
    - name: api-server-stable
      namespace: production
    - name: api-server-canary
      namespace: production
  resources:
    - "@type": type.googleapis.com/envoy.config.listener.v3.Listener
      name: api-server-listener
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: api-server
                route_config:
                  name: local_route
                  virtual_hosts:
                    - name: api-server
                      domains: ["*"]
                      routes:
                        - match:
                            prefix: "/"
                          route:
                            weighted_clusters:
                              clusters:
                                - name: "production/api-server-stable"
                                  weight: 90
                                - name: "production/api-server-canary"
                                  weight: 10
                            retry_policy:
                              retry_on: "5xx"
                              num_retries: 3
```

---

## Mesh Selection Decision Tree

| Criteria | Istio | Linkerd | Cilium |
|---|---|---|---|
| **Complexity** | High | Low | Medium |
| **Resource overhead** | High (sidecars) | Low (Rust sidecars) | Lowest (no sidecars) |
| **L7 features** | Full (VirtualService, AuthzPolicy) | Moderate (ServiceProfile) | Growing (CiliumEnvoyConfig) |
| **mTLS** | Manual or auto | Always on, zero-config | WireGuard (node-level) |
| **Multi-cluster** | Mature (multi-primary) | Supported (multi-cluster) | ClusterMesh (mature) |
| **Best for** | Complex routing, JWT auth, multi-tenant | Simplicity, low overhead | Already using Cilium CNI |

**Decision rules:**
1. Already using Cilium as CNI? Start with Cilium Service Mesh.
2. Need simplest mesh with lowest overhead? Linkerd.
3. Need advanced L7 routing, JWT validation, external authz? Istio.
4. Multi-cluster with different mesh per cluster? Istio (most battle-tested).

---

## Multi-Cluster Mesh

### Istio Multi-Primary

```yaml
# Cluster 1: east
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: istio-east
spec:
  profile: minimal
  values:
    global:
      meshID: production-mesh
      multiCluster:
        clusterName: east
      network: network-east
  meshConfig:
    accessLogFile: /dev/stdout
---
# After installing on both clusters, link them:
# istioctl create-remote-secret --name=east | kubectl apply -f - --context=west
# istioctl create-remote-secret --name=west | kubectl apply -f - --context=east
```

### Cilium ClusterMesh

```bash
# Enable ClusterMesh on both clusters
cilium clustermesh enable --context cluster-east
cilium clustermesh enable --context cluster-west

# Connect clusters
cilium clustermesh connect --context cluster-east --destination-context cluster-west

# Verify
cilium clustermesh status --context cluster-east
```

Global services are exposed by annotating:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api-server
  namespace: production
  annotations:
    service.cilium.io/global: "true"
    service.cilium.io/shared: "true"  # Share endpoints across clusters
spec:
  selector:
    app: api-server
  ports:
    - port: 8080
```

---

## Observability

### Kiali (Istio)

```bash
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.22/samples/addons/kiali.yaml
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.22/samples/addons/prometheus.yaml
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.22/samples/addons/jaeger.yaml
```

Kiali provides a service graph, traffic analysis, and Istio config validation.

### Linkerd Viz

```bash
linkerd viz install | kubectl apply -f -
linkerd viz dashboard &
```

Built-in dashboards show golden metrics (success rate, latency, throughput) per route.

### Hubble (Cilium)

```bash
# Already enabled via Helm values
# Access Hubble UI
cilium hubble ui

# CLI flow observation
hubble observe --namespace production --protocol http \
  --verdict DROPPED -f

# Export to Grafana via Prometheus
hubble observe --namespace production -o json | \
  jq '.flow | {src: .source.labels, dst: .destination.labels, verdict: .verdict}'
```

Hubble provides eBPF-level flow visibility — every packet, DNS query, and HTTP request without sidecars.

---

## Quick Reference: Mesh Feature Comparison

| Feature | Istio | Linkerd | Cilium |
|---|---|---|---|
| Sidecar model | Envoy sidecar | Rust micro-proxy | No sidecar (eBPF) |
| mTLS | Envoy certs | Identity certs | WireGuard |
| Traffic splitting | VirtualService | TrafficSplit (SMI) | CiliumEnvoyConfig |
| Circuit breaking | DestinationRule | Automatic | Envoy config |
| Retries | VirtualService | ServiceProfile | Envoy config |
| Auth policy | AuthorizationPolicy | AuthorizationPolicy | CiliumNetworkPolicy |
| Observability | Kiali + Jaeger | Linkerd Viz | Hubble |
| Gateway API | Native support | Supported | Native support |
| Install complexity | High | Low | Medium (CNI swap) |
| Memory per pod | ~50-100MB | ~10-20MB | 0 (kernel) |
