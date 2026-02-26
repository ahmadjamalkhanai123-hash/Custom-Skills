# Zero-Trust Patterns — SPIFFE/SPIRE, cert-manager, mTLS

## Zero-Trust Principles for Kubernetes

```
1. Never trust, always verify — every workload proves identity before communicating
2. Least privilege — minimum access needed for function
3. Assume breach — mutual TLS everywhere, even within cluster
4. Short-lived credentials — SVID/cert rotation ≤ 24h
5. Explicit policy — PeerAuthentication STRICT, AuthorizationPolicy allow-list
```

---

## cert-manager {#cert-manager}

### Installation

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.3/cert-manager.yaml
```

### ClusterIssuer: Self-Signed (Dev/Staging)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-issuer
spec:
  selfSigned: {}
---
# CA root certificate
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: authorizer-ca
  namespace: cert-manager
spec:
  isCA: true
  commonName: authorizer-ca
  secretName: authorizer-ca-secret
  privateKey:
    algorithm: ECDSA
    size: 384
  issuerRef:
    name: selfsigned-issuer
    kind: ClusterIssuer
    group: cert-manager.io
---
# CA-backed ClusterIssuer
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: authorizer-ca-issuer
spec:
  ca:
    secretName: authorizer-ca-secret
```

### ClusterIssuer: Let's Encrypt (Production)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: platform@company.com
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
      - http01:
          ingress:
            ingressClassName: nginx
      - dns01:
          route53:
            region: us-east-1
            hostedZoneID: Z1PA6795UKMFR9
            role: arn:aws:iam::123456789:role/cert-manager-role
```

### ClusterIssuer: HashiCorp Vault (Enterprise)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: vault-issuer
spec:
  vault:
    server: https://vault.company.com
    path: pki/sign/kubernetes-role
    auth:
      kubernetes:
        mountPath: /v1/auth/kubernetes
        role: cert-manager
        secretRef:
          name: vault-cert-manager-sa-token
          key: token
```

### Certificate: Service mTLS

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: backend-service-tls
  namespace: team-backend
spec:
  secretName: backend-service-tls
  duration: 24h
  renewBefore: 8h
  privateKey:
    algorithm: ECDSA
    size: 384
    rotationPolicy: Always
  subject:
    organizations:
      - company.com
  commonName: backend-service.team-backend.svc.cluster.local
  dnsNames:
    - backend-service
    - backend-service.team-backend
    - backend-service.team-backend.svc
    - backend-service.team-backend.svc.cluster.local
  issuerRef:
    name: authorizer-ca-issuer
    kind: ClusterIssuer
```

---

## SPIFFE / SPIRE {#spire}

### Architecture

```
SPIRE Server (control plane)
      │  ─ Node attestation (aws-iid / k8s-psat / tpm)
      │  ─ Workload attestation (k8s-sat)
      │  ─ Issues SVIDs (X.509 / JWT)
      │
SPIRE Agent (per node DaemonSet)
      │
Workload API (Unix domain socket)
      │
Application (fetches SVID via SPIFFE Workload API)
```

### SPIRE Server Deployment

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: spire-server
  namespace: spire
spec:
  selector:
    matchLabels:
      app: spire-server
  serviceName: spire-server
  replicas: 1
  template:
    metadata:
      labels:
        app: spire-server
    spec:
      serviceAccountName: spire-server
      containers:
        - name: spire-server
          image: ghcr.io/spiffe/spire-server:1.10.3
          args:
            - -config
            - /run/spire/config/server.conf
          volumeMounts:
            - name: spire-config
              mountPath: /run/spire/config
              readOnly: true
            - name: spire-data
              mountPath: /run/spire/data
      volumes:
        - name: spire-config
          configMap:
            name: spire-server-config
        - name: spire-data
          persistentVolumeClaim:
            claimName: spire-data
```

### SPIRE Server ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: spire-server-config
  namespace: spire
data:
  server.conf: |
    server {
      bind_address = "0.0.0.0"
      bind_port = "8081"
      socket_path = "/tmp/spire-server/private/api.sock"
      trust_domain = "company.com"
      data_dir = "/run/spire/data"
      log_level = "INFO"
      default_x509_svid_ttl = "1h"
      default_jwt_svid_ttl = "5m"
      ca_ttl = "24h"
      ca_subject {
        country = ["US"]
        organization = ["Company, Inc."]
        common_name = "company.com"
      }
    }

    plugins {
      DataStore "sql" {
        plugin_data {
          database_type = "sqlite3"
          connection_string = "/run/spire/data/datastore.sqlite3"
        }
      }

      NodeAttestor "k8s_psat" {
        plugin_data {
          clusters = {
            "production" = {
              service_account_allow_list = ["spire:spire-agent"]
              kube_config_file = ""
            }
          }
        }
      }

      KeyManager "disk" {
        plugin_data {
          keys_path = "/run/spire/data/keys.json"
        }
      }
    }
```

### SPIRE Agent DaemonSet

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: spire-agent
  namespace: spire
spec:
  selector:
    matchLabels:
      app: spire-agent
  template:
    metadata:
      labels:
        app: spire-agent
    spec:
      hostPID: true
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      serviceAccountName: spire-agent
      initContainers:
        - name: init
          image: ghcr.io/spiffe/wait-for-it:latest
          args: ["-t", "30", "spire-server:8081"]
      containers:
        - name: spire-agent
          image: ghcr.io/spiffe/spire-agent:1.10.3
          args:
            - -config
            - /run/spire/config/agent.conf
          volumeMounts:
            - name: spire-config
              mountPath: /run/spire/config
              readOnly: true
            - name: spire-agent-socket
              mountPath: /run/spire/sockets
              readOnly: false
            - name: spire-token
              mountPath: /var/run/secrets/tokens
      volumes:
        - name: spire-config
          configMap:
            name: spire-agent-config
        - name: spire-agent-socket
          hostPath:
            path: /run/spire/sockets
            type: DirectoryOrCreate
        - name: spire-token
          projected:
            sources:
              - serviceAccountToken:
                  path: spire-agent
                  expirationSeconds: 7200
                  audience: spire-server
```

### SPIRE Registration Entry

```bash
# Register workload entry (SA-based attestation)
kubectl exec -n spire spire-server-0 -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://company.com/ns/team-backend/sa/backend-app-sa \
  -parentID spiffe://company.com/k8s-workload-registrar/production/node \
  -selector k8s:ns:team-backend \
  -selector k8s:sa:backend-app-sa
```

---

## mTLS with Service Mesh {#mtls}

### Istio: STRICT mTLS

```yaml
# Global STRICT mTLS (Tier 4+)
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default-strict-mtls
  namespace: istio-system   # Global policy
spec:
  mtls:
    mode: STRICT
---
# AuthorizationPolicy: workload-to-workload
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: allow-backend-from-frontend
  namespace: team-backend
spec:
  selector:
    matchLabels:
      app: backend-service
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/team-frontend/sa/frontend-app-sa"
      to:
        - operation:
            methods: ["GET", "POST"]
            paths: ["/api/*"]
```

### Linkerd: Automatic mTLS

```yaml
# Linkerd auto-injects mTLS — just annotate namespace
apiVersion: v1
kind: Namespace
metadata:
  name: team-backend
  annotations:
    linkerd.io/inject: enabled
---
# Server (policy)
apiVersion: policy.linkerd.io/v1beta3
kind: Server
metadata:
  name: backend-server
  namespace: team-backend
spec:
  podSelector:
    matchLabels:
      app: backend-service
  port: 8080
  proxyProtocol: HTTP/2
---
# ServerAuthorization
apiVersion: policy.linkerd.io/v1beta3
kind: AuthorizationPolicy
metadata:
  name: allow-frontend-to-backend
  namespace: team-backend
spec:
  targetRef:
    group: policy.linkerd.io
    kind: Server
    name: backend-server
  requiredAuthenticationRefs:
    - group: policy.linkerd.io
      kind: MeshTLSAuthentication
      name: frontend-auth
---
apiVersion: policy.linkerd.io/v1beta3
kind: MeshTLSAuthentication
metadata:
  name: frontend-auth
  namespace: team-backend
spec:
  identities:
    - "team-frontend.serviceaccount.identity.linkerd.cluster.local"
```
