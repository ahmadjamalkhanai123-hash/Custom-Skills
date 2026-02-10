# Helm and Kustomize

Packaging, templating, and configuration management patterns for Kubernetes applications.

---

## Helm 3 Chart Structure

```
mychart/
  Chart.yaml              # Chart metadata
  Chart.lock              # Dependency lock file
  values.yaml             # Default values
  values-staging.yaml     # Environment overlay
  values-production.yaml  # Environment overlay
  templates/
    _helpers.tpl          # Named template definitions
    deployment.yaml
    service.yaml
    ingress.yaml
    hpa.yaml
    pdb.yaml
    serviceaccount.yaml
    configmap.yaml
    secret.yaml
    networkpolicy.yaml
    tests/
      test-connection.yaml
    NOTES.txt             # Post-install instructions
  charts/                 # Dependency charts
  crds/                   # Custom Resource Definitions
```

### Chart.yaml

```yaml
apiVersion: v2
name: myapp
description: A production-grade microservice chart
type: application
version: 1.5.0                     # Chart version (SemVer)
appVersion: "2.3.1"                # Application version
kubeVersion: ">=1.28.0"
keywords:
  - microservice
  - api
home: https://github.com/myorg/myapp
sources:
  - https://github.com/myorg/myapp
maintainers:
  - name: Platform Team
    email: platform@example.com
dependencies:
  - name: postgresql
    version: "15.x.x"
    repository: https://charts.bitnami.com/bitnami
    condition: postgresql.enabled
  - name: redis
    version: "19.x.x"
    repository: https://charts.bitnami.com/bitnami
    condition: redis.enabled
```

### values.yaml (Base)

```yaml
# -- Number of replicas
replicaCount: 2

image:
  # -- Container image repository
  repository: myregistry.io/myapp
  # -- Image pull policy
  pullPolicy: IfNotPresent
  # -- Image tag (defaults to chart appVersion)
  tag: ""

imagePullSecrets:
  - name: registry-creds

nameOverride: ""
fullnameOverride: ""

serviceAccount:
  create: true
  automount: false
  annotations: {}
  name: ""

podAnnotations: {}
podLabels:
  app.kubernetes.io/part-of: myplatform

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 65534
  runAsGroup: 65534
  fsGroup: 65534
  seccompProfile:
    type: RuntimeDefault

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL

service:
  type: ClusterIP
  port: 80
  targetPort: 8080

ingress:
  enabled: false
  className: nginx
  annotations: {}
  hosts:
    - host: myapp.example.com
      paths:
        - path: /
          pathType: Prefix
  tls: []

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi

autoscaling:
  enabled: false
  minReplicas: 2
  maxReplicas: 20
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

pdb:
  enabled: true
  minAvailable: 1

nodeSelector: {}

tolerations: []

topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule

probes:
  liveness:
    httpGet:
      path: /healthz
      port: http
    initialDelaySeconds: 10
    periodSeconds: 10
  readiness:
    httpGet:
      path: /readyz
      port: http
    initialDelaySeconds: 5
    periodSeconds: 5
  startup:
    httpGet:
      path: /healthz
      port: http
    failureThreshold: 30
    periodSeconds: 10

env: []
envFrom: []

config:
  # -- Application-specific config (rendered as ConfigMap)
  LOG_LEVEL: info
  CACHE_TTL: "300"

postgresql:
  enabled: false

redis:
  enabled: false
```

### _helpers.tpl (Named Templates)

```yaml
{{/*
Expand the name of the chart.
*/}}
{{- define "myapp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "myapp.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "myapp.labels" -}}
helm.sh/chart: {{ include "myapp.chart" . }}
{{ include "myapp.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "myapp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "myapp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Chart name and version
*/}}
{{- define "myapp.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Service account name
*/}}
{{- define "myapp.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "myapp.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image reference with tag or digest
*/}}
{{- define "myapp.image" -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository $tag }}
{{- end }}
```

### templates/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "myapp.fullname" . }}
  labels:
    {{- include "myapp.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "myapp.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      annotations:
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
        {{- with .Values.podAnnotations }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      labels:
        {{- include "myapp.labels" . | nindent 8 }}
        {{- with .Values.podLabels }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ include "myapp.serviceAccountName" . }}
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      {{- with .Values.topologySpreadConstraints }}
      topologySpreadConstraints:
        {{- range . }}
        - maxSkew: {{ .maxSkew }}
          topologyKey: {{ .topologyKey }}
          whenUnsatisfiable: {{ .whenUnsatisfiable }}
          labelSelector:
            matchLabels:
              {{- include "myapp.selectorLabels" $ | nindent 14 }}
        {{- end }}
      {{- end }}
      containers:
        - name: {{ .Chart.Name }}
          image: {{ include "myapp.image" . }}
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
          ports:
            - name: http
              containerPort: {{ .Values.service.targetPort }}
              protocol: TCP
          {{- with .Values.probes.startup }}
          startupProbe:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- with .Values.probes.liveness }}
          livenessProbe:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- with .Values.probes.readiness }}
          readinessProbe:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          {{- with .Values.env }}
          env:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          envFrom:
            - configMapRef:
                name: {{ include "myapp.fullname" . }}-config
            {{- with .Values.envFrom }}
            {{- toYaml . | nindent 12 }}
            {{- end }}
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 100Mi
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
```

### Helm Hooks

```yaml
# templates/hooks/db-migrate.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "myapp.fullname" . }}-db-migrate
  labels:
    {{- include "myapp.labels" . | nindent 4 }}
  annotations:
    "helm.sh/hook": pre-upgrade,pre-install
    "helm.sh/hook-weight": "-5"         # Run before other hooks
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: Never
      serviceAccountName: {{ include "myapp.serviceAccountName" . }}
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      containers:
        - name: migrate
          image: {{ include "myapp.image" . }}
          command: ["./migrate", "up"]
          envFrom:
            - secretRef:
                name: {{ include "myapp.fullname" . }}-db-secret
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
---
# templates/hooks/smoke-test.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "myapp.fullname" . }}-smoke-test
  labels:
    {{- include "myapp.labels" . | nindent 4 }}
  annotations:
    "helm.sh/hook": post-install,post-upgrade
    "helm.sh/hook-weight": "5"
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: smoke-test
          image: curlimages/curl:8.7.1
          command:
            - /bin/sh
            - -c
            - |
              set -e
              echo "Waiting for service to be ready..."
              sleep 10
              RESP=$(curl -sf http://{{ include "myapp.fullname" . }}:{{ .Values.service.port }}/healthz)
              echo "Health check response: ${RESP}"
              echo "Smoke test passed!"
```

### Helm Test

```yaml
# templates/tests/test-connection.yaml
apiVersion: v1
kind: Pod
metadata:
  name: {{ include "myapp.fullname" . }}-test-connection
  labels:
    {{- include "myapp.labels" . | nindent 4 }}
  annotations:
    "helm.sh/hook": test
    "helm.sh/hook-delete-policy": before-hook-creation
spec:
  restartPolicy: Never
  containers:
    - name: wget
      image: busybox:1.36
      command:
        - wget
        - --spider
        - --timeout=5
        - http://{{ include "myapp.fullname" . }}:{{ .Values.service.port }}/healthz
```

### NOTES.txt

```
{{- $fullName := include "myapp.fullname" . -}}
1. Get the application URL:
{{- if .Values.ingress.enabled }}
{{- range $host := .Values.ingress.hosts }}
  http{{ if $.Values.ingress.tls }}s{{ end }}://{{ $host.host }}
{{- end }}
{{- else if contains "LoadBalancer" .Values.service.type }}
  export SERVICE_IP=$(kubectl get svc {{ $fullName }} -n {{ .Release.Namespace }} -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
  echo http://$SERVICE_IP:{{ .Values.service.port }}
{{- else }}
  kubectl port-forward svc/{{ $fullName }} -n {{ .Release.Namespace }} 8080:{{ .Values.service.port }}
  echo http://127.0.0.1:8080
{{- end }}

2. Run tests:
  helm test {{ .Release.Name }} -n {{ .Release.Namespace }}
```

### Multi-Environment Values Overrides

```yaml
# values-production.yaml
replicaCount: 5

image:
  tag: "2.3.1"

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
  hosts:
    - host: api.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: api-tls
      hosts:
        - api.example.com

resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: "2"
    memory: 2Gi

autoscaling:
  enabled: true
  minReplicas: 5
  maxReplicas: 50

pdb:
  enabled: true
  minAvailable: 3

config:
  LOG_LEVEL: warn
  CACHE_TTL: "600"

postgresql:
  enabled: true
  primary:
    persistence:
      size: 100Gi

redis:
  enabled: true
```

---

## Kustomize

### Base Structure

```
myapp/
  base/
    kustomization.yaml
    deployment.yaml
    service.yaml
    configmap.yaml
    networkpolicy.yaml
  overlays/
    staging/
      kustomization.yaml
      patches/
        deployment-replicas.yaml
        ingress.yaml
    production/
      kustomization.yaml
      patches/
        deployment-replicas.yaml
        hpa.yaml
        pdb.yaml
      resources/
        ingress.yaml
  components/
    monitoring/
      kustomization.yaml
      servicemonitor.yaml
    caching/
      kustomization.yaml
      redis-deployment.yaml
```

### base/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

metadata:
  name: myapp

commonLabels:
  app.kubernetes.io/name: myapp
  app.kubernetes.io/managed-by: kustomize

resources:
  - deployment.yaml
  - service.yaml
  - configmap.yaml
  - networkpolicy.yaml
```

### base/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: myapp
  template:
    metadata:
      labels:
        app.kubernetes.io/name: myapp
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 65534
        seccompProfile:
          type: RuntimeDefault
      automountServiceAccountToken: false
      containers:
        - name: myapp
          image: myregistry.io/myapp
          ports:
            - containerPort: 8080
              name: http
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
          envFrom:
            - configMapRef:
                name: myapp-config
```

### overlays/production/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: production

resources:
  - ../../base
  - resources/ingress.yaml

components:
  - ../../components/monitoring

images:
  - name: myregistry.io/myapp
    newTag: v2.3.1
    digest: sha256:abc123def456...

replicas:
  - name: myapp
    count: 5

configMapGenerator:
  - name: myapp-config
    behavior: merge
    literals:
      - LOG_LEVEL=warn
      - CACHE_TTL=600
      - DB_HOST=postgres-primary.production.svc

secretGenerator:
  - name: myapp-secrets
    type: Opaque
    envs:
      - secrets.env                 # Not committed; injected by CI
    options:
      disableNameSuffixHash: false

patches:
  # Strategic merge patch -- increase resources
  - target:
      kind: Deployment
      name: myapp
    patch: |-
      apiVersion: apps/v1
      kind: Deployment
      metadata:
        name: myapp
      spec:
        template:
          spec:
            containers:
              - name: myapp
                resources:
                  requests:
                    cpu: 500m
                    memory: 512Mi
                  limits:
                    cpu: "2"
                    memory: 2Gi

  # JSON patch -- add topology spread
  - target:
      kind: Deployment
      name: myapp
    patch: |-
      - op: add
        path: /spec/template/spec/topologySpreadConstraints
        value:
          - maxSkew: 1
            topologyKey: topology.kubernetes.io/zone
            whenUnsatisfiable: DoNotSchedule
            labelSelector:
              matchLabels:
                app.kubernetes.io/name: myapp

  # Add PDB
  - path: patches/pdb.yaml

  # Add HPA
  - path: patches/hpa.yaml
```

### Kustomize Patches

#### patches/pdb.yaml (Strategic Merge)

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: myapp-pdb
spec:
  minAvailable: 3
  selector:
    matchLabels:
      app.kubernetes.io/name: myapp
```

#### patches/hpa.yaml

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: myapp-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  minReplicas: 5
  maxReplicas: 50
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### Kustomize Components (Optional Features)

```yaml
# components/monitoring/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component

resources:
  - servicemonitor.yaml

patches:
  - target:
      kind: Deployment
      name: myapp
    patch: |-
      apiVersion: apps/v1
      kind: Deployment
      metadata:
        name: myapp
      spec:
        template:
          metadata:
            annotations:
              prometheus.io/scrape: "true"
              prometheus.io/port: "9090"
              prometheus.io/path: "/metrics"
```

```yaml
# components/monitoring/servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: myapp
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: myapp
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

---

## Helm vs Kustomize Decision Tree

```
Do you need...
  |
  |-- Complex templating logic (conditionals, loops)?
  |     YES --> Helm
  |
  |-- Package distribution (public/private chart registry)?
  |     YES --> Helm
  |
  |-- Dependency management (PostgreSQL, Redis sub-charts)?
  |     YES --> Helm
  |
  |-- Lifecycle hooks (pre-install, post-upgrade)?
  |     YES --> Helm
  |
  |-- Simple overlay-based config (just patch per environment)?
  |     YES --> Kustomize
  |
  |-- No templating language (plain YAML)?
  |     YES --> Kustomize
  |
  |-- GitOps with ArgoCD/Flux (native support for both)?
  |     EITHER --> Both work well
  |
  |-- Both complex templating AND environment overlays?
  |     YES --> Helm + Kustomize (render Helm, patch with Kustomize)
```

---

## Helmfile (Multi-Chart Management)

```yaml
# helmfile.yaml
environments:
  staging:
    values:
      - environments/staging.yaml
  production:
    values:
      - environments/production.yaml

helmDefaults:
  wait: true
  timeout: 600
  createNamespace: true
  atomic: true

repositories:
  - name: bitnami
    url: https://charts.bitnami.com/bitnami
  - name: ingress-nginx
    url: https://kubernetes.github.io/ingress-nginx
  - name: cert-manager
    url: https://charts.jetstack.io

releases:
  - name: ingress-nginx
    namespace: ingress-system
    chart: ingress-nginx/ingress-nginx
    version: 4.10.x
    values:
      - charts/ingress-nginx/values.yaml
      - charts/ingress-nginx/values-{{ .Environment.Name }}.yaml

  - name: cert-manager
    namespace: cert-manager
    chart: cert-manager/cert-manager
    version: 1.15.x
    set:
      - name: installCRDs
        value: "true"

  - name: myapp
    namespace: {{ .Environment.Name }}
    chart: ./charts/myapp
    version: 1.5.0
    values:
      - charts/myapp/values.yaml
      - charts/myapp/values-{{ .Environment.Name }}.yaml
    secrets:
      - charts/myapp/secrets-{{ .Environment.Name }}.yaml
    needs:
      - ingress-system/ingress-nginx
      - cert-manager/cert-manager

  - name: postgres
    namespace: {{ .Environment.Name }}
    chart: bitnami/postgresql
    version: 15.x.x
    condition: postgresql.enabled
    values:
      - charts/postgres/values-{{ .Environment.Name }}.yaml
```

### ct lint (Chart Testing)

```yaml
# ct.yaml (chart-testing config)
target-branch: main
chart-dirs:
  - charts
chart-repos:
  - bitnami=https://charts.bitnami.com/bitnami
helm-extra-args: --timeout 600s
validate-maintainers: false
check-version-increment: true
```

```bash
# CI usage:
# ct lint --config ct.yaml                    # Lint changed charts
# ct install --config ct.yaml                 # Install and test changed charts
# helm lint charts/myapp -f charts/myapp/values-production.yaml
# helm template myapp charts/myapp -f charts/myapp/values-production.yaml | kubectl apply --dry-run=server -f -
```
