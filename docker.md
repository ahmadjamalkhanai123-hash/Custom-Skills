# Docker Mastery Skill — Full Specification

> Enterprise-grade Docker skill covering everything from `hello-world` to
> Google/Meta-scale container orchestration. Builder type, production-ready,
> designed for any dimension of containerization work.

---

## 1. Skill Identity

| Field | Value |
|-------|-------|
| **Name** | `docker-mastery` |
| **Type** | Builder (creates production Docker artifacts) |
| **Location** | `.claude/skills/docker-mastery/` |
| **Target Score** | 93-97/100 (Production grade) |
| **Lines Budget** | SKILL.md ~450 lines (under 500 limit) |
| **Description** | Creates production-ready Docker images, Compose stacks, and enterprise container architectures — from single-container hello-world to Google/Meta-scale orchestrated platforms with supply-chain security, multi-arch builds, and zero-downtime deployments. |

---

## 2. What This Skill Covers (Dimensions)

### Dimension 1 — Basics (Hello World → Single App)
- Writing Dockerfiles from scratch (any language/runtime)
- Image building, tagging, pushing to registries
- Container lifecycle (run, stop, restart, logs, exec)
- Volume mounts, port mapping, environment variables
- .dockerignore best practices
- Understanding layers, caching, build context

### Dimension 2 — Intermediate (Multi-Container → Development)
- Docker Compose for multi-service stacks
- Networking (bridge, host, overlay, custom networks)
- Named volumes and bind mounts for persistence
- Multi-stage builds for size optimization
- Build arguments (ARG) vs runtime environment (ENV)
- Health checks and restart policies
- Docker init for scaffolding

### Dimension 3 — Production (Hardened → Scalable)
- Distroless and minimal base images (Alpine, scratch, Chainguard)
- Non-root user execution and read-only filesystems
- Image scanning (Trivy, Grype, Snyk)
- Layer optimization (sub-50MB production images)
- BuildKit features (cache mounts, secrets, SSH forwarding)
- Docker Content Trust (DCT) and image signing (Cosign/Sigstore)
- Container resource limits (CPU, memory, PID, ulimits)
- Logging drivers (json-file, fluentd, Loki)
- Graceful shutdown (SIGTERM handling, PID 1 problem)

### Dimension 4 — Enterprise (Google/Meta Scale)
- Multi-arch builds (linux/amd64, linux/arm64, linux/arm/v7)
- Private registry architecture (Harbor, Artifactory, ECR/GCR/ACR)
- Supply chain security (SBOM generation, SLSA provenance, in-toto attestations)
- Rootless Docker and user namespace remapping
- Content-addressable storage and layer deduplication at scale
- Moby BuildKit distributed builds
- OCI image spec compliance and custom annotations
- Container runtime selection (containerd, cri-o, gVisor, Kata Containers)
- Sysdig Falco runtime security monitoring
- eBPF-based network policies and observability
- GitOps-driven image promotion pipelines (dev → staging → prod)
- Canary and blue-green deployments with container orchestrators
- Compliance frameworks (SOC 2, HIPAA, PCI-DSS container controls)
- Platform engineering (Internal Developer Platform with Docker)

---

## 3. Tier System (Decision Tree)

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
| Base Image | Official | Official/Alpine | Distroless/Chainguard | Custom + Signed |
| Build | `docker build` | `docker compose build` | BuildKit + CI | Multi-arch + Distributed |
| Registry | Docker Hub | Docker Hub/Private | Private (Harbor/ECR) | Federated + Geo-replicated |
| Security | Basic | Non-root + .dockerignore | Scanning + DCT + Secrets | SBOM + SLSA + Runtime |
| Networking | Port mapping | Compose networks | Overlay + DNS | Service mesh + eBPF |
| Storage | Bind mounts | Named volumes | CSI drivers | Distributed (Ceph/EBS) |
| Monitoring | `docker logs` | Log drivers | Prometheus + Loki | Full observability stack |
| Deploy | Manual | Compose up | CI/CD pipeline | GitOps + Canary |
| Complexity | Low | Medium | High | Very High |
| Best for | Learning, dev | Small teams | Production apps | Google/Meta scale |

---

## 4. Complete Skill Structure

```
.claude/skills/docker-mastery/
├── SKILL.md                              ← Main skill (≤500 lines)
├── references/
│   ├── dockerfile-patterns.md            ← Dockerfile best practices per language
│   ├── compose-patterns.md               ← Compose v2 patterns and networking
│   ├── multi-stage-builds.md             ← Size optimization, cache strategies
│   ├── security-hardening.md             ← Non-root, scanning, signing, secrets
│   ├── enterprise-patterns.md            ← Multi-arch, supply chain, compliance
│   ├── registry-management.md            ← Harbor, ECR/GCR/ACR, geo-replication
│   ├── networking-storage.md             ← Network drivers, volume strategies
│   ├── observability.md                  ← Logging, metrics, health checks
│   ├── ci-cd-integration.md             ← GitHub Actions, GitLab CI, Jenkins
│   ├── runtime-security.md              ← Falco, gVisor, seccomp, AppArmor
│   ├── performance-optimization.md       ← Layer caching, BuildKit, build speed
│   └── anti-patterns.md                  ← 20+ common Docker mistakes with fixes
├── assets/
│   └── templates/
│       ├── dockerfile_python.Dockerfile  ← Production Python (multi-stage + distroless)
│       ├── dockerfile_node.Dockerfile    ← Production Node.js (multi-stage + alpine)
│       ├── dockerfile_go.Dockerfile      ← Production Go (scratch final stage)
│       ├── dockerfile_rust.Dockerfile    ← Production Rust (scratch final stage)
│       ├── dockerfile_java.Dockerfile    ← Production Java (JRE distroless)
│       ├── compose_full_stack.yml        ← Complete app + DB + cache + proxy stack
│       ├── compose_dev.yml               ← Dev override with hot reload
│       ├── docker_bake.hcl              ← BuildKit bake for multi-target builds
│       ├── harbor_values.yaml           ← Harbor Helm chart values (enterprise)
│       └── github_actions_docker.yml     ← CI/CD pipeline: build, scan, sign, push
└── scripts/
    └── scaffold_docker.py                ← Generate Docker setup for any project
```

**Total: ~22 files, estimated ~4500-5000 lines**

---

## 5. SKILL.md Content Blueprint

The main SKILL.md file (~450 lines) contains:

### Section 1: Frontmatter + Identity (lines 1-10)
```yaml
---
name: docker-mastery
description: |
  Creates production-ready Docker images, Compose stacks, and enterprise container
  architectures — from single-container apps to platform-scale systems with
  supply-chain security, multi-arch builds, and zero-downtime deployments.
  This skill should be used when users want to containerize applications, create
  Docker Compose stacks, optimize images, harden container security, set up
  registries, or architect enterprise container platforms.
---
```

### Section 2: What This Skill Does / Does NOT Do (lines 12-35)

**Does:**
- Creates Dockerfiles for any language/framework (Python, Node, Go, Rust, Java, .NET)
- Generates Docker Compose stacks for multi-service architectures
- Implements multi-stage builds with sub-50MB production images
- Configures security hardening (non-root, scanning, signing, SBOM)
- Sets up multi-arch builds (amd64 + arm64)
- Architects private registry systems (Harbor, cloud-native registries)
- Generates CI/CD pipelines for build → scan → sign → push → deploy
- Implements supply chain security (SLSA provenance, in-toto attestations)
- Creates development environments with hot-reload and debugging

**Does NOT:**
- Manage Kubernetes clusters (scaffolds K8s-compatible images only)
- Provision cloud infrastructure (AWS, GCP, Azure)
- Build CI/CD platforms (generates pipeline configs only)
- Manage DNS, SSL certificates, or domain routing
- Create application code (only containerizes existing code)
- Deploy to production (generates deployment artifacts only)

### Section 3: Before Implementation / Context Gathering (lines 37-55)

| Source | Gather |
|--------|--------|
| **Codebase** | Language/framework, existing Dockerfile, .dockerignore, package files |
| **Conversation** | What to containerize, scale needs, security requirements |
| **Skill References** | Patterns from `references/` for the appropriate tier |
| **User Guidelines** | Registry target, CI/CD platform, compliance requirements |

### Section 4: Required Clarifications (lines 57-100)

1. **Application Type**: "What are you containerizing?"
   - Web application (Python/Node/Go/Rust/Java)
   - CLI tool or utility
   - Multi-service stack (app + DB + cache + proxy)
   - Machine learning / GPU workload
   - Platform / Internal Developer Platform

2. **Tier**: "What scale?"
   - Single container (learning, dev, simple deployment)
   - Compose stack (multi-service local/staging)
   - Production (hardened, CI/CD, private registry)
   - Enterprise (multi-arch, supply chain, compliance)

3. **Language/Runtime**: Auto-detect from codebase or ask
4. **Registry Target**: Docker Hub (default), ECR, GCR, ACR, Harbor, GHCR
5. **CI/CD Platform**: GitHub Actions (default), GitLab CI, Jenkins, CircleCI

**Defaults Table:**

| Clarification | Default |
|---------------|---------|
| Tier | Single Container (Tier 1) |
| Base Image | Language-appropriate official image |
| Final Stage | Distroless (Tier 3+), Alpine (Tier 2), Official (Tier 1) |
| Registry | Docker Hub |
| CI/CD | GitHub Actions |
| Architecture | linux/amd64 (multi-arch at Tier 4) |
| User | Non-root (UID 1001) |
| Health Check | Included from Tier 2+ |

### Section 5: Dockerfile Decision Tree (lines 102-140)

```
Language detected?

Python?
  → Multi-stage: python:3.12-slim → build deps → distroless/python3
  → Template: assets/templates/dockerfile_python.Dockerfile
  → Ref: references/dockerfile-patterns.md#python

Node.js?
  → Multi-stage: node:22-alpine → build → node:22-alpine (prod deps only)
  → Template: assets/templates/dockerfile_node.Dockerfile
  → Ref: references/dockerfile-patterns.md#nodejs

Go?
  → Multi-stage: golang:1.23 → build → scratch (static binary)
  → Template: assets/templates/dockerfile_go.Dockerfile
  → Ref: references/dockerfile-patterns.md#go

Rust?
  → Multi-stage: rust:1.80 → build → scratch or distroless
  → Template: assets/templates/dockerfile_rust.Dockerfile
  → Ref: references/dockerfile-patterns.md#rust

Java?
  → Multi-stage: eclipse-temurin:21-jdk → build → distroless/java21
  → Template: assets/templates/dockerfile_java.Dockerfile
  → Ref: references/dockerfile-patterns.md#java
```

### Section 6: Workflow (lines 142-220)

```
Tier → Dockerfile → Compose (if needed) → Security → CI/CD → Registry → Deploy
```

**Step 1: Select Tier** — Use decision tree, read relevant references.

**Step 2: Generate Dockerfile**
- Read `references/dockerfile-patterns.md` for language-specific patterns
- Read `references/multi-stage-builds.md` for optimization
- Apply tier-appropriate base image and final stage

**Step 3: Generate Compose (Tier 2+)**
- Read `references/compose-patterns.md`
- Add services, networks, volumes, health checks
- Create dev override file for hot-reload

**Step 4: Apply Security Hardening (Tier 3+)**
- Read `references/security-hardening.md`
- Non-root user, read-only filesystem, dropped capabilities
- Image scanning integration (Trivy)
- Docker Content Trust / Cosign signing

**Step 5: Generate CI/CD Pipeline (Tier 3+)**
- Read `references/ci-cd-integration.md`
- Build → Test → Scan → Sign → Push workflow
- Multi-arch manifest creation (Tier 4)

**Step 6: Registry Configuration (Tier 3+)**
- Read `references/registry-management.md`
- Authentication, retention policies, vulnerability scanning

### Section 7: Output Specification (lines 222-270)

Every generated Docker setup includes:

**Tier 1 Output:**
- [ ] Dockerfile with appropriate base image
- [ ] .dockerignore (language-specific)
- [ ] Build and run commands documented

**Tier 2 Output (includes Tier 1 +):**
- [ ] docker-compose.yml with all services
- [ ] docker-compose.override.yml for development
- [ ] Named volumes for persistence
- [ ] Custom network with service DNS
- [ ] Health checks on all services
- [ ] .env.example with all variables

**Tier 3 Output (includes Tier 2 +):**
- [ ] Multi-stage Dockerfile (build → test → production)
- [ ] Non-root user execution
- [ ] Read-only root filesystem where possible
- [ ] Trivy scan integration
- [ ] Image signing configuration
- [ ] CI/CD pipeline file
- [ ] Structured logging configuration
- [ ] Resource limits (CPU, memory)

**Tier 4 Output (includes Tier 3 +):**
- [ ] Multi-arch build configuration (docker buildx bake)
- [ ] SBOM generation (syft/docker sbom)
- [ ] SLSA provenance attestation
- [ ] Harbor/registry Helm values
- [ ] GitOps promotion pipeline
- [ ] Runtime security policy (Falco rules)
- [ ] Compliance documentation
- [ ] Platform engineering templates

### Section 8: Domain Standards (lines 272-320)

**Must Follow:**
- [ ] One process per container (PID 1 best practices)
- [ ] Multi-stage builds (never ship build tools in production)
- [ ] Non-root execution (USER directive, UID ≥ 1000)
- [ ] Specific image tags (never use `:latest` in production)
- [ ] .dockerignore before every build context
- [ ] COPY over ADD (unless tar extraction needed)
- [ ] Combine RUN commands to minimize layers
- [ ] Order layers by change frequency (dependencies before code)
- [ ] Use HEALTHCHECK for all long-running containers
- [ ] LABEL for image metadata (OCI annotations)
- [ ] Handle SIGTERM gracefully (exec form CMD/ENTRYPOINT)
- [ ] Pin package versions in package manager installs
- [ ] Clean package manager caches in same RUN layer

**Must Avoid:**
- Running as root in production containers
- Using `:latest` tag in production deployments
- Storing secrets in image layers (use BuildKit secrets or runtime injection)
- Installing unnecessary packages (curl, vim, etc. in production)
- Using ADD for remote URLs (use curl/wget + verify checksum)
- Hardcoding configuration in Dockerfile (use ENV + config files)
- Ignoring .dockerignore (bloated build context, leaked secrets)
- Using VOLUME in Dockerfile for production (declare in Compose)
- Committing node_modules, __pycache__, .git to image
- Using docker commit for production images

### Section 9: Error Handling (lines 322-350)

| Scenario | Detection | Action |
|----------|-----------|--------|
| Build fails on dependency install | Exit code ≠ 0 on RUN | Check base image compatibility, pin versions |
| Image too large (>500MB) | `docker images` size check | Switch to multi-stage, use Alpine/distroless |
| Container exits immediately | Exit code inspection | Check CMD/ENTRYPOINT exec form, PID 1 |
| Permission denied at runtime | Log inspection | Verify USER directive, file ownership |
| Port already in use | Compose error | Use different host port mapping |
| Health check failing | `docker inspect` health status | Verify endpoint, add startup grace period |
| Secrets leaked in layer | `docker history` inspection | Use BuildKit --mount=type=secret |
| Build cache not working | Slow rebuilds | Reorder COPY layers, use cache mounts |
| OOM killed | Container restart + OOMKilled flag | Set appropriate memory limits |
| Network connectivity issues | Container-to-container DNS | Check network attachment, service names |

### Section 10: Output Checklist (lines 352-410)

**Architecture:**
- [ ] Tier appropriate for requirements
- [ ] Multi-stage build (Tier 2+)
- [ ] Compose for multi-service (Tier 2+)
- [ ] CI/CD pipeline (Tier 3+)
- [ ] Multi-arch support (Tier 4)

**Image Quality:**
- [ ] Final image < 100MB (language-dependent)
- [ ] No unnecessary packages in production stage
- [ ] Specific base image tags with digest
- [ ] Layer count minimized
- [ ] Build cache optimized

**Security:**
- [ ] Non-root user (Tier 2+)
- [ ] No secrets in layers
- [ ] .dockerignore comprehensive
- [ ] Scanning integrated (Tier 3+)
- [ ] Signing configured (Tier 3+)
- [ ] SBOM generated (Tier 4)
- [ ] Read-only filesystem where feasible

**Operations:**
- [ ] Health checks configured
- [ ] Graceful shutdown handling
- [ ] Resource limits set (Tier 3+)
- [ ] Logging configured (stdout/stderr)
- [ ] .env.example with all variables
- [ ] Restart policies defined

**Documentation:**
- [ ] Build instructions in comments or README
- [ ] LABEL metadata (maintainer, version, description)
- [ ] Environment variable documentation

### Section 11: Reference Files Table + Scripts + Templates (lines 412-450)

---

## 6. Reference Files — Content Specification

### `references/dockerfile-patterns.md` (~250 lines)
Complete Dockerfile patterns for 6 languages:
- **Python**: pip/uv/poetry multi-stage, Gunicorn/Uvicorn entrypoint, distroless final
- **Node.js**: npm/pnpm/yarn multi-stage, PM2 or node entrypoint, Alpine final
- **Go**: CGO_ENABLED=0 static binary, scratch final, minimal attack surface
- **Rust**: cargo-chef for caching, scratch/distroless final
- **Java**: Maven/Gradle build, JLink custom JRE, distroless/java final
- **General**: ARG/ENV patterns, ENTRYPOINT+CMD combo, HEALTHCHECK per language

### `references/compose-patterns.md` (~200 lines)
- Compose file v3.8+ / Compose Specification
- Service dependency ordering (depends_on with health conditions)
- Network isolation (frontend/backend network separation)
- Volume management (named vs bind, tmpfs)
- Environment management (.env, env_file, variable substitution)
- Profiles for optional services
- Development override files (compose.override.yml)
- GPU passthrough for ML workloads
- Complete full-stack examples: app + postgres + redis + nginx

### `references/multi-stage-builds.md` (~180 lines)
- Stage naming and referencing (`FROM ... AS builder`)
- Cache mount patterns (`--mount=type=cache,target=/root/.cache`)
- BuildKit secret mounts (`--mount=type=secret,id=npmrc`)
- SSH forwarding for private dependencies
- Conditional stages with build arguments
- Size comparison tables (standard vs optimized)
- Layer analysis with `docker history` and `dive`
- Build matrix with `docker buildx bake`

### `references/security-hardening.md` (~300 lines)
- **Base Image Selection**: Official → Alpine → Distroless → Scratch → Chainguard decision tree
- **User Configuration**: Creating non-root users, file ownership, capability dropping
- **Filesystem**: Read-only root, tmpfs for writable paths, no-new-privileges
- **Secret Management**: BuildKit secrets, Docker secrets (Swarm), runtime injection patterns
- **Image Scanning**: Trivy CLI integration, severity thresholds, ignore files
- **Image Signing**: Docker Content Trust (DCT), Cosign/Sigstore, verification policies
- **SBOM**: Syft generation, SPDX/CycloneDX formats, dependency tracking
- **SLSA**: Provenance attestation, builder identity, supply chain levels
- **Runtime Security**: seccomp profiles, AppArmor policies, Linux capabilities
- **Network Security**: No privileged ports, internal-only networks

### `references/enterprise-patterns.md` (~350 lines)
- **Multi-arch Builds**: buildx create (multi-node builder), platform matrix, manifest lists
- **Registry Architecture**: Harbor deployment, geo-replication, project quotas, robot accounts
- **Supply Chain**: Complete SLSA Level 3 pipeline, in-toto layout, policy enforcement (OPA/Kyverno)
- **Compliance**: SOC 2 controls mapping, HIPAA container requirements, PCI-DSS image standards
- **Platform Engineering**: Golden Dockerfiles, base image management, developer self-service
- **Cost Optimization**: Image size budgets, registry storage costs, build time optimization
- **Disaster Recovery**: Registry backup, image promotion, rollback strategies
- **Scale Patterns**: 10K+ images, 100K+ pulls/day, multi-cluster distribution

### `references/registry-management.md` (~180 lines)
- Docker Hub: organizations, access tokens, rate limits, automated builds
- ECR: lifecycle policies, cross-account access, replication, scanning
- GCR/Artifact Registry: IAM, vulnerability scanning, binary authorization
- ACR: geo-replication, tasks, content trust
- Harbor: installation, project management, replication rules, Trivy integration
- GHCR: packages, visibility, token auth
- Retention policies, garbage collection, storage optimization

### `references/networking-storage.md` (~200 lines)
- **Network Drivers**: bridge (default), host, overlay, macvlan, none
- **DNS Resolution**: Container name discovery, custom DNS, external DNS
- **Service Mesh**: Traefik, nginx-proxy, Consul Connect patterns
- **Storage Drivers**: overlay2 (recommended), device-mapper, btrfs
- **Volume Types**: named volumes, bind mounts, tmpfs, NFS, CIFS
- **Volume Drivers**: local, NFS, cloud (EBS, Azure Disk, GCE PD)
- **Backup/Restore**: Volume backup patterns, data migration between hosts

### `references/observability.md` (~180 lines)
- **Logging**: JSON logging to stdout/stderr, fluentd driver, Loki integration
- **Metrics**: Container metrics (cAdvisor), custom Prometheus endpoints, Grafana dashboards
- **Health Checks**: HTTP, TCP, CMD health checks, startup probes, timing configuration
- **Tracing**: OpenTelemetry auto-instrumentation, Jaeger/Zipkin integration
- **Alerts**: Container restart alerts, resource threshold alerts, image vulnerability alerts

### `references/ci-cd-integration.md` (~250 lines)
- **GitHub Actions**: Complete workflow (build, test, scan, sign, push, deploy)
- **GitLab CI**: Pipeline stages, Docker-in-Docker, Kaniko builder
- **Jenkins**: Declarative pipeline, Docker agents, registry credentials
- **General**: Tagging strategy (semver, git SHA, branch), cache optimization, parallel builds
- **Multi-arch CI**: Matrix builds, QEMU emulation, native builders
- **Promotion Pipeline**: dev → staging → production with approval gates

### `references/runtime-security.md` (~200 lines)
- **Container Isolation**: namespaces, cgroups v2, seccomp profiles
- **Runtime Monitoring**: Falco rules for Docker, anomaly detection
- **gVisor**: Installation, runsc configuration, performance tradeoffs
- **Kata Containers**: VM-based isolation, when to use
- **Rootless Docker**: Installation, limitations, user namespace mapping
- **Podman**: Drop-in replacement, daemonless architecture, rootless by default
- **eBPF**: Cilium for network policies, Tetragon for runtime enforcement

### `references/performance-optimization.md` (~180 lines)
- **Build Speed**: BuildKit parallelism, cache mounts, remote cache (registry/S3)
- **Image Size**: Layer analysis tools (dive, docker-slim), minification strategies
- **Runtime Performance**: CPU pinning, NUMA awareness, huge pages
- **I/O Optimization**: Storage driver selection, volume mount performance, overlay2 tuning
- **Network**: Host networking for max throughput, MTU optimization
- **Benchmarking**: container-benchmark-tool, sysbench in containers

### `references/anti-patterns.md` (~250 lines)
20+ common Docker mistakes with before/after fixes:
1. Running as root
2. Using `:latest` in production
3. Fat images with build tools
4. Secrets in ENV/ARG
5. Single layer RUN with apt-get
6. No .dockerignore
7. ADD instead of COPY
8. Not handling PID 1/signals
9. No health checks
10. Hardcoded configs
11. Installing unnecessary tools
12. Not pinning versions
13. Ignoring build cache order
14. docker commit for images
15. Privileged containers
16. Mounting Docker socket
17. Not cleaning apt/pip cache
18. Using VOLUME in Dockerfile
19. No resource limits
20. Ignoring image scanning results

---

## 7. Asset Templates — Content Specification

### `assets/templates/dockerfile_python.Dockerfile`
```dockerfile
# Production Python multi-stage build
# Tier 3+ pattern: build deps → distroless runtime
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src/ ./src/

FROM gcr.io/distroless/python3-debian12:nonroot
WORKDIR /app
COPY --from=builder /app/.venv/lib /usr/local/lib
COPY --from=builder /app/src ./src
EXPOSE 8000
USER nonroot
HEALTHCHECK --interval=30s --timeout=3s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
ENTRYPOINT ["python", "-m", "src.main"]
```

### `assets/templates/dockerfile_node.Dockerfile`
Production Node.js with npm ci, Alpine final, non-root.

### `assets/templates/dockerfile_go.Dockerfile`
Static binary build, scratch final, zero dependencies.

### `assets/templates/dockerfile_rust.Dockerfile`
cargo-chef for layer caching, scratch final stage.

### `assets/templates/dockerfile_java.Dockerfile`
Maven/Gradle build, JLink custom JRE, distroless final.

### `assets/templates/compose_full_stack.yml`
Complete stack: app + PostgreSQL + Redis + Nginx reverse proxy + monitoring.

### `assets/templates/compose_dev.yml`
Development override: hot reload, debug ports, volume mounts, log verbosity.

### `assets/templates/docker_bake.hcl`
BuildKit bake file for multi-target, multi-arch, cached builds.

### `assets/templates/harbor_values.yaml`
Harbor Helm chart values for enterprise registry deployment.

### `assets/templates/github_actions_docker.yml`
Complete CI/CD: lint Dockerfile → build → test → scan (Trivy) → sign (Cosign) → push → deploy.

---

## 8. Scaffold Script — `scripts/scaffold_docker.py`

```
Usage:
  python scaffold_docker.py <project-name> \
    --tier <1|2|3|4> \
    --lang <python|node|go|rust|java> \
    --path <output-dir> \
    [--registry <dockerhub|ecr|gcr|acr|harbor|ghcr>] \
    [--ci <github|gitlab|jenkins|none>] \
    [--compose] \
    [--multi-arch]
```

**Generates:**
- Tier 1: Dockerfile + .dockerignore
- Tier 2: + docker-compose.yml + compose.override.yml + .env.example
- Tier 3: + CI/CD pipeline + Trivy config + signing config
- Tier 4: + bake.hcl + harbor values + SBOM config + Falco rules

---

## 9. How This Skill Would Be Created

### Creation Process (following skill-creator-pro patterns)

**Phase 1: Context Gathering**
- Analyze Docker official documentation (docs.docker.com)
- Study Dockerfile best practices from Docker, Google, Chainguard
- Review enterprise patterns from CNCF, NIST container security guide
- Examine real-world Dockerfiles from major open source projects
- Study supply chain security frameworks (SLSA, in-toto, Sigstore)

**Phase 2: Skill Architecture**
- Design 4-tier system (basics → intermediate → production → enterprise)
- Map reference files to tiers (which refs needed at which tier)
- Design language-specific decision tree
- Create template matrix (language x tier)

**Phase 3: SKILL.md Writing**
- Write within 500-line budget using progressive disclosure
- Embed Docker expertise in decision trees and defaults
- Reference files for deep domain knowledge (not in SKILL.md)
- Include clarifications, output spec, domain standards, checklist

**Phase 4: Reference Files**
- 12 reference files covering every Docker dimension
- Each file self-contained with runnable examples
- Anti-patterns file with before/after fixes
- Enterprise patterns with compliance mapping

**Phase 5: Templates + Scripts**
- 10 asset templates (5 language Dockerfiles + 2 Compose + bake + harbor + CI)
- Scaffold script generates per-tier project structure
- All templates production-ready (not toy examples)

**Phase 6: Validation**
- Run through skill-validator (target 93+ score)
- Verify zero-shot capability (no external knowledge needed)
- Test all tiers produce working artifacts
- Validate enterprise patterns against CNCF/NIST guidelines

### Expected Validation Score Breakdown

| Category | Weight | Expected Score | Notes |
|----------|--------|----------------|-------|
| Structure & Organization | 10% | 9.5/10 | 4-tier, decision trees, progressive disclosure |
| Content Quality & Depth | 15% | 14/15 | 12 reference files, enterprise depth |
| User Interaction Flow | 10% | 9/10 | Clarifications, defaults table, before-asking rules |
| Documentation Standards | 10% | 9.5/10 | Does/Does NOT, output spec, checklist |
| Domain Standards Compliance | 15% | 14/15 | OCI spec, CNCF patterns, NIST guidelines |
| Technical Robustness | 15% | 14/15 | Error handling, 20+ anti-patterns |
| Maintainability | 10% | 9/10 | Modular refs, versioned templates |
| Zero-Shot Implementation | 10% | 9.5/10 | All expertise embedded, no external deps |
| Reusability | 5% | 4.5/5 | Any language, any tier, any scale |
| **Total** | **100%** | **~93-95/100** | **Production grade** |

---

## 10. What Makes This Enterprise-Grade (Google/Meta Level)

### Why Google/Meta Would Need This Skill

| Capability | Google/Meta Requirement | How Skill Handles It |
|------------|------------------------|---------------------|
| **Multi-arch** | arm64 for custom silicon (TPU hosts, Graviton) | Tier 4 buildx bake with platform matrix |
| **Supply Chain** | SLSA Level 3+ for all production images | SBOM + provenance + attestation pipeline |
| **Scale** | 100K+ images, millions of pulls/day | Registry federation, geo-replication, CDN |
| **Compliance** | SOC 2, FedRAMP, GDPR for container controls | Compliance mapping in enterprise-patterns.md |
| **Security** | Zero-trust container runtime | gVisor/Kata + Falco + eBPF policies |
| **Speed** | Sub-minute builds for developer iteration | BuildKit cache mounts + remote cache + parallelism |
| **Platform** | Internal Developer Platform for 10K+ engineers | Golden Dockerfiles, base image management |
| **Cost** | Minimize registry storage and egress costs | Image size budgets, layer dedup, retention policies |
| **Reliability** | Zero-downtime deployments, instant rollback | Canary + blue-green + immutable image tags |
| **Observability** | Full container lifecycle visibility | OpenTelemetry + Prometheus + Loki + Falco |

### Key Differentiators from Basic Docker Skills

1. **Not just Dockerfiles** — Full container lifecycle from build to runtime security
2. **Not just `docker run`** — CI/CD pipelines, registry architecture, GitOps
3. **Not just single-arch** — Multi-architecture builds for heterogeneous infrastructure
4. **Not just scanning** — Full supply chain security (SBOM, SLSA, attestations)
5. **Not just containers** — Platform engineering patterns for developer self-service
6. **Not just Docker** — Awareness of containerd, Podman, gVisor, Kata alternatives
7. **Not just Linux** — Awareness of Windows containers and cross-platform builds

---

## 11. Comparison with Existing Skills

| Aspect | fastapi-forge | hybrid-sdk-agents | docker-mastery |
|--------|---------------|-------------------|----------------|
| Tiers | 3 | N/A (SDK-based) | 4 |
| References | 10 | 9 | 12 |
| Templates | 5 | 8 | 10 |
| Scripts | 1 | 1 | 1 |
| Total Files | ~17 | ~19 | ~24 |
| Total Lines | ~3,664 | ~4,108 | ~4,500-5,000 |
| Scope | FastAPI apps | AI agents | Container lifecycle |
| Enterprise | Tier 3 | Hybrid combos | Tier 4 (supply chain + compliance) |

---

## 12. Official Documentation Sources

| Resource | URL | Use For |
|----------|-----|---------|
| Docker Docs | https://docs.docker.com | Core reference |
| Dockerfile Reference | https://docs.docker.com/reference/dockerfile/ | Instruction syntax |
| Compose Specification | https://docs.docker.com/compose/compose-file/ | Compose file format |
| BuildKit | https://docs.docker.com/build/buildkit/ | Advanced build features |
| Docker Scout | https://docs.docker.com/scout/ | Vulnerability scanning |
| Chainguard Images | https://images.chainguard.dev | Hardened base images |
| Sigstore/Cosign | https://docs.sigstore.dev | Image signing |
| SLSA Framework | https://slsa.dev | Supply chain levels |
| Harbor | https://goharbor.io/docs/ | Enterprise registry |
| Trivy | https://aquasecurity.github.io/trivy/ | Image scanning |
| Falco | https://falco.org/docs/ | Runtime security |
| OCI Image Spec | https://github.com/opencontainers/image-spec | Container standards |
| NIST SP 800-190 | NIST website | Container security guide |

---

## Summary

**docker-mastery** is a 4-tier Builder skill (~24 files, ~5,000 lines) that takes users
from writing their first Dockerfile to architecting enterprise container platforms
at Google/Meta scale. It embeds the full spectrum of Docker expertise — from image
layer mechanics to supply chain attestations — following the same proven patterns as
fastapi-forge and hybrid-sdk-agents but with the added Tier 4 for true enterprise
compliance and platform engineering.

The skill is zero-shot (all Docker expertise embedded in references), progressive
(tiers scale with user needs), and production-validated (patterns sourced from OCI
specs, CNCF guidelines, and NIST container security standards).
