---
name: docker-mastery
description: |
  Creates production-ready Docker images, Compose stacks, and enterprise container
  architectures from single-container apps to platform-scale systems with supply-chain
  security, multi-arch builds, and zero-downtime deployments.
  This skill should be used when users want to containerize applications, create
  Docker Compose stacks, optimize images, harden container security, set up CI/CD
  pipelines for containers, configure registries, or architect enterprise platforms.
---

# Docker Mastery

Build production-ready Docker containers — from hello-world to Google/Meta-scale platforms.

## What This Skill Does

- Creates Dockerfiles for any language (Python, Node, Go, Rust, Java, .NET)
- Generates Docker Compose stacks for multi-service architectures
- Implements multi-stage builds with optimized production images
- Configures security hardening (non-root, scanning, signing, SBOM)
- Sets up multi-arch builds (amd64 + arm64 + arm/v7)
- Architects private registry systems (Harbor, ECR, GCR, ACR, GHCR)
- Generates CI/CD pipelines for build → scan → sign → push → deploy
- Creates development environments with hot-reload and debugging
- Implements supply chain security (SLSA provenance, attestations)

## What This Skill Does NOT Do

- Manage Kubernetes clusters (scaffolds K8s-compatible images only)
- Provision cloud infrastructure (AWS, GCP, Azure)
- Build CI/CD platforms (generates pipeline configs only)
- Create application code (only containerizes existing code)
- Deploy to production (generates deployment artifacts only)
- Manage DNS, SSL, or domain routing

---

## Before Implementation

Gather context to ensure successful implementation:

| Source | Gather |
|--------|--------|
| **Codebase** | Language/framework, existing Dockerfile, .dockerignore, package files |
| **Conversation** | What to containerize, scale needs, security requirements |
| **Skill References** | Patterns from `references/` for the appropriate tier |
| **User Guidelines** | Registry target, CI/CD platform, compliance requirements |

Ensure all required context is gathered before implementing.
Only ask user for THEIR specific requirements (Docker expertise is in this skill).

---

## Required Clarifications

Before building, ask:

1. **Application Type**: "What are you containerizing?"
   - Web application (Python/Node/Go/Rust/Java/.NET)
   - CLI tool or batch processor
   - Multi-service stack (app + DB + cache + proxy)
   - Machine learning / GPU workload

2. **Scale Tier**: "What scale?"
   - Single container (dev, learning, simple deploy)
   - Compose stack (multi-service, local/staging)
   - Production (hardened, CI/CD, private registry)
   - Enterprise (multi-arch, supply chain, compliance)

## Optional Clarifications

3. **Language/Runtime**: Auto-detect from codebase or ask
4. **Registry**: Docker Hub (default), ECR, GCR, ACR, Harbor, GHCR
5. **CI/CD**: GitHub Actions (default), GitLab CI, Jenkins, CircleCI

Note: Start with questions 1-2. Follow up with 3-5 based on context.

### Defaults (If Not Specified)

| Clarification | Default |
|---------------|---------|
| Tier | Single Container (Tier 1) |
| Base Image | Language-appropriate official image |
| Final Stage | Official (T1), Alpine (T2), Distroless (T3+) |
| Registry | Docker Hub |
| CI/CD | GitHub Actions |
| Architecture | linux/amd64 (multi-arch at Tier 4) |
| User | Non-root (UID 1001) at Tier 2+ |
| Health Check | Included from Tier 2+ |
| Scanning | Trivy at Tier 3+ |
| Signing | Cosign at Tier 3+ |

### Before Asking

1. Check conversation history for prior answers
2. Infer from existing project files (Dockerfile, package.json, go.mod, pyproject.toml)
3. Only ask what cannot be determined from context

---

## Tier Selection Decision Tree

```
What's the primary need?

Single container for an app/service?
  → Tier 1: Single Container (references/dockerfile-patterns.md)

Multi-service stack with networking and persistence?
  → Tier 2: Compose Stack (references/compose-patterns.md)

Hardened production with CI/CD and registry?
  → Tier 3: Production (references/security-hardening.md)

Enterprise platform with supply chain + multi-arch + compliance?
  → Tier 4: Enterprise (references/enterprise-patterns.md)

Not sure?
  → Start Tier 1, scale up when needed
```

### Tier Comparison

| Factor | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|--------|--------|--------|--------|--------|
| Containers | 1 | 2-10 | 10-50 | 50+ |
| Base Image | Official | Alpine | Distroless/Chainguard | Custom + Signed |
| Build | docker build | compose build | BuildKit + CI | Multi-arch distributed |
| Registry | Docker Hub | Hub/Private | Private (Harbor/ECR) | Federated + geo-replicated |
| Security | Basic | Non-root + ignore | Scanning + DCT | SBOM + SLSA + Runtime |
| Networking | Port map | Compose networks | Overlay + DNS | Service mesh + eBPF |
| Monitoring | docker logs | Log drivers | Prometheus + Loki | Full observability |
| Deploy | Manual | compose up | CI/CD pipeline | GitOps + Canary |
| Best for | Learning/dev | Small teams | Production apps | Enterprise platforms |

---

## Workflow

```
Tier → Dockerfile → Compose (if needed) → Security → CI/CD → Registry → Deploy
```

### Step 1: Select Tier

Use decision tree above. Read the relevant reference files.

### Step 2: Generate Dockerfile

Read `references/dockerfile-patterns.md` for language-specific patterns.
Read `references/multi-stage-builds.md` for optimization.

**Language Decision Tree:**
```
Python?  → python:3.12-slim build → distroless/python3 final
Node.js? → node:22-alpine build → node:22-alpine prod-deps final
Go?      → golang:1.23 build → scratch (static binary)
Rust?    → rust:1.80 build → scratch or distroless
Java?    → eclipse-temurin:21-jdk build → distroless/java21 final
```

Use templates from `assets/templates/` as starting points.

### Step 3: Generate Compose (Tier 2+)

Read `references/compose-patterns.md`:
- Service definitions with health check conditions
- Network isolation (frontend/backend separation)
- Named volumes for persistence
- Dev override file for hot-reload

### Step 4: Apply Security (Tier 3+)

Read `references/security-hardening.md`:
- Non-root user (USER directive, UID ≥ 1000)
- Read-only root filesystem
- Dropped Linux capabilities
- Image scanning integration (Trivy)
- Image signing (Cosign/Sigstore)

### Step 5: Generate CI/CD (Tier 3+)

Read `references/ci-cd-integration.md`:
- Build → Test → Scan → Sign → Push workflow
- Multi-arch manifest creation (Tier 4)
- Cache optimization for fast builds

### Step 6: Configure Registry (Tier 3+)

Read `references/registry-management.md`:
- Authentication and access control
- Retention policies and garbage collection
- Vulnerability scanning integration

---

## Output Specification

### Tier 1 Output
- [ ] Dockerfile with appropriate base image and multi-stage build
- [ ] .dockerignore (language-specific)
- [ ] Build and run commands documented in comments

### Tier 2 Output (includes Tier 1 +)
- [ ] docker-compose.yml with all services
- [ ] docker-compose.override.yml for development
- [ ] Named volumes for persistence
- [ ] Custom network with service DNS
- [ ] Health checks on all services
- [ ] .env.example with all variables

### Tier 3 Output (includes Tier 2 +)
- [ ] Multi-stage Dockerfile (build → test → production)
- [ ] Non-root user execution
- [ ] Read-only root filesystem where possible
- [ ] Trivy scan configuration
- [ ] Cosign signing configuration
- [ ] CI/CD pipeline file (GitHub Actions / GitLab CI)
- [ ] Resource limits (CPU, memory)

### Tier 4 Output (includes Tier 3 +)
- [ ] Multi-arch build configuration (docker buildx bake)
- [ ] SBOM generation (syft / docker sbom)
- [ ] SLSA provenance attestation
- [ ] Harbor/registry deployment values
- [ ] GitOps promotion pipeline
- [ ] Runtime security policy (Falco rules)
- [ ] Compliance documentation mapping

---

## Domain Standards

### Must Follow

- [ ] One process per container (PID 1 best practices)
- [ ] Multi-stage builds (never ship build tools in production)
- [ ] Non-root execution at Tier 2+ (USER directive, UID ≥ 1000)
- [ ] Specific image tags (never `:latest` in production)
- [ ] .dockerignore before every build context
- [ ] COPY over ADD (unless tar extraction needed)
- [ ] Combine RUN commands to minimize layers
- [ ] Order layers by change frequency (deps before code)
- [ ] HEALTHCHECK for all long-running containers
- [ ] LABEL for OCI image metadata
- [ ] Exec form for CMD/ENTRYPOINT (signal handling)
- [ ] Pin package versions in installs
- [ ] Clean caches in same RUN layer

### Must Avoid

- Running as root in production
- `:latest` tag in production deployments
- Secrets in image layers (use BuildKit secrets or runtime injection)
- Unnecessary packages in production (curl, vim, etc.)
- ADD for remote URLs (use curl + checksum verification)
- Hardcoded configuration in Dockerfile
- Missing .dockerignore (bloated context, leaked secrets)
- VOLUME directive in Dockerfile for production
- Committing node_modules, __pycache__, .git into images
- docker commit for production images

---

## Error Handling

| Scenario | Detection | Action |
|----------|-----------|--------|
| Build fails on deps | Exit code ≠ 0 | Check base image compat, pin versions |
| Image too large (>500MB) | `docker images` size | Switch to multi-stage, Alpine/distroless |
| Container exits immediately | Exit code check | Verify CMD exec form, PID 1 handling |
| Permission denied at runtime | Log inspection | Verify USER directive, file ownership |
| Port already in use | Compose error | Use different host port mapping |
| Health check failing | `docker inspect` | Verify endpoint, add startup grace period |
| Secrets leaked in layer | `docker history` | Use BuildKit --mount=type=secret |
| Build cache not working | Slow rebuilds | Reorder COPY layers, use cache mounts |
| OOM killed | OOMKilled flag | Set appropriate memory limits |
| DNS resolution failure | Container networking | Check network attachment, service names |

---

## Output Checklist

Before delivering any Docker setup, verify ALL items:

### Architecture
- [ ] Tier appropriate for requirements
- [ ] Multi-stage build implemented
- [ ] Compose for multi-service (Tier 2+)
- [ ] CI/CD pipeline (Tier 3+)
- [ ] Multi-arch support (Tier 4)

### Image Quality
- [ ] Final image appropriately sized for language
- [ ] No build tools in production stage
- [ ] Specific base image tags (no `:latest`)
- [ ] Layer count minimized
- [ ] Build cache optimized (deps before code)

### Security
- [ ] Non-root user (Tier 2+)
- [ ] No secrets in image layers
- [ ] .dockerignore comprehensive
- [ ] Scanning integrated (Tier 3+)
- [ ] Signing configured (Tier 3+)
- [ ] SBOM generated (Tier 4)

### Operations
- [ ] Health checks configured
- [ ] Graceful shutdown (SIGTERM handling)
- [ ] Resource limits set (Tier 3+)
- [ ] Logging to stdout/stderr
- [ ] .env.example with all variables
- [ ] Restart policies defined

### Documentation
- [ ] Build/run instructions in Dockerfile comments
- [ ] LABEL metadata (maintainer, version, description)
- [ ] Environment variable documentation

---

## Reference Files

| File | When to Read |
|------|--------------|
| `references/dockerfile-patterns.md` | Dockerfile patterns for Python, Node, Go, Rust, Java |
| `references/compose-patterns.md` | Compose v2 service definitions, networking, volumes |
| `references/multi-stage-builds.md` | Size optimization, cache mounts, BuildKit features |
| `references/security-hardening.md` | Non-root, scanning, signing, SBOM, secrets management |
| `references/enterprise-patterns.md` | Multi-arch, supply chain, compliance, platform engineering |
| `references/registry-management.md` | Harbor, ECR, GCR, ACR, GHCR configuration |
| `references/networking-storage.md` | Network drivers, volume types, service mesh patterns |
| `references/observability.md` | Logging, metrics, health checks, tracing |
| `references/ci-cd-integration.md` | GitHub Actions, GitLab CI, Jenkins pipelines |
| `references/runtime-security.md` | Falco, gVisor, seccomp, AppArmor, rootless Docker |
| `references/performance-optimization.md` | Build speed, image size, runtime performance |
| `references/anti-patterns.md` | 20 common Docker mistakes with fixes |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scaffold_docker.py` | Generate Docker setup for any project. Usage: `python scaffold_docker.py <name> --tier <1\|2\|3\|4> --lang <python\|node\|go\|rust\|java> --path <dir> [--registry <hub\|ecr\|gcr\|acr\|harbor\|ghcr>] [--ci <github\|gitlab\|jenkins>] [--compose] [--multi-arch]` |

## Asset Templates

| Template | Purpose |
|----------|---------|
| `assets/templates/dockerfile_python.Dockerfile` | Production Python (multi-stage + uv + distroless) |
| `assets/templates/dockerfile_node.Dockerfile` | Production Node.js (multi-stage + Alpine) |
| `assets/templates/dockerfile_go.Dockerfile` | Production Go (static binary + scratch) |
| `assets/templates/dockerfile_rust.Dockerfile` | Production Rust (cargo-chef + scratch) |
| `assets/templates/dockerfile_java.Dockerfile` | Production Java (Maven + distroless JRE) |
| `assets/templates/compose_full_stack.yml` | Full stack: app + Postgres + Redis + Nginx |
| `assets/templates/compose_dev.yml` | Dev override: hot reload, debug ports, volumes |
| `assets/templates/docker_bake.hcl` | BuildKit bake for multi-target, multi-arch builds |
| `assets/templates/harbor_values.yaml` | Harbor Helm chart values for enterprise registry |
| `assets/templates/github_actions_docker.yml` | CI/CD: lint → build → scan → sign → push |

## Official Documentation

| Resource | URL | Use For |
|----------|-----|---------|
| Docker Docs | https://docs.docker.com | Core reference |
| Dockerfile Ref | https://docs.docker.com/reference/dockerfile/ | Instruction syntax |
| Compose Spec | https://docs.docker.com/compose/compose-file/ | Compose format |
| BuildKit | https://docs.docker.com/build/buildkit/ | Advanced builds |
| Docker Scout | https://docs.docker.com/scout/ | Vulnerability scanning |
| Chainguard | https://images.chainguard.dev | Hardened base images |
| Cosign | https://docs.sigstore.dev | Image signing |
| SLSA | https://slsa.dev | Supply chain levels |
| Harbor | https://goharbor.io/docs/ | Enterprise registry |
| Trivy | https://aquasecurity.github.io/trivy/ | Image scanning |

Last verified: February 2026.

For patterns not covered in references, fetch from official Docker documentation.
