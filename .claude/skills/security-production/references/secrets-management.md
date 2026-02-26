# Secrets Management

## Secrets Maturity Model

```
Level 1: K8s Secrets (base64 only — not secure at rest without encryption)
Level 2: Sealed Secrets / SOPS (git-safe encrypted secrets)
Level 3: External Secrets Operator → Cloud KMS or Vault
Level 4: HashiCorp Vault HA (dynamic secrets, leases, audit)
Level 5: Vault + HSM (PKCS#11, FIPS 140-2, hardware key protection)
```

**Rule**: Never store secrets in:
- Environment variables (visible in `kubectl describe pod`)
- ConfigMaps (not encrypted)
- Git repositories (even base64 encoded)
- Container image layers (`docker history` reveals them)
- Application logs (filter before logging)

---

## HashiCorp Vault

### Vault Architecture (HA Production)

```
┌─────────────────────────────────────────────────────┐
│  Vault Cluster (3 nodes, Integrated Storage/Raft)   │
│                                                      │
│  vault-0 (active)  ←→  vault-1 (standby)            │
│       ↕                      ↕                      │
│  vault-2 (standby)                                  │
│                                                      │
│  Storage: Raft (integrated, no Consul needed)        │
│  Seal: AWS KMS / GCP KMS (auto-unseal)              │
│  Auth: Kubernetes, OIDC, AppRole                    │
│  Audit: File + Syslog                               │
└─────────────────────────────────────────────────────┘
```

### Vault Kubernetes Auth

```hcl
# Enable K8s auth method
vault auth enable kubernetes

# Configure with cluster details
vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  token_reviewer_jwt=@/var/run/secrets/kubernetes.io/serviceaccount/token \
  issuer="https://kubernetes.default.svc.cluster.local"

# Create role binding K8s SA to Vault policy
vault write auth/kubernetes/role/payment-service \
  bound_service_account_names=payment-service \
  bound_service_account_namespaces=payments \
  policies=payment-service-policy \
  ttl=1h \
  max_ttl=4h
```

### Vault Policies (Least-Privilege)

```hcl
# payment-service-policy.hcl
path "secret/data/payments/+/database" {
  capabilities = ["read"]
}

path "secret/data/payments/+/api-keys" {
  capabilities = ["read"]
}

# Dynamic database credentials (short-lived, auto-rotated)
path "database/creds/payment-db-role" {
  capabilities = ["read"]
}

# Deny admin paths
path "sys/*" {
  capabilities = ["deny"]
}

path "auth/*" {
  capabilities = ["deny"]
}
```

### Vault Agent Injector (K8s Sidecar)

```yaml
# Annotate deployment for Vault Agent auto-injection
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  template:
    metadata:
      annotations:
        # Enable injection
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "payment-service"

        # Inject secret as file
        vault.hashicorp.com/agent-inject-secret-db: "secret/data/payments/prod/database"
        vault.hashicorp.com/agent-inject-template-db: |
          {{- with secret "secret/data/payments/prod/database" -}}
          DB_HOST={{ .Data.data.host }}
          DB_PORT={{ .Data.data.port }}
          DB_USER={{ .Data.data.username }}
          DB_PASS={{ .Data.data.password }}
          {{- end }}

        # Vault sidecar resources
        vault.hashicorp.com/agent-requests-cpu: "50m"
        vault.hashicorp.com/agent-requests-mem: "64Mi"
        vault.hashicorp.com/agent-limits-cpu: "100m"
        vault.hashicorp.com/agent-limits-mem: "128Mi"

        # Renew lease before expiry
        vault.hashicorp.com/agent-pre-populate-only: "false"
        vault.hashicorp.com/secret-volume-path: "/vault/secrets"
```

### Vault Dynamic Database Credentials

```bash
# Enable database secrets engine
vault secrets enable database

# Configure PostgreSQL
vault write database/config/payment-db \
  plugin_name=postgresql-database-plugin \
  allowed_roles="payment-service-role" \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/payments?sslmode=require" \
  username="vault-admin" \
  password="vault-admin-password" \
  rotation_period="72h"

# Create role with TTL = 1 hour
vault write database/roles/payment-service-role \
  db_name=payment-db \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="4h"

# Application reads dynamic credentials (never static password)
vault read database/creds/payment-service-role
# Key      Value
# username v-kubern-payment-xm5vYuqAk
# password A1a-7zTvbFIXGq3oKp4t
# lease_duration  1h
```

---

## External Secrets Operator (ESO)

### AWS Secrets Manager Provider

```yaml
# ClusterSecretStore — admin-configured, usable across namespaces
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: aws-secrets-manager
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets-sa
            namespace: external-secrets
---
# ExternalSecret — reads from AWS SM, creates K8s Secret
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: payment-service-secrets
  namespace: payments
spec:
  refreshInterval: 5m          # Re-sync every 5 minutes
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: payment-service-secrets   # K8s Secret to create
    creationPolicy: Owner
    template:
      type: Opaque
      data:
        DATABASE_URL: "postgresql://{{ .db_user }}:{{ .db_pass }}@{{ .db_host }}/payments"
  data:
    - secretKey: db_user
      remoteRef:
        key: production/payments/database
        property: username
    - secretKey: db_pass
      remoteRef:
        key: production/payments/database
        property: password
    - secretKey: db_host
      remoteRef:
        key: production/payments/database
        property: host
```

### GCP Secret Manager Provider

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: gcp-secret-manager
  namespace: production
spec:
  provider:
    gcpsm:
      projectID: my-gcp-project
      auth:
        workloadIdentity:
          clusterLocation: us-central1
          clusterName: production-cluster
          clusterProjectID: my-gcp-project
          serviceAccountRef:
            name: external-secrets-sa
```

---

## Sealed Secrets

```bash
# Install Sealed Secrets controller
helm install sealed-secrets \
  sealed-secrets/sealed-secrets \
  --namespace kube-system \
  --set fullnameOverride=sealed-secrets-controller

# Seal a secret (asymmetric encryption, private key stays in cluster)
kubectl create secret generic my-secret \
  --from-literal=password=supersecret \
  --dry-run=client -o yaml | \
  kubeseal --format yaml > my-sealed-secret.yaml

# my-sealed-secret.yaml is safe to commit to Git
# Only the cluster's private key can unseal it
```

---

## SOPS (Secrets OPerationS)

```yaml
# .sops.yaml — configure encryption by path
creation_rules:
  - path_regex: environments/production/.*\.yaml$
    kms: arn:aws:kms:us-east-1:123456789012:key/mrk-abc123
    gcp_kms: projects/my-project/locations/global/keyRings/my-ring/cryptoKeys/my-key
    age: age1xxxxxxxxxx...
    encrypted_regex: "^(data|stringData)$"  # Only encrypt secret values

  - path_regex: environments/staging/.*\.yaml$
    age: age1xxxxxxxxxx...   # Age key for staging (simpler)
```

```bash
# Encrypt secrets
sops --encrypt secrets.yaml > secrets.enc.yaml

# Decrypt for use
sops --decrypt secrets.enc.yaml | kubectl apply -f -

# Edit in-place (decrypts → editor → re-encrypts)
sops secrets.enc.yaml
```

---

## Secret Rotation Best Practices

```
Rotation Intervals:
  Database passwords:     24h (use Vault dynamic creds)
  API keys:               30 days (automated rotation)
  Service account tokens: 1h (projected tokens, K8s native)
  TLS certificates:       90 days (cert-manager auto-renew)
  Root CA:                1-5 years (HSM-protected)
  Encryption keys:        Annual (AWS KMS auto-rotation)

Rotation Process:
  1. Generate new secret
  2. Update consumers (rolling deploy)
  3. Verify all consumers use new secret
  4. Revoke old secret
  5. Audit log the rotation event
```

---

## Secret Detection in CI

```bash
# detect-secrets pre-commit hook
pip install detect-secrets
detect-secrets scan > .secrets.baseline

# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']

# GitLeaks in CI
gitleaks detect --source . --exit-code 1 --redact
```
