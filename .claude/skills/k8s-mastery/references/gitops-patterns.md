# GitOps Patterns for Kubernetes

Production GitOps with ArgoCD, Flux, progressive delivery, and secrets management.

---

## ArgoCD Core Resources

### Application

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: api-service
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
  annotations:
    notifications.argoproj.io/subscribe.on-sync-succeeded.slack: deployments
spec:
  project: production
  source:
    repoURL: https://github.com/org/platform-gitops.git
    targetRevision: main
    path: apps/api-service/overlays/production
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - PruneLast=true
      - ApplyOutOfSyncOnly=true
    retry:
      limit: 3
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas  # Managed by HPA
```

### AppProject

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: production
  namespace: argocd
spec:
  description: Production workloads
  sourceRepos:
    - "https://github.com/org/platform-gitops.git"
    - "https://charts.example.com"
  destinations:
    - namespace: "production"
      server: https://kubernetes.default.svc
    - namespace: "production-*"
      server: https://kubernetes.default.svc
  clusterResourceWhitelist:
    - group: ""
      kind: Namespace
  namespaceResourceWhitelist:
    - group: "apps"
      kind: Deployment
    - group: "apps"
      kind: StatefulSet
    - group: ""
      kind: Service
    - group: "networking.k8s.io"
      kind: Ingress
    - group: "autoscaling"
      kind: HorizontalPodAutoscaler
  roles:
    - name: deployer
      description: CI/CD pipeline role
      policies:
        - p, proj:production:deployer, applications, sync, production/*, allow
        - p, proj:production:deployer, applications, get, production/*, allow
      groups:
        - platform-team
        - sre-team
  orphanedResources:
    warn: true
```

---

## App-of-Apps Pattern

```yaml
# Root application that manages all other applications
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/platform-gitops.git
    targetRevision: main
    path: apps  # Contains Application manifests for each service
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true

---
# Directory structure for app-of-apps:
# apps/
#   api-service.yaml        <- Application CR
#   web-frontend.yaml       <- Application CR
#   payment-service.yaml    <- Application CR
#   platform/
#     cert-manager.yaml     <- Application CR
#     ingress-nginx.yaml    <- Application CR
#     monitoring.yaml       <- Application CR
```

---

## ApplicationSet Generators

### Git Directory Generator

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: cluster-services
  namespace: argocd
spec:
  goTemplate: true
  goTemplateOptions: ["missingkey=error"]
  generators:
    - git:
        repoURL: https://github.com/org/platform-gitops.git
        revision: main
        directories:
          - path: "apps/*/overlays/production"
          - path: "apps/experimental/*"
            exclude: true
  template:
    metadata:
      name: "{{ index .path.segments 1 }}"
      namespace: argocd
    spec:
      project: production
      source:
        repoURL: https://github.com/org/platform-gitops.git
        targetRevision: main
        path: "{{ .path.path }}"
      destination:
        server: https://kubernetes.default.svc
        namespace: "{{ index .path.segments 1 }}"
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

### Matrix Generator (Cluster x App)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: multi-cluster-apps
  namespace: argocd
spec:
  goTemplate: true
  generators:
    - matrix:
        generators:
          - clusters:
              selector:
                matchLabels:
                  env: production
          - git:
              repoURL: https://github.com/org/platform-gitops.git
              revision: main
              directories:
                - path: "apps/*"
  template:
    metadata:
      name: "{{ .name }}-{{ index .path.segments 1 }}"
    spec:
      project: production
      source:
        repoURL: https://github.com/org/platform-gitops.git
        targetRevision: main
        path: "{{ .path.path }}/overlays/{{ .metadata.labels.region }}"
      destination:
        server: "{{ .server }}"
        namespace: "{{ index .path.segments 1 }}"
```

### Cluster Generator

```yaml
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
        values:
          region: "{{ .metadata.labels.region }}"
          tier: "{{ .metadata.labels.tier }}"
  template:
    metadata:
      name: "platform-{{ .name }}"
    spec:
      project: platform
      source:
        repoURL: https://github.com/org/platform-gitops.git
        targetRevision: main
        path: platform/base
        kustomize:
          patches:
            - target:
                kind: Deployment
              patch: |
                - op: add
                  path: /metadata/labels/cluster
                  value: "{{ .name }}"
      destination:
        server: "{{ .server }}"
        namespace: platform
```

---

## Repository Structure (Monorepo)

```
platform-gitops/
  apps/
    api-service/
      base/
        deployment.yaml
        service.yaml
        kustomization.yaml
      overlays/
        dev/
          kustomization.yaml
          patches/
        staging/
          kustomization.yaml
          patches/
        production/
          kustomization.yaml
          patches/
    web-frontend/
      base/
      overlays/
    payment-service/
      base/
      overlays/
  platform/
    cert-manager/
      base/
      overlays/
    ingress-nginx/
      base/
      overlays/
    monitoring/
      base/
      overlays/
  teams/
    team-alpha/
      rbac.yaml
      resourcequota.yaml
      limitrange.yaml
    team-beta/
  clusters/
    production-us-east/
      cluster-config.yaml
      argocd-apps.yaml
    production-eu-west/
      cluster-config.yaml
      argocd-apps.yaml
```

---

## Environment Promotion

### Dev -> Staging -> Prod Sync Policies

```yaml
# DEV: Auto-sync, no approval needed
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: api-service-dev
spec:
  source:
    path: apps/api-service/overlays/dev
  syncPolicy:
    automated:
      prune: true
      selfHeal: true

---
# STAGING: Auto-sync from staging branch, requires health check
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: api-service-staging
spec:
  source:
    path: apps/api-service/overlays/staging
    targetRevision: main
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - Validate=true
      - PruneLast=true

---
# PRODUCTION: Manual sync, requires approval
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: api-service-production
  annotations:
    notifications.argoproj.io/subscribe.on-sync-status-unknown.slack: prod-deployments
spec:
  source:
    path: apps/api-service/overlays/production
    targetRevision: main
  syncPolicy:
    # No automated block = manual sync only
    syncOptions:
      - Validate=true
      - PruneLast=true
      - PrunePropagationPolicy=foreground
```

---

## Helm Values in ArgoCD

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: redis-production
  namespace: argocd
spec:
  project: production
  source:
    repoURL: https://charts.bitnami.com/bitnami
    chart: redis
    targetRevision: 18.6.1
    helm:
      releaseName: redis
      valuesObject:
        architecture: replication
        auth:
          existingSecret: redis-credentials
        master:
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
          persistence:
            size: 20Gi
        replica:
          replicaCount: 3
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
        metrics:
          enabled: true
          serviceMonitor:
            enabled: true
  destination:
    server: https://kubernetes.default.svc
    namespace: production
```

---

## Progressive Delivery with Argo Rollouts

### Canary Strategy

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: api-service
  namespace: production
spec:
  replicas: 10
  revisionHistoryLimit: 3
  selector:
    matchLabels:
      app: api-service
  template:
    metadata:
      labels:
        app: api-service
    spec:
      containers:
        - name: api
          image: registry.example.com/api-service:v2.1.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
  strategy:
    canary:
      canaryService: api-service-canary
      stableService: api-service-stable
      trafficRouting:
        istio:
          virtualServices:
            - name: api-service-vsvc
              routes:
                - primary
        # Or with nginx:
        # nginx:
        #   stableIngress: api-service-ingress
      steps:
        - setWeight: 5
        - pause: {duration: 2m}
        - analysis:
            templates:
              - templateName: success-rate
            args:
              - name: service-name
                value: api-service-canary
        - setWeight: 25
        - pause: {duration: 5m}
        - analysis:
            templates:
              - templateName: success-rate
              - templateName: latency-check
        - setWeight: 50
        - pause: {duration: 10m}
        - setWeight: 100
      analysis:
        successfulRunHistoryLimit: 3
        unsuccessfulRunHistoryLimit: 3
```

### Blue-Green Strategy

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: web-frontend
  namespace: production
spec:
  replicas: 5
  selector:
    matchLabels:
      app: web-frontend
  template:
    metadata:
      labels:
        app: web-frontend
    spec:
      containers:
        - name: web
          image: registry.example.com/web-frontend:v3.0.0
  strategy:
    blueGreen:
      activeService: web-frontend-active
      previewService: web-frontend-preview
      autoPromotionEnabled: false
      scaleDownDelaySeconds: 300
      prePromotionAnalysis:
        templates:
          - templateName: smoke-test
        args:
          - name: preview-url
            value: "http://web-frontend-preview.production.svc"
      postPromotionAnalysis:
        templates:
          - templateName: success-rate
```

### AnalysisTemplate for Automated Rollback

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
  namespace: production
spec:
  args:
    - name: service-name
  metrics:
    - name: success-rate
      interval: 60s
      count: 5
      successCondition: result[0] >= 0.99
      failureLimit: 2
      provider:
        prometheus:
          address: http://prometheus-operated.monitoring:9090
          query: |
            sum(rate(http_requests_total{status!~"5..",service="{{args.service-name}}"}[2m]))
            /
            sum(rate(http_requests_total{service="{{args.service-name}}"}[2m]))

---
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: latency-check
  namespace: production
spec:
  metrics:
    - name: p99-latency
      interval: 60s
      count: 5
      successCondition: result[0] < 0.5
      failureLimit: 2
      provider:
        prometheus:
          address: http://prometheus-operated.monitoring:9090
          query: |
            histogram_quantile(0.99,
              sum(rate(http_request_duration_seconds_bucket{service="{{args.service-name}}"}[2m])) by (le)
            )

---
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: smoke-test
  namespace: production
spec:
  args:
    - name: preview-url
  metrics:
    - name: smoke-test
      count: 1
      provider:
        job:
          spec:
            backoffLimit: 1
            template:
              spec:
                restartPolicy: Never
                containers:
                  - name: smoke
                    image: curlimages/curl:8.5.0
                    command:
                      - sh
                      - -c
                      - |
                        set -e
                        curl -sf "{{args.preview-url}}/healthz" || exit 1
                        curl -sf "{{args.preview-url}}/api/v1/status" || exit 1
                        echo "Smoke tests passed"
```

---

## Flux CD

### GitRepository

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: platform-gitops
  namespace: flux-system
spec:
  interval: 1m
  url: https://github.com/org/platform-gitops.git
  ref:
    branch: main
  secretRef:
    name: flux-git-credentials
  ignore: |
    # Exclude files not needed for deployment
    /**/README.md
    /**/docs/
```

### Kustomization (Flux)

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: api-service-production
  namespace: flux-system
spec:
  interval: 5m
  retryInterval: 2m
  timeout: 3m
  sourceRef:
    kind: GitRepository
    name: platform-gitops
  path: ./apps/api-service/overlays/production
  prune: true
  wait: true
  healthChecks:
    - apiVersion: apps/v1
      kind: Deployment
      name: api-service
      namespace: production
  dependsOn:
    - name: platform-services
  postBuild:
    substituteFrom:
      - kind: ConfigMap
        name: cluster-settings
```

### HelmRelease (Flux)

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: ingress-nginx
  namespace: ingress-nginx
spec:
  interval: 30m
  chart:
    spec:
      chart: ingress-nginx
      version: "4.9.x"
      sourceRef:
        kind: HelmRepository
        name: ingress-nginx
        namespace: flux-system
  install:
    remediation:
      retries: 3
  upgrade:
    remediation:
      retries: 3
      remediateLastFailure: true
    cleanupOnFail: true
  values:
    controller:
      replicas: 3
      resources:
        requests:
          cpu: 200m
          memory: 256Mi
      metrics:
        enabled: true
        serviceMonitor:
          enabled: true
```

---

## Secrets in GitOps

### Sealed Secrets

```yaml
# Create sealed secret (CLI)
# kubeseal --format yaml --cert pub-cert.pem < secret.yaml > sealed-secret.yaml

apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: database-credentials
  namespace: production
spec:
  encryptedData:
    username: AgA3x8...encrypted...base64==
    password: AgB7y2...encrypted...base64==
  template:
    metadata:
      labels:
        app: api-service
    type: Opaque
```

### External Secrets Operator

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secrets-manager
  namespace: production
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets-sa

---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: database-credentials
  namespace: production
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: database-credentials
    creationPolicy: Owner
    template:
      type: Opaque
      data:
        DATABASE_URL: "postgresql://{{ .username }}:{{ .password }}@db.example.com:5432/app"
  data:
    - secretKey: username
      remoteRef:
        key: production/database
        property: username
    - secretKey: password
      remoteRef:
        key: production/database
        property: password
```

### SOPS with Age Encryption

```yaml
# .sops.yaml (repo root)
creation_rules:
  - path_regex: ".*production.*"
    age: "age1xyz...production-key"
  - path_regex: ".*staging.*"
    age: "age1abc...staging-key"
  - path_regex: ".*"
    age: "age1def...default-key"

# Flux decryption config
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: secrets
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: platform-gitops
  path: ./secrets/production
  prune: true
  decryption:
    provider: sops
    secretRef:
      name: sops-age-key
```

---

## Decision Matrix

| Feature | ArgoCD | Flux |
|---------|--------|------|
| UI Dashboard | Built-in | Third-party (Weave GitOps) |
| Multi-cluster | ApplicationSet + hub | Kustomization per cluster |
| Helm Support | Native + values | HelmRelease CRD |
| RBAC | AppProject + OIDC | Kubernetes native RBAC |
| Progressive Delivery | Argo Rollouts | Flagger |
| Secrets | External Secrets / Sealed | SOPS native decryption |
| Notifications | Built-in | Notification Controller |
| Best For | Platform teams, multi-cluster | Single-cluster, GitOps-purist |
