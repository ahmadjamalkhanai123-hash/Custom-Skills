# Secrets Management Reference

OIDC keyless auth, Vault integration, cloud KMS, secret scanning, and least privilege.

---

## Secret Management by Tier

| Tier | Strategy | Tools |
|------|----------|-------|
| 1 — Dev | Platform-native secrets | .env files (not committed), direnv |
| 2 — Standard | CI platform secrets | GitHub Secrets, GitLab CI vars, Azure Key groups |
| 3 — Production | OIDC + short-lived tokens | GitHub OIDC → AWS/GCP/Azure (no static keys) |
| 4 — Microservices | Dynamic secrets + Vault | HashiCorp Vault, AWS Secrets Manager |
| 5 — Enterprise | Just-in-time secrets | Vault + PKI + dynamic DB credentials |

---

## OIDC (Keyless Auth) — Mandatory for Tier 3+

### How OIDC Works
```
GitHub Actions runner
       │
       │ 1. Request OIDC token (JWT) from GitHub IdP
       ▼
GitHub OIDC Provider
       │
       │ 2. Present JWT to cloud provider
       ▼
Cloud Provider (AWS/GCP/Azure)
       │
       │ 3. Verify JWT signature + claims (repo, branch, ref)
       │ 4. Issue short-lived credentials (15min - 1hr)
       ▼
CI Job uses credentials (no stored secrets)
```

### GitHub Actions → AWS OIDC
```yaml
# Setup once in AWS:
# 1. Add GitHub as Identity Provider
# 2. Create IAM Role with trust policy:
# {
#   "Condition": {
#     "StringLike": {
#       "token.actions.githubusercontent.com:sub": "repo:ORG/REPO:*"
#     }
#   }
# }

permissions:
  id-token: write    # REQUIRED for OIDC
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::123456789:role/GithubActionsRole
      aws-region: us-east-1
      # role-session-name: MySession (optional)
      # role-duration-seconds: 3600 (default)

  - name: Access AWS Resources (no static keys)
    run: |
      aws ecr get-login-password | docker login --username AWS \
        --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com
      aws s3 ls s3://my-bucket/
```

### GitHub Actions → GCP OIDC
```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: >-
        projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider
      service_account: ci-deployer@my-project.iam.gserviceaccount.com

  - uses: google-github-actions/setup-gcloud@v2

  - name: Deploy to GKE
    run: |
      gcloud container clusters get-credentials my-cluster --region us-central1
      kubectl apply -f k8s/
```

### GitHub Actions → Azure OIDC (Federated Credentials)
```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: azure/login@v2
    with:
      client-id: ${{ secrets.AZURE_CLIENT_ID }}
      tenant-id: ${{ secrets.AZURE_TENANT_ID }}
      subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      # Uses federated identity credential — no client secret
```

### GitLab CI OIDC
```yaml
deploy:
  id_tokens:
    GITLAB_OIDC_TOKEN:
      aud: "https://vault.example.com"  # For Vault
  script:
    # Exchange OIDC token for Vault credentials
    - |
      VAULT_TOKEN=$(vault write -field=token auth/jwt/login \
        role=gitlab-ci \
        jwt="${GITLAB_OIDC_TOKEN}")
      export VAULT_TOKEN
      vault kv get -field=password secret/myapp/db
```

---

## HashiCorp Vault Integration

### Vault Agent (Kubernetes)
```yaml
# K8s Deployment with Vault Agent sidecar
annotations:
  vault.hashicorp.com/agent-inject: "true"
  vault.hashicorp.com/role: "myapp"
  vault.hashicorp.com/agent-inject-secret-db-password: "secret/data/myapp/db"
  vault.hashicorp.com/agent-inject-template-db-password: |
    {{- with secret "secret/data/myapp/db" -}}
    export DB_PASSWORD="{{ .Data.data.password }}"
    {{- end }}
# Vault Agent writes secrets to /vault/secrets/ at runtime
# App reads /vault/secrets/db-password (no secrets in env vars or config)
```

### Dynamic Database Credentials (Just-in-Time)
```python
# App fetches short-lived DB credentials at startup (never stored)
import hvac

def get_db_credentials():
    client = hvac.Client(url=os.environ["VAULT_ADDR"])
    client.auth.kubernetes.login(role="myapp", jwt=get_k8s_jwt())

    # Generate dynamic credentials (expire in 1h)
    creds = client.secrets.database.generate_credentials(name="myapp-readonly")
    return creds["data"]["username"], creds["data"]["password"]
```

### Vault in CI Pipeline
```yaml
- name: Get Secrets from Vault
  uses: hashicorp/vault-action@v3
  id: secrets
  with:
    url: https://vault.example.com
    method: jwt
    jwtGithubAudience: "vault.example.com"
    role: github-ci
    secrets: |
      secret/data/myapp/production db_password | DB_PASSWORD ;
      secret/data/myapp/production api_key | EXTERNAL_API_KEY

- name: Use Secret (masked in logs)
  run: |
    # ${{ steps.secrets.outputs.DB_PASSWORD }} is auto-masked
    export DB_PASSWORD="${{ steps.secrets.outputs.DB_PASSWORD }}"
```

---

## AWS Secrets Manager

### Fetch in CI (with OIDC auth)
```bash
# After OIDC auth (no static keys needed)
SECRET=$(aws secretsmanager get-secret-value \
  --secret-id myapp/production/db \
  --query SecretString \
  --output text)

DB_PASSWORD=$(echo $SECRET | jq -r '.password')
# Mask in GitHub Actions:
echo "::add-mask::${DB_PASSWORD}"
echo "DB_PASSWORD=${DB_PASSWORD}" >> $GITHUB_ENV
```

### Fetch in Application
```python
import boto3
import json

def get_secret(secret_name: str, region: str = "us-east-1") -> dict:
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])

# Usage
creds = get_secret("myapp/production/database")
db = connect(host=creds["host"], password=creds["password"])
```

---

## Azure Key Vault

### Fetch in CI (with OIDC)
```yaml
- uses: azure/login@v2
  with:
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

- name: Get Secrets from Key Vault
  run: |
    DB_PASSWORD=$(az keyvault secret show \
      --vault-name myapp-production-kv \
      --name db-password \
      --query value -o tsv)
    echo "::add-mask::${DB_PASSWORD}"
    echo "DB_PASSWORD=${DB_PASSWORD}" >> $GITHUB_ENV
```

### Kubernetes CSI Provider (Runtime)
```yaml
# SecretProviderClass — sync Key Vault → K8s Secret
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: myapp-akv
spec:
  provider: azure
  parameters:
    keyvaultName: myapp-production-kv
    objects: |
      array:
        - |
          objectName: db-password
          objectType: secret
  secretObjects:
    - secretName: myapp-db-secret
      type: Opaque
      data:
        - objectName: db-password
          key: password
```

---

## Google Cloud Secret Manager

### Fetch in CI (OIDC)
```bash
# After google-github-actions/auth
DB_PASSWORD=$(gcloud secrets versions access latest \
  --secret="myapp-db-password" \
  --project="my-gcp-project")
echo "::add-mask::${DB_PASSWORD}"
echo "DB_PASSWORD=${DB_PASSWORD}" >> $GITHUB_ENV
```

---

## Secret Scanning (Prevent Leaks)

### Pre-commit Hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.0
    hooks:
      - id: gitleaks
        name: Detect hardcoded secrets

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

### CI Secret Scanning
```yaml
- name: TruffleHog (Full History Scan on PR)
  uses: trufflesecurity/trufflehog@v3.63.11
  with:
    path: ./
    base: ${{ github.event.pull_request.base.sha }}
    head: ${{ github.event.pull_request.head.sha }}
    extra_args: --only-verified

- name: Gitleaks Diff Scan
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### .gitleaks.toml (Custom Rules)
```toml
[allowlist]
  commits = ["abc123"]  # Exempt specific historical commits
  paths = [".secrets.baseline"]
  regexes = ["example.com", "placeholder"]

[[rules]]
  description = "Internal API Keys"
  id = "internal-api-key"
  regex = '''INTERNAL_[A-Z]+_KEY=[A-Za-z0-9]{32}'''
  tags = ["api", "internal"]
```

---

## Least Privilege Principles

### GitHub Actions Token Permissions
```yaml
# Global: restrict all permissions
permissions: {}

# Per-job: grant only what's needed
jobs:
  build:
    permissions:
      contents: read        # Checkout
      packages: write       # Push to GHCR
      id-token: write       # OIDC
      security-events: write # Upload SARIF results

  deploy:
    permissions:
      id-token: write       # OIDC to cloud
      # No 'contents: write' — deployment shouldn't push code
```

### IAM Role Scoping (AWS)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "arn:aws:ecr:us-east-1:123456789:repository/myapp"
    }
  ]
}
```

### Secret Masking in Logs
```yaml
# GitHub Actions — auto-mask registered secrets
# Any value stored in ${{ secrets.* }} is masked in logs

# For dynamically fetched secrets, add mask explicitly:
- name: Mask Dynamic Secrets
  run: |
    DB_PASS=$(fetch-secret db-password)
    echo "::add-mask::${DB_PASS}"
    # Now DB_PASS is masked: logs show ***

# GitLab CI masking
# Variables with 'masked' flag are automatically redacted in job logs
```
