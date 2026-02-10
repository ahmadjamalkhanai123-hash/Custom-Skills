# Secrets Management

Full secrets maturity model from basic K8s Secrets through enterprise-grade Vault HA with dynamic credentials, CSI Secret Store Driver, and GitOps-safe encryption.

---

## Secrets Maturity Decision Tree

```
What is your security posture?

Dev/learning, no compliance?
  -> Tier 1: K8s Secrets + encryption at rest

Single team, need GitOps-safe secrets?
  -> Tier 2: Sealed Secrets (kubeseal)

Multi-team, external secret stores, compliance?
  -> Tier 3: External Secrets Operator + Vault

Enterprise, dynamic credentials, auto-rotation?
  -> Tier 4: Vault HA + dynamic database credentials

Zero-trust, secrets never in etcd, CSI volumes?
  -> Tier 5: CSI Secret Store Driver
```

---

## Tier 1: Kubernetes Secrets with Encryption at Rest

### Basic Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: api-credentials
  namespace: payments
  labels:
    app.kubernetes.io/name: api-server
type: Opaque
stringData:                       # plain text input (auto-encoded to base64)
  db-password: "supersecret123"
  api-key: "ak_live_abc123def456"
```

**Important:** `stringData` is a write-only convenience field. Kubernetes stores secrets as base64 in the `data` field. Base64 is encoding, NOT encryption.

### Encryption at Rest (EncryptionConfiguration)

Without this, secrets are stored in etcd as base64 (readable by anyone with etcd access).

```yaml
# /etc/kubernetes/encryption-config.yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - aescbc:                    # AES-CBC encryption
          keys:
            - name: key1
              secret: "c2VjcmV0LWtleS0xMjM0NTY3ODkwYWJjZGVm"  # 32-byte base64
      - identity: {}               # fallback for reading old unencrypted secrets
```

```bash
# Apply to kube-apiserver
# Add flag: --encryption-provider-config=/etc/kubernetes/encryption-config.yaml

# Verify encryption is active
kubectl get secret api-credentials -n payments -o json | \
  kubectl get --raw /api/v1/namespaces/payments/secrets/api-credentials

# Re-encrypt all existing secrets after enabling
kubectl get secrets --all-namespaces -o json | \
  kubectl replace -f -
```

### AWS KMS Provider (EKS)

```yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - kms:
          apiVersion: v2
          name: aws-kms
          endpoint: unix:///var/run/kmsplugin/socket.sock
      - identity: {}
```

### Mounting Secrets Best Practice

```yaml
# PREFERRED: Mount as file (auto-rotated by kubelet)
spec:
  containers:
    - name: app
      volumeMounts:
        - name: secrets
          mountPath: /etc/app/secrets
          readOnly: true
  volumes:
    - name: secrets
      secret:
        secretName: api-credentials
        defaultMode: 0400          # owner read-only
        items:
          - key: db-password
            path: db-password      # /etc/app/secrets/db-password

# AVOID: Environment variables (visible in process list, logs, core dumps)
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: api-credentials
        key: db-password
```

---

## Tier 2: Sealed Secrets

Sealed Secrets let you encrypt secrets client-side so they can be safely committed to Git.

### Install Sealed Secrets Controller

```bash
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm install sealed-secrets sealed-secrets/sealed-secrets \
  --namespace kube-system \
  --set fullnameOverride=sealed-secrets-controller

# Install kubeseal CLI
KUBESEAL_VERSION=$(curl -s https://api.github.com/repos/bitnami-labs/sealed-secrets/releases/latest | jq -r .tag_name | cut -c 2-)
curl -OL "https://github.com/bitnami-labs/sealed-secrets/releases/download/v${KUBESEAL_VERSION}/kubeseal-${KUBESEAL_VERSION}-linux-amd64.tar.gz"
tar -xvzf kubeseal-*.tar.gz kubeseal
sudo install -m 755 kubeseal /usr/local/bin/kubeseal
```

### Create a SealedSecret

```bash
# Create a regular secret (do NOT apply it)
kubectl create secret generic api-credentials \
  --namespace=payments \
  --from-literal=db-password='supersecret123' \
  --from-literal=api-key='ak_live_abc123def456' \
  --dry-run=client -o yaml > secret.yaml

# Seal it (encrypts with controller's public key)
kubeseal --format=yaml < secret.yaml > sealed-secret.yaml

# Delete the plaintext secret
rm secret.yaml
```

### SealedSecret YAML (safe to commit to Git)

```yaml
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: api-credentials
  namespace: payments
  annotations:
    sealedsecrets.bitnami.com/cluster-wide: "false"
spec:
  encryptedData:
    db-password: AgBy3i4OJSWK+PiTySYZZA9rO...   # encrypted
    api-key: AgCtr2KJSWK+PiTySYZZA9rO43...       # encrypted
  template:
    metadata:
      name: api-credentials
      namespace: payments
      labels:
        app.kubernetes.io/name: api-server
    type: Opaque
```

### Key Rotation

```bash
# Sealed Secrets controller auto-generates new keys every 30 days
# Old keys are retained to decrypt old SealedSecrets

# Force key rotation
kubectl -n kube-system delete secret \
  -l sealedsecrets.bitnami.com/sealed-secrets-key=active

# Re-seal all secrets with new key
kubeseal --re-encrypt < sealed-secret.yaml > sealed-secret-new.yaml

# Backup sealing keys (critical for disaster recovery)
kubectl get secret -n kube-system \
  -l sealedsecrets.bitnami.com/sealed-secrets-key \
  -o yaml > sealed-secrets-keys-backup.yaml
# Store this backup securely (Vault, cloud KMS, offline)
```

### Sealed Secrets Scopes

```bash
# strict (default): bound to name + namespace
kubeseal --scope strict

# namespace-wide: can be renamed within namespace
kubeseal --scope namespace-wide

# cluster-wide: can be moved to any namespace (least secure)
kubeseal --scope cluster-wide
```

---

## Tier 3: External Secrets Operator + HashiCorp Vault

External Secrets Operator (ESO) syncs secrets from external stores (Vault, AWS Secrets Manager, GCP Secret Manager, Azure Key Vault) into K8s Secrets.

### Install ESO

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace \
  --set installCRDs=true
```

### ClusterSecretStore (Vault backend)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "https://vault.example.com"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "external-secrets"
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

### ClusterSecretStore (AWS Secrets Manager)

```yaml
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
```

### ExternalSecret (sync from Vault to K8s Secret)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: api-credentials
  namespace: payments
  labels:
    app.kubernetes.io/name: api-server
spec:
  refreshInterval: 1h              # sync every hour
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: api-credentials           # K8s Secret name
    creationPolicy: Owner
    deletionPolicy: Retain
    template:
      type: Opaque
      metadata:
        labels:
          app.kubernetes.io/name: api-server
  data:
    - secretKey: db-password         # key in K8s Secret
      remoteRef:
        key: payments/api-server     # Vault path
        property: db-password        # Vault key
    - secretKey: api-key
      remoteRef:
        key: payments/api-server
        property: api-key
```

### ExternalSecret with Template (connection string)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: db-connection
  namespace: payments
spec:
  refreshInterval: 30m
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: db-connection
    template:
      engineVersion: v2
      data:
        DATABASE_URL: "postgresql://{{ .username }}:{{ .password }}@{{ .host }}:5432/{{ .database }}?sslmode=require"
  data:
    - secretKey: username
      remoteRef:
        key: payments/postgres
        property: username
    - secretKey: password
      remoteRef:
        key: payments/postgres
        property: password
    - secretKey: host
      remoteRef:
        key: payments/postgres
        property: host
    - secretKey: database
      remoteRef:
        key: payments/postgres
        property: database
```

### ExternalSecret with dataFrom (sync all keys)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: all-payment-secrets
  namespace: payments
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: payment-secrets
  dataFrom:
    - extract:
        key: payments/all-secrets    # all keys from this Vault path
```

---

## Tier 4: Vault HA with Dynamic Credentials

### Vault HA Deployment (Helm)

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  --values vault-values.yaml
```

```yaml
# vault-values.yaml
global:
  enabled: true
  tlsDisable: false

server:
  ha:
    enabled: true
    replicas: 3
    raft:
      enabled: true
      config: |
        ui = true
        listener "tcp" {
          address = "[::]:8200"
          cluster_address = "[::]:8201"
          tls_cert_file = "/vault/userconfig/vault-tls/tls.crt"
          tls_key_file = "/vault/userconfig/vault-tls/tls.key"
        }
        storage "raft" {
          path = "/vault/data"
          retry_join {
            leader_api_addr = "https://vault-0.vault-internal:8200"
          }
          retry_join {
            leader_api_addr = "https://vault-1.vault-internal:8200"
          }
          retry_join {
            leader_api_addr = "https://vault-2.vault-internal:8200"
          }
        }
        seal "awskms" {
          region     = "us-east-1"
          kms_key_id = "alias/vault-auto-unseal"
        }
        service_registration "kubernetes" {}
  resources:
    requests:
      cpu: 500m
      memory: 256Mi
    limits:
      cpu: "2"
      memory: 1Gi
  dataStorage:
    enabled: true
    size: 10Gi
    storageClass: gp3-encrypted
  auditStorage:
    enabled: true
    size: 10Gi

injector:
  enabled: true
  resources:
    requests:
      cpu: 50m
      memory: 64Mi
    limits:
      cpu: 250m
      memory: 128Mi

ui:
  enabled: true
```

### Auto-Unseal with AWS KMS (Terraform)

```hcl
# Terraform for Vault auto-unseal KMS key
resource "aws_kms_key" "vault_unseal" {
  description             = "Vault auto-unseal key"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "VaultUnseal"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.vault_server.arn
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_kms_alias" "vault_unseal" {
  name          = "alias/vault-auto-unseal"
  target_key_id = aws_kms_key.vault_unseal.key_id
}
```

### Dynamic Database Credentials

```bash
# Enable database secrets engine
vault secrets enable database

# Configure PostgreSQL connection
vault write database/config/payments-db \
  plugin_name=postgresql-database-plugin \
  allowed_roles="payments-readonly,payments-readwrite" \
  connection_url="postgresql://{{username}}:{{password}}@postgres.data.svc:5432/payments?sslmode=require" \
  username="vault-admin" \
  password="admin-password"

# Create a role for read-only access
vault write database/roles/payments-readonly \
  db_name=payments-db \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="24h"

# Create a role for read-write access
vault write database/roles/payments-readwrite \
  db_name=payments-db \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="24h"
```

### Vault Agent Injector Sidecar Pattern

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  namespace: payments
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "payments-api"
        vault.hashicorp.com/agent-inject-secret-db-creds: "database/creds/payments-readwrite"
        vault.hashicorp.com/agent-inject-template-db-creds: |
          {{- with secret "database/creds/payments-readwrite" -}}
          postgresql://{{ .Data.username }}:{{ .Data.password }}@postgres.data.svc:5432/payments?sslmode=require
          {{- end }}
        vault.hashicorp.com/agent-inject-secret-api-key: "secret/data/payments/api-key"
        vault.hashicorp.com/agent-inject-template-api-key: |
          {{- with secret "secret/data/payments/api-key" -}}
          {{ .Data.data.key }}
          {{- end }}
        vault.hashicorp.com/agent-pre-populate-only: "false"  # keep refreshing
        vault.hashicorp.com/agent-revoke-on-shutdown: "true"
        vault.hashicorp.com/agent-revoke-grace: "30"
    spec:
      serviceAccountName: api-server    # must match Vault K8s auth role
      containers:
        - name: api-server
          image: registry.example.com/api-server@sha256:abc123...
          # Secrets are written to /vault/secrets/db-creds and /vault/secrets/api-key
          # Application reads from files, auto-refreshed by Vault Agent
```

### Vault Kubernetes Auth Config

```bash
# Enable K8s auth in Vault
vault auth enable kubernetes

vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc:443"

# Create policy
vault policy write payments-api - <<EOF
path "secret/data/payments/*" {
  capabilities = ["read"]
}
path "database/creds/payments-readwrite" {
  capabilities = ["read"]
}
EOF

# Bind to K8s ServiceAccount
vault write auth/kubernetes/role/payments-api \
  bound_service_account_names=api-server \
  bound_service_account_namespaces=payments \
  policies=payments-api \
  ttl=1h
```

---

## Tier 5: CSI Secret Store Driver

The Secrets Store CSI Driver mounts secrets from external stores as volumes, without creating K8s Secret objects (secrets never in etcd).

### Install CSI Driver

```bash
helm repo add secrets-store-csi-driver https://kubernetes-sigs.github.io/secrets-store-csi-driver/charts
helm install csi-secrets-store secrets-store-csi-driver/secrets-store-csi-driver \
  --namespace kube-system \
  --set syncSecret.enabled=true \
  --set enableSecretRotation=true \
  --set rotationPollInterval=2m
```

### SecretProviderClass (Vault)

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: vault-payments-secrets
  namespace: payments
spec:
  provider: vault
  parameters:
    vaultAddress: "https://vault.vault.svc:8200"
    roleName: "payments-api"
    objects: |
      - objectName: "db-password"
        secretPath: "secret/data/payments/api-server"
        secretKey: "db-password"
      - objectName: "api-key"
        secretPath: "secret/data/payments/api-server"
        secretKey: "api-key"
  # Optional: also sync to K8s Secret (for env vars)
  secretObjects:
    - secretName: api-credentials-synced
      type: Opaque
      data:
        - objectName: db-password
          key: db-password
        - objectName: api-key
          key: api-key
```

### SecretProviderClass (AWS Secrets Manager)

```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: aws-payments-secrets
  namespace: payments
spec:
  provider: aws
  parameters:
    objects: |
      - objectName: "arn:aws:secretsmanager:us-east-1:123456789012:secret:payments/api-creds"
        objectType: "secretsmanager"
        jmesPath:
          - path: db-password
            objectAlias: db-password
          - path: api-key
            objectAlias: api-key
```

### Volume Mount Pattern

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  namespace: payments
spec:
  template:
    spec:
      serviceAccountName: api-server
      containers:
        - name: api-server
          image: registry.example.com/api-server@sha256:abc123...
          volumeMounts:
            - name: secrets
              mountPath: /mnt/secrets
              readOnly: true
          # Reads:
          #   /mnt/secrets/db-password
          #   /mnt/secrets/api-key
      volumes:
        - name: secrets
          csi:
            driver: secrets-store.csi.k8s.io
            readOnly: true
            volumeAttributes:
              secretProviderClass: vault-payments-secrets
```

---

## SOPS + age Encryption for GitOps

SOPS encrypts specific values in YAML/JSON files, leaving keys readable. Combined with age (modern encryption), it enables GitOps-safe secrets.

### Setup

```bash
# Install sops
brew install sops  # or download from https://github.com/getsops/sops

# Install age
brew install age

# Generate age key pair
age-keygen -o age-key.txt
# Public key: age1abc123...
# Store age-key.txt securely (Vault, 1Password, etc.)
```

### .sops.yaml Configuration

```yaml
# .sops.yaml (in repo root)
creation_rules:
  - path_regex: secrets/.*\.yaml$
    encrypted_regex: "^(data|stringData)$"
    age: "age1abc123def456..."    # public key
  - path_regex: secrets/prod/.*\.yaml$
    encrypted_regex: "^(data|stringData)$"
    age: "age1abc123def456...,age1prod789..."   # multiple recipients
```

### Encrypt/Decrypt Workflow

```bash
# Encrypt a secret file
sops --encrypt --in-place secrets/api-credentials.yaml

# Decrypt for editing
sops secrets/api-credentials.yaml    # opens in $EDITOR

# Decrypt to stdout
sops --decrypt secrets/api-credentials.yaml

# ArgoCD + SOPS: use ksops or argocd-vault-plugin
# Flux: native SOPS support with --decryption-provider=sops
```

### Flux SOPS Decryption

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: payments
  namespace: flux-system
spec:
  interval: 10m
  path: ./clusters/prod/payments
  prune: true
  sourceRef:
    kind: GitRepository
    name: platform-config
  decryption:
    provider: sops
    secretRef:
      name: sops-age         # K8s Secret containing age private key
```

---

## Secret Rotation Automation

### Vault Dynamic Secret Rotation (automatic)

Dynamic secrets from Vault (database credentials, AWS STS tokens) are automatically rotated at their TTL. No manual action needed.

### External Secrets Operator Rotation

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: rotating-secret
  namespace: payments
spec:
  refreshInterval: 15m       # check for changes every 15 min
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: api-credentials
    creationPolicy: Owner
  data:
    - secretKey: api-key
      remoteRef:
        key: payments/api-key
        version: ""           # always latest version
```

### Stakater Reloader (restart pods on secret change)

```bash
helm repo add stakater https://stakater.github.io/stakater-charts
helm install reloader stakater/reloader --namespace kube-system
```

```yaml
# Annotate deployment to auto-restart when secret changes
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  namespace: payments
  annotations:
    reloader.stakater.com/auto: "true"
    # Or be specific:
    # secret.reloader.stakater.com/reload: "api-credentials"
```

---

## Anti-Patterns and Fixes

| Anti-Pattern | Why It Is Dangerous | Fix |
|--------------|-------------------|-----|
| Secrets in env vars | Visible in `/proc`, logs, core dumps, `kubectl describe` | Mount as files with `0400` mode |
| Base64 = encrypted | Base64 is encoding, trivially decoded | Use encryption at rest + Sealed Secrets or ESO |
| Secrets in ConfigMaps | ConfigMaps have no encryption, wider RBAC | Use Secret objects or external stores |
| Hardcoded in manifests | Leaked in Git history forever | Use Sealed Secrets, SOPS, or ESO |
| `kubectl create secret` in scripts | Plain text in shell history, CI logs | Use kubeseal, SOPS, or Vault CLI |
| Shared secrets across namespaces | Blast radius, no audit trail | Per-namespace ExternalSecret with least-privilege Vault policy |
| No rotation policy | Stale credentials, compliance failure | Vault dynamic secrets or ESO refreshInterval |
| Sealing key not backed up | Lose Sealed Secrets controller = lose all secrets | Backup controller keys to Vault/KMS |
| `automountServiceAccountToken: true` | SA token readable by all containers in pod | Default `false`, mount only when needed |
| Secrets in Docker image layers | Extractable from image history | Multi-stage builds, runtime injection only |

---

## Tier Selection Summary

| Feature | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---------|--------|--------|--------|--------|--------|
| Storage | etcd (base64) | etcd (encrypted) | External store | Vault HA | Never in etcd |
| Encryption | At-rest (AES/KMS) | Sealed Secrets | Vault transit | Vault + KMS | CSI volume |
| Rotation | Manual | Manual re-seal | ESO refresh | Dynamic (auto) | CSI rotation |
| GitOps safe | No | Yes (sealed) | Yes (ESO CRD) | Yes (ESO CRD) | Yes (SPC CRD) |
| Audit trail | K8s audit log | K8s audit log | Vault audit | Vault audit | Vault audit |
| Dynamic creds | No | No | No | Yes | Yes |
| Complexity | Low | Low-Medium | Medium | High | High |
| Best for | Dev/learning | Small teams | Multi-team | Enterprise | Zero-trust |
