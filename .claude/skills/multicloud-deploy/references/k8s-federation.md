# Kubernetes Federation Reference

## Karmada (Recommended — CNCF Incubating)

Karmada is the primary multi-cluster orchestration layer for Tier 2+.
It provides a K8s-native API for distributing workloads across clusters.

### Architecture

```
┌──────────────────────────────────────────────┐
│         Karmada Control Plane                │
│  (dedicated management cluster or standalone) │
│                                              │
│  karmada-apiserver   karmada-controller-mgr  │
│  karmada-scheduler   karmada-webhook         │
│  etcd (karmada state)                        │
└──────────────────────┬───────────────────────┘
                       │ registers
       ┌───────────────┼───────────────┐
       │               │               │
  AWS EKS          GCP GKE        Azure AKS
  (member)         (member)       (member)
```

### Installation
```bash
# Install karmadactl
curl -s https://raw.githubusercontent.com/karmada-io/karmada/master/hack/install-cli.sh | bash

# Init Karmada control plane on management cluster
karmadactl init --kube-image-registry=registry.k8s.io

# Join member clusters
karmadactl join aws-eks \
  --kubeconfig=~/.kube/karmada.config \
  --cluster-kubeconfig=~/.kube/eks.config \
  --cluster-context=arn:aws:eks:us-east-1:ACCOUNT:cluster/prod-aws

karmadactl join gcp-gke \
  --kubeconfig=~/.kube/karmada.config \
  --cluster-kubeconfig=~/.kube/gke.config
```

### PropagationPolicy — Workload Distribution

```yaml
# Distribute to specific clouds with weights
apiVersion: policy.karmada.io/v1alpha1
kind: PropagationPolicy
metadata:
  name: checkout-api-propagation
  namespace: payments
spec:
  resourceSelectors:
    - apiVersion: apps/v1
      kind: Deployment
      name: checkout-api
  placement:
    clusterAffinity:
      clusterNames:
        - aws-eks
        - gcp-gke
        - azure-aks
    replicaScheduling:
      replicaSchedulingType: Divided
      replicaDivisionPreference: Weighted
      weightPreference:
        staticClusterWeight:
          - targetCluster:
              clusterNames: [aws-eks]
            weight: 5          # 50% traffic to AWS (primary)
          - targetCluster:
              clusterNames: [gcp-gke]
            weight: 3          # 30% to GCP
          - targetCluster:
              clusterNames: [azure-aks]
            weight: 2          # 20% to Azure
```

### PropagationPolicy — DR Failover

```yaml
# Active-passive: all traffic to primary, failover to secondary
apiVersion: policy.karmada.io/v1alpha1
kind: PropagationPolicy
metadata:
  name: failover-propagation
spec:
  resourceSelectors:
    - apiVersion: apps/v1
      kind: Deployment
      name: payment-service
  placement:
    clusterTolerations:
      - key: cluster.karmada.io/not-ready
        operator: Exists
        effect: NoExecute
        tolerationSeconds: 30    # failover after 30s of cluster unready
    clusterAffinity:
      clusterNames: [aws-eks, gcp-gke]
    spreadConstraints:
      - spreadByField: cluster
        minGroups: 1
        maxGroups: 2
```

### OverridePolicy — Cloud-Specific Configs

```yaml
# Override image registry per cloud
apiVersion: policy.karmada.io/v1alpha1
kind: OverridePolicy
metadata:
  name: aws-image-override
spec:
  resourceSelectors:
    - apiVersion: apps/v1
      kind: Deployment
  targetCluster:
    clusterNames: [aws-eks]
  overrideRules:
    - targetCluster:
        clusterNames: [aws-eks]
      overriders:
        imageOverrider:
          - component: Registry
            operator: replace
            value: "123456789.dkr.ecr.us-east-1.amazonaws.com"
    - targetCluster:
        clusterNames: [gcp-gke]
      overriders:
        imageOverrider:
          - component: Registry
            operator: replace
            value: "us-central1-docker.pkg.dev/my-project/prod"
```

### ClusterPropagationPolicy (Cluster-Scoped)
Use for Namespace, ClusterRole, ClusterRoleBinding distribution:
```yaml
apiVersion: policy.karmada.io/v1alpha1
kind: ClusterPropagationPolicy
metadata:
  name: namespace-propagation
spec:
  resourceSelectors:
    - apiVersion: v1
      kind: Namespace
      name: payments
  placement:
    clusterAffinity:
      matchExpressions:
        - key: cloud
          operator: In
          values: [aws, gcp, azure]
```

---

## Cluster API (CAPI)

Cluster API provisions K8s clusters via K8s-native API.
Use alongside Karmada: CAPI manages cluster lifecycle, Karmada manages workload distribution.

### Providers Required

| Provider Type | AWS | GCP | Azure |
|--------------|-----|-----|-------|
| Infrastructure | CAPA | CAPG | CAPZ |
| Bootstrap | kubeadm | kubeadm | kubeadm |
| Control Plane | kubeadm | kubeadm | kubeadm |

### Cluster Definition (AWS Example)
```yaml
apiVersion: cluster.x-k8s.io/v1beta1
kind: Cluster
metadata:
  name: prod-aws-us-east-1
  namespace: capi-system
spec:
  clusterNetwork:
    pods:
      cidrBlocks: ["10.10.0.0/16"]
    services:
      cidrBlocks: ["10.20.0.0/16"]
  infrastructureRef:
    apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
    kind: AWSCluster
    name: prod-aws-us-east-1
  controlPlaneRef:
    apiVersion: controlplane.cluster.x-k8s.io/v1beta1
    kind: KubeadmControlPlane
    name: prod-aws-us-east-1-cp
---
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: AWSCluster
metadata:
  name: prod-aws-us-east-1
spec:
  region: us-east-1
  sshKeyName: prod-key
  network:
    vpc:
      cidrBlock: "10.10.0.0/16"
```

### ClusterClass (Reusable Templates)
Define once, instantiate many:
```yaml
apiVersion: cluster.x-k8s.io/v1beta1
kind: ClusterClass
metadata:
  name: production-cluster-class
spec:
  controlPlane:
    ref:
      apiVersion: controlplane.cluster.x-k8s.io/v1beta1
      kind: KubeadmControlPlaneTemplate
      name: production-cp-template
  workers:
    machineDeployments:
      - class: default-worker
        template:
          ref:
            apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
            kind: AWSMachineTemplate
            name: production-worker-template
```

---

## Cilium Cluster Mesh

Network-layer federation — extends K8s NetworkPolicy across clusters.
Works with or without Karmada (complements workload distribution).

### Setup
```bash
# Enable cluster mesh on each cluster
cilium clustermesh enable --context=aws-eks
cilium clustermesh enable --context=gcp-gke

# Connect clusters
cilium clustermesh connect \
  --context=aws-eks \
  --destination-context=gcp-gke

# Verify
cilium clustermesh status --context=aws-eks
```

### Global Service (Cross-Cluster Load Balancing)
```yaml
apiVersion: v1
kind: Service
metadata:
  name: payment-service
  annotations:
    service.cilium.io/global: "true"           # expose across clusters
    service.cilium.io/shared: "true"            # share endpoints
    service.cilium.io/affinity: "local"         # prefer local-cluster endpoint
spec:
  selector:
    app: payment-service
  ports:
    - port: 8080
      targetPort: 8080
```

### Cross-Cluster Network Policy
```yaml
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: allow-cross-cluster
spec:
  endpointSelector:
    matchLabels:
      app: checkout-api
  ingress:
    - fromEndpoints:
        - matchLabels:
            io.cilium.k8s.namespace.labels.kubernetes.io/metadata.name: payments
            # This matches pods in 'payments' namespace across ALL mesh clusters
```

---

## Submariner (Alternative to Cilium for Cross-Cluster Networking)

Use when Cilium is not feasible (existing CNI constraints):

```bash
# Deploy Submariner broker
subctl deploy-broker --kubeconfig aws-broker.yaml

# Join clusters to broker
subctl join broker-info.subm \
  --clusterid aws-eks \
  --kubeconfig aws.yaml

subctl join broker-info.subm \
  --clusterid gcp-gke \
  --kubeconfig gcp.yaml
```

Submariner enables:
- Cross-cluster service discovery (ServiceExport/ServiceImport)
- Encrypted inter-cluster tunnel (WireGuard or IPSec)
- Globalnet for overlapping CIDR handling

---

## CIDR Planning (Critical — Must Define Before Provisioning)

No CIDR overlaps allowed across clouds. Plan allocation:

| Cloud | Pod CIDR | Service CIDR | Node CIDR |
|-------|----------|--------------|-----------|
| AWS us-east-1 | 10.10.0.0/16 | 10.20.0.0/16 | 10.30.0.0/24 |
| AWS eu-west-1 | 10.11.0.0/16 | 10.21.0.0/16 | 10.31.0.0/24 |
| GCP us-central1 | 172.16.0.0/16 | 172.17.0.0/16 | 172.18.0.0/24 |
| GCP eu-west4 | 172.19.0.0/16 | 172.20.0.0/16 | 172.21.0.0/24 |
| Azure eastus | 192.168.0.0/16 | 192.169.0.0/16 | 192.170.0.0/24 |
| Azure westeurope | 192.171.0.0/16 | 192.172.0.0/16 | 192.173.0.0/24 |
| On-prem | 100.64.0.0/16 | 100.65.0.0/16 | 100.66.0.0/24 |

**Rule**: Allocate /16 per cloud per region, subdivide for pods/services/nodes.

---

## Multi-Cluster RBAC

Karmada propagates RBAC from control plane to member clusters:

```yaml
# ClusterRole defined once, propagated everywhere
apiVersion: policy.karmada.io/v1alpha1
kind: ClusterPropagationPolicy
metadata:
  name: rbac-propagation
spec:
  resourceSelectors:
    - apiVersion: rbac.authorization.k8s.io/v1
      kind: ClusterRole
    - apiVersion: rbac.authorization.k8s.io/v1
      kind: ClusterRoleBinding
  placement:
    clusterAffinity:
      matchExpressions:
        - key: environment
          operator: In
          values: [production]
```

---

## Cluster Labels and Selectors

Label all member clusters for policy targeting:

```bash
kubectl label cluster aws-eks \
  cloud=aws \
  region=us-east-1 \
  environment=production \
  tier=primary \
  --kubeconfig=~/.kube/karmada.config

kubectl label cluster gcp-gke \
  cloud=gcp \
  region=us-central1 \
  environment=production \
  tier=secondary
```
