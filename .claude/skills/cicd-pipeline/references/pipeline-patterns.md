# Pipeline Patterns Reference

Build, cache, artifact, matrix, and parallelism patterns for production pipelines.

---

## Standard Stage Execution Order

```
Fail-fast stages (cheap, runs first):
1. Checkout + dependency install
2. Lint + format check + type check
3. Secret detection
4. SAST (static analysis)

Main stages:
5. Unit tests + coverage (parallel with build if possible)
6. Docker build (with cache)
7. Dependency SCA

Quality + security (post-build):
8. Container image scan
9. Integration tests

Artifact stages:
10. Push to registry
11. Image sign + SBOM

Deploy stages:
12. Deploy to dev (auto)
13. Deploy to staging (auto on main)
14. DAST on staging
15. Manual gate → Production deploy
16. Smoke test
17. Notify
```

---

## Docker Build Patterns

### Multi-Stage Build (Production)
```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
WORKDIR /app
RUN pip install uv

FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM base AS test
COPY --from=deps /app/.venv .venv
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project
RUN pytest --cov=src --cov-fail-under=80

FROM gcr.io/distroless/python3-debian12 AS production
COPY --from=deps /app/.venv /app/.venv
COPY --from=deps /app/src /app/src
USER nonroot
ENTRYPOINT ["/app/.venv/bin/python", "-m", "src.main"]
```

### BuildKit Cache Mount (CI)
```yaml
# GitHub Actions with BuildKit
- uses: docker/setup-buildx-action@v3
- uses: docker/build-push-action@v6
  with:
    context: .
    target: production
    push: ${{ github.event_name != 'pull_request' }}
    tags: |
      ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
      ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
    cache-from: type=gha
    cache-to: type=gha,mode=max
    build-args: |
      BUILD_DATE=${{ github.event.head_commit.timestamp }}
      GIT_SHA=${{ github.sha }}
    labels: |
      org.opencontainers.image.revision=${{ github.sha }}
      org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}
```

---

## Caching Strategies by Language

### Python (uv / pip)
```yaml
# GitHub Actions
- uses: actions/cache@v4
  with:
    path: |
      ~/.cache/uv
      ~/.cache/pip
      .venv/
    key: ${{ runner.os }}-python-${{ hashFiles('**/uv.lock', '**/requirements*.txt') }}

# GitLab CI
cache:
  key:
    files: [uv.lock]
  paths: [.venv/, ~/.cache/uv]
```

### Node.js
```yaml
# Use setup-node built-in cache
- uses: actions/setup-node@v4
  with:
    node-version: '20'
    cache: 'pnpm'  # or npm, yarn

# pnpm with lockfile hash
- uses: pnpm/action-setup@v4
  with:
    version: 9
    run_install: false
- uses: actions/cache@v4
  with:
    path: ~/.pnpm-store
    key: pnpm-${{ runner.os }}-${{ hashFiles('**/pnpm-lock.yaml') }}
```

### Go
```yaml
- uses: actions/setup-go@v5
  with:
    go-version-file: go.mod
    cache: true  # Built-in cache for go.sum
```

### Java / Maven / Gradle
```yaml
- uses: actions/cache@v4
  with:
    path: ~/.m2/repository
    key: maven-${{ runner.os }}-${{ hashFiles('**/pom.xml') }}

- uses: gradle/actions/setup-gradle@v3  # Built-in Gradle caching
```

### Rust
```yaml
- uses: Swatinem/rust-cache@v2
  with:
    cache-on-failure: true
    shared-key: "rust-${{ runner.os }}"
```

---

## Matrix Build Strategies

### GitHub Actions Matrix
```yaml
strategy:
  fail-fast: false  # Don't cancel other jobs on failure
  matrix:
    # Simple matrix
    python-version: ['3.11', '3.12', '3.13']
    os: [ubuntu-latest, windows-latest, macos-latest]

    # Exclude combinations
    exclude:
      - os: windows-latest
        python-version: '3.11'

    # Add extra variables per matrix entry
    include:
      - python-version: '3.12'
        os: ubuntu-latest
        is-primary: true  # Used in: if: matrix.is-primary
```

### Microservices Matrix (Change-Aware)
```yaml
# Job 1: Detect changes
detect-changes:
  outputs:
    services: ${{ steps.filter.outputs.changes }}
  steps:
    - uses: dorny/paths-filter@v3
      id: filter
      with:
        filters: |
          auth: [services/auth/**, shared/**]
          orders: [services/orders/**, shared/**]
          payments: [services/payments/**, shared/**]
          notifications: [services/notifications/**]

# Job 2: Build only changed services
build-services:
  needs: detect-changes
  if: needs.detect-changes.outputs.services != '[]'
  strategy:
    fail-fast: false
    matrix:
      service: ${{ fromJson(needs.detect-changes.outputs.services) }}
  steps:
    - name: Build ${{ matrix.service }}
      run: docker build -t myapp/${{ matrix.service }}:${{ github.sha }} services/${{ matrix.service }}/
```

### GitLab CI Parallel Matrix
```yaml
build-matrix:
  parallel:
    matrix:
      - SERVICE: [auth, orders, payments]
        ENVIRONMENT: [staging]
  script:
    - docker build -t myapp/${SERVICE}:${CI_COMMIT_SHA} services/${SERVICE}/
    - docker push myapp/${SERVICE}:${CI_COMMIT_SHA}
```

---

## Artifact Management

### Build Once, Deploy Many
```yaml
# Principle: build image once, promote same digest across environments
# Never rebuild for staging vs production — same artifact

# Step 1: Build and push (CI)
build:
  outputs:
    image-digest: ${{ steps.push.outputs.digest }}
  steps:
    - id: push
      uses: docker/build-push-action@v6
      with:
        push: true
        tags: ${{ env.REGISTRY }}/myapp:${{ github.sha }}

# Step 2: Retag (no rebuild) for each environment
deploy-staging:
  steps:
    - run: |
        docker pull ${{ env.REGISTRY }}/myapp@${{ needs.build.outputs.image-digest }}
        docker tag ${{ env.REGISTRY }}/myapp@${{ needs.build.outputs.image-digest }} \
                   ${{ env.REGISTRY }}/myapp:staging-latest
        docker push ${{ env.REGISTRY }}/myapp:staging-latest
```

### Artifact Versioning Strategy
```bash
# Semantic version + git SHA (immutable, traceable)
IMAGE_TAG="v1.2.3-sha${GIT_SHA:0:8}"
# e.g., myapp:v1.2.3-sha9a3b8c1d

# For pre-release (staging)
IMAGE_TAG="${BRANCH_NAME}-sha${GIT_SHA:0:8}"
# e.g., myapp:develop-sha9a3b8c1d

# Never use: myapp:latest (in production pipelines)
```

### Test Result Artifacts
```yaml
- name: Upload Test Results
  if: always()  # Run even on test failure
  uses: actions/upload-artifact@v4
  with:
    name: test-results-${{ github.run_id }}
    path: |
      coverage/
      reports/
      *.xml
    retention-days: 7  # Auto-delete after 7 days

- name: Publish Test Report
  uses: dorny/test-reporter@v1
  if: always()
  with:
    name: Test Results
    path: reports/test-results.xml
    reporter: java-junit
```

---

## Parallelism Patterns

### Parallel Jobs (GitHub Actions)
```yaml
jobs:
  # These 3 run in parallel
  lint:
    runs-on: ubuntu-latest
    steps: [...]

  security:
    runs-on: ubuntu-latest
    steps: [...]

  test:
    runs-on: ubuntu-latest
    steps: [...]

  # This waits for all 3
  build:
    needs: [lint, security, test]
    steps: [...]
```

### Parallel Steps (Within a Job)
```yaml
# GitLab CI parallel stages
lint-and-sast:
  stage: quality
  parallel:
    matrix:
      - CHECK: [flake8, mypy, semgrep, bandit]
  script:
    - case $CHECK in
        flake8) flake8 src/ ;;
        mypy) mypy src/ ;;
        semgrep) semgrep --config auto src/ ;;
        bandit) bandit -r src/ ;;
      esac
```

---

## Pipeline Observability

### Step Summary (GitHub Actions)
```yaml
- name: Pipeline Summary
  if: always()
  run: |
    cat >> $GITHUB_STEP_SUMMARY << 'EOF'
    ## Pipeline Results
    | Stage | Duration | Status |
    |-------|----------|--------|
    | Lint | ${{ steps.lint.outputs.duration }}s | ${{ steps.lint.outcome }} |
    | Test | ${{ steps.test.outputs.duration }}s | ${{ steps.test.outcome }} |
    | Build | ${{ steps.build.outputs.duration }}s | ${{ steps.build.outcome }} |
    | Scan | ${{ steps.scan.outputs.duration }}s | ${{ steps.scan.outcome }} |

    **Image**: `${{ env.IMAGE_NAME }}:${{ github.sha }}`
    **Coverage**: ${{ steps.test.outputs.coverage }}%
    EOF
```

### DORA Metrics Collection
```yaml
# Emit deployment event for DORA metrics tracking
- name: Record Deployment (DORA)
  if: success()
  run: |
    curl -X POST "${{ secrets.METRICS_ENDPOINT }}/deployments" \
      -H "Authorization: Bearer ${{ secrets.METRICS_TOKEN }}" \
      -H "Content-Type: application/json" \
      -d '{
        "service": "myapp",
        "environment": "production",
        "version": "${{ github.sha }}",
        "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
        "lead_time_seconds": ${{ steps.lead-time.outputs.seconds }}
      }'
```

---

## Branch Strategy Patterns

### Trunk-Based Development (Recommended — Tier 1-3)
```
main ─────────────────────────────────────────► production
     └─ feature/x (short-lived ≤2 days) → PR → main
     └─ hotfix/y → PR → main (emergency fast-track)

CI triggers:
- Push to main → deploy staging
- Tag v* → deploy production
- PR → CI only (no deploy)
```

### GitFlow (Tier 4-5)
```
main ──────────────────────────────► production (tags only)
develop ────────────────────────────► staging (auto)
        └─ feature/x → develop
        └─ release/1.2 → main+develop
        └─ hotfix/y → main+develop
```

### Monorepo Trigger Strategy
```yaml
# Only trigger for relevant paths
on:
  push:
    paths:
      - 'services/auth/**'
      - 'shared/proto/**'
      - '.github/workflows/auth-pipeline.yml'
    branches: [main, develop]
```
