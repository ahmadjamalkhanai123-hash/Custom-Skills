---
name: cicd-pipeline
description: |
  Creates production-ready CI/CD pipeline configurations for any platform, environment,
  and project type — from local developer workflows to enterprise multi-cloud GitOps.
  Supports GitHub Actions, GitLab CI, Jenkins, Azure DevOps, CircleCI, Bitbucket Pipelines,
  Tekton, and all major CD platforms (ArgoCD, Flux, Spinnaker, Harness, Argo Rollouts).
  This skill should be used when users want to build CI pipelines, create CD workflows,
  set up GitOps, configure automated testing, implement security scanning (SAST/DAST/SCA),
  containerize builds, scaffold microservice pipelines, deploy to any cloud vendor (AWS,
  GCP, Azure, DigitalOcean, on-prem), or architect enterprise DevOps for large microservices
  and agentic autonomous AI systems.
---

# CI/CD Pipeline

Build production-grade CI/CD pipelines for any platform, environment, and project type.

## What This Skill Builds

| Tier | Scope | Use Case |
|------|-------|----------|
| **1 — Developer** | Pre-commit hooks, Makefile, local `act` runner | Fast local feedback loop |
| **2 — Standard** | Single CI platform, Docker build, test, deploy | Small teams, single-service apps |
| **3 — Production** | Multi-stage, SAST/DAST/SCA, signing, multi-env | SaaS, regulated workloads |
| **4 — Microservices** | Matrix builds, change detection, integration testing | Large distributed systems |
| **5 — Enterprise** | Multi-cloud GitOps, progressive delivery, compliance | Platform engineering, global scale |

## What This Skill Does NOT Do

- Execute live pipeline runs against cloud accounts (generates configs, not deploys)
- Provision cloud infrastructure (use `k8s-mastery`, `docker-mastery`, `dapr-mastery`)
- Write application business logic (only DevOps and pipeline code)
- Replace runtime observability (generates alert configs, not live dashboards)
- Manage vendor account onboarding or billing

---

## Before Implementation

Gather context to ensure correct implementation:

| Source | Gather |
|--------|--------|
| **Codebase** | Existing CI files, languages, frameworks, Dockerfiles, test commands |
| **Conversation** | Tier, CI platform, CD target, cloud provider, project type, branch strategy |
| **Skill References** | `references/` — platforms, patterns, security, environments, testing |
| **User Guidelines** | Team conventions, secret management approach, compliance requirements |

Only ask users for THEIR requirements — domain expertise is embedded in `references/`.

---

## Required Clarifications

Ask in **two messages** — do not dump all questions at once.

**Message 1 (always ask):**
```
1. Deployment Tier (1-5)?
   1=Developer (local hooks+Makefile)
   2=Standard (CI platform + basic deploy)
   3=Production (multi-stage + security scanning)
   4=Microservices (matrix builds + GitOps)
   5=Enterprise (multi-cloud + progressive delivery + compliance)

2. CI Platform?
   □ GitHub Actions  □ GitLab CI  □ Jenkins  □ Azure DevOps
   □ CircleCI  □ Bitbucket Pipelines  □ Tekton  □ Drone  □ Local only

3. Project type?
   □ Single App  □ Monorepo  □ Microservices (polyrepo)  □ Agentic AI System
```

**Message 2 (ask only if Tier ≥ 3 or ambiguous):**
```
4. CD strategy?
   □ Direct (kubectl/helm)  □ ArgoCD  □ Flux  □ Spinnaker  □ Harness

5. Cloud / deployment target?
   □ AWS  □ GCP  □ Azure  □ DigitalOcean  □ On-prem K8s  □ Multi-cloud

6. Security / compliance requirements?
   □ SAST  □ DAST  □ SCA  □ Container scanning  □ SBOM
   □ SOC2  □ HIPAA  □ PCI-DSS  □ None
```

**If user skips optional questions**: Apply defaults and proceed.
**If user is vague about tier**: Use decision tree below to recommend, then confirm.

### Defaults (If Not Specified)

| Clarification | Default |
|---------------|---------|
| CI Platform | GitHub Actions |
| CD Strategy | Direct helm (Tier 2-3), ArgoCD (Tier 4-5) |
| Cloud Target | Generic Kubernetes |
| Security | None (Tier 1-2), SAST + container scan (Tier 3+) |
| Secret Management | Platform-native secrets (Tier 1-2), OIDC (Tier 3+) |
| Notifications | GitHub status checks + Slack (if webhook provided) |
| Branch Strategy | Trunk-based (Tier 1-3), GitFlow (Tier 4-5) |

---

## Tier Architecture Decision Tree

```
                    START
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
  Local Dev       Single App    Multi-service
       │              │              │
   TIER 1         TIER 2      Needs GitOps/Security?
 Pre-commit      Standard CI        │
 Makefile+act    build+test+deploy  ├─── TIER 3 Production
                                    │    (security scanning,
                                    │     multi-env, signing)
                                    │
                              Microservices or
                              Compliance needed?
                                    │
                             ┌──────┴──────┐
                             ▼             ▼
                         TIER 4        TIER 5
                     Microservices   Enterprise
                     Matrix+GitOps   Multi-cloud+
                     Integration     DORA+Compliance
```

---

## Platform Selection Matrix

### CI Platforms

| Platform | Best For | Killer Feature | Model |
|----------|----------|----------------|-------|
| GitHub Actions | GitHub repos, OSS | OIDC, Marketplace 20k+ | Both |
| GitLab CI | GitLab repos | Native registry, security scanning | Both |
| Jenkins | Enterprise, complex logic | Full control, 1800+ plugins | Self-hosted |
| Azure DevOps | Microsoft stack | Boards + Repos + Pipelines | Both |
| CircleCI | Performance-focused | DLC, test splitting, orbs | Both |
| Bitbucket Pipelines | Atlassian ecosystem | Jira/Confluence native | Hosted |
| Tekton | K8s-native CI | CRD-based tasks, reusable | Self-hosted |
| Drone | Lightweight, fast | Docker-native, plugin system | Self-hosted |

### CD Platforms

| Platform | Model | Best For |
|----------|-------|----------|
| ArgoCD | Pull (GitOps) | K8s declarative, multi-cluster, UI |
| Flux | Pull (GitOps) | K8s, Helm, image automation, lightweight |
| Argo Rollouts | Progressive | Canary/blue-green with metrics analysis |
| Spinnaker | Push | Multi-cloud, complex promotion |
| Harness | SaaS | Enterprise, AI-assisted, cost management |
| Jenkins X | Push+GitOps | Jenkins ecosystem on K8s |

---

## Workflow

```
Clarify → Design → CI Stages → CD Strategy → Security → Secrets → Test → Validate
```

### Step 1: Design Pipeline Architecture

Select tier-appropriate architecture from `references/pipeline-patterns.md`:

```
Tier 1: pre-commit hooks + Makefile → local act simulation
Tier 2: trigger → lint → build → test → package → deploy (single env)
Tier 3: trigger → lint+SAST → build → test → scan → sign → deploy (dev→staging→prod)
Tier 4: change detection → matrix build → integration → progressive deploy (GitOps)
Tier 5: Tier 4 + multi-cloud promotion + compliance gates + DORA metrics
```

### Step 2: Implement CI Stages

Read `references/ci-platforms.md` for platform-specific syntax.

**Standard stage order** (all platforms):
```
Stage 1 — Code Quality:  lint (ESLint/Flake8/gofmt) + type check + format
                         SAST: Semgrep / CodeQL / Snyk Code (Tier 3+)
Stage 2 — Build:         Docker multi-stage / Maven / Gradle / go build
                         Cache: layer cache + dependency cache
Stage 3 — Test:          unit (≥80% coverage) + integration (Testcontainers)
                         E2E (Playwright/Cypress) on staging (Tier 3+)
Stage 4 — Security:      SCA (Snyk/Trivy/Dependabot) — fail on CRITICAL
                         Image scan (Trivy/Grype) — fail on CRITICAL/HIGH
                         DAST (OWASP ZAP) against staging (Tier 3+)
                         Secret detection (Gitleaks/TruffleHog) — always
Stage 5 — Artifact:      Push to registry (ECR/GCR/ACR/GHCR/Harbor)
                         Sign with Cosign (keyless) + SBOM (Syft) (Tier 4+)
                         Tag: semver + git SHA
```

> Platform YAML examples → `references/ci-platforms.md`
> Security gate configs → `references/security-scanning.md`

### Step 3: Implement CD Strategy

Read `references/cd-platforms.md` for platform configs.

**Direct deploy** (Tier 2-3):
```
helm upgrade --install → rollout status → smoke test → alert on failure
```

**GitOps** (Tier 4-5):
```
Image digest update in Git → ArgoCD/Flux detects delta → syncs to cluster → health check
```

**Progressive delivery** (Tier 4-5):
```
Argo Rollouts → canary 10% → AnalysisRun (Prometheus metrics) → promote/rollback
```

> ArgoCD/Flux patterns → `references/cd-platforms.md`
> Canary/blue-green → `references/environment-strategies.md`

### Step 4: Multi-Environment Strategy

Read `references/environment-strategies.md`:

| Environment | Trigger | Approval | Deploy Strategy |
|-------------|---------|----------|-----------------|
| **dev** | push to `develop` | Automatic | Rolling |
| **staging** | push to `main` | Automatic | Rolling |
| **production** | tag `v*` / manual | Manual gate | Canary / Blue-Green |
| **hotfix** | push to `hotfix/*` | Auto + Slack | Rolling → Prod fast-track |

### Step 5: Secrets & Auth

Read `references/secrets-management.md`:

```
Tier 1-2: Platform-native (GitHub Secrets / GitLab CI vars / Azure Key groups)
Tier 3:   Cloud OIDC (keyless, short-lived tokens, zero stored credentials)
Tier 4-5: HashiCorp Vault / AWS Secrets Manager / Azure Key Vault (dynamic secrets)
```

**OIDC (mandatory Tier 3+)**:
- GitHub Actions → AWS/GCP/Azure without static access keys
- Audit trail per workflow run, auto-expiring tokens

### Step 6: Microservices Patterns (Tier 4-5)

Read `references/microservices-patterns.md`:
- **Change detection**: path filters → only rebuild affected services
- **Matrix builds**: parallel service builds with topological dependency order
- **Integration testing**: k3d / kind / Testcontainers for full service mesh
- **Monorepo tooling**: Nx, Turborepo, Bazel for incremental builds

### Step 7: Agentic AI System Patterns (Tier 4-5)

Read `references/agentic-patterns.md`:
- **Model validation gate**: LLM output evaluation before promoting new model version
- **Safety pipeline**: adversarial/red-team test suite as blocking CI stage
- **Prompt regression**: golden-set validation on every prompt/model update
- **A/B model deploy**: canary traffic split with output quality metrics

### Step 8: Validate Output

Apply Output Checklist below.

---

## Pipeline Security Gate Matrix

| Gate | Tier | Tool Options | Block on Fail? |
|------|------|--------------|----------------|
| Secret Detection | 2+ | Gitleaks, TruffleHog, detect-secrets | Yes |
| SAST | 3+ | Semgrep, CodeQL, Snyk Code, Checkov (IaC) | Yes (HIGH+) |
| Dependency SCA | 2+ | Snyk, Trivy, Dependabot, OWASP Dep-Check | Yes (CRITICAL) |
| Container Scan | 3+ | Trivy, Grype, Snyk Container | Yes (CRITICAL/HIGH) |
| DAST | 3+ | OWASP ZAP, Nuclei | Warn (staging) |
| Image Signing | 4+ | Cosign keyless, Notary v2 | Yes |
| SBOM | 4+ | Syft (SPDX/CycloneDX) | Generate + attest |
| License Check | 4+ | FOSSA, OSS Review Toolkit | Warn |
| IaC Scan | 3+ | Checkov, KICS, Trivy config | Yes (HIGH+) |

---

## Output Specification

### Tier 1 (Developer) Delivers
- `.pre-commit-config.yaml` (lint, format, secret detection, commit-msg)
- `Makefile` with `make lint`, `make test`, `make build`, `make docker`, `make ci` (local CI simulation)
- `.actrc` config for local GitHub Actions simulation via `act` (install: `brew install act`)
- `README-cicd.md` with setup steps and team onboarding notes

### Tier 2 (Standard) Delivers
- CI workflow file (platform-specific YAML/Groovy)
- Docker multi-stage build + layer caching config
- Test + coverage enforcement (fail below threshold)
- Deploy to single environment with health check

### Tier 3 (Production) Delivers
- Everything in Tier 2 +
- SAST + SCA + container scan stages
- Multi-environment pipeline (dev → staging → prod)
- Manual approval gate for production
- OIDC / KMS secrets (no static credentials)
- Cosign image signing + Syft SBOM generation

### Tier 4 (Microservices) Delivers
- Everything in Tier 3 +
- Change-detection (affected services only)
- Matrix build + parallel service pipeline
- Cross-service integration test (k3d + Testcontainers)
- ArgoCD / Flux application manifests
- Argo Rollouts canary with AnalysisTemplate
- Service-specific reusable pipeline templates

### Tier 5 (Enterprise) Delivers
- Everything in Tier 4 +
- Multi-cloud promotion manifests
- Compliance audit gates (SOC2/HIPAA/PCI-DSS)
- DORA metrics collection (deployment freq, lead time, MTTR, CFR)
- Pipeline SLO dashboards (Grafana)
- Drift detection + reconciliation
- `scripts/scaffold_cicd.py` for rapid service onboarding
- `scripts/cicd_mcp_server.py` for AI-assisted pipeline operations

---

## Domain Standards

### Must Follow

- [ ] Pin all action/image versions (use `@sha256:` or `@v1.2.3`, never `@latest`)
- [ ] OIDC for cloud auth (no long-lived static credentials in CI — Tier 3+)
- [ ] `CODEOWNERS` covering all pipeline YAML/Groovy files
- [ ] Fail-fast: lint + secret detection before expensive build/test stages
- [ ] Coverage threshold enforced (≥80% lines, fail pipeline below)
- [ ] Immutable artifact tags (`registry/image:sha-<gitsha>`, never reuse `:latest`)
- [ ] Semantic versioning for all artifacts (`v1.2.3-sha123abcd`)
- [ ] Rollback: automated on health-check failure, documented procedure
- [ ] Pipeline-as-Code: all configs in git, zero manual web UI configuration
- [ ] Timeout set on all jobs (prevent runaway builds consuming quota)

### Must Avoid

- Static long-lived cloud credentials (`AWS_ACCESS_KEY_ID` in CI env vars)
- Unpinned actions (`actions/checkout@main` — supply chain attack vector)
- `continue-on-error: true` on security scanning stages
- Printing secrets via debug flags (`--debug`, `set -x` in shells)
- Building same image multiple times per pipeline (cache + reuse digest)
- Monolithic single pipeline YAML for all services (kills parallelism)
- Manual deployments not tracked in Git (GitOps violation)
- Storing artifacts indefinitely (set retention policy ≤30 days)
- Skipping tests to speed up ("just merge it" anti-pattern)
- Hardcoded environment URLs or IPs (use config / env vars)

---

## Production Checklist

### Pipeline Core
- [ ] All action/step versions pinned (SHA or semver, not `latest`)
- [ ] Branch protection: required status checks + no direct push to main
- [ ] Least privilege: pipeline token scoped to minimum needed permissions
- [ ] Artifact tagged `git-sha + semver`; retained ≤30 days
- [ ] Cache configured (Docker layer, dependency, test result)
- [ ] Timeout configured on every job (`timeout-minutes: 30`)

### Security Gates
- [ ] Secret detection: pre-commit (Gitleaks) + CI (TruffleHog)
- [ ] SAST before build (fail on HIGH+ findings)
- [ ] Dependency SCA (fail on CRITICAL vulnerabilities)
- [ ] Container image scan (fail on CRITICAL/HIGH)
- [ ] OIDC auth to cloud (no static keys in CI env)
- [ ] `CODEOWNERS` covers pipeline files

### Testing Gates
- [ ] Unit tests ≥80% coverage enforced (fail below)
- [ ] Integration tests against real dependencies (Testcontainers)
- [ ] Smoke test after every deployment (automated)
- [ ] Rollback test validated in staging

### CD / GitOps
- [ ] GitOps repo structure: app manifests separate from infra
- [ ] ArgoCD/Flux sync health visible in pipeline
- [ ] Progressive delivery: Argo Rollouts with metric-based analysis
- [ ] Multi-environment promotion with manual gate for production

### Observability
- [ ] DORA metrics collected (deployment frequency, lead time, MTTR, CFR)
- [ ] Pipeline failure alerts → Slack / PagerDuty
- [ ] Build time tracked per stage (detect regressions)
- [ ] Full audit log: who deployed, when, what SHA, to where

---

## MCP Server Tools

Context-optimized CI/CD MCP server in `scripts/cicd_mcp_server.py`:

| Tool | Purpose |
|------|---------|
| `pipeline_status` | Check pipeline run status across CI platforms |
| `validate_config` | Lint and validate CI YAML/Groovy configs for errors |
| `security_audit` | Audit pipeline files for security anti-patterns |
| `generate_workflow` | Generate workflow YAML for given platform + tier |
| `dora_metrics` | Calculate DORA metrics from deployment history |

Setup: `pip install fastmcp httpx pyyaml`
Start: `python scripts/cicd_mcp_server.py` (stdio transport)

---

## Reference Files

| File | Contents | Grep For |
|------|----------|----------|
| `references/ci-platforms.md` | GitHub Actions, GitLab CI, Jenkins, Azure DevOps, CircleCI, Bitbucket | `on:`, `stage:`, `pipeline`, `steps:` |
| `references/cd-platforms.md` | ArgoCD, Flux, Spinnaker, Harness, Argo Rollouts | `Application`, `Kustomization`, `canary` |
| `references/pipeline-patterns.md` | Build, cache, artifact, matrix, parallel patterns | `cache`, `matrix`, `artifact`, `parallel` |
| `references/security-scanning.md` | SAST, DAST, SCA, container scan, signing, SBOM | `semgrep`, `trivy`, `cosign`, `sbom` |
| `references/testing-strategies.md` | Unit, integration, E2E, smoke, load, chaos | `testcontainers`, `k3d`, `playwright`, `k6` |
| `references/environment-strategies.md` | Env promotion, feature flags, canary, blue-green | `promote`, `canary`, `blue-green`, `gate` |
| `references/microservices-patterns.md` | Matrix builds, change detection, service graphs | `matrix`, `changes`, `depends_on`, `affected` |
| `references/agentic-patterns.md` | AI agent pipelines, model eval, safety, regression | `model`, `eval`, `safety`, `llm`, `agent` |
| `references/secrets-management.md` | OIDC, Vault, AWS/GCP/Azure KMS, scanning | `oidc`, `vault`, `secretsmanager`, `keyvault` |
| `references/anti-patterns.md` | Common CI/CD mistakes and production pitfalls | check before delivery |

> Search within large references: `grep -n "keyword" references/ci-platforms.md`

## Asset Templates

| Template | Purpose |
|----------|---------|
| `assets/templates/github_actions_base.yml` | Standard GitHub Actions CI/CD workflow |
| `assets/templates/github_actions_microservices.yml` | Matrix build for microservices monorepo |
| `assets/templates/gitlab_ci_base.yml` | GitLab CI multi-stage pipeline |
| `assets/templates/jenkins_pipeline.groovy` | Jenkins Declarative Pipeline (Tier 3) |
| `assets/templates/azure_devops_pipeline.yml` | Azure Pipelines multi-stage YAML |
| `assets/templates/argocd_application.yaml` | ArgoCD Application with sync policy |
| `assets/templates/flux_kustomization.yaml` | Flux Kustomization + ImagePolicy |
| `assets/templates/pre_commit_config.yaml` | Pre-commit hooks (lint, format, secrets) |
| `assets/templates/makefile_ci.mk` | Makefile targets mirroring CI stages |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scaffold_cicd.py` | Generate full project: `--tier 1\|2\|3\|4\|5 --ci --cd --cloud --security --project-type` |
| `scripts/cicd_mcp_server.py` | MCP server: pipeline_status, validate, audit, generate, dora_metrics |

## Official Documentation

| Resource | URL | Use For |
|----------|-----|---------|
| GitHub Actions | https://docs.github.com/en/actions | Workflow syntax, contexts, OIDC |
| GitLab CI | https://docs.gitlab.com/ee/ci/ | .gitlab-ci.yml reference |
| Jenkins Pipelines | https://www.jenkins.io/doc/book/pipeline/ | Declarative pipeline syntax |
| Azure DevOps Pipelines | https://learn.microsoft.com/en-us/azure/devops/pipelines/ | YAML schema, tasks |
| CircleCI Docs | https://circleci.com/docs/ | Orbs, executor config, DLC |
| ArgoCD | https://argo-cd.readthedocs.io/ | Application CRDs, sync policies |
| Flux | https://fluxcd.io/docs/ | Kustomization, HelmRelease, ImagePolicy |
| Argo Rollouts | https://argoproj.github.io/rollouts/ | Canary, blue-green, AnalysisTemplate |
| Trivy | https://aquasecurity.github.io/trivy/ | Container, IaC, SBOM scanning |
| Cosign / Sigstore | https://docs.sigstore.dev/ | Keyless image signing |
| OWASP ZAP | https://www.zaproxy.org/docs/ | DAST automation |
| GitHub OIDC | https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments | Keyless cloud auth |

Last verified: February 2026.
When CI platform syntax changes: update `references/ci-platforms.md` action versions and syntax.
For patterns not in references, fetch from official documentation URLs above.
