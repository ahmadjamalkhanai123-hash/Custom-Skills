# CD Platforms Reference

Continuous delivery platforms: GitOps, progressive delivery, and multi-cloud deployment.

---

## ArgoCD

### Application CRD
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp-production
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io  # Cascade delete
spec:
  project: default
  source:
    repoURL: https://github.com/org/gitops-repo
    targetRevision: main
    path: apps/myapp/overlays/production  # Kustomize
    # OR for Helm:
    # chart: myapp
    # helm:
    #   releaseName: myapp
    #   valueFiles: [values-production.yaml]
    #   parameters:
    #     - name: image.tag
    #       value: v1.2.3

  destination:
    server: https://kubernetes.default.svc
    namespace: production

  syncPolicy:
    automated:
      prune: true           # Remove resources deleted from Git
      selfHeal: true        # Correct drift automatically
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - RespectIgnoreDifferences=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m

  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas  # HPA manages this
```

### ArgoCD App-of-Apps Pattern
```yaml
# root-app.yaml — manages all other apps
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-app
  namespace: argocd
spec:
  source:
    path: apps/
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### Sync Waves and Hooks
```yaml
# Annotate resources to control sync order
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "-1"  # Run before main resources (e.g., migrations)
    argocd.argoproj.io/hook: PreSync
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
```

### ArgoCD CI Integration
```bash
# In CI pipeline — update image tag, let ArgoCD sync
# 1. Update image tag in Git
cd gitops-repo
sed -i "s|image: myapp:.*|image: myapp:${GIT_SHA}|" apps/myapp/overlays/staging/kustomization.yaml
git commit -m "chore: update myapp to ${GIT_SHA}"
git push

# 2. Wait for ArgoCD sync (optional — use ArgoCD CLI)
argocd app wait myapp-staging --sync --health --timeout 300
```

### ArgoCD RBAC
```yaml
# argocd-rbac-cm ConfigMap
data:
  policy.csv: |
    p, role:developer, applications, get, */*, allow
    p, role:developer, applications, sync, */dev, allow
    p, role:developer, applications, sync, */staging, allow
    p, role:deployer, applications, sync, */production, allow
    g, team-developers, role:developer
    g, team-devops, role:deployer
```

---

## Flux (GitOps)

### Kustomization (App Deployment)
```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: myapp
  namespace: flux-system
spec:
  interval: 5m
  path: ./apps/myapp/overlays/production
  prune: true
  sourceRef:
    kind: GitRepository
    name: gitops-repo
  healthChecks:
    - apiVersion: apps/v1
      kind: Deployment
      name: myapp
      namespace: production
  postBuild:
    substitute:
      ENVIRONMENT: production
      REGION: us-east-1
```

### HelmRelease
```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: myapp
  namespace: production
spec:
  interval: 10m
  chart:
    spec:
      chart: myapp
      version: ">=1.0.0 <2.0.0"
      sourceRef:
        kind: HelmRepository
        name: myapp-charts
  values:
    replicaCount: 3
    image:
      repository: myacr.azurecr.io/myapp
      tag: latest  # Overridden by ImagePolicy
  upgrade:
    remediation:
      retries: 3
  rollback:
    timeout: 5m
```

### Flux Image Automation
```yaml
# ImageRepository — watch container registry
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageRepository
metadata:
  name: myapp
  namespace: flux-system
spec:
  image: ghcr.io/org/myapp
  interval: 5m
---
# ImagePolicy — select which tag to use
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: myapp
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: myapp
  filterTags:
    pattern: '^v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$'
    extract: '$version'
  policy:
    semver:
      range: '>=1.0.0'
---
# ImageUpdateAutomation — commit new tags to Git
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImageUpdateAutomation
metadata:
  name: flux-system
  namespace: flux-system
spec:
  interval: 10m
  sourceRef:
    kind: GitRepository
    name: gitops-repo
  git:
    checkout:
      ref:
        branch: main
    commit:
      author:
        email: fluxcdbot@users.noreply.github.com
        name: fluxcdbot
      messageTemplate: 'chore: update {{range .Updated.Images}}{{println .}}{{end}}'
    push:
      branch: main
  update:
    path: ./apps
    strategy: Setters  # Uses # {"$imagepolicy": "flux-system:myapp"} markers
```

### Flux Multi-Tenancy
```yaml
# Tenant isolation via Kustomization serviceAccountName
spec:
  serviceAccountName: tenant-a-flux  # Scoped RBAC per tenant
  sourceRef:
    kind: GitRepository
    name: tenant-a-repo
```

---

## Argo Rollouts (Progressive Delivery)

### Canary Rollout
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: myapp
spec:
  replicas: 10
  selector:
    matchLabels:
      app: myapp
  template:
    # ... pod template same as Deployment
  strategy:
    canary:
      steps:
        - setWeight: 10        # Send 10% to canary
        - pause: {duration: 5m}
        - analysis:
            templates:
              - templateName: success-rate
        - setWeight: 40
        - pause: {duration: 5m}
        - setWeight: 100
      canaryService: myapp-canary
      stableService: myapp-stable
      trafficRouting:
        nginx:
          stableIngress: myapp-stable
```

### AnalysisTemplate (Metrics Gate)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
spec:
  metrics:
    - name: success-rate
      interval: 2m
      successCondition: result[0] >= 0.95  # 95% success rate
      failureLimit: 3
      provider:
        prometheus:
          address: http://prometheus:9090
          query: |
            sum(rate(http_requests_total{status=~"2.."}[5m]))
            /
            sum(rate(http_requests_total[5m]))
    - name: error-rate
      successCondition: result[0] <= 0.01
      provider:
        prometheus:
          query: |
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            /
            sum(rate(http_requests_total[5m]))
```

### Blue-Green Rollout
```yaml
strategy:
  blueGreen:
    activeService: myapp-active
    previewService: myapp-preview
    autoPromotionEnabled: false   # Require manual promotion
    scaleDownDelaySeconds: 30     # Keep old version briefly
    prePromotionAnalysis:
      templates:
        - templateName: smoke-test
      args:
        - name: service-name
          value: myapp-preview
```

---

## Spinnaker (Multi-Cloud)

### Pipeline JSON (key stages)
```json
{
  "stages": [
    {
      "type": "bakeManifest",
      "templateRenderer": "HELM3",
      "releaseName": "myapp",
      "inputArtifacts": [{"account": "github", "artifact": {"type": "github/file", "name": "chart.tgz"}}]
    },
    {
      "type": "deployManifest",
      "account": "k8s-staging",
      "manifests": [],
      "cloudProvider": "kubernetes"
    },
    {
      "type": "manualJudgment",
      "judgmentInputs": [{"value": "Approve Production"}],
      "notifications": [{"type": "slack", "message": {"manualJudgment": {"text": "Approve deploy?"}}}]
    },
    {
      "type": "canary",
      "analysisType": "realTime",
      "canaryConfig": {
        "lifetimeDuration": "PT1H",
        "successThreshold": {"score": 80}
      }
    }
  ]
}
```

---

## Harness CD (Key Concepts)

### Pipeline YAML (Harness native)
```yaml
pipeline:
  name: Deploy MyApp
  stages:
    - stage:
        name: Deploy Staging
        type: Deployment
        spec:
          service:
            serviceRef: myapp
          environment:
            environmentRef: staging
          execution:
            steps:
              - step:
                  type: HelmDeploy
                  spec:
                    releaseName: myapp-staging
              - step:
                  type: HarnessApproval
                  spec:
                    approvers:
                      userGroups: [platform-team]
```

---

## GitOps Repository Structure

### Recommended Layout (Environment-per-Directory)
```
gitops-repo/
├── apps/
│   ├── myapp/
│   │   ├── base/
│   │   │   ├── deployment.yaml
│   │   │   ├── service.yaml
│   │   │   └── kustomization.yaml
│   │   └── overlays/
│   │       ├── dev/
│   │       │   └── kustomization.yaml  # patches for dev
│   │       ├── staging/
│   │       │   └── kustomization.yaml
│   │       └── production/
│   │           └── kustomization.yaml
├── infrastructure/
│   ├── cert-manager/
│   ├── ingress-nginx/
│   └── monitoring/
└── clusters/
    ├── staging/
    │   └── flux-system/  # Flux bootstrap configs
    └── production/
        └── flux-system/
```

### Kustomize Overlay Pattern
```yaml
# overlays/production/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
patches:
  - patch: |-
      - op: replace
        path: /spec/replicas
        value: 5
    target:
      kind: Deployment
      name: myapp
images:
  - name: myapp
    newTag: v1.2.3  # Updated by CI/Flux
```

---

## CI → CD Integration Patterns

### Pattern 1: Image Tag Update in Git (GitOps)
```bash
#!/bin/bash
# In CI pipeline after image push:
NEW_TAG="${REGISTRY}/myapp:${GIT_SHA}"

# Clone GitOps repo with deploy key
git clone git@github.com:org/gitops-repo.git
cd gitops-repo

# Update image tag using kustomize
cd apps/myapp/overlays/staging
kustomize edit set image myapp=${NEW_TAG}

git config user.email "ci@example.com"
git config user.name "CI Bot"
git commit -am "chore: deploy myapp ${GIT_SHA} to staging"
git push
```

### Pattern 2: ArgoCD Image Updater (Automated)
```yaml
# Annotate ArgoCD Application
metadata:
  annotations:
    argocd-image-updater.argoproj.io/image-list: myapp=myacr.azurecr.io/myapp
    argocd-image-updater.argoproj.io/myapp.update-strategy: semver
    argocd-image-updater.argoproj.io/myapp.allow-tags: regexp:^v[0-9]+\.[0-9]+\.[0-9]+$
    argocd-image-updater.argoproj.io/write-back-method: git
```

### Pattern 3: Helm Chart Version Bump
```bash
# In CI: build chart, update Chart.yaml, push to registry
helm package chart/ --app-version ${GIT_TAG} --version ${CHART_VERSION}
helm push myapp-${CHART_VERSION}.tgz oci://ghcr.io/org/charts
# Flux HelmRelease version range picks it up automatically
```
