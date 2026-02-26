# CI/CD Anti-Patterns Reference

Common mistakes that destroy pipeline reliability, security, and team velocity.

---

## Security Anti-Patterns

### ❌ Static Long-Lived Credentials in CI
```yaml
# WRONG — storing AWS keys as CI secrets
env:
  AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
  AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
# If secrets rotate → pipeline breaks
# If leaked → permanent compromise until manually rotated
```
```yaml
# RIGHT — OIDC keyless (Tier 3+)
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::123456789:role/GitHubActionsRole
    aws-region: us-east-1
# No stored credentials, auto-expires in 1 hour
```

### ❌ Unpinned Actions (Supply Chain Attack)
```yaml
# WRONG — @main can be updated to inject malicious code
- uses: actions/checkout@main
- uses: some-action/untrusted@latest

# RIGHT — pin to commit SHA or semver tag
- uses: actions/checkout@v4          # Pin to major version
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # Pin to SHA
```

### ❌ Secrets Printed to Logs
```yaml
# WRONG — debug flag exposes all env vars including secrets
- run: docker build --progress=plain . && set -x && deploy.sh

# RIGHT — no -x flag, no debug flags with secrets in scope
- run: deploy.sh
  env:
    DB_PASSWORD: ${{ secrets.DB_PASSWORD }}  # Will be masked, but don't -x
```

### ❌ continue-on-error on Security Stages
```yaml
# WRONG — security failures silently ignored
- name: Security Scan
  continue-on-error: true  # This defeats the entire purpose
  run: trivy image myapp:latest

# RIGHT — fail on findings, gate the pipeline
- name: Security Scan
  run: trivy image --exit-code 1 --severity CRITICAL,HIGH myapp:latest
```

### ❌ Over-Privileged Pipeline Token
```yaml
# WRONG — default permissions allow writing to everything
# (GitHub Actions default was write-all before 2023)
name: CI
# No permissions block = inherits org defaults (often too broad)

# RIGHT — explicit minimal permissions
permissions:
  contents: read
  packages: write
  id-token: write
```

---

## Reliability Anti-Patterns

### ❌ No Timeouts on Jobs
```yaml
# WRONG — runaway job consumes all CI quota
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: npm run build  # Could hang forever

# RIGHT — timeout prevents quota exhaustion
jobs:
  build:
    timeout-minutes: 30
    runs-on: ubuntu-latest
```

### ❌ Rebuilding Image Multiple Times
```yaml
# WRONG — build in CI, then build again for staging deploy
jobs:
  test:
    steps:
      - run: docker build -t myapp:test .
      - run: pytest (using the image)
  deploy-staging:
    steps:
      - run: docker build -t myapp:staging .  # Rebuilds! Wastes 5-10 min
      - run: docker push myapp:staging

# RIGHT — build once, pass digest to all jobs
jobs:
  build:
    outputs:
      digest: ${{ steps.push.outputs.digest }}
    steps:
      - id: push
        uses: docker/build-push-action@v6
        with:
          push: true
          tags: ${{ env.REGISTRY }}/myapp:${{ github.sha }}

  deploy-staging:
    needs: build
    steps:
      - run: helm set image.digest=${{ needs.build.outputs.digest }}
```

### ❌ No Cache Configuration
```yaml
# WRONG — installs all dependencies from scratch every run
- run: pip install -r requirements.txt  # 2-5 minutes every time

# RIGHT — cache reduces to seconds on cache hit
- uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: pip-${{ hashFiles('requirements*.txt') }}
- run: pip install -r requirements.txt
```

### ❌ Fail-Fast on Matrix (Hides All Failures)
```yaml
# WRONG — first service failure cancels all other services
strategy:
  fail-fast: true  # Default in GitHub Actions
  matrix:
    service: [auth, orders, payments, notifications]

# RIGHT — see all failures at once
strategy:
  fail-fast: false
  matrix:
    service: [auth, orders, payments, notifications]
```

### ❌ Deploying Untested Code to Production
```yaml
# WRONG — deploy job doesn't depend on tests
jobs:
  test:
    runs-on: ubuntu-latest
    steps: [...]
  deploy-production:
    # Missing: needs: [test]  ← No dependency!
    runs-on: ubuntu-latest

# RIGHT — explicit dependency chain
jobs:
  deploy-production:
    needs: [lint, test, security-scan, deploy-staging, smoke-test]
    if: startsWith(github.ref, 'refs/tags/v')
```

---

## Performance Anti-Patterns

### ❌ Serial Stages That Could Parallelize
```yaml
# WRONG — lint and SAST run one after another
steps:
  - name: Lint
    run: flake8 src/
  - name: Type Check
    run: mypy src/
  - name: SAST
    run: semgrep --config auto src/

# RIGHT — parallel jobs for independent checks
jobs:
  lint:
    steps:
      - run: flake8 src/ && mypy src/
  sast:
    steps:
      - run: semgrep --config auto src/
  # Both run simultaneously
```

### ❌ Full Monorepo Build on Every Change
```yaml
# WRONG — build all 20 services even if only auth changed
strategy:
  matrix:
    service: [auth, orders, payments, notifications, search, ...]  # All 20

# RIGHT — change detection + dynamic matrix
detect-changes:
  outputs:
    changed: ${{ steps.filter.outputs.changes }}
  steps:
    - uses: dorny/paths-filter@v3
      # ... only outputs changed services
```

### ❌ No Concurrency Cancellation
```yaml
# WRONG — 10 PRs queued builds all run (wastes 10x resources)
name: CI
on: [push]

# RIGHT — cancel superseded runs on same branch
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

---

## GitOps Anti-Patterns

### ❌ Manual kubectl apply in CD Pipeline
```yaml
# WRONG — not tracked in Git, no audit trail, no drift detection
- name: Deploy
  run: kubectl apply -f k8s/  # Manual and untracked

# RIGHT — commit to GitOps repo, let ArgoCD/Flux sync
- name: Update GitOps Repo
  run: |
    cd gitops-repo
    kustomize edit set image myapp=$NEW_IMAGE
    git commit -am "chore: deploy ${GIT_SHA}"
    git push
# ArgoCD/Flux detects and applies automatically
```

### ❌ Mixing Application Code and GitOps Manifests
```
# WRONG — same repo for code and k8s manifests
myapp/
├── src/          ← Application code
├── tests/
└── k8s/          ← K8s manifests — triggers CI on every code change

# RIGHT — separate repositories
myapp/            ← Application code (triggers CI, builds image)
myapp-gitops/     ← K8s manifests only (ArgoCD watches this)
```

### ❌ Storing Secrets in GitOps Repo
```yaml
# WRONG — plaintext secrets in GitOps repo
# k8s/secret.yaml (accidentally committed!)
apiVersion: v1
kind: Secret
data:
  password: c3VwZXJzZWNyZXQ=  # base64 is NOT encryption

# RIGHT — use sealed-secrets or external-secrets operator
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret  # Encrypted, safe to commit
# Or reference from AWS/GCP/Azure secrets manager
```

---

## Testing Anti-Patterns

### ❌ Skipping Tests to Speed Up Pipeline
```yaml
# WRONG — common "just this once" that becomes permanent
- run: pytest -k "not slow" --timeout=10  # Skips important tests
- run: pytest --ignore=tests/integration/  # Skips integration tests

# RIGHT — fix slow tests, don't skip them
# - Use pytest-xdist for parallelism
# - Mock slow external dependencies
# - Cache test results (pytest-cache)
```

### ❌ Tests Not Enforcing Coverage Threshold
```yaml
# WRONG — coverage generated but not enforced
- run: pytest --cov=src --cov-report=xml
# No --cov-fail-under → always passes

# RIGHT — enforce minimum coverage
- run: pytest --cov=src --cov-fail-under=80
# Pipeline fails if coverage drops below 80%
```

### ❌ No Post-Deploy Smoke Test
```yaml
# WRONG — deploy succeeds even if app is broken
- run: helm upgrade --install myapp chart/
# No verification that deployment actually works

# RIGHT — always verify after deploy
- run: helm upgrade --install myapp chart/ --atomic --timeout 5m
- run: ./scripts/smoke_test.sh https://staging.example.com
```

---

## Notification Anti-Patterns

### ❌ Notification Spam (Alert on Every Build)
```yaml
# WRONG — Slack flooded with "build succeeded" every 5 minutes
- name: Notify Slack
  if: always()  # Runs on success AND failure
  run: curl -X POST $SLACK_WEBHOOK -d '{"text":"Build finished"}'

# RIGHT — notify on failure + first success after failure
- name: Notify on Failure
  if: failure()
  run: |
    curl -X POST ${{ secrets.SLACK_WEBHOOK }} \
      -d '{"text":"🚨 Pipeline failed: ${{ github.repository }}/${{ github.workflow }}"}'
```

### ❌ No Context in Failure Notifications
```yaml
# WRONG — unhelpful notification
- run: curl -d '{"text":"Build failed"}' $WEBHOOK

# RIGHT — actionable notification with context
- if: failure()
  run: |
    curl -X POST ${{ secrets.SLACK_WEBHOOK }} \
      -H "Content-Type: application/json" \
      -d '{
        "text": "🚨 Pipeline Failed",
        "attachments": [{
          "color": "danger",
          "fields": [
            {"title": "Repository", "value": "${{ github.repository }}"},
            {"title": "Branch", "value": "${{ github.ref_name }}"},
            {"title": "Commit", "value": "${{ github.sha }}"},
            {"title": "Actor", "value": "${{ github.actor }}"},
            {"title": "Run", "value": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"}
          ]
        }]
      }'
```

---

## Quick Anti-Pattern Checklist

Before finalizing any pipeline, check:
- [ ] No static cloud credentials (use OIDC)
- [ ] All actions pinned to semver or SHA
- [ ] `continue-on-error: true` NOT on security stages
- [ ] `timeout-minutes` set on all jobs
- [ ] `concurrency.cancel-in-progress: true` set
- [ ] `fail-fast: false` on matrix builds
- [ ] Cache configured for all dependency installs
- [ ] Build once, deploy same artifact everywhere
- [ ] Smoke test after every deployment
- [ ] Coverage threshold enforced with `--cov-fail-under`
- [ ] Production deploy requires all quality gates (via `needs:`)
- [ ] Secrets masked in logs
- [ ] GitOps manifests in separate repo (Tier 4+)
- [ ] No plaintext secrets in GitOps repo
