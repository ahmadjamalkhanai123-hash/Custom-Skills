# Microservices CI/CD Patterns Reference

Matrix builds, change detection, service graphs, monorepo tooling, and cross-service testing.

---

## Repository Strategies

### Monorepo (Single Repo — All Services)
```
monorepo/
├── services/
│   ├── auth/             ← Independent pipeline triggers
│   ├── orders/
│   ├── payments/
│   └── notifications/
├── shared/
│   ├── proto/            ← Shared protobuf definitions
│   ├── libs/             ← Shared libraries
│   └── infra/            ← Shared infrastructure
├── .github/
│   └── workflows/
│       ├── auth.yml      ← Service-specific workflow
│       ├── orders.yml
│       └── shared.yml    ← Triggers all services on shared changes
└── nx.json / turbo.json  ← Build orchestration
```

**Pros**: Single PR spans multiple services, shared code changes atomic
**Cons**: Requires change detection to avoid rebuilding everything

### Polyrepo (Separate Repo per Service)
```
org/auth-service        ← Full standalone CI/CD
org/orders-service
org/payments-service
org/gitops-repo         ← Central deployment manifests
org/shared-libs         ← Publishes packages to private registry
```

**Pros**: Full isolation, independent versioning
**Cons**: Cross-service changes require multiple PRs, harder integration testing

---

## Change Detection

### GitHub Actions — paths-filter
```yaml
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      auth: ${{ steps.filter.outputs.auth }}
      orders: ${{ steps.filter.outputs.orders }}
      payments: ${{ steps.filter.outputs.payments }}
      shared: ${{ steps.filter.outputs.shared }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            auth:
              - 'services/auth/**'
              - 'shared/proto/**'
              - 'shared/libs/**'
            orders:
              - 'services/orders/**'
              - 'shared/proto/**'
              - 'shared/libs/**'
            payments:
              - 'services/payments/**'
              - 'shared/**'
            shared:
              - 'shared/**'
              - '.github/workflows/**'

  build-auth:
    needs: detect-changes
    if: needs.detect-changes.outputs.auth == 'true'
    uses: ./.github/workflows/build-service.yml
    with:
      service: auth
      path: services/auth
```

### Nx (Monorepo Build Orchestration)
```bash
# Only affected projects since last commit on main
nx affected --target=build --base=origin/main
nx affected --target=test --base=origin/main
nx affected --target=docker-build --base=origin/main

# In CI
npx nx affected --target=lint,test,build --base=origin/main --head=HEAD --parallel=5
```

### Turborepo (Task Pipeline)
```json
// turbo.json
{
  "pipeline": {
    "build": {
      "dependsOn": ["^build"],  // Build deps first
      "outputs": ["dist/**", ".next/**"]
    },
    "test": {
      "dependsOn": ["build"],
      "outputs": ["coverage/**"]
    },
    "docker-build": {
      "dependsOn": ["test"],
      "cache": false
    }
  }
}
```

```bash
# CI: only run affected + their dependencies
npx turbo run test docker-build --filter='[origin/main]' --parallel
```

---

## Matrix Build Strategy

### Dynamic Matrix from Changed Services
```yaml
jobs:
  detect:
    outputs:
      matrix: ${{ steps.set-matrix.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - id: set-matrix
        run: |
          CHANGED=$(git diff --name-only origin/main...HEAD | \
            grep '^services/' | \
            cut -d'/' -f2 | \
            sort -u | \
            jq -R -s -c 'split("\n")[:-1]')
          echo "matrix={\"service\":${CHANGED}}" >> $GITHUB_OUTPUT

  build:
    needs: detect
    if: needs.detect.outputs.matrix != '{"service":[]}'
    strategy:
      fail-fast: false
      matrix: ${{ fromJson(needs.detect.outputs.matrix) }}
    steps:
      - uses: actions/checkout@v4
      - name: Build ${{ matrix.service }}
        run: |
          docker build \
            -t ${{ env.REGISTRY }}/myapp/${{ matrix.service }}:${{ github.sha }} \
            services/${{ matrix.service }}/
          docker push ${{ env.REGISTRY }}/myapp/${{ matrix.service }}:${{ github.sha }}
```

### Static Matrix with Dependencies
```yaml
strategy:
  matrix:
    include:
      - service: auth
        depends_on: []
        port: 8080
      - service: orders
        depends_on: [auth]
        port: 8081
      - service: payments
        depends_on: [auth, orders]
        port: 8082
        pci_scope: true
      - service: notifications
        depends_on: [orders]
        port: 8083
```

---

## Service Build Order (Topological Sort)

### Parallel Groups with Dependencies
```yaml
# Group 1: No dependencies (build in parallel)
build-group-1:
  strategy:
    matrix:
      service: [auth, user, config]

# Group 2: Depends on Group 1 (wait, then build in parallel)
build-group-2:
  needs: [build-group-1]
  strategy:
    matrix:
      service: [orders, inventory, search]

# Group 3: Depends on Group 2
build-group-3:
  needs: [build-group-2]
  strategy:
    matrix:
      service: [payments, checkout, fulfillment]
```

---

## Cross-Service Integration Testing

### Docker Compose Integration Stack
```yaml
# docker-compose.test.yml
services:
  auth:
    image: ${REGISTRY}/auth:${GIT_SHA}
    healthcheck:
      test: [CMD, curl, -sf, http://localhost:8080/health]
      interval: 5s
      retries: 12

  orders:
    image: ${REGISTRY}/orders:${GIT_SHA}
    depends_on:
      auth:
        condition: service_healthy

  payments:
    image: ${REGISTRY}/payments:${GIT_SHA}
    depends_on:
      auth:
        condition: service_healthy
      orders:
        condition: service_healthy

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: testdb
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test

  test-runner:
    build:
      context: tests/integration
    depends_on:
      - auth
      - orders
      - payments
    command: pytest tests/ -v
```

### k3d Multi-Service Integration
```yaml
- name: Create k3d Cluster
  run: k3d cluster create integration --agents 3 --wait

- name: Import Service Images
  run: |
    for SERVICE in auth orders payments; do
      docker pull $REGISTRY/$SERVICE:$GIT_SHA
      k3d image import $REGISTRY/$SERVICE:$GIT_SHA -c integration
    done

- name: Deploy All Services
  run: |
    kubectl apply -f tests/integration/k8s/
    kubectl wait --for=condition=available deployment --all --timeout=120s

- name: Run Integration Tests
  run: pytest tests/integration/ -v --base-url=http://$(k3d kubeconfig get integration)

- name: Cleanup
  if: always()
  run: k3d cluster delete integration
```

---

## Service Mesh Integration Testing

### Istio Service Mesh in CI
```yaml
- name: Install Istio (minimal profile)
  run: |
    istioctl install --set profile=minimal -y
    kubectl label namespace default istio-injection=enabled

- name: Deploy Services with Sidecar
  run: kubectl apply -f services/

- name: Test Service-to-Service Communication
  run: |
    # Verify mTLS is active between services
    kubectl exec deployment/auth -- curl -sf http://orders/api/v1/health
    # Verify Istio rejected non-mTLS calls
    kubectl exec deployment/attacker -- curl -sf http://payments/api/v1 && exit 1 || true
```

---

## Reusable Pipeline Templates

### Shared Build Workflow (GitHub Actions)
```yaml
# .github/workflows/reusable-service-build.yml
on:
  workflow_call:
    inputs:
      service-name:
        required: true
        type: string
      service-path:
        required: true
        type: string
      coverage-threshold:
        type: number
        default: 80
    outputs:
      image-digest:
        value: ${{ jobs.build.outputs.digest }}

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ${{ inputs.service-path }}
    steps:
      - uses: actions/checkout@v4
      - name: Test
        run: pytest --cov-fail-under=${{ inputs.coverage-threshold }}

  build:
    needs: test
    outputs:
      digest: ${{ steps.push.outputs.digest }}
    steps:
      - uses: docker/build-push-action@v6
        id: push
        with:
          context: ${{ inputs.service-path }}
          push: true
          tags: ${{ env.REGISTRY }}/${{ inputs.service-name }}:${{ github.sha }}
```

### Per-Service Caller
```yaml
# services/auth/.github/workflows/ci.yml
jobs:
  ci:
    uses: ./.github/workflows/reusable-service-build.yml
    with:
      service-name: auth
      service-path: services/auth
      coverage-threshold: 85
```

---

## Service Versioning Strategy

### Independent Versioning (Recommended for Microservices)
```bash
# Each service has its own semantic version
services/auth:     v2.3.1
services/orders:   v1.8.0
services/payments: v3.0.2

# Image tags: service:version-sha
auth:v2.3.1-sha9a3b8c1d
orders:v1.8.0-sha9a3b8c1d
```

### Coordinated Release (Monorepo)
```bash
# All services share a root version (simpler but tight coupling)
# v1.2.3 = all services at this monorepo commit
# Use when services must be deployed together

# Release pipeline:
1. Tag monorepo: git tag v1.2.3
2. Build all services: build-matrix with v1.2.3
3. Create release manifest: lists all service:v1.2.3 images
4. Deploy atomically
```

---

## DORA Metrics for Microservices

```yaml
# Track per-service DORA metrics
- name: Record Deployment
  run: |
    # Deployment frequency + lead time
    curl -X POST "$METRICS_API/events/deployment" -d '{
      "service": "${{ matrix.service }}",
      "version": "${{ github.sha }}",
      "environment": "production",
      "timestamp": "'$(date -Iseconds)'",
      "commit_time": "${{ github.event.head_commit.timestamp }}",
      "lead_time_seconds": '$(($(date +%s) - $(date -d "${{ github.event.head_commit.timestamp }}" +%s)))'
    }'
```

| Metric | Elite | High | Medium | Low |
|--------|-------|------|--------|-----|
| Deployment Frequency | Multiple/day | Daily-weekly | Weekly-monthly | Monthly+ |
| Lead Time | <1 hour | 1d-1wk | 1wk-1mo | >6mo |
| MTTR | <1 hour | <1 day | 1d-1wk | >1wk |
| Change Failure Rate | <5% | <10% | 15% | >30% |
