# Environment Tiers — Authorization Configurations

## Tier 1: Local Developer (kind / minikube / k3s)

### kind Cluster with RBAC Enabled

```yaml
# kind-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: dev-cluster
kubeadmConfigPatches:
  - |
    kind: ClusterConfiguration
    apiServer:
      extraArgs:
        authorization-mode: "Node,RBAC"
        audit-log-path: "/var/log/kubernetes/audit.log"
        audit-log-maxage: "7"
        audit-policy-file: "/etc/kubernetes/audit-policy.yaml"
    extraVolumes:
      - name: audit-policy
        hostPath: /etc/kubernetes/audit-policy.yaml
        mountPath: /etc/kubernetes/audit-policy.yaml
        readOnly: true
nodes:
  - role: control-plane
    extraMounts:
      - hostPath: ./audit-policy.yaml
        containerPath: /etc/kubernetes/audit-policy.yaml
```

### Developer Bootstrap (Tier 1 RBAC)

```bash
#!/bin/bash
# bootstrap-dev.sh — Create dev RBAC with kind

# Create namespace + SA
kubectl create namespace dev
kubectl create serviceaccount dev-app -n dev

# Developer ClusterRoleBinding
kubectl create clusterrolebinding dev-app-viewer \
  --clusterrole=view \
  --serviceaccount=dev:dev-app

# Test access
kubectl auth can-i list pods -n dev \
  --as=system:serviceaccount:dev:dev-app
```

---

## Tier 2: Standard (Single Cluster, Staging)

### Namespace RBAC + Kyverno Baseline

```yaml
# staging-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: staging
  labels:
    environment: staging
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
---
# ResourceQuota for staging
apiVersion: v1
kind: ResourceQuota
metadata:
  name: staging-quota
  namespace: staging
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    pods: "50"
    secrets: "20"
```

---

## Tier 3: Production (Regulated, OIDC + Audit)

### API Server Flags for Production OIDC

```bash
# /etc/kubernetes/manifests/kube-apiserver.yaml additions
- --authorization-mode=Node,RBAC
- --oidc-issuer-url=https://sso.company.com
- --oidc-client-id=kubernetes
- --oidc-username-claim=email
- --oidc-username-prefix=oidc:
- --oidc-groups-claim=groups
- --oidc-groups-prefix=oidc:
- --audit-log-path=/var/log/kubernetes/audit.log
- --audit-log-maxage=90
- --audit-log-maxbackup=10
- --audit-log-maxsize=100
- --audit-policy-file=/etc/kubernetes/audit-policy.yaml
- --enable-admission-plugins=NodeRestriction,PodSecurity,ServiceAccount
- --service-account-issuer=https://kubernetes.default.svc
- --service-account-signing-key-file=/etc/kubernetes/pki/sa.key
- --service-account-key-file=/etc/kubernetes/pki/sa.pub
```

### Production Namespace Template

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    environment: production
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: latest
  annotations:
    authorizer.io/tier: "3"
    authorizer.io/compliance: "soc2,hipaa"
```

---

## Tier 4: Enterprise (Cloud, IRSA/WI, SPIFFE)

### EKS Production Authorization Stack

```yaml
# aws-auth ConfigMap (EKS node + IAM role mappings)
apiVersion: v1
kind: ConfigMap
metadata:
  name: aws-auth
  namespace: kube-system
data:
  mapRoles: |
    - rolearn: arn:aws:iam::123456789012:role/eks-node-role
      username: system:node:{{EC2PrivateDNSName}}
      groups:
        - system:bootstrappers
        - system:nodes
    - rolearn: arn:aws:iam::123456789012:role/platform-admin-role
      username: platform-admin
      groups:
        - system:masters
    - rolearn: arn:aws:iam::123456789012:role/dev-team-role
      username: dev-team
      groups:
        - oidc:dev-team
  mapUsers: |
    - userarn: arn:aws:iam::123456789012:user/ops-user
      username: ops-user
      groups:
        - system:masters
```

### GKE Production Authorization Stack

```bash
# Enable Workload Identity on existing cluster
gcloud container clusters update production \
  --workload-pool=PROJECT_ID.svc.id.goog \
  --region=us-central1

# Enable Binary Authorization
gcloud container clusters update production \
  --binauthz-evaluation-mode=PROJECT_SINGLETON_POLICY_ENFORCE

# Enable Autopilot-style node auto-provisioning with SA restriction
gcloud container node-pools update default-pool \
  --cluster=production \
  --workload-metadata=GKE_METADATA
```

### AKS Production Authorization Stack

```bash
# Enable AAD integration and RBAC
az aks update \
  --resource-group my-rg \
  --name production \
  --enable-aad \
  --aad-admin-group-object-ids $AAD_ADMIN_GROUP_ID \
  --enable-azure-rbac

# Enable workload identity
az aks update \
  --resource-group my-rg \
  --name production \
  --enable-workload-identity \
  --enable-oidc-issuer
```

---

## Tier 5: Multi-Cluster / Enterprise Fleet

### Fleet RBAC Strategy

```
Global Identity (OIDC/AAD/Google Identity)
        │
        ├──► Hub Cluster (GitOps + Policy)
        │         │
        │         ├── ArgoCD RBAC → controls deployment to all spokes
        │         ├── ACM / Config Sync → pushes RBAC manifests to spokes
        │         └── SPIRE federation → cross-cluster SVIDs
        │
        ├──► Production Cluster (restricted)
        │         ├── Namespace RBAC from Git
        │         └── OPA/Kyverno enforced
        │
        └──► Staging Cluster (standard)
                  ├── Namespace RBAC from Git
                  └── Kyverno audit mode
```

### Hierarchical Namespace Controller (HNC)

```yaml
# HNC: propagate RBAC from parent to child namespaces
apiVersion: hnc.x-k8s.io/v1alpha2
kind: HierarchyConfiguration
metadata:
  name: hierarchy
  namespace: team-backend
spec:
  parent: company-root
---
# RoleBinding in parent auto-propagates to children
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: bind-sre-platform
  namespace: team-backend
  annotations:
    hnc.x-k8s.io/inherited-from: company-root
subjects:
  - kind: Group
    name: oidc:sre-team
roleRef:
  kind: ClusterRole
  name: authorizer:sre:platform-operator
  apiGroup: rbac.authorization.k8s.io
```

## Environment Authorization Defaults

| Environment | PSA Level | Policy Engine | Zero-Trust | Audit |
|-------------|----------|---------------|------------|-------|
| Local dev (kind) | privileged | None | None | Minimal |
| Staging | baseline | Kyverno audit | cert-manager | Standard |
| Production | restricted | Kyverno enforce + OPA | cert-manager + mTLS | Full |
| Enterprise | restricted | Both enforce | SPIFFE/SPIRE | Extended 90d |
| Multi-cluster | restricted | Both enforce | SPIFFE federated | Centralized |
