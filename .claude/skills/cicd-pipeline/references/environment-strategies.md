# Environment Strategies Reference

Environment promotion, feature flags, canary, blue-green, and rollback patterns.

---

## Environment Hierarchy

```
developer workstation (Tier 1)
    │
    ▼
dev/preview (auto-deploy on PR or feature branch)
    │
    ▼
staging / QA (auto-deploy on main merge)
    │  ← DAST + integration tests here
    ▼
production (manual gate + canary)
    │
    ▼
hotfix (emergency fast-track with abbreviated checks)
```

---

## Environment Configuration Patterns

### GitHub Environments (Protected)
```yaml
# .github/workflows/deploy.yml
jobs:
  deploy-staging:
    environment:
      name: staging
      url: https://staging.example.com
    # Auto-deploys (no approval)

  deploy-production:
    environment:
      name: production
      url: https://example.com
    # Requires approval from "production-approvers" team
    # Configured in GitHub → Settings → Environments → Required reviewers
```

### Per-Environment Secrets
```
GitHub Environments:
- staging: uses STAGING_KUBECONFIG, STAGING_DB_URL
- production: uses PROD_KUBECONFIG, PROD_DB_URL (restricted access)

Each secret scoped to its environment — staging CI cannot read prod secrets
```

### Environment Variables by Context
```yaml
# Matrix approach — same pipeline, different config
jobs:
  deploy:
    strategy:
      matrix:
        include:
          - environment: staging
            cluster: staging-k8s
            replicas: 2
            log_level: debug
          - environment: production
            cluster: prod-k8s
            replicas: 5
            log_level: warn
    steps:
      - name: Deploy to ${{ matrix.environment }}
        run: |
          helm upgrade --install myapp chart/ \
            --set replicaCount=${{ matrix.replicas }} \
            --set logLevel=${{ matrix.log_level }}
```

---

## Promotion Strategies

### Automated Promotion (Tier 2-3)
```yaml
# On success in staging, auto-promote to production (if tag)
promote-to-production:
  needs: [deploy-staging, run-dast, smoke-test-staging]
  if: startsWith(github.ref, 'refs/tags/v')
  environment: production
  steps:
    - name: Promote image
      run: |
        # Retag without rebuilding (same digest)
        docker pull $REGISTRY/myapp:${{ github.sha }}
        docker tag $REGISTRY/myapp:${{ github.sha }} $REGISTRY/myapp:${{ github.ref_name }}
        docker push $REGISTRY/myapp:${{ github.ref_name }}
    - name: Helm upgrade production
      run: |
        helm upgrade --install myapp chart/ \
          --namespace production \
          --set image.tag=${{ github.sha }} \
          --atomic \
          --timeout 5m
```

### GitOps Image Promotion (Tier 4-5)
```bash
#!/bin/bash
# promote.sh — update GitOps repo for environment promotion
ENVIRONMENT=$1  # staging or production
SERVICE=$2
NEW_TAG=$3

git clone git@github.com:org/gitops-repo.git /tmp/gitops
cd /tmp/gitops/apps/${SERVICE}/overlays/${ENVIRONMENT}

# Update image tag
kustomize edit set image ${SERVICE}=${REGISTRY}/${SERVICE}:${NEW_TAG}

git config user.email "ci-bot@example.com"
git config user.name "CI Bot"
git add .
git commit -m "chore(${ENVIRONMENT}): promote ${SERVICE} to ${NEW_TAG}

Promoted by: $GITHUB_ACTOR
Source run: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
git push
```

---

## Canary Deployment

### Nginx Ingress Canary (Simple)
```yaml
# canary-ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp-canary
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-weight: "10"  # 10% to canary
    # Or cookie-based:
    # nginx.ingress.kubernetes.io/canary-by-cookie: "canary"
    # Or header-based:
    # nginx.ingress.kubernetes.io/canary-by-header: "X-Canary"
spec:
  rules:
    - host: example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myapp-canary  # Canary service
                port:
                  number: 80
```

### Argo Rollouts Canary (Recommended — Tier 4+)
```yaml
# See cd-platforms.md for full AnalysisTemplate
# Quick summary of canary steps:
steps:
  - setWeight: 5         # 5% traffic to new version
  - pause: {duration: 2m}
  - analysis:            # Automated metrics check
      templates:
        - templateName: success-rate
  - setWeight: 20
  - pause: {duration: 5m}
  - analysis:
      templates:
        - templateName: success-rate
        - templateName: latency-check
  - setWeight: 50
  - pause: {}            # Manual pause — human verification
  - setWeight: 100       # Full rollout
```

### Canary Rollback Trigger
```bash
# Automated rollback if error rate exceeds threshold
# (handled by Argo Rollouts AnalysisRun automatically)

# Manual rollback:
kubectl argo rollouts abort myapp       # Abort and rollback
kubectl argo rollouts undo myapp        # Rollback to previous
kubectl argo rollouts promote myapp     # Force promote to 100%
```

---

## Blue-Green Deployment

### Service Selector Swap
```yaml
# Blue deployment (current production)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp-blue
  labels:
    color: blue
    version: v1.2.3

---
# Green deployment (new version)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp-green
  labels:
    color: green
    version: v1.3.0

---
# Service — points to blue (switch to green to promote)
apiVersion: v1
kind: Service
metadata:
  name: myapp
spec:
  selector:
    app: myapp
    color: blue  # Change to 'green' to switch traffic
```

### Blue-Green Switch Script
```bash
#!/bin/bash
CURRENT=$(kubectl get service myapp -o jsonpath='{.spec.selector.color}')
NEW_COLOR=$([ "$CURRENT" = "blue" ] && echo "green" || echo "blue")

echo "Switching from $CURRENT to $NEW_COLOR"

# Verify green is healthy before switching
kubectl rollout status deployment/myapp-${NEW_COLOR} --timeout=120s

# Switch traffic
kubectl patch service myapp -p '{"spec":{"selector":{"color":"'${NEW_COLOR}'"}}}'

# Smoke test new version
sleep 5
curl -sf https://example.com/health || {
  echo "Smoke test failed! Rolling back to $CURRENT"
  kubectl patch service myapp -p '{"spec":{"selector":{"color":"'${CURRENT}'"}}}'
  exit 1
}

echo "Switch complete. $NEW_COLOR is now production."
```

---

## Feature Flags

### LaunchDarkly (Managed)
```yaml
# CI integration — evaluate flags before deploy
- name: Check Feature Flag State
  run: |
    FLAG_ENABLED=$(curl -sf \
      "https://sdk.launchdarkly.com/sdk/eval/myapp/flags/new-payment-flow" \
      -H "Authorization: ${{ secrets.LAUNCHDARKLY_SDK_KEY }}" \
      | jq '.value')
    echo "FLAG_ENABLED=${FLAG_ENABLED}" >> $GITHUB_ENV
```

### Flagsmith / Unleash (Self-hosted)
```python
# Application code — not pipeline
from flagsmith import Flagsmith

client = Flagsmith(environment_key=os.environ["FLAGSMITH_KEY"])

def use_new_checkout():
    flags = client.get_environment_flags()
    return flags.is_feature_enabled("new_checkout_v2")
```

### Simple Environment Variable Flags (Tier 2-3)
```yaml
# helm values-production.yaml
featureFlags:
  newPaymentFlow: false    # Set true when ready
  aiAssistant: true
  betaFeatures: false
```

---

## Rollback Strategies

### Helm Rollback (Immediate)
```bash
# View history
helm history myapp -n production

# Rollback to previous release
helm rollback myapp 0 -n production --wait

# Rollback to specific revision
helm rollback myapp 3 -n production
```

### Kubernetes Deployment Rollback
```bash
# View rollout history
kubectl rollout history deployment/myapp -n production

# Rollback to previous
kubectl rollout undo deployment/myapp -n production

# Rollback to specific revision
kubectl rollout undo deployment/myapp -n production --to-revision=3

# Check status
kubectl rollout status deployment/myapp -n production
```

### Automated Rollback in Pipeline
```yaml
- name: Deploy to Production
  id: deploy
  run: |
    helm upgrade --install myapp chart/ \
      --namespace production \
      --set image.tag=${{ github.sha }} \
      --atomic \          # Rollback automatically on failure
      --timeout 5m \
      --cleanup-on-fail

- name: Smoke Test
  id: smoke
  run: ./scripts/smoke_test.sh https://example.com

- name: Rollback on Smoke Failure
  if: failure() && steps.smoke.outcome == 'failure'
  run: |
    helm rollback myapp 0 -n production --wait
    echo "Rolled back due to smoke test failure"
    # Alert team
    curl -X POST ${{ secrets.SLACK_WEBHOOK }} \
      -d '{"text":"🚨 Production rollback triggered for myapp at ${{ github.sha }}"}'
```

---

## Database Migration Strategy

### Pre-deploy Migration (Safe)
```yaml
# Run migration BEFORE new code deploys (backward-compatible)
jobs:
  migrate:
    steps:
      - name: Run Migration
        run: |
          kubectl run migration \
            --image=${{ env.IMAGE }}:${{ github.sha }} \
            --restart=Never \
            --env="DATABASE_URL=${{ secrets.DATABASE_URL }}" \
            --command -- python manage.py migrate
          kubectl wait --for=condition=complete job/migration --timeout=120s

  deploy:
    needs: migrate
    # Deploy new code after migration succeeds
```

### Zero-Downtime Migration Rules
```
Safe (can run before or after deploy):
✅ Adding nullable column
✅ Adding index (concurrently)
✅ Creating new table

Requires 2-phase deploy:
⚠️ Renaming column (add new → backfill → deploy → remove old)
⚠️ Changing column type
⚠️ Dropping column (remove from code first, then drop)

Never in CI/CD:
❌ Truncating tables
❌ Locking tables (use NOWAIT or lock_timeout)
```
