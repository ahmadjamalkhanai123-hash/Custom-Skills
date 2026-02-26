# Testing Strategies Reference

Unit, integration, E2E, smoke, load, and chaos testing in CI/CD pipelines.

---

## Test Pyramid for CI/CD

```
         /\
        /E2E\         ← Few, slow, high-value (run on staging)
       /──────\
      /Integration\   ← Medium, Testcontainers/k3d (run on PR + main)
     /────────────\
    /   Unit Tests  \  ← Many, fast, cheap (run on every commit)
   /────────────────\
  / Pre-commit Hooks  \ ← Instant (lint, format, secret check)
 /────────────────────\
```

### Coverage Thresholds by Tier
| Tier | Minimum Coverage | Enforcement |
|------|-----------------|-------------|
| 1 Dev | 70% | Warning |
| 2 Standard | 80% | Fail pipeline |
| 3 Production | 80% | Fail pipeline |
| 4 Microservices | 85% per service | Fail pipeline |
| 5 Enterprise | 90% critical paths | Fail + block merge |

---

## Unit Testing

### Python (pytest)
```yaml
- name: Run Unit Tests
  run: |
    pytest tests/unit/ \
      --cov=src \
      --cov-report=xml:coverage.xml \
      --cov-report=html:coverage-html/ \
      --cov-fail-under=80 \
      --junitxml=reports/unit-results.xml \
      -n auto \           # Parallel with pytest-xdist
      --timeout=60        # Per-test timeout

- name: Upload Coverage to Codecov
  uses: codecov/codecov-action@v4
  with:
    files: coverage.xml
    fail_ci_if_error: true
    token: ${{ secrets.CODECOV_TOKEN }}
```

### Node.js (Vitest / Jest)
```yaml
- name: Run Unit Tests (Vitest)
  run: |
    npx vitest run --coverage \
      --coverage.thresholds.lines=80 \
      --coverage.thresholds.functions=80 \
      --reporter=verbose \
      --reporter=junit \
      --outputFile=reports/test-results.xml

- name: Run Unit Tests (Jest)
  run: |
    npx jest \
      --coverage \
      --coverageThreshold='{"global":{"lines":80}}' \
      --forceExit \
      --runInBand  # In CI, avoid worker conflicts
```

### Go
```yaml
- name: Run Tests
  run: |
    go test ./... \
      -race \           # Detect race conditions
      -coverprofile=coverage.out \
      -covermode=atomic \
      -count=1 \        # No test caching
      -timeout 5m

- name: Check Coverage
  run: |
    COVERAGE=$(go tool cover -func=coverage.out | grep total | awk '{print $3}' | tr -d '%')
    if (( $(echo "$COVERAGE < 80" | bc -l) )); then
      echo "Coverage ${COVERAGE}% is below 80%"
      exit 1
    fi
```

---

## Integration Testing (Testcontainers)

### Python with Testcontainers
```python
# tests/integration/test_user_service.py
import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from testcontainers.compose import DockerCompose

@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg

@pytest.fixture(scope="session")
def redis():
    with RedisContainer("redis:7-alpine") as r:
        yield r

def test_user_creation(postgres, redis):
    db_url = postgres.get_connection_url()
    # Run actual database operations against real Postgres
    from myapp.database import create_user
    user = create_user(name="test", db_url=db_url)
    assert user.id is not None
```

### Docker Compose for Integration (GitHub Actions)
```yaml
- name: Start Services
  run: docker compose -f docker-compose.test.yml up -d --wait

- name: Run Integration Tests
  run: pytest tests/integration/ -v --timeout=120

- name: Collect Logs on Failure
  if: failure()
  run: docker compose -f docker-compose.test.yml logs

- name: Stop Services
  if: always()
  run: docker compose -f docker-compose.test.yml down -v
```

### GitLab CI Services
```yaml
integration-tests:
  image: python:3.12-slim
  services:
    - postgres:16-alpine
    - redis:7-alpine
    - name: rabbitmq:3-management
      alias: rabbitmq
  variables:
    POSTGRES_DB: testdb
    POSTGRES_USER: test
    POSTGRES_PASSWORD: test
    POSTGRES_HOST: postgres
    REDIS_URL: redis://redis:6379
  script:
    - pip install -r requirements-dev.txt
    - pytest tests/integration/ -v
```

---

## End-to-End Testing

### Playwright (Browser E2E)
```yaml
- name: Install Playwright
  run: npx playwright install --with-deps chromium

- name: Run E2E Tests
  run: npx playwright test
  env:
    BASE_URL: https://staging.example.com
    CI: true

- name: Upload Playwright Report
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: playwright-report
    path: playwright-report/
    retention-days: 7
```

```typescript
// playwright.config.ts
export default {
  testDir: './e2e',
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'html',
};
```

### Cypress
```yaml
- name: Cypress E2E Tests
  uses: cypress-io/github-action@v6
  with:
    start: npm start
    wait-on: 'http://localhost:3000'
    wait-on-timeout: 60
    browser: chrome
    record: true
  env:
    CYPRESS_RECORD_KEY: ${{ secrets.CYPRESS_RECORD_KEY }}
```

---

## Kubernetes Integration Testing (k3d / kind)

### k3d Cluster in CI
```yaml
- name: Install k3d
  run: |
    curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
    k3d cluster create test --agents 2 --wait

- name: Load Image
  run: |
    docker build -t myapp:test .
    k3d image import myapp:test -c test

- name: Deploy to k3d
  run: |
    kubectl apply -f k8s/
    kubectl wait --for=condition=available deployment/myapp --timeout=60s

- name: Run Integration Tests
  run: |
    kubectl port-forward svc/myapp 8080:80 &
    sleep 2
    pytest tests/k8s-integration/ --base-url=http://localhost:8080

- name: Cleanup
  if: always()
  run: k3d cluster delete test
```

---

## Smoke Tests (Post-Deploy Validation)

### HTTP Smoke Test
```bash
#!/bin/bash
# scripts/smoke_test.sh
set -e

BASE_URL="${1:-http://localhost:8080}"
MAX_RETRIES=10
RETRY_DELAY=5

echo "Running smoke tests against ${BASE_URL}"

for i in $(seq 1 $MAX_RETRIES); do
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health")
  if [ "${HTTP_STATUS}" -eq 200 ]; then
    echo "Health check passed (${HTTP_STATUS})"
    break
  fi
  echo "Attempt ${i}/${MAX_RETRIES}: Got ${HTTP_STATUS}, retrying in ${RETRY_DELAY}s..."
  sleep ${RETRY_DELAY}
  if [ "${i}" -eq "${MAX_RETRIES}" ]; then
    echo "Smoke test FAILED after ${MAX_RETRIES} attempts"
    exit 1
  fi
done

# Critical endpoint checks
curl -sf "${BASE_URL}/api/v1/status" | jq '.status == "ok"' || exit 1
curl -sf "${BASE_URL}/metrics" | grep -q 'http_requests_total' || exit 1

echo "All smoke tests passed"
```

### Python Smoke Test (pytest + httpx)
```python
# tests/smoke/test_deployment.py
import httpx
import pytest

BASE_URL = pytest.fixture(scope="session")(lambda: pytest.ini_options.get("base_url", "http://localhost:8080"))

def test_health_check(base_url):
    r = httpx.get(f"{base_url}/health", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_api_responds(base_url):
    r = httpx.get(f"{base_url}/api/v1/status", timeout=10)
    assert r.status_code == 200

def test_metrics_exposed(base_url):
    r = httpx.get(f"{base_url}/metrics", timeout=10)
    assert r.status_code == 200
    assert "http_requests_total" in r.text
```

---

## Load Testing

### k6 (CI Load Test)
```yaml
- name: k6 Load Test (Staging)
  uses: grafana/k6-action@v0.3.1
  with:
    filename: tests/load/smoke.js
    flags: --out json=results.json
  env:
    K6_BASE_URL: https://staging.example.com

- name: Check SLA
  run: |
    # Fail if p95 > 500ms or error rate > 1%
    python scripts/check_slo.py results.json \
      --p95-threshold=500 \
      --error-rate-threshold=0.01
```

```javascript
// tests/load/smoke.js — baseline load test for CI
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95th percentile < 500ms
    errors: ['rate<0.01'],              // < 1% error rate
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const res = http.get(`${__ENV.K6_BASE_URL}/api/v1/status`);
  errorRate.add(res.status !== 200);
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}
```

---

## Test Parallelism (Split Tests Across Runners)

### GitHub Actions Test Splitting
```yaml
strategy:
  matrix:
    shard: [1, 2, 3, 4]
steps:
  - name: Run Tests (Shard ${{ matrix.shard }}/4)
    run: |
      pytest tests/ \
        --shard-id=${{ matrix.shard }} \
        --num-shards=4 \
        --cov=src
    # Requires pytest-shard package
```

### CircleCI Test Splitting (Built-in)
```yaml
- run:
    name: Run Tests
    command: |
      TEST_FILES=$(circleci tests glob "tests/**/*.py" | circleci tests split --split-by=timings)
      pytest $TEST_FILES --junitxml=reports/test-results.xml
```

---

## Flaky Test Handling

```yaml
# Retry flaky tests automatically
- name: Run Tests (with retry)
  run: |
    pytest tests/ \
      --reruns=3 \           # Retry failed tests 3 times
      --reruns-delay=1 \     # Wait 1s between retries
      --only-rerun "FLAKY"   # Only retry tests marked @pytest.mark.flaky
  # Requires pytest-rerunfailures

# Mark known flaky tests
# @pytest.mark.flaky(reruns=3, reruns_delay=2)
# def test_external_api(): ...
```

---

## Quality Gates Summary

```yaml
# Enforce all quality gates before merge
required-checks:
  - lint-and-format
  - unit-tests (coverage ≥ 80%)
  - integration-tests
  - sast-semgrep
  - dependency-sca
  - container-scan (Tier 3+)
  - e2e-tests (Tier 3+ on staging)
```
