# Cloud Auth Patterns — IRSA, Workload Identity, Azure AAD

## AWS: IAM Roles for Service Accounts (IRSA) {#irsa}

### How IRSA Works

```
Pod SA Token (OIDC signed)
      │
      ▼
AWS STS AssumeRoleWithWebIdentity
      │
      ▼
IAM Role with Trust Policy (allows EKS OIDC issuer)
      │
      ▼
Temporary AWS credentials (via IRSA projected volume)
```

### Setup Steps

```bash
# 1. Get OIDC issuer URL
aws eks describe-cluster --name my-cluster \
  --query "cluster.identity.oidc.issuer" --output text

# 2. Create OIDC provider in IAM
eksctl utils associate-iam-oidc-provider \
  --cluster my-cluster --approve

# 3. Create IAM role with trust policy
OIDC_ISSUER=$(aws eks describe-cluster --name my-cluster \
  --query "cluster.identity.oidc.issuer" --output text | sed s|https://||)

cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/${OIDC_ISSUER}"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "${OIDC_ISSUER}:sub": "system:serviceaccount:${NAMESPACE}:${SA_NAME}",
        "${OIDC_ISSUER}:aud": "sts.amazonaws.com"
      }
    }
  }]
}
EOF

aws iam create-role --role-name my-app-role \
  --assume-role-policy-document file://trust-policy.json

# 4. Attach policy to the role
aws iam attach-role-policy \
  --role-name my-app-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess
```

### ServiceAccount with IRSA Annotation

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: backend-app-sa
  namespace: team-backend
  annotations:
    eks.amazonaws.com/role-arn: "arn:aws:iam::123456789012:role/my-app-role"
    eks.amazonaws.com/token-expiration: "3600"          # 1 hour
    eks.amazonaws.com/sts-regional-endpoints: "true"   # Use regional STS
automountServiceAccountToken: false
```

### EKS Pod Identity (New, 2023+)

```bash
# Simpler than IRSA — no OIDC trust policy needed
eksctl create podidentityassociation \
  --cluster my-cluster \
  --namespace team-backend \
  --service-account-name backend-app-sa \
  --role-arn arn:aws:iam::123456789012:role/my-app-role
```

```yaml
# No annotation needed — EKS Pod Identity Agent handles binding
apiVersion: v1
kind: ServiceAccount
metadata:
  name: backend-app-sa
  namespace: team-backend
automountServiceAccountToken: false
```

---

## GCP: Workload Identity {#workload-identity}

### How Workload Identity Works

```
Pod SA Token ──► GKE Metadata Server (gke-metadata-server)
                        │
                        ▼
              Google IAM Token Exchange
                        │
                        ▼
              Google Service Account credentials
```

### Setup Steps

```bash
# 1. Enable Workload Identity on cluster
gcloud container clusters update my-cluster \
  --workload-pool=PROJECT_ID.svc.id.goog

# 2. Create Google Service Account
gcloud iam service-accounts create backend-app-gsa \
  --display-name="Backend App GSA"

# 3. Grant GSA permissions
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:backend-app-gsa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

# 4. Allow KSA to impersonate GSA
gcloud iam service-accounts add-iam-policy-binding \
  backend-app-gsa@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:PROJECT_ID.svc.id.goog[team-backend/backend-app-sa]"
```

### ServiceAccount with Workload Identity Annotation

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: backend-app-sa
  namespace: team-backend
  annotations:
    iam.gke.io/gcp-service-account: "backend-app-gsa@PROJECT_ID.iam.gserviceaccount.com"
automountServiceAccountToken: false
```

---

## Azure: Workload Identity (AAD) {#azure}

### How Azure Workload Identity Works

```
Pod SA Token (OIDC) ──► Azure AD Federated Credential
                               │
                               ▼
                    Azure AD Token ──► Azure Resources
```

### Setup Steps

```bash
# 1. Install Azure Workload Identity webhook
helm repo add azure-workload-identity https://azure.github.io/azure-workload-identity/charts
helm install workload-identity-webhook azure-workload-identity/workload-identity-webhook \
  --namespace azure-workload-identity-system \
  --set azureTenantID="${AZURE_TENANT_ID}"

# 2. Create Azure AD Application
az ad app create --display-name backend-app-aad

# 3. Create Federated Identity Credential
az ad app federated-credential create \
  --id "${APP_OBJECT_ID}" \
  --parameters "{
    \"name\": \"backend-app-federated\",
    \"issuer\": \"https://oidc.prod-aks.azure.com/${TENANT_ID}/${CLUSTER_NAME}/\",
    \"subject\": \"system:serviceaccount:team-backend:backend-app-sa\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }"

# 4. Create service principal and assign permissions
az ad sp create --id "${APP_ID}"
az role assignment create \
  --assignee "${APP_ID}" \
  --role "Storage Blob Data Reader" \
  --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/my-rg"
```

### ServiceAccount with Azure Workload Identity

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: backend-app-sa
  namespace: team-backend
  annotations:
    azure.workload.identity/client-id: "${AZURE_CLIENT_ID}"
    azure.workload.identity/tenant-id: "${AZURE_TENANT_ID}"
labels:
  azure.workload.identity/use: "true"
automountServiceAccountToken: false
```

---

## On-Prem / Bare-Metal: OIDC with Dex or Keycloak {#on-prem}

```bash
# kube-apiserver OIDC configuration
--oidc-issuer-url=https://dex.company.com
--oidc-client-id=kubernetes
--oidc-username-claim=email
--oidc-groups-claim=groups
--oidc-ca-file=/etc/kubernetes/pki/dex-ca.crt
```

```yaml
# Dex static client for kubectl
staticClients:
  - id: kubernetes
    redirectURIs:
      - http://localhost:8000
      - http://localhost:18000
    name: Kubernetes
    secret: dex-kubernetes-secret
```

---

## Multi-Cloud OIDC Federation

```yaml
# Cross-cloud SA federation via OIDC
# AWS → GCP: Use AWS OIDC issuer in GCP Workload Identity Pool
gcloud iam workload-identity-pools create aws-pool \
  --location="global" \
  --display-name="AWS Workload Identity Pool"

gcloud iam workload-identity-pools providers create-oidc aws-eks-provider \
  --location="global" \
  --workload-identity-pool="aws-pool" \
  --display-name="AWS EKS Provider" \
  --attribute-mapping="google.subject=assertion.sub" \
  --issuer-uri="https://oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B716D3041E"
```

## Cloud Auth Anti-Patterns

| Anti-Pattern | Risk | Fix |
|-------------|------|-----|
| Node IAM profile with broad permissions | All pods on node inherit permissions | Use IRSA/WI per SA |
| Long-lived credentials in Secrets | Credential exposure if etcd compromised | Use IRSA/WI/Vault |
| Wildcard IAM policies | Over-permissioned access | Scope to specific resources |
| Sharing SA across teams | Blast radius too large | One SA per workload |
| `automountServiceAccountToken: true` | Token mounted in all pods including untrusted | Set false, use projected |
