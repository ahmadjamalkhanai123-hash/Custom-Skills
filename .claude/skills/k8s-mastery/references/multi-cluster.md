# Multi-Cluster Kubernetes Patterns

Production patterns for managing, networking, and federating multiple Kubernetes clusters.

---

## ArgoCD Hub-Spoke Model

### Management Cluster Configuration

```yaml
# Register workload clusters as ArgoCD targets
apiVersion: v1
kind: Secret
metadata:
  name: cluster-us-east-production
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: cluster
    env: production
    region: us-east-1
    tier: primary
type: Opaque
stringData:
  name: production-us-east
  server: https://k8s-api.us-east.example.com
  config: |
    {
      "execProviderConfig": {
        "command": "argocd-k8s-auth",
        "args": ["aws", "--cluster-name", "prod-us-east"],
        "apiVersion": "client.authentication.k8s.io/v1beta1"
      },
      "tlsClientConfig": {
        "insecure": false,
        "caData": "LS0tLS1CRUdJTi..."
      }
    }

---
# ApplicationSet deploying to all production clusters
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: platform-services
  namespace: argocd
spec:
  goTemplate: true
  generators:
    - clusters:
        selector:
          matchLabels:
            env: production
  template:
    metadata:
      name: "platform-{{ .name }}"
    spec:
      project: platform
      source:
        repoURL: https://github.com/org/platform-gitops.git
        targetRevision: main
        path: "platform/overlays/{{ .metadata.labels.region }}"
      destination:
        server: "{{ .server }}"
        namespace: platform
      syncPolicy:
        automated:
          prune: true
          selfHeal: true

---
# Per-cluster configuration via values
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: regional-apps
  namespace: argocd
spec:
  goTemplate: true
  generators:
    - clusters:
        selector:
          matchLabels:
            env: production
        values:
          dns_zone: "{{ .metadata.labels.region }}.example.com"
          replicas: '{{ if eq .metadata.labels.tier "primary" }}5{{ else }}3{{ end }}'
  template:
    metadata:
      name: "api-{{ .name }}"
    spec:
      source:
        repoURL: https://github.com/org/platform-gitops.git
        path: apps/api-service/base
        kustomize:
          patches:
            - target:
                kind: Deployment
              patch: |
                - op: replace
                  path: /spec/replicas
                  value: {{ .values.replicas }}
            - target:
                kind: Ingress
              patch: |
                - op: replace
                  path: /spec/rules/0/host
                  value: api.{{ .values.dns_zone }}
      destination:
        server: "{{ .server }}"
        namespace: production
```

---

## Istio Multi-Primary (Multi-Cluster Service Mesh)

### Shared Trust Domain Setup

```yaml
# Cluster 1: us-east
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: istio-control-plane
  namespace: istio-system
spec:
  profile: default
  values:
    global:
      meshID: production-mesh
      multiCluster:
        clusterName: us-east
      network: network-east
    pilot:
      env:
        PILOT_ENABLE_CROSS_CLUSTER_WORKLOAD_ENTRY: "true"
  meshConfig:
    defaultConfig:
      proxyMetadata:
        ISTIO_META_DNS_CAPTURE: "true"
        ISTIO_META_DNS_AUTO_ALLOCATE: "true"
    trustDomain: example.com
    # Enable mTLS across clusters
    accessLogFile: /dev/stdout

---
# Remote secret: allow cluster 1 to discover services in cluster 2
# Generated with: istioctl create-remote-secret --name=us-west --server=https://k8s-api.us-west.example.com
apiVersion: v1
kind: Secret
metadata:
  name: istio-remote-secret-us-west
  namespace: istio-system
  labels:
    istio/multiCluster: "true"
  annotations:
    networking.istio.io/cluster: us-west
type: Opaque
data:
  us-west: <base64-encoded-kubeconfig>

---
# Cross-cluster gateway
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: cross-cluster-gateway
  namespace: istio-system
spec:
  selector:
    istio: eastwestgateway
  servers:
    - port:
        number: 15443
        name: tls
        protocol: TLS
      tls:
        mode: AUTO_PASSTHROUGH
      hosts:
        - "*.local"
```

### Cross-Cluster Service Discovery

```yaml
# ServiceEntry for explicit cross-cluster routing
apiVersion: networking.istio.io/v1beta1
kind: ServiceEntry
metadata:
  name: payment-service-us-west
  namespace: production
spec:
  hosts:
    - payment-service.production.svc.cluster.local
  location: MESH_INTERNAL
  ports:
    - number: 8080
      name: http
      protocol: HTTP
  resolution: DNS
  endpoints:
    - address: payment-service.production.svc.cluster.local
      network: network-west
      locality: us-west-2/us-west-2a

---
# Locality-aware load balancing
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: payment-service
  namespace: production
spec:
  host: payment-service.production.svc.cluster.local
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 1000
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 10s
      baseEjectionTime: 30s
    loadBalancer:
      localityLbSetting:
        enabled: true
        failover:
          - from: us-east-1
            to: us-west-2
        distribute:
          - from: us-east-1/*
            to:
              "us-east-1/*": 80
              "us-west-2/*": 20
```

---

## Cilium ClusterMesh

### ClusterMesh Configuration

```yaml
# Enable ClusterMesh on each cluster via Helm values
# Cluster 1
cilium:
  cluster:
    name: us-east
    id: 1
  clustermesh:
    useAPIServer: true
    apiserver:
      replicas: 3
      service:
        type: LoadBalancer
        annotations:
          service.beta.kubernetes.io/aws-load-balancer-scheme: internal
      tls:
        auto:
          enabled: true
          method: helm
  ipam:
    mode: cluster-pool
    operator:
      clusterPoolIPv4PodCIDRList:
        - 10.1.0.0/16  # Must not overlap with other clusters

---
# Cluster 2
cilium:
  cluster:
    name: us-west
    id: 2
  clustermesh:
    useAPIServer: true
    apiserver:
      replicas: 3
  ipam:
    mode: cluster-pool
    operator:
      clusterPoolIPv4PodCIDRList:
        - 10.2.0.0/16  # Non-overlapping CIDR

# Connect clusters:
# cilium clustermesh connect --context us-east --destination-context us-west
```

### Global Services with Cilium

```yaml
# Service available across all clusters
apiVersion: v1
kind: Service
metadata:
  name: shared-cache
  namespace: production
  annotations:
    io.cilium/global-service: "true"
    io.cilium/shared-service: "true"  # Share endpoints across clusters
spec:
  selector:
    app: redis-cache
  ports:
    - port: 6379
      protocol: TCP

---
# Affinity: prefer local cluster, failover to remote
apiVersion: v1
kind: Service
metadata:
  name: api-service
  namespace: production
  annotations:
    io.cilium/global-service: "true"
    io.cilium/service-affinity: "local"  # Prefer local endpoints
spec:
  selector:
    app: api-service
  ports:
    - port: 8080
```

---

## Submariner: Cross-Cluster Networking

```yaml
# Submariner Broker (on management cluster)
apiVersion: submariner.io/v1alpha1
kind: Broker
metadata:
  name: submariner-broker
  namespace: submariner-k8s-broker
spec:
  globalnetEnabled: true  # Handle overlapping CIDRs
  globalnetCIDRRange: 242.0.0.0/8

---
# Submariner Join (on each workload cluster)
# subctl join broker-info.subm --clusterid us-east --natt=false

# Export a service for cross-cluster access
apiVersion: multicluster.x-k8s.io/v1alpha1
kind: ServiceExport
metadata:
  name: database-primary
  namespace: production

---
# Import service in consuming cluster
apiVersion: multicluster.x-k8s.io/v1alpha1
kind: ServiceImport
metadata:
  name: database-primary
  namespace: production
spec:
  type: ClusterSetIP
  ports:
    - port: 5432
      protocol: TCP
# Access via: database-primary.production.svc.clusterset.local
```

---

## Multi-Cluster DNS

### ExternalDNS for Multi-Cluster

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: external-dns
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: external-dns
  template:
    spec:
      serviceAccountName: external-dns
      containers:
        - name: external-dns
          image: registry.k8s.io/external-dns/external-dns:v0.14.0
          args:
            - --source=service
            - --source=ingress
            - --provider=aws
            - --aws-zone-type=public
            - --domain-filter=example.com
            - --policy=upsert-only
            - --registry=txt
            - --txt-owner-id=us-east-cluster
            - --txt-prefix=externaldns-
          env:
            - name: AWS_DEFAULT_REGION
              value: us-east-1

---
# Split-horizon DNS: internal vs external resolution
apiVersion: v1
kind: Service
metadata:
  name: api-service
  namespace: production
  annotations:
    # Public DNS record
    external-dns.alpha.kubernetes.io/hostname: api.example.com
    # Weighted routing across clusters
    external-dns.alpha.kubernetes.io/aws-weight: "70"
    external-dns.alpha.kubernetes.io/set-identifier: us-east
spec:
  type: LoadBalancer
  selector:
    app: api-service
  ports:
    - port: 443
      targetPort: 8080
```

---

## Active-Passive Failover Pattern

```yaml
# Primary cluster: weight 100
apiVersion: v1
kind: Service
metadata:
  name: api-primary
  namespace: production
  annotations:
    external-dns.alpha.kubernetes.io/hostname: api.example.com
    external-dns.alpha.kubernetes.io/aws-failover: PRIMARY
    external-dns.alpha.kubernetes.io/set-identifier: us-east-primary
    external-dns.alpha.kubernetes.io/aws-health-check-id: "abc123"
spec:
  type: LoadBalancer
  selector:
    app: api-service

---
# Secondary cluster: failover target
apiVersion: v1
kind: Service
metadata:
  name: api-secondary
  namespace: production
  annotations:
    external-dns.alpha.kubernetes.io/hostname: api.example.com
    external-dns.alpha.kubernetes.io/aws-failover: SECONDARY
    external-dns.alpha.kubernetes.io/set-identifier: us-west-secondary
spec:
  type: LoadBalancer
  selector:
    app: api-service

---
# Health check CRD (AWS Route53)
# Configured outside K8s; checks /healthz endpoint on primary LB
# Automatic failover when primary health check fails
```

---

## Active-Active with Global Load Balancing

```yaml
# GKE Multi-Cluster Ingress
apiVersion: networking.gke.io/v1
kind: MultiClusterIngress
metadata:
  name: api-global
  namespace: production
  annotations:
    networking.gke.io/static-ip: "global-api-ip"
    networking.gke.io/pre-shared-certs: "api-cert"
spec:
  template:
    spec:
      backend:
        serviceName: api-service
        servicePort: 8080
      rules:
        - host: api.example.com
          http:
            paths:
              - path: /*
                backend:
                  serviceName: api-service
                  servicePort: 8080

---
apiVersion: networking.gke.io/v1
kind: MultiClusterService
metadata:
  name: api-service
  namespace: production
  annotations:
    networking.gke.io/app-protocols: '{"http":"HTTP"}'
    beta.cloud.google.com/backend-config: '{"default":"api-backend-config"}'
spec:
  template:
    spec:
      selector:
        app: api-service
      ports:
        - port: 8080
          name: http
  clusters:
    - link: "us-east1/production-us-east"
    - link: "europe-west1/production-eu-west"
```

---

## Cross-Cluster RBAC via Shared OIDC

```yaml
# Dex OIDC provider on management cluster
apiVersion: v1
kind: ConfigMap
metadata:
  name: dex-config
  namespace: dex
data:
  config.yaml: |
    issuer: https://dex.example.com
    storage:
      type: kubernetes
      config:
        inCluster: true
    connectors:
      - type: oidc
        id: google
        name: Google
        config:
          issuer: https://accounts.google.com
          clientID: $GOOGLE_CLIENT_ID
          clientSecret: $GOOGLE_CLIENT_SECRET
          redirectURI: https://dex.example.com/callback
          scopes: [openid, profile, email, groups]
    staticClients:
      - id: kubernetes
        name: Kubernetes
        secret: $DEX_CLIENT_SECRET
        redirectURIs:
          - http://localhost:8000
          - https://argocd.example.com/api/dex/callback

---
# kube-apiserver flags (on each workload cluster)
# --oidc-issuer-url=https://dex.example.com
# --oidc-client-id=kubernetes
# --oidc-username-claim=email
# --oidc-groups-claim=groups

# Consistent RBAC across all clusters
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: platform-admins
subjects:
  - kind: Group
    name: platform-team@example.com
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: team-alpha-developer
  namespace: team-alpha
subjects:
  - kind: Group
    name: team-alpha@example.com
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: edit
  apiGroup: rbac.authorization.k8s.io
```

---

## Fleet Management

### Rancher Fleet

```yaml
# fleet.yaml in Git repo root
defaultNamespace: production
helm:
  releaseName: api-service
  chart: ./charts/api-service
  values:
    replicaCount: 3
targetCustomizations:
  - name: production-us
    clusterSelector:
      matchLabels:
        region: us-east
    helm:
      values:
        replicaCount: 5
        ingress:
          host: api.us.example.com
  - name: production-eu
    clusterSelector:
      matchLabels:
        region: eu-west
    helm:
      values:
        replicaCount: 3
        ingress:
          host: api.eu.example.com
```

### Azure Arc (Flux-based)

```yaml
# Azure Arc GitOps configuration
apiVersion: microsoft.kubernetes/fluxConfigurations
metadata:
  name: platform-config
spec:
  scope: cluster
  namespace: flux-system
  sourceKind: GitRepository
  gitRepository:
    url: https://github.com/org/platform-gitops.git
    syncIntervalInSeconds: 60
    repositoryRef:
      branch: main
  kustomizations:
    platform:
      path: ./platform/base
      prune: true
      syncIntervalInSeconds: 120
    apps:
      path: ./apps
      dependsOn: [platform]
      prune: true
```

---

## Cluster API (CAPI) Lifecycle Management

```yaml
# Cluster definition with CAPI
apiVersion: cluster.x-k8s.io/v1beta1
kind: Cluster
metadata:
  name: production-us-east
  namespace: capi-clusters
  labels:
    env: production
    region: us-east-1
spec:
  clusterNetwork:
    services:
      cidrBlocks: ["10.96.0.0/12"]
    pods:
      cidrBlocks: ["192.168.0.0/16"]
  controlPlaneRef:
    apiVersion: controlplane.cluster.x-k8s.io/v1beta1
    kind: KubeadmControlPlane
    name: production-us-east-cp
  infrastructureRef:
    apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
    kind: AWSCluster
    name: production-us-east

---
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: AWSCluster
metadata:
  name: production-us-east
  namespace: capi-clusters
spec:
  region: us-east-1
  sshKeyName: capi-key
  network:
    vpc:
      cidrBlock: 10.0.0.0/16
    subnets:
      - availabilityZone: us-east-1a
        cidrBlock: 10.0.1.0/24
        isPublic: false
      - availabilityZone: us-east-1b
        cidrBlock: 10.0.2.0/24
        isPublic: false

---
apiVersion: controlplane.cluster.x-k8s.io/v1beta1
kind: KubeadmControlPlane
metadata:
  name: production-us-east-cp
  namespace: capi-clusters
spec:
  replicas: 3
  version: v1.29.2
  machineTemplate:
    infrastructureRef:
      apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
      kind: AWSMachineTemplate
      name: production-us-east-cp
  kubeadmConfigSpec:
    initConfiguration:
      nodeRegistration:
        kubeletExtraArgs:
          cloud-provider: external
    joinConfiguration:
      nodeRegistration:
        kubeletExtraArgs:
          cloud-provider: external

---
apiVersion: cluster.x-k8s.io/v1beta1
kind: MachineDeployment
metadata:
  name: production-us-east-workers
  namespace: capi-clusters
spec:
  clusterName: production-us-east
  replicas: 5
  selector:
    matchLabels: {}
  template:
    spec:
      clusterName: production-us-east
      version: v1.29.2
      bootstrap:
        configRef:
          apiVersion: bootstrap.cluster.x-k8s.io/v1beta1
          kind: KubeadmConfigTemplate
          name: production-us-east-worker
      infrastructureRef:
        apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
        kind: AWSMachineTemplate
        name: production-us-east-worker

---
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: AWSMachineTemplate
metadata:
  name: production-us-east-worker
  namespace: capi-clusters
spec:
  template:
    spec:
      instanceType: m6i.2xlarge
      iamInstanceProfile: nodes.cluster-api-provider-aws.sigs.k8s.io
      rootVolume:
        size: 100
        type: gp3
```

---

## Decision Matrix

| Pattern | Use Case | Complexity | Networking |
|---------|----------|------------|------------|
| ArgoCD Hub-Spoke | GitOps multi-cluster deploy | Medium | No cross-cluster networking |
| Istio Multi-Primary | Service mesh across clusters | High | Full L7, mTLS, traffic mgmt |
| Cilium ClusterMesh | eBPF networking, global services | Medium | L3/L4, kernel-level |
| Submariner | Cross-cluster pod networking | Medium | L3 tunnels, overlapping CIDR |
| GKE Multi-Cluster Ingress | Global HTTP(S) load balancing | Low | Google Cloud only |
| ExternalDNS Weighted | Simple DNS-based failover | Low | DNS only |
| Cluster API | Cluster lifecycle management | High | N/A (provisioning) |

## Anti-Patterns

- **Shared etcd across clusters**: Never share etcd; use federation instead
- **Flat network without encryption**: Always enable mTLS or WireGuard for cross-cluster traffic
- **Overlapping Pod CIDRs without GlobalNet**: Causes routing conflicts; use Submariner GlobalNet or non-overlapping ranges
- **Single management cluster without HA**: Management cluster is a single point of failure; run HA or have a recovery plan
- **Hardcoded cluster endpoints**: Use service discovery; endpoints change during cluster upgrades
