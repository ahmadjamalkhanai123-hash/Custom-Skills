# Kubernetes Networking Patterns

> Production networking patterns: NetworkPolicy, Gateway API, DNS, service types, and Cilium L7 policies.

---

## NetworkPolicy: Default Deny All

Every production namespace MUST start with default deny for both ingress and egress.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

This blocks all traffic to and from every pod in the namespace. Pods cannot communicate with each other, the internet, or even DNS until explicit allow policies are created.

---

## NetworkPolicy: Explicit Allow Patterns

### Allow Ingress from Specific Pods

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-api
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api-server
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
```

### Allow Egress to Specific Destinations

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-egress-db
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api-server
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - protocol: TCP
          port: 5432
```

---

## Cross-Namespace Allow

Use `namespaceSelector` combined with `podSelector` to allow traffic across namespaces. Requires labels on the namespace itself.

```yaml
# Label the namespace first: kubectl label namespace monitoring purpose=monitoring
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-monitoring-scrape
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api-server
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              purpose: monitoring
          podSelector:
            matchLabels:
              app: prometheus
      ports:
        - protocol: TCP
          port: 9090
```

Note: when `namespaceSelector` and `podSelector` are in the same `from` entry (no dash before `podSelector`), they are ANDed. If they are separate list items (each with a dash), they are ORed.

---

## DNS Egress Allowlist Pattern

Every pod that has egress denied needs explicit DNS access, otherwise name resolution fails.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-egress
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

### CIDR-Based External Egress Allowlist

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-external-api
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: payment-service
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 203.0.113.0/24  # External payment provider
      ports:
        - protocol: TCP
          port: 443
```

---

## Gateway API

Gateway API is the successor to Ingress. Use `gateway.networking.k8s.io/v1` (GA since K8s 1.29).

### GatewayClass

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: production
spec:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
```

### Gateway

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: production-gateway
  namespace: gateway-system
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  gatewayClassName: production
  listeners:
    - name: https
      protocol: HTTPS
      port: 443
      tls:
        mode: Terminate
        certificateRefs:
          - name: wildcard-tls
            namespace: gateway-system
      allowedRoutes:
        namespaces:
          from: Selector
          selector:
            matchLabels:
              gateway-access: "true"
    - name: http-redirect
      protocol: HTTP
      port: 80
```

### HTTPRoute

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: api-routes
  namespace: production
spec:
  parentRefs:
    - name: production-gateway
      namespace: gateway-system
      sectionName: https
  hostnames:
    - "api.example.com"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /v2
      backendRefs:
        - name: api-v2
          port: 8080
          weight: 90
        - name: api-v3
          port: 8080
          weight: 10  # Canary 10% to v3
    - matches:
        - path:
            type: PathPrefix
            value: /v1
      backendRefs:
        - name: api-v1
          port: 8080
      filters:
        - type: RequestHeaderModifier
          requestHeaderModifier:
            set:
              - name: X-Api-Version
                value: "v1-deprecated"
```

### GRPCRoute

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GRPCRoute
metadata:
  name: grpc-services
  namespace: production
spec:
  parentRefs:
    - name: production-gateway
      namespace: gateway-system
  hostnames:
    - "grpc.example.com"
  rules:
    - matches:
        - method:
            service: myapp.UserService
            method: GetUser
      backendRefs:
        - name: user-service-grpc
          port: 50051
    - matches:
        - method:
            service: myapp.OrderService
      backendRefs:
        - name: order-service-grpc
          port: 50051
```

### TLSRoute (Passthrough)

```yaml
apiVersion: gateway.networking.k8s.io/v1alpha2
kind: TLSRoute
metadata:
  name: tls-passthrough
  namespace: production
spec:
  parentRefs:
    - name: production-gateway
      namespace: gateway-system
  hostnames:
    - "db.example.com"
  rules:
    - backendRefs:
        - name: postgres-primary
          port: 5432
```

---

## Ingress to Gateway API Migration

### Legacy Ingress (Deprecate)

```yaml
# LEGACY — migrate to Gateway API
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - api.example.com
      secretName: api-tls
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api-server
                port:
                  number: 8080
```

Migration steps:
1. Deploy Gateway API CRDs and a controller (Envoy Gateway, Cilium, or NGINX Gateway Fabric).
2. Create GatewayClass and Gateway resources.
3. Convert each Ingress rule to an HTTPRoute with `parentRefs` pointing to the Gateway.
4. Annotations become `filters` (rewrites, redirects, rate limits).
5. Run both in parallel, shift DNS, remove old Ingress.

---

## cert-manager Integration

### ClusterIssuer (Let's Encrypt)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: platform@example.com
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
      - http01:
          gatewayHTTPRoute:
            parentRefs:
              - name: production-gateway
                namespace: gateway-system
      - dns01:
          cloudDNS:
            project: my-gcp-project
          selector:
            dnsZones:
              - "example.com"
```

### Certificate Resource

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: wildcard-tls
  namespace: gateway-system
spec:
  secretName: wildcard-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
    - "*.example.com"
    - "example.com"
  duration: 2160h    # 90 days
  renewBefore: 720h  # 30 days before expiry
```

---

## ExternalDNS for Automatic DNS Records

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: external-dns
  namespace: kube-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: external-dns
  template:
    metadata:
      labels:
        app: external-dns
    spec:
      serviceAccountName: external-dns
      containers:
        - name: external-dns
          image: registry.k8s.io/external-dns/external-dns:v0.14.2
          args:
            - --source=gateway-httproute
            - --source=gateway-grpcroute
            - --source=service
            - --provider=cloudflare
            - --policy=upsert-only   # Never delete records
            - --registry=txt
            - --txt-owner-id=k8s-prod
            - --domain-filter=example.com
          env:
            - name: CF_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: cloudflare-credentials
                  key: api-token
```

ExternalDNS watches Gateway API routes and Services with `external-dns.alpha.kubernetes.io/hostname` annotations to automatically create DNS records.

---

## Cilium L7 NetworkPolicy

Cilium extends Kubernetes NetworkPolicy with L7 (HTTP, gRPC, Kafka) visibility and enforcement.

```yaml
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: api-l7-policy
  namespace: production
spec:
  endpointSelector:
    matchLabels:
      app: api-server
  ingress:
    - fromEndpoints:
        - matchLabels:
            app: frontend
      toPorts:
        - ports:
            - port: "8080"
              protocol: TCP
          rules:
            http:
              - method: GET
                path: "/api/v2/users.*"
              - method: POST
                path: "/api/v2/orders"
                headers:
                  - 'Content-Type: application/json'
  egress:
    - toEndpoints:
        - matchLabels:
            app: postgres
      toPorts:
        - ports:
            - port: "5432"
              protocol: TCP
    - toFQDNs:
        - matchName: "api.stripe.com"
      toPorts:
        - ports:
            - port: "443"
              protocol: TCP
```

The `toFQDNs` field allows DNS-based egress filtering — pods can only reach `api.stripe.com`, not arbitrary external hosts.

---

## Service Types

### ClusterIP (Default)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api-server
  namespace: production
spec:
  type: ClusterIP
  selector:
    app: api-server
  ports:
    - name: http
      port: 8080
      targetPort: 8080
      protocol: TCP
```

### Headless Service (StatefulSet DNS)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: production
spec:
  type: ClusterIP
  clusterIP: None  # Headless — DNS returns pod IPs directly
  selector:
    app: postgres
  ports:
    - name: postgres
      port: 5432
      targetPort: 5432
```

Headless services give each pod a stable DNS name: `postgres-0.postgres.production.svc.cluster.local`.

### NodePort

```yaml
apiVersion: v1
kind: Service
metadata:
  name: debug-service
  namespace: staging
spec:
  type: NodePort
  selector:
    app: debug-tool
  ports:
    - port: 8080
      targetPort: 8080
      nodePort: 30080  # Range: 30000-32767
```

### LoadBalancer

```yaml
apiVersion: v1
kind: Service
metadata:
  name: public-api
  namespace: production
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: nlb
    service.beta.kubernetes.io/aws-load-balancer-scheme: internet-facing
    service.beta.kubernetes.io/aws-load-balancer-cross-zone-load-balancing-enabled: "true"
spec:
  type: LoadBalancer
  selector:
    app: api-gateway
  ports:
    - name: https
      port: 443
      targetPort: 8443
```

---

## DNS: CoreDNS Tuning

### ndots Optimization

The default `ndots: 5` causes 4-5 DNS lookups per external domain. Set `ndots: 2` on pods that make many external calls.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: api-server
spec:
  dnsConfig:
    options:
      - name: ndots
        value: "2"
      - name: single-request-reopen
      - name: timeout
        value: "3"
      - name: attempts
        value: "2"
  dnsPolicy: ClusterFirst
  containers:
    - name: api
      image: myapp:latest
```

### CoreDNS ConfigMap Tuning

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns
  namespace: kube-system
data:
  Corefile: |
    .:53 {
        errors
        health {
            lameduck 5s
        }
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {
            pods insecure
            fallthrough in-addr.arpa ip6.arpa
            ttl 30
        }
        hosts /etc/coredns/NodeHosts {
            ttl 60
            reload 15s
            fallthrough
        }
        prometheus :9153
        forward . /etc/resolv.conf {
            max_concurrent 1000
            policy sequential
        }
        cache 30 {
            success 9984 30
            denial 9984 5
        }
        loop
        reload
        loadbalance
    }
```

Key tuning parameters:
- `cache 30`: cache positive responses for 30 seconds.
- `denial 9984 5`: cache NXDOMAIN for only 5 seconds (prevents stale negative cache).
- `max_concurrent 1000`: allow 1000 concurrent upstream queries.
- `ttl 30`: internal record TTL of 30 seconds.

---

## Quick Reference: Networking Decision Tree

| Scenario | Solution |
|---|---|
| Block all traffic by default | Default deny NetworkPolicy |
| L4 pod-to-pod filtering | NetworkPolicy (ingress/egress) |
| L7 HTTP/gRPC filtering | CiliumNetworkPolicy or service mesh |
| DNS-based egress filtering | CiliumNetworkPolicy `toFQDNs` |
| External HTTP routing | Gateway API HTTPRoute |
| gRPC routing | Gateway API GRPCRoute |
| TLS passthrough | Gateway API TLSRoute |
| Automatic TLS certificates | cert-manager + ClusterIssuer |
| Automatic DNS records | ExternalDNS |
| Stable pod DNS names | Headless Service + StatefulSet |
| Cross-namespace access | namespaceSelector + podSelector |
