# Zero-Trust Networking

## Zero-Trust Principles

```
1. Never trust, always verify — authenticate every request, even internal
2. Least privilege access — grant minimum permissions for each operation
3. Assume breach — design systems to limit blast radius
4. Encrypt everything — mTLS between all services, even within cluster
5. Continuous verification — re-authenticate, don't rely on session state
```

---

## SPIFFE / SPIRE (Workload Identity)

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  SPIRE Server (control plane)                               │
│  - Issues X.509 SVIDs (SPIFFE Verifiable Identity Docs)    │
│  - Stores registration entries (workload → SPIFFE ID)      │
│  - CA: issues short-lived certs (1h default)               │
│                                                             │
│  SPIRE Agent (DaemonSet on each node)                       │
│  - Attests node identity (AWS, GCP, K8s node attestor)     │
│  - Issues SVIDs to workloads via Workload API               │
│  - Rotates SVIDs automatically                              │
│                                                             │
│  SPIFFE ID format: spiffe://trust-domain/path               │
│  Example: spiffe://prod.example.com/ns/payments/sa/payment-service
└─────────────────────────────────────────────────────────────┘
```

### SPIRE Server Kubernetes Deployment

```yaml
# spire-server ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: spire-server
  namespace: spire
data:
  server.conf: |
    server {
      bind_address = "0.0.0.0"
      bind_port = "8081"
      socket_path = "/tmp/spire-server/private/api.sock"
      trust_domain = "prod.example.com"
      data_dir = "/run/spire/data"
      log_level = "INFO"
      ca_ttl = "12h"
      default_x509_svid_ttl = "1h"
      default_jwt_svid_ttl = "5m"
    }

    plugins {
      DataStore "sql" {
        plugin_data {
          database_type = "postgres"
          connection_string = "dbname=spire user=spire password=secret host=postgres sslmode=require"
        }
      }

      NodeAttestor "k8s_psat" {
        plugin_data {
          clusters = {
            "production" = {
              service_account_allow_list = ["spire:spire-agent"]
              audience = ["spire-server"]
            }
          }
        }
      }

      KeyManager "disk" {
        plugin_data {
          keys_path = "/run/spire/data/keys.json"
        }
      }

      Notifier "k8sbundle" {
        plugin_data {
          namespace = "spire"
        }
      }
    }
```

### Registration Entry for Workload

```bash
# Register payment-service workload
kubectl exec -n spire spire-server-0 -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://prod.example.com/ns/payments/sa/payment-service \
  -parentID spiffe://prod.example.com/spire/agent/k8s_psat/production/$(kubectl get node -o jsonpath='{.items[0].metadata.uid}') \
  -selector k8s:ns:payments \
  -selector k8s:sa:payment-service \
  -ttl 3600
```

---

## Istio Service Mesh Security

### Enable Strict mTLS Cluster-Wide

```yaml
# PeerAuthentication: STRICT mTLS for entire mesh
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-system    # Cluster-wide when in root namespace
spec:
  mtls:
    mode: STRICT             # Reject all non-mTLS traffic
---
# Namespace-level override (if needed for migration)
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: default
  namespace: legacy-namespace
spec:
  mtls:
    mode: PERMISSIVE         # Allow both mTLS and plaintext (migration period)
```

### AuthorizationPolicy: Zero-Trust Service-to-Service

```yaml
# Default: deny all traffic in namespace
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: deny-all
  namespace: payments
spec:
  {}   # Empty spec = deny all
---
# Allow only order-service → payment-service:8080 POST /payments
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: allow-order-to-payment
  namespace: payments
spec:
  selector:
    matchLabels:
      app: payment-service
  action: ALLOW
  rules:
    - from:
        - source:
            # Verify identity via SPIFFE SVID
            principals:
              - "cluster.local/ns/orders/sa/order-service"
      to:
        - operation:
            methods: ["POST"]
            paths: ["/payments", "/payments/*"]
      when:
        - key: request.headers[x-request-id]
          notValues: [""]            # Require correlation ID
---
# Allow Prometheus scraping metrics
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: allow-prometheus-scrape
  namespace: payments
spec:
  selector:
    matchLabels:
      app: payment-service
  action: ALLOW
  rules:
    - from:
        - source:
            namespaces: ["monitoring"]
      to:
        - operation:
            methods: ["GET"]
            paths: ["/metrics"]
```

### Istio JWT Authentication (OIDC)

```yaml
# RequestAuthentication: validate JWTs
apiVersion: security.istio.io/v1
kind: RequestAuthentication
metadata:
  name: jwt-validation
  namespace: payments
spec:
  selector:
    matchLabels:
      app: payment-service
  jwtRules:
    - issuer: "https://accounts.google.com"
      jwksUri: "https://www.googleapis.com/oauth2/v3/certs"
      audiences: ["payment-api"]
      forwardOriginalToken: true
---
# AuthorizationPolicy: require valid JWT
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: require-jwt
  namespace: payments
spec:
  selector:
    matchLabels:
      app: payment-service
  action: ALLOW
  rules:
    - from:
        - source:
            requestPrincipals: ["https://accounts.google.com/*"]
      when:
        - key: request.auth.claims[roles]
          values: ["payments-writer", "payments-admin"]
```

---

## Cilium: eBPF Network Policy

### L7 HTTP Policy (beyond NetworkPolicy)

```yaml
# CiliumNetworkPolicy: L7 HTTP-aware policy
apiVersion: "cilium.io/v2"
kind: CiliumNetworkPolicy
metadata:
  name: payment-service-l7
  namespace: payments
spec:
  endpointSelector:
    matchLabels:
      app: payment-service
  ingress:
    - fromEndpoints:
        - matchLabels:
            app: order-service
            io.kubernetes.pod.namespace: orders
      toPorts:
        - ports:
            - port: "8080"
              protocol: TCP
          rules:
            http:
              - method: "POST"
                path: "/payments"
              - method: "GET"
                path: "/payments/[0-9]+"
    # Block any other HTTP methods/paths
  egress:
    - toEndpoints:
        - matchLabels:
            app: postgres
            io.kubernetes.pod.namespace: databases
      toPorts:
        - ports:
            - port: "5432"
              protocol: TCP
```

### Cilium ClusterMesh (Multi-Cluster mTLS)

```yaml
# Enable ClusterMesh
helm upgrade cilium cilium/cilium \
  --set cluster.name=production-us-east \
  --set cluster.id=1 \
  --set clustermesh.useAPIServer=true \
  --set clustermesh.apiserver.tls.auto.method=certmanager
```

---

## cert-manager for TLS Automation

```yaml
# ClusterIssuer: Let's Encrypt production
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: security@mycompany.com
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
      - http01:
          ingress:
            class: nginx
---
# Internal CA for service mesh
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: internal-ca
spec:
  ca:
    secretName: internal-ca-key-pair
---
# Certificate for service
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: payment-service-tls
  namespace: payments
spec:
  secretName: payment-service-tls
  issuerRef:
    name: internal-ca
    kind: ClusterIssuer
  commonName: payment-service.payments.svc.cluster.local
  dnsNames:
    - payment-service.payments.svc.cluster.local
    - payment-service.payments.svc
  duration: 24h            # Short-lived certs
  renewBefore: 8h          # Auto-renew before expiry
```

---

## Zero-Trust Decision Matrix

| Scenario | Control | Implementation |
|----------|---------|---------------|
| Service-to-service auth | mTLS + SVID | SPIFFE/SPIRE + Istio |
| User → API auth | JWT/OIDC | Istio RequestAuthentication |
| North-south TLS | TLS 1.3 | cert-manager + Ingress |
| East-west encryption | mTLS mesh | Istio STRICT mode |
| Network segmentation | L3/L4 policy | NetworkPolicy + Cilium |
| L7 HTTP policy | Method/path filtering | Cilium CiliumNetworkPolicy |
| Multi-cluster auth | ClusterMesh mTLS | Cilium ClusterMesh |
| External service auth | Egress + ServiceEntry | Istio ServiceEntry + AuthzPolicy |
