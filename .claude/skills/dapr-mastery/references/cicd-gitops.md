# Dapr CI/CD & GitOps Reference

Production Dapr deployments require automated pipelines for components,
application deployments, and Dapr control plane upgrades.

---

## GitOps Repository Structure

```
dapr-platform/
├── clusters/
│   ├── production/
│   │   ├── dapr-system/          # Control plane Helm release
│   │   │   └── helmrelease.yaml
│   │   ├── components/           # Dapr component CRDs
│   │   │   ├── statestore.yaml
│   │   │   ├── pubsub.yaml
│   │   │   └── resiliency.yaml
│   │   └── apps/                 # Application deployments
│   │       ├── order-service/
│   │       └── workflow-service/
│   └── staging/
│       └── ...
├── base/                         # Kustomize base configs
└── .github/workflows/            # CI pipelines
```

---

## GitHub Actions — CI Pipeline

### Full CI: Test + Build + Deploy

```yaml
# .github/workflows/dapr-ci.yaml
name: Dapr Application CI/CD

on:
  push:
    branches: [main, release/*]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
  DAPR_VERSION: "1.15.0"

jobs:
  # ── Unit Tests ───────────────────────────────────────────────────────────────
  unit-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-test.txt

      - name: Run unit tests
        run: pytest tests/unit/ -v --cov=. --cov-report=xml --cov-fail-under=80

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml

  # ── Integration Tests with Dapr ───────────────────────────────────────────
  integration-test:
    runs-on: ubuntu-latest
    needs: unit-test
    steps:
      - uses: actions/checkout@v4

      - name: Install Dapr CLI
        run: |
          wget -q https://raw.githubusercontent.com/dapr/cli/master/install/install.sh -O - | /bin/bash -s ${{ env.DAPR_VERSION }}
          dapr init --runtime-version ${{ env.DAPR_VERSION }}

      - name: Start Redis for tests
        run: docker run -d -p 6379:6379 redis:7-alpine

      - name: Run integration tests
        run: |
          dapr run --app-id test-service --app-port 8090 \
            --resources-path ./test-components \
            -- pytest tests/integration/ -v &
          sleep 5 && wait

  # ── Build & Push Image ────────────────────────────────────────────────────
  build:
    runs-on: ubuntu-latest
    needs: integration-test
    if: github.ref == 'refs/heads/main'
    permissions:
      contents: read
      packages: write
    outputs:
      image-digest: ${{ steps.push.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=semver,pattern={{version}}
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}

      - name: Build and push
        id: push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          platforms: linux/amd64,linux/arm64

      - name: Sign image with cosign
        uses: sigstore/cosign-installer@v3
        with:
          cosign-release: v2.2.0
      - run: cosign sign --yes ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.push.outputs.digest }}

  # ── Deploy to Staging ─────────────────────────────────────────────────────
  deploy-staging:
    runs-on: ubuntu-latest
    needs: build
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.STAGING_KUBECONFIG }}

      - name: Validate Dapr components
        run: |
          dapr components -k -n staging
          dapr status -k

      - name: Update image tag
        run: |
          kubectl set image deployment/order-service \
            order-service=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build.outputs.image-digest }} \
            -n staging

      - name: Wait for rollout
        run: kubectl rollout status deployment/order-service -n staging --timeout=300s

      - name: Run smoke tests
        run: pytest tests/e2e/ -v --base-url=${{ secrets.STAGING_URL }} -m smoke

  # ── Deploy to Production (manual approval) ────────────────────────────────
  deploy-production:
    runs-on: ubuntu-latest
    needs: deploy-staging
    environment:
      name: production
      url: ${{ secrets.PROD_URL }}
    steps:
      - uses: actions/checkout@v4

      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.PROD_KUBECONFIG }}

      - name: Blue/Green switch via Dapr canary
        run: |
          # Update 10% of traffic first
          kubectl patch deployment order-service -n production \
            -p '{"spec":{"strategy":{"rollingUpdate":{"maxSurge":"10%","maxUnavailable":"0"}}}}'

          kubectl set image deployment/order-service \
            order-service=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build.outputs.image-digest }} \
            -n production

          # Monitor error rate for 5 minutes
          sleep 300
          ERROR_RATE=$(kubectl exec -n monitoring prometheus-0 -- \
            promtool query instant 'rate(dapr_http_server_response_count{status_code=~"5..",namespace="production"}[5m])')

          if [[ "$ERROR_RATE" > "0.01" ]]; then
            echo "Error rate too high — rolling back"
            kubectl rollout undo deployment/order-service -n production
            exit 1
          fi

          # Complete rollout
          kubectl rollout status deployment/order-service -n production --timeout=600s
```

---

## ArgoCD GitOps — Dapr Control Plane

```yaml
# clusters/production/dapr-system/helmrelease.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dapr
  namespace: argocd
spec:
  project: infrastructure
  source:
    repoURL: https://dapr.github.io/helm-charts/
    chart: dapr
    targetRevision: 1.15.x          # Pin version — never use *
    helm:
      valuesFiles:
        - helm/dapr-production-values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: dapr-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
    retry:
      limit: 3
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

### ArgoCD — Dapr Components (Separate App)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dapr-components-production
  namespace: argocd
spec:
  project: production
  source:
    repoURL: https://github.com/myorg/dapr-platform.git
    targetRevision: HEAD
    path: clusters/production/components
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  syncPolicy:
    automated:
      prune: false              # Never auto-delete components
      selfHeal: true
    syncOptions:
      - Validate=true
      - ApplyOutOfSyncOnly=true
```

---

## Flux CD — Alternative GitOps

```yaml
# flux-system/dapr-helmrelease.yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: dapr
  namespace: dapr-system
spec:
  interval: 1h
  chart:
    spec:
      chart: dapr
      version: "1.15.x"
      sourceRef:
        kind: HelmRepository
        name: dapr
        namespace: flux-system
  values:
    global:
      logLevel: warn
      mtls:
        enabled: true
    dapr_operator:
      replicaCount: 3
    dapr_placement:
      replicaCount: 3
  upgrade:
    remediation:
      retries: 3
  rollback:
    timeout: 10m
```

---

## Dapr Component Validation in CI

```yaml
# .github/workflows/validate-components.yaml
name: Validate Dapr Components

on:
  pull_request:
    paths:
      - 'components/**'
      - 'clusters/**/components/**'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Dapr CLI
        run: wget -q https://raw.githubusercontent.com/dapr/cli/master/install/install.sh -O - | bash

      - name: Validate component YAML schema
        run: |
          for f in components/*.yaml; do
            echo "Validating $f"
            # Check required fields
            python3 -c "
          import yaml, sys
          with open('$f') as fp:
              doc = yaml.safe_load(fp)
          assert doc.get('apiVersion') == 'dapr.io/v1alpha1', 'Wrong apiVersion'
          assert 'kind' in doc, 'Missing kind'
          assert 'name' in doc.get('metadata', {}), 'Missing name'
          assert 'namespace' in doc.get('metadata', {}), 'Missing namespace (required)'
          spec = doc.get('spec', {})
          assert 'type' in spec, 'Missing spec.type'
          assert 'version' in spec, 'Missing spec.version'
          # Security: check no plaintext secrets
          for item in spec.get('metadata', []):
              assert 'secretKeyRef' in item or 'value' not in str(item.get('value','')).lower().replace(' ',''),\
                  f'Possible plaintext secret in {item.get(\"name\")}'
          print(f'  PASS: $f')
          "
          done

      - name: Check no plaintext credentials
        run: |
          # Fail if any component has password/key/secret as plain value
          if grep -rn "value:.*password\|value:.*secret\|value:.*token\|value:.*key" components/ \
            | grep -v "secretKeyRef" | grep -v "#"; then
            echo "FAIL: Found potential plaintext credentials in components/"
            exit 1
          fi
          echo "PASS: No plaintext credentials found"

      - name: Lint with yamllint
        run: |
          pip install yamllint
          yamllint -d relaxed components/
```

---

## Production Upgrade Pipeline

```yaml
# .github/workflows/upgrade-dapr.yaml
name: Upgrade Dapr Control Plane

on:
  workflow_dispatch:
    inputs:
      dapr_version:
        description: "Dapr version (e.g., 1.15.5)"
        required: true
      cluster:
        description: "Target cluster (staging|production)"
        required: true
        default: staging

jobs:
  upgrade:
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.cluster }}
    steps:
      - uses: actions/checkout@v4

      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets[format('{0}_KUBECONFIG', upper(github.event.inputs.cluster))] }}

      - name: Pre-upgrade health check
        run: |
          dapr status -k
          kubectl get pods -n dapr-system
          echo "All Dapr control plane pods must be Running before upgrade"

      - name: Upgrade Dapr via Helm
        run: |
          helm upgrade dapr dapr/dapr \
            --namespace dapr-system \
            --version ${{ github.event.inputs.dapr_version }} \
            --values helm/dapr-production-values.yaml \
            --wait --timeout 10m

      - name: Restart app sidecars (rolling)
        run: |
          # New sidecar version requires pod restart
          for ns in production staging; do
            kubectl rollout restart deployment -n $ns
            kubectl rollout status deployment -n $ns --timeout=5m
          done

      - name: Post-upgrade validation
        run: |
          dapr status -k
          kubectl get pods -n dapr-system
          # Verify version
          kubectl get pods -n dapr-system -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].image}{"\n"}{end}'
```

---

## CI/CD Quality Gates for Dapr Apps

| Gate | Tool | Threshold |
|------|------|-----------|
| Unit test coverage | pytest-cov | ≥ 80% |
| Actor state coverage | Custom | All transitions |
| Workflow determinism | WorkflowTestHarness | 100% paths |
| Image vulnerabilities | Trivy | 0 critical CVEs |
| Component secrets check | yamllint + grep | 0 plaintext |
| Sidecar resource limits | OPA / kyverno | Required annotations |
| mTLS enabled | dapr mtls check | Always true |
| Rollout success | kubectl rollout | 100% healthy pods |
