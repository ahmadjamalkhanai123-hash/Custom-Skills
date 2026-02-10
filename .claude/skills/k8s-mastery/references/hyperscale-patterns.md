# Hyperscale Kubernetes Patterns

Patterns for Google/Meta/Netflix-scale Kubernetes: fleet management, infrastructure-as-K8s, custom operators, platform engineering, and cluster optimization.

---

## Fleet Management (20-200+ Clusters)

### Fleet Architecture

```
Management Plane (3 clusters, multi-region HA)
  ├── ArgoCD (hub) → deploys to all workload clusters
  ├── Crossplane → provisions cloud infrastructure
  ├── Cluster API → lifecycle management
  ├── Thanos Query → federated metrics
  ├── Kubecost → federated cost data
  └── Backstage → developer portal

Workload Clusters (organized by tier)
  ├── Tier 1: Critical (payment, auth) — dedicated, hardened
  ├── Tier 2: Standard (APIs, services) — shared, multi-tenant
  └── Tier 3: Batch (ML training, ETL) — spot/preemptible, autoscaling
```

### Fleet-Wide Policy with Kyverno

```yaml
# Enforced across all clusters via ArgoCD ApplicationSet
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: fleet-standards
  annotations:
    policies.kyverno.io/title: Fleet-Wide Standards
spec:
  validationFailureAction: Enforce
  background: true
  rules:
    - name: require-resource-limits
      match:
        any:
          - resources:
              kinds: ["Deployment", "StatefulSet", "DaemonSet"]
      validate:
        message: "All containers must have resource limits"
        pattern:
          spec:
            template:
              spec:
                containers:
                  - resources:
                      limits:
                        memory: "?*"
                        cpu: "?*"

    - name: require-team-label
      match:
        any:
          - resources:
              kinds: ["Namespace"]
      validate:
        message: "Namespaces must have team and cost-center labels"
        pattern:
          metadata:
            labels:
              team: "?*"
              cost-center: "?*"

    - name: restrict-registries
      match:
        any:
          - resources:
              kinds: ["Pod"]
      validate:
        message: "Images must come from approved registries"
        pattern:
          spec:
            containers:
              - image: "registry.example.com/* | gcr.io/org-approved/*"
            initContainers:
              - image: "registry.example.com/* | gcr.io/org-approved/*"
```

---

## Crossplane: Infrastructure as Kubernetes

### Composite Resource Definition (XRD)

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xdatabases.platform.example.com
spec:
  group: platform.example.com
  names:
    kind: XDatabase
    plural: xdatabases
  claimNames:
    kind: Database
    plural: databases
  versions:
    - name: v1alpha1
      served: true
      referenceable: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                parameters:
                  type: object
                  properties:
                    engine:
                      type: string
                      enum: [postgres, mysql]
                      default: postgres
                    version:
                      type: string
                      default: "15"
                    size:
                      type: string
                      enum: [small, medium, large]
                      default: small
                    region:
                      type: string
                    highAvailability:
                      type: boolean
                      default: false
                  required: [engine, region]
```

### Composition

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: database-aws
  labels:
    provider: aws
    engine: postgres
spec:
  compositeTypeRef:
    apiVersion: platform.example.com/v1alpha1
    kind: XDatabase
  mode: Pipeline
  pipeline:
    - step: patch-and-transform
      functionRef:
        name: function-patch-and-transform
      input:
        apiVersion: pt.fn.crossplane.io/v1beta1
        kind: Resources
        resources:
          - name: rds-instance
            base:
              apiVersion: rds.aws.upbound.io/v1beta1
              kind: Instance
              spec:
                forProvider:
                  engine: postgres
                  instanceClass: db.t3.micro
                  allocatedStorage: 20
                  publiclyAccessible: false
                  skipFinalSnapshot: false
                  storageEncrypted: true
                  autoMinorVersionUpgrade: true
                  backupRetentionPeriod: 7
                  vpcSecurityGroupIdSelector:
                    matchControllerRef: true
                  dbSubnetGroupNameSelector:
                    matchControllerRef: true
                providerConfigRef:
                  name: aws-provider
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.region
                toFieldPath: spec.forProvider.region
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.version
                toFieldPath: spec.forProvider.engineVersion
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.size
                toFieldPath: spec.forProvider.instanceClass
                transforms:
                  - type: map
                    map:
                      small: db.t3.micro
                      medium: db.r6g.large
                      large: db.r6g.2xlarge
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.highAvailability
                toFieldPath: spec.forProvider.multiAz

          - name: security-group
            base:
              apiVersion: ec2.aws.upbound.io/v1beta1
              kind: SecurityGroup
              spec:
                forProvider:
                  description: "Database security group"
                  vpcIdSelector:
                    matchLabels:
                      network: production
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.region
                toFieldPath: spec.forProvider.region

          - name: db-secret
            base:
              apiVersion: kubernetes.crossplane.io/v1alpha2
              kind: Object
              spec:
                forProvider:
                  manifest:
                    apiVersion: v1
                    kind: Secret
                    metadata:
                      namespace: ""
                    type: Opaque
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: metadata.labels["crossplane.io/claim-namespace"]
                toFieldPath: spec.forProvider.manifest.metadata.namespace
```

### Developer Claim (Self-Service)

```yaml
# Developer creates this — Crossplane handles the rest
apiVersion: platform.example.com/v1alpha1
kind: Database
metadata:
  name: orders-db
  namespace: team-alpha
spec:
  parameters:
    engine: postgres
    version: "15"
    size: medium
    region: us-east-1
    highAvailability: true
  compositionSelector:
    matchLabels:
      provider: aws
      engine: postgres
```

---

## Custom Operators with Kubebuilder

### Scaffold and Reconciliation Loop

```go
// api/v1alpha1/microservice_types.go
package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// MicroserviceSpec defines the desired state
type MicroserviceSpec struct {
	// Image is the container image
	Image string `json:"image"`
	// Replicas is the desired replica count
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=100
	Replicas int32 `json:"replicas"`
	// Port is the container port
	Port int32 `json:"port"`
	// Tier determines resource allocation
	// +kubebuilder:validation:Enum=small;medium;large
	Tier string `json:"tier"`
	// EnableCanary enables canary deployment
	EnableCanary bool `json:"enableCanary,omitempty"`
	// Team owning this microservice
	Team string `json:"team"`
}

// MicroserviceStatus defines the observed state
type MicroserviceStatus struct {
	// ReadyReplicas is the number of ready pods
	ReadyReplicas int32 `json:"readyReplicas,omitempty"`
	// Phase is the current lifecycle phase
	// +kubebuilder:validation:Enum=Pending;Running;Degraded;Failed
	Phase string `json:"phase,omitempty"`
	// Conditions represent the latest available observations
	Conditions []metav1.Condition `json:"conditions,omitempty"`
	// URL is the external URL once deployed
	URL string `json:"url,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Ready",type=integer,JSONPath=`.status.readyReplicas`
// +kubebuilder:printcolumn:name="URL",type=string,JSONPath=`.status.url`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`
type Microservice struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   MicroserviceSpec   `json:"spec,omitempty"`
	Status MicroserviceStatus `json:"status,omitempty"`
}
```

### Reconciler

```go
// internal/controller/microservice_controller.go
package controller

import (
	"context"
	"fmt"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	networkingv1 "k8s.io/api/networking/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	platformv1 "example.com/microservice-operator/api/v1alpha1"
)

type MicroserviceReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=platform.example.com,resources=microservices,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=platform.example.com,resources=microservices/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=networking.k8s.io,resources=ingresses,verbs=get;list;watch;create;update;patch;delete

func (r *MicroserviceReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// Fetch the Microservice instance
	var ms platformv1.Microservice
	if err := r.Get(ctx, req.NamespacedName, &ms); err != nil {
		if errors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// Reconcile Deployment
	if err := r.reconcileDeployment(ctx, &ms); err != nil {
		log.Error(err, "Failed to reconcile Deployment")
		return ctrl.Result{RequeueAfter: 30 * time.Second}, err
	}

	// Reconcile Service
	if err := r.reconcileService(ctx, &ms); err != nil {
		log.Error(err, "Failed to reconcile Service")
		return ctrl.Result{RequeueAfter: 30 * time.Second}, err
	}

	// Reconcile Ingress
	if err := r.reconcileIngress(ctx, &ms); err != nil {
		log.Error(err, "Failed to reconcile Ingress")
		return ctrl.Result{RequeueAfter: 30 * time.Second}, err
	}

	// Update status
	if err := r.updateStatus(ctx, &ms); err != nil {
		return ctrl.Result{RequeueAfter: 10 * time.Second}, err
	}

	return ctrl.Result{RequeueAfter: 5 * time.Minute}, nil
}

func (r *MicroserviceReconciler) reconcileDeployment(ctx context.Context, ms *platformv1.Microservice) error {
	resources := tierToResources(ms.Spec.Tier)

	deploy := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      ms.Name,
			Namespace: ms.Namespace,
		},
	}

	_, err := ctrl.CreateOrUpdate(ctx, r.Client, deploy, func() error {
		deploy.Spec = appsv1.DeploymentSpec{
			Replicas: &ms.Spec.Replicas,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					"app":  ms.Name,
					"team": ms.Spec.Team,
				},
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app":  ms.Name,
						"team": ms.Spec.Team,
					},
				},
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{{
						Name:      "app",
						Image:     ms.Spec.Image,
						Ports:     []corev1.ContainerPort{{ContainerPort: ms.Spec.Port}},
						Resources: resources,
					}},
				},
			},
		}
		return ctrl.SetControllerReference(ms, deploy, r.Scheme)
	})

	return err
}

func (r *MicroserviceReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&platformv1.Microservice{}).
		Owns(&appsv1.Deployment{}).
		Owns(&corev1.Service{}).
		Owns(&networkingv1.Ingress{}).
		Complete(r)
}
```

---

## Platform Engineering with Backstage

### Backstage Template for Kubernetes Service

```yaml
# backstage-template.yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: kubernetes-microservice
  title: Kubernetes Microservice
  description: Create a new microservice with CI/CD, observability, and GitOps
  tags:
    - kubernetes
    - microservice
    - recommended
spec:
  owner: platform-team
  type: service

  parameters:
    - title: Service Configuration
      required: [name, team, tier]
      properties:
        name:
          title: Service Name
          type: string
          pattern: "^[a-z][a-z0-9-]*$"
          maxLength: 40
        description:
          title: Description
          type: string
        team:
          title: Owning Team
          type: string
          ui:field: OwnerPicker
          ui:options:
            catalogFilter:
              kind: Group
        tier:
          title: Service Tier
          type: string
          enum: [small, medium, large]
          enumNames: ["Small (0.25 CPU, 256Mi)", "Medium (1 CPU, 1Gi)", "Large (4 CPU, 4Gi)"]
          default: small

    - title: Infrastructure
      properties:
        database:
          title: Database
          type: string
          enum: [none, postgres, mysql, redis]
          default: none
        cloud:
          title: Cloud Provider
          type: string
          enum: [aws, gcp]
          default: aws
        environments:
          title: Environments
          type: array
          items:
            type: string
            enum: [dev, staging, production]
          uniqueItems: true
          default: [dev, staging, production]

  steps:
    - id: scaffold
      name: Scaffold Service
      action: fetch:template
      input:
        url: ./skeleton
        values:
          name: ${{ parameters.name }}
          team: ${{ parameters.team }}
          tier: ${{ parameters.tier }}
          database: ${{ parameters.database }}

    - id: create-repo
      name: Create Repository
      action: publish:github
      input:
        repoUrl: github.com?owner=org&repo=${{ parameters.name }}
        defaultBranch: main
        protectDefaultBranch: true

    - id: create-gitops
      name: Create GitOps Manifests
      action: fetch:template
      input:
        url: ./gitops-skeleton
        targetPath: ../platform-gitops/apps/${{ parameters.name }}
        values:
          name: ${{ parameters.name }}
          team: ${{ parameters.team }}
          tier: ${{ parameters.tier }}
          environments: ${{ parameters.environments }}

    - id: create-database
      name: Provision Database
      if: ${{ parameters.database !== 'none' }}
      action: crossplane:create
      input:
        apiVersion: platform.example.com/v1alpha1
        kind: Database
        metadata:
          name: ${{ parameters.name }}-db
          namespace: ${{ parameters.team }}
        spec:
          parameters:
            engine: ${{ parameters.database }}
            size: ${{ parameters.tier }}

    - id: register
      name: Register in Catalog
      action: catalog:register
      input:
        repoContentsUrl: ${{ steps['create-repo'].output.repoContentsUrl }}
        catalogInfoPath: /catalog-info.yaml

  output:
    links:
      - title: Repository
        url: ${{ steps['create-repo'].output.remoteUrl }}
      - title: Open in Catalog
        icon: catalog
        entityRef: ${{ steps['register'].output.entityRef }}
```

---

## vcluster: Virtual Clusters for Tenant Isolation

```yaml
# vcluster Helm values
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: vcluster-team-alpha
  namespace: argocd
spec:
  source:
    repoURL: https://charts.loft.sh
    chart: vcluster
    targetRevision: 0.19.x
    helm:
      valuesObject:
        vcluster:
          image: rancher/k3s:v1.29.2-k3s1
        sync:
          ingresses:
            enabled: true
          persistentvolumes:
            enabled: true
          storageclasses:
            enabled: true
          nodes:
            enabled: true
            syncAllNodes: true
        syncer:
          extraArgs:
            - --tls-san=vcluster-team-alpha.example.com
            - --out-kube-config-server=https://vcluster-team-alpha.example.com
        isolation:
          enabled: true
          namespace: null
          resourceQuota:
            enabled: true
            quota:
              requests.cpu: "10"
              requests.memory: 20Gi
              limits.cpu: "20"
              limits.memory: 40Gi
              pods: "100"
              services: "20"
              persistentvolumeclaims: "10"
          limitRange:
            enabled: true
            default:
              cpu: 500m
              memory: 512Mi
            defaultRequest:
              cpu: 100m
              memory: 128Mi
          networkPolicy:
            enabled: true
        coredns:
          enabled: true
  destination:
    server: https://kubernetes.default.svc
    namespace: vc-team-alpha
```

---

## eBPF: Cilium and Tetragon

### Cilium Advanced Configuration

```yaml
# Cilium Helm values for hyperscale
cilium:
  k8sServiceHost: api-server.example.com
  k8sServicePort: 6443
  kubeProxyReplacement: true
  bpf:
    masquerade: true
    hostRouting: true
    lbExternalClusterIP: true
    tproxy: true
  # Bandwidth Manager (replaces tc)
  bandwidthManager:
    enabled: true
    bbr: true
  # DSR (Direct Server Return) for better LB performance
  loadBalancer:
    mode: dsr
    acceleration: native  # XDP acceleration
    algorithm: maglev     # Consistent hashing
  # Hubble for network observability
  hubble:
    enabled: true
    relay:
      enabled: true
      replicas: 3
    ui:
      enabled: true
    metrics:
      enabled:
        - dns
        - drop
        - tcp
        - flow
        - port-distribution
        - icmp
        - httpV2:exemplars=true;labelsContext=source_ip,destination_ip
      serviceMonitor:
        enabled: true
  # WireGuard transparent encryption
  encryption:
    enabled: true
    type: wireguard
    nodeEncryption: true
  # BGP for bare-metal
  bgpControlPlane:
    enabled: true
  # Envoy proxy for L7 (replacement for kube-proxy + ingress)
  envoyConfig:
    enabled: true
```

### Tetragon (Runtime Security)

```yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: detect-privilege-escalation
spec:
  kprobes:
    - call: "security_file_open"
      syscall: false
      args:
        - index: 0
          type: "file"
        - index: 1
          type: "int"
      selectors:
        - matchArgs:
            - index: 0
              operator: "Prefix"
              values:
                - "/etc/shadow"
                - "/etc/passwd"
          matchActions:
            - action: Sigkill  # Kill process immediately
            - action: Post     # Also log the event

---
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: monitor-network-connections
spec:
  kprobes:
    - call: "tcp_connect"
      syscall: false
      args:
        - index: 0
          type: "sock"
      selectors:
        - matchArgs:
            - index: 0
              operator: "NotDAddr"
              values:
                - "10.0.0.0/8"
                - "172.16.0.0/12"
          matchActions:
            - action: Post
              rateLimit: "1m"  # Rate limit external connection alerts
```

---

## Scale Patterns: 10K+ Nodes

### etcd Tuning

```yaml
# etcd configuration for large clusters
# Applied via kubeadm or Cluster API
etcd:
  local:
    extraArgs:
      quota-backend-bytes: "8589934592"      # 8GB (default 2GB)
      snapshot-count: "5000"                   # Compact more frequently
      auto-compaction-mode: revision
      auto-compaction-retention: "1000"
      max-request-bytes: "10485760"            # 10MB
      heartbeat-interval: "250"                # 250ms (default 100ms for WAN)
      election-timeout: "2500"                 # 2500ms
      # Performance
      experimental-initial-corrupt-check: "true"
      experimental-corrupt-check-time: "240m"
    extraVolumes:
      - name: etcd-data
        hostPath: /var/lib/etcd
        mountPath: /var/lib/etcd
        pathType: DirectoryOrCreate
    # Use local NVMe SSD for etcd
    # Minimum: 50 sequential IOPS/s sustained
    # Recommended: 500+ IOPS/s for 10K+ nodes
```

### API Server Optimization

```yaml
# kube-apiserver extra args for large clusters
apiServer:
  extraArgs:
    # Request handling
    max-requests-inflight: "800"          # Default 400
    max-mutating-requests-inflight: "400" # Default 200
    # Watch bookmarks (reduces reconnection load)
    feature-gates: "WatchBookmark=true"
    # Event rate limiting
    event-ttl: "1h"
    # API priority and fairness
    enable-priority-and-fairness: "true"
    # Profiling (disable in production)
    profiling: "false"
    # Audit logging at scale
    audit-log-maxage: "7"
    audit-log-maxbackup: "3"
    audit-log-maxsize: "100"
    # Encryption at rest
    encryption-provider-config: /etc/kubernetes/encryption-config.yaml
  # Resource allocation for large clusters
  resources:
    requests:
      cpu: "4"
      memory: 16Gi

---
# APF (API Priority and Fairness) configuration
apiVersion: flowcontrol.apiserver.k8s.io/v1
kind: PriorityLevelConfiguration
metadata:
  name: platform-controllers
spec:
  type: Limited
  limited:
    nominalConcurrencyShares: 200
    lendablePercent: 50
    limitResponse:
      type: Queue
      queuing:
        queues: 64
        handSize: 6
        queueLengthLimit: 100

---
apiVersion: flowcontrol.apiserver.k8s.io/v1
kind: FlowSchema
metadata:
  name: platform-controllers
spec:
  priorityLevelConfiguration:
    name: platform-controllers
  matchingPrecedence: 500
  rules:
    - subjects:
        - kind: ServiceAccount
          serviceAccount:
            name: "*"
            namespace: "platform-system"
      resourceRules:
        - verbs: ["*"]
          apiGroups: ["*"]
          resources: ["*"]
          namespaces: ["*"]
```

### Custom Scheduler

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
profiles:
  - schedulerName: platform-scheduler
    plugins:
      score:
        enabled:
          - name: NodeResourcesFit
            weight: 2
          - name: InterPodAffinity
            weight: 2
          - name: NodeAffinity
            weight: 1
          - name: TaintToleration
            weight: 1
        disabled:
          - name: NodeResourcesBalancedAllocation  # Disable for bin-packing
      filter:
        enabled:
          - name: NodeResourcesFit
          - name: NodeAffinity
          - name: TaintToleration
    pluginConfig:
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: MostAllocated  # Bin-packing to reduce node count
            resources:
              - name: cpu
                weight: 1
              - name: memory
                weight: 1
              - name: nvidia.com/gpu
                weight: 5

---
# Topology-aware scheduling
apiVersion: apps/v1
kind: Deployment
metadata:
  name: latency-sensitive-app
spec:
  template:
    spec:
      schedulerName: platform-scheduler
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: latency-sensitive-app
        - maxSkew: 2
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: latency-sensitive-app
```

---

## Cost at Scale: Kubecost Federation

```yaml
# Kubecost Helm values (per cluster)
kubecost:
  kubecostProductConfigs:
    clusterName: production-us-east
    clusterProfile: production
    currencyCode: USD
    # Federated metrics
    federatedClusters:
      - name: production-us-east
        endpoint: http://kubecost.us-east.internal
      - name: production-eu-west
        endpoint: http://kubecost.eu-west.internal
    # Cloud integration
    cloudIntegrationSecret: cloud-integration
    # Custom pricing
    customPricesEnabled: true
    defaultModelPricing:
      CPU: "0.031611"    # On-demand $/hr
      spotCPU: "0.0094"  # Spot $/hr
      RAM: "0.004237"
      spotRAM: "0.00127"
      storage: "0.00005479"
  prometheus:
    kubeStateMetrics:
      enabled: false  # Use existing kube-state-metrics
    nodeExporter:
      enabled: false  # Use existing node-exporter
  thanos:
    enabled: true
    queryFrontend:
      enabled: true

---
# Network cost allocation DaemonSet
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: kubecost-network-costs
  namespace: kubecost
spec:
  selector:
    matchLabels:
      app: kubecost-network-costs
  template:
    spec:
      hostNetwork: true
      containers:
        - name: network-costs
          image: gcr.io/kubecost1/kubecost-network-costs:v0.17.3
          env:
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
          securityContext:
            capabilities:
              add: ["NET_ADMIN", "NET_RAW"]
```

---

## KCP: kube-like Control Plane

```yaml
# KCP workspace for multi-tenant platform
apiVersion: tenancy.kcp.io/v1alpha1
kind: Workspace
metadata:
  name: team-alpha
spec:
  type:
    name: team
    path: root:organization
  shard:
    name: us-east

---
# APIBinding: team workspace binds to platform APIs
apiVersion: apis.kcp.io/v1alpha1
kind: APIBinding
metadata:
  name: platform-databases
spec:
  reference:
    export:
      path: root:organization:platform
      name: databases

---
# SyncTarget: syncs resources from KCP to physical cluster
apiVersion: workload.kcp.io/v1alpha1
kind: SyncTarget
metadata:
  name: production-us-east
spec:
  supportedAPIExports:
    - export:
        path: root:organization:platform
        name: databases
    - export:
        path: root:organization:platform
        name: microservices
```

---

## Decision Matrix

| Pattern | Scale | Complexity | Use Case |
|---------|-------|------------|----------|
| Crossplane | 10-200 clusters | High | Cloud-agnostic IaC |
| Custom Operator | Any | High | Domain-specific automation |
| Backstage | 50+ services | Medium | Developer self-service portal |
| vcluster | 10-1000 tenants | Low | Multi-tenancy without cluster sprawl |
| eBPF/Cilium | Any | Medium | High-perf networking + security |
| KCP | 100+ teams | Very High | Massive multi-tenant platforms |
| Custom Scheduler | 1K+ nodes | High | GPU, topology, bin-packing |
| Kubecost Federation | 5+ clusters | Medium | Cost visibility across fleet |

## Anti-Patterns at Scale

- **Over-abstracting too early**: Start with Kustomize, graduate to Crossplane when complexity justifies it
- **Ignoring API server limits**: At 5K+ nodes, default API server settings cause timeouts; tune proactively
- **Single etcd cluster for everything**: Separate etcd for events; consider external etcd on NVMe
- **No cost governance**: Without showback/chargeback, cloud bills grow 3-5x annually
- **Treating all workloads equally**: Separate critical (Tier 1) from batch (Tier 3) clusters for blast radius
- **Custom operators without health checks**: Always implement readiness gates, leader election, and metrics
