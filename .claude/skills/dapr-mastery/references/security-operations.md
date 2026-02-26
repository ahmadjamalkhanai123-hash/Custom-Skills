# Dapr Security & Operations Reference

## Zero-Trust Security Model

Dapr implements zero-trust via:
1. **mTLS** — all sidecar-to-sidecar traffic encrypted and mutually authenticated
2. **SPIFFE X.509** — every sidecar gets a unique workload identity certificate
3. **Access Control Lists** — fine-grained API/method access control
4. **App-to-Sidecar auth** — token-based authentication for local API calls
5. **Component scoping** — restrict which apps can use which components
6. **Secret store integration** — no plaintext secrets in component YAML

---

## mTLS Configuration

### Sentry (Certificate Authority)
Dapr's built-in CA. In production: bring your own CA or use cert-manager.

```yaml
# Dapr Helm values — production mTLS
dapr_sentry:
  replicaCount: 3           # HA: 3 replicas
  resources:
    requests: { cpu: "100m", memory: "128Mi" }
    limits: { cpu: "300m", memory: "256Mi" }

global:
  mtls:
    enabled: true
    workloadCertTTL: 24h    # Workload cert valid 24h
    allowedClockSkew: 15m   # Clock skew tolerance
```

### Custom Root CA (Production Recommended)
```bash
# Generate root CA with cert-manager or Vault PKI
# Then configure Dapr to use external CA:
kubectl create secret generic dapr-trust-bundle \
  --from-file=ca.crt=./ca.crt \
  --from-file=issuer.crt=./issuer.crt \
  --from-file=issuer.key=./issuer.key \
  -n dapr-system
```

### Verify mTLS
```bash
dapr mtls check --namespace production
# Should show: mTLS is enabled
```

---

## App-to-Sidecar Authentication

Prevent unauthorized apps from calling the Dapr API on port 3500:

```yaml
# In Deployment env vars
env:
  - name: APP_API_TOKEN
    valueFrom:
      secretKeyRef:
        name: dapr-api-token
        key: token
  - name: DAPR_API_TOKEN   # SDK auto-reads this
    valueFrom:
      secretKeyRef:
        name: dapr-api-token
        key: token
```

```python
# SDK automatically uses DAPR_API_TOKEN from environment
with DaprClient() as d:
    # Token sent automatically in every request
    resp = d.invoke_method("service-b", "endpoint", data=b"")
```

---

## Access Control Lists (ACL)

Restrict which services can invoke which methods:

```yaml
apiVersion: dapr.io/v1alpha1
kind: Configuration
metadata:
  name: production-config
  namespace: production
spec:
  accessControl:
    defaultAction: deny          # Deny-by-default (production standard)
    trustDomain: "cluster.local"
    policies:
      # Order service: can only be called by API gateway and payment service
      - appId: order-service
        defaultAction: deny
        namespace: production
        operations:
          - name: /orders/create
            httpVerb: [POST]
            action: allow
          - name: /orders/*
            httpVerb: [GET]
            action: allow

      # Payment service: restricted callers
      - appId: payment-service
        defaultAction: deny
        namespace: production
        operations:
          - name: /payments/charge
            httpVerb: [POST]
            action: allow
            # Only from: order-service (trust domain handles this)
```

---

## Component Scoping

Restrict which app IDs can use a component:

```yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: payment-state-store
  namespace: production
spec:
  type: state.redis
  version: v1
  metadata:
    - name: redisHost
      secretKeyRef: { name: redis-prod, key: host }
scopes:
  - payment-service          # Only payment-service can use this
  - payment-worker           # And payment-worker
  # All other services denied
```

---

## Secret Store Security

### Kubernetes Secrets (Default)
```yaml
# Create K8s secret
kubectl create secret generic my-app-secrets \
  --from-literal=db-password=supersecret \
  -n production

# Reference in component
spec:
  metadata:
    - name: connectionString
      secretKeyRef:
        name: my-app-secrets
        key: db-password
```

### HashiCorp Vault (Enterprise)
```yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: vault-store
spec:
  type: secretstores.hashicorp.vault
  version: v1
  metadata:
    - name: vaultAddr
      value: "https://vault.internal:8200"
    - name: vaultTokenMountPath
      value: "/var/run/secrets/vault/token"   # Vault Agent injected token
    - name: enginePath
      value: "secret"
    - name: vaultKVVersion
      value: "v2"
    - name: tlsCACert
      secretKeyRef: { name: vault-tls-ca, key: ca.crt }
    - name: namespace
      value: "production"                     # Vault namespace
```

### Azure Key Vault
```yaml
spec:
  type: secretstores.azure.keyvault
  version: v1
  metadata:
    - name: vaultName
      value: "my-production-vault"
    - name: azureClientId
      value: "mi-client-id"       # Use Managed Identity in AKS
    - name: azureTenantId
      secretKeyRef: { name: az-secret, key: tenantId }
```

---

## Network Security

### Kubernetes NetworkPolicy
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: dapr-sidecar-policy
  namespace: production
spec:
  podSelector: {}        # Apply to all pods
  policyTypes: [Ingress, Egress]
  ingress:
    # Allow Dapr sidecar port from within namespace only
    - from:
        - namespaceSelector:
            matchLabels:
              name: production
      ports:
        - port: 3500      # Dapr HTTP
        - port: 50001     # Dapr gRPC
        - port: 9090      # Dapr metrics
  egress:
    # Allow sidecar to reach Dapr control plane
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: dapr-system
      ports:
        - port: 50001
        - port: 80
```

---

## Production Security Checklist

### Identity & Auth
- [ ] mTLS enabled (verify with `dapr mtls check`)
- [ ] DAPR_API_TOKEN set in all deployments
- [ ] Custom root CA for Sentry (not self-signed in enterprise)
- [ ] Workload cert TTL ≤ 24h, clock skew ≤ 15m
- [ ] Certificate rotation tested (zero downtime)

### Access Control
- [ ] `defaultAction: deny` in all Dapr Configurations
- [ ] Access policies defined per app ID and method
- [ ] Component scopes set (no wildcard access)
- [ ] Trust domain configured to cluster domain

### Secrets
- [ ] No plaintext in component YAML (all via `secretKeyRef`)
- [ ] Secret store scoped to specific apps
- [ ] Vault/KMS integration for enterprise
- [ ] Secrets rotated, TTLs set

### Network
- [ ] NetworkPolicy restricts sidecar port 3500 to namespace
- [ ] Dapr control plane isolated in `dapr-system` namespace
- [ ] Egress rules for Dapr → external components
- [ ] TLS for all external component connections (`enableTLS: true`)

### Compliance
- [ ] Audit logging enabled (`dapr.io/enable-api-logging: "true"`)
- [ ] Log sampling rate set for compliance requirements
- [ ] mTLS certificates auditable (certificate transparency)
- [ ] Component metadata audit trail
