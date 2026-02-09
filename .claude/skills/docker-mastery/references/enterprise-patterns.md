# Enterprise Patterns

Production-grade container patterns for Google/Meta scale:
10K+ images, 100K+ pulls/day, multi-region, compliance-driven environments.

---

## Multi-Arch Builds

### Multi-Node Builder Setup

```bash
# Create multi-node buildx builder with dedicated nodes per architecture
docker buildx create --name enterprise-builder \
  --driver docker-container --platform linux/amd64 \
  --node amd64-node --config /etc/buildkit/buildkitd.toml
docker buildx create --name enterprise-builder --append \
  --platform linux/arm64 --node arm64-node ssh://builder@arm64-host.internal
docker buildx create --name enterprise-builder --append \
  --platform linux/arm/v7 --node armv7-node ssh://builder@armv7-host.internal
docker buildx use enterprise-builder && docker buildx inspect --bootstrap
```

### Platform Matrix Build

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  --tag registry.internal/myapp:v1.4.0 --push \
  --cache-from type=registry,ref=registry.internal/myapp:cache \
  --cache-to type=registry,ref=registry.internal/myapp:cache,mode=max \
  --sbom=true --provenance=mode=max .
```

### QEMU vs Native Builders

| Approach       | Build Speed  | Fidelity | Setup Complexity |
|----------------|--------------|----------|------------------|
| QEMU emulation | 3-10x slower | Good     | Low (single host)|
| Native builders| Native speed | Perfect  | High (per-arch)  |
| Hybrid (mix)   | Balanced     | Perfect  | Medium           |

Use QEMU for infrequent arm/v7; native nodes for amd64/arm64 where volume justifies hardware.

### Buildx Bake Multi-Arch

```hcl
# docker-bake.hcl
group "default" { targets = ["app", "worker", "migrator"] }

target "platforms" { platforms = ["linux/amd64", "linux/arm64"] }

target "app" {
  inherits   = ["platforms"]
  context    = "./services/app"
  dockerfile = "Dockerfile"
  tags       = ["registry.internal/app:${TAG}"]
  cache-from = ["type=registry,ref=registry.internal/app:cache"]
  cache-to   = ["type=registry,ref=registry.internal/app:cache,mode=max"]
  args       = { GO_VERSION = "1.22" }
}
target "worker" {
  inherits = ["platforms"]
  context  = "./services/worker"
  tags     = ["registry.internal/worker:${TAG}"]
}
target "migrator" {
  inherits = ["platforms"]
  context  = "./services/migrator"
  tags     = ["registry.internal/migrator:${TAG}"]
}
```

```bash
TAG=v1.4.0 docker buildx bake --push
```

---

## Registry Architecture

### Harbor Components (v2.11+)

| Component  | Role                                    |
|------------|-----------------------------------------|
| Core       | API server, UI, project/user management |
| Registry   | OCI distribution backend (stores blobs) |
| Jobservice | Async tasks: replication, GC, scanning  |
| Trivy      | Vulnerability scanning (replaces Clair) |
| Notary     | Content trust / image signing           |

### harbor-values.yaml (Key Settings)

```yaml
expose:
  type: ingress
  tls: { enabled: true, certSource: secret, secret: { secretName: harbor-tls } }
  ingress: { hosts: { core: registry.company.com }, className: nginx }
persistence:
  enabled: true
  resourcePolicy: "keep"
  persistentVolumeClaim:
    registry: { storageClass: gp3-encrypted, size: 2Ti }
    database: { storageClass: gp3-encrypted, size: 100Gi }
database:
  type: external
  external:
    host: harbor-pg.cluster-xyz.us-east-1.rds.amazonaws.com
    port: "5432"
    sslmode: verify-full
trivy: { enabled: true, autoScan: true }
# Robot accounts: POST /api/v2.0/robots with project-scoped push/pull
```

### Project Organization

```
registry.company.com/
  platform/        # Base images (platform team owned)
  team-payments/   # Team-scoped project
  team-search/     # Team-scoped project
  public-mirror/   # Proxy cache for upstream images
```

Robot accounts: one per CI pipeline, scoped to single project, `push`+`pull` only.

### Replication and Garbage Collection

```yaml
# Push-based replication to secondary region
source: registry.us-east.company.com/platform/*
destination: registry.eu-west.company.com/platform/*
trigger: on_push
filters: [{ tag: "v*" }, { label: "approved=true" }]
```

Schedule GC off-peak (Sunday 02:00 UTC), `--delete-untagged`, 72-hour grace period.

---

## Supply Chain Security

### SLSA Level 3 Pipeline

Requires: hermetic builds, authenticated provenance, non-falsifiable metadata, isolated build environments.

```
Source ──► Hermetic Build ──► Attest (SLSA) ──► Sign (Cosign) ──► Verify ──► Admit (K8s)
  │            │                   │                │               │            │
tag push  BuildKit sandbox     in-toto          Sigstore       OPA/Kyverno   Webhook
(signed)  (no network)        provenance       transparency    policy eval    admission
```

### Build + Attest + Sign

```bash
# Step 1: Hermetic build (no network access)
docker buildx build --network=none \
  --platform linux/amd64,linux/arm64 \
  --tag registry.internal/app:${GIT_SHA} --push \
  --provenance=mode=max --sbom=true .

# Step 2: Sign with Cosign (keyless via Fulcio + Rekor)
cosign sign --yes --rekor-url=https://rekor.sigstore.dev \
  registry.internal/app@sha256:${DIGEST}

# Step 3: Attach SLSA provenance and SBOM attestations
cosign attest --yes --predicate provenance.json --type slsaprovenance \
  registry.internal/app@sha256:${DIGEST}
cosign attach sbom --sbom sbom.spdx.json \
  registry.internal/app@sha256:${DIGEST}
```

### In-Toto Attestation (SLSA v1)

```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [{ "name": "registry.internal/app", "digest": { "sha256": "abc123..." } }],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://github.com/slsa-framework/slsa-github-generator",
      "externalParameters": { "source": { "uri": "git+https://...", "digest": { "sha1": "..." } } }
    },
    "runDetails": {
      "builder": { "id": "https://github.com/slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml" }
    }
  }
}
```

### Verify at Admission (Kyverno)

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-slsa-provenance
spec:
  validationFailureAction: Enforce
  rules:
    - name: check-signature-and-provenance
      match:
        any: [{ resources: { kinds: ["Pod"] } }]
      verifyImages:
        - imageReferences: ["registry.internal/*"]
          attestors:
            - entries:
                - keyless:
                    issuer: "https://token.actions.githubusercontent.com"
                    subject: "https://github.com/myorg/*"
                    rekor: { url: https://rekor.sigstore.dev }
          attestations:
            - type: slsaprovenance
              conditions:
                - all:
                    - key: "{{ buildDefinition.buildType }}"
                      operator: Equals
                      value: "https://github.com/slsa-framework/*"
```

### GCP Binary Authorization

```bash
gcloud container binauthz attestors create slsa-attestor \
  --attestation-authority-note=projects/${PROJECT}/notes/slsa-note \
  --attestation-authority-note-project=${PROJECT}
gcloud container binauthz policy import policy.yaml
```

---

## Compliance Frameworks

### Control-to-Implementation Mapping

| Compliance Control                   | Docker Implementation                                     |
|--------------------------------------|-----------------------------------------------------------|
| **SOC 2 - CC6.1** Access Control     | Registry RBAC, robot accounts, namespace isolation        |
| **SOC 2 - CC7.2** System Monitoring  | Container runtime audit (Falco), registry audit logs      |
| **SOC 2 - CC6.7** Data Encryption    | TLS for registry transport, encrypted PVCs at rest        |
| **HIPAA** - PHI Isolation            | Dedicated node pools, network policies, encrypted volumes |
| **HIPAA** - Audit Trails             | Immutable logs to WORM storage (S3 Object Lock)           |
| **HIPAA** - Access Logging           | Registry pull/push audit to SIEM, kubectl audit policy    |
| **PCI-DSS 6.3** Vuln Management     | Trivy scan-on-push, block Critical/High in admission      |
| **PCI-DSS 1.3** Network Segmentation| Calico/Cilium network policies, service mesh mTLS         |
| **PCI-DSS 10.2** Audit Logging       | Falco + Fluentd to tamper-proof log aggregation           |
| **FedRAMP** - Boundary Protection    | Air-gapped registries, FIPS-validated crypto in images    |
| **FedRAMP** - Config Management      | Immutable images, no shell/package-manager in prod        |

### Runtime Compliance (Falco)

```yaml
- rule: Unexpected Spawned Process
  desc: Detect process not in allowed list
  condition: spawned_process and container and not proc.name in (allowed_processes)
  output: "Unexpected process (user=%user.name cmd=%proc.cmdline container=%container.name)"
  priority: WARNING
  tags: [soc2, cc7.2]
```

### Key Requirements by Framework

- **HIPAA**: Read-only container FS, PHI to encrypted PVCs, zero-trust network policies, 7-day Critical CVE SLA
- **PCI-DSS**: No Critical/High CVE in prod (admission webhook enforced), signed images, MFA registry access
- **FedRAMP**: Air-gapped registries, FIPS crypto, no shells/package-managers in production images

---

## Platform Engineering

### Golden Dockerfiles

Platform team maintains blessed base images with security hardening, observability, and compliance built in.

```dockerfile
FROM python:3.12-slim-bookworm AS platform-python
LABEL maintainer="platform-team@company.com"
LABEL com.company.base-image="true"
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && apt-get update && apt-get install -y --no-install-recommends \
       ca-certificates curl tini \
    && apt-get purge -y --auto-remove && rm -rf /var/lib/apt/lists/*
COPY --from=datadog/serverless-init:1 /datadog-init /usr/local/bin/datadog-init
RUN rm -f /usr/bin/apt* /usr/bin/dpkg* /bin/sh || true
ENTRYPOINT ["tini", "--"]
USER appuser
WORKDIR /app
```

### Base Image Pipeline

```
Upstream release ──► Platform CI builds golden image ──► Trivy scan ──► Cosign sign
    ──► Publish registry.internal/platform/python:3.12-YYYYMMDD
    ──► Renovate/Dependabot opens PRs in downstream repos ──► Teams merge + rebuild
```

### Developer Self-Service (Backstage)

```yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata: { name: python-service, title: Python Microservice }
spec:
  parameters:
    - title: Service Configuration
      properties:
        serviceName: { type: string }
        team: { type: string, enum: [payments, search, platform] }
        needsDatabase: { type: boolean, default: false }
  steps:
    - id: fetch-skeleton
      action: fetch:template
      input:
        url: ./skeleton
        values:
          name: ${{ parameters.serviceName }}
          baseImage: registry.internal/platform/python:3.12-latest
    - id: publish
      action: publish:github
      input: { repoUrl: "github.com?owner=myorg&repo=${{ parameters.serviceName }}" }
```

Teams get a repo pre-wired with golden Dockerfile, CI pipeline, Helm chart, and observability.
Renovate PRs auto-merge when CI passes, keeping all services on latest patched base.

---

## Cost Optimization

### Image Size Budgets

| Language / Runtime | Target     | Max Allowed | Strategy                          |
|--------------------|------------|-------------|-----------------------------------|
| Go (static binary) | 10-20 MB   | 50 MB       | `scratch` or `distroless`         |
| Rust               | 10-30 MB   | 50 MB       | `scratch` or `distroless`         |
| Python             | 80-150 MB  | 250 MB      | `slim-bookworm` + venv copy       |
| Node.js            | 100-180 MB | 300 MB      | `alpine` + prod deps only         |
| Java (GraalVM)     | 50-100 MB  | 150 MB      | Native image on `distroless`      |
| Java (JVM)         | 200-300 MB | 400 MB      | `eclipse-temurin` + jlink         |
| .NET               | 80-150 MB  | 250 MB      | `runtime-deps` + trimmed publish  |

```bash
# CI enforcement
MAX_SIZE_MB=250
ACTUAL=$(docker image inspect myapp:latest --format '{{.Size}}' | awk '{print int($1/1048576)}')
[ "$ACTUAL" -gt "$MAX_SIZE_MB" ] && echo "FAIL: ${ACTUAL}MB > ${MAX_SIZE_MB}MB budget" && exit 1
```

### Build Cache (Registry + S3)

```bash
# Registry-backed cache (preferred for CI)
docker buildx build \
  --cache-from type=registry,ref=registry.internal/cache/app:main \
  --cache-to type=registry,ref=registry.internal/cache/app:main,mode=max \
  --tag registry.internal/app:${SHA} --push .
# S3-backed cache (air-gapped environments)
docker buildx build \
  --cache-from type=s3,region=us-east-1,bucket=buildcache,name=app \
  --cache-to type=s3,region=us-east-1,bucket=buildcache,name=app,mode=max .
```

### Egress and Storage Reduction

- Geo-local registry mirrors per region eliminate cross-region egress
- Proxy cache for Docker Hub reduces pulls and avoids rate limits
- Retention policy: keep last 10 semver tags, 5 SHA tags, delete untagged after 14 days
- Estimate: 10K images x 200MB avg = 2TB; S3 at $0.023/GB = ~$46/month base storage

---

## Disaster Recovery

### Registry Backup

- **Blob storage**: S3 cross-region replication for registry backend
- **Metadata DB**: Daily RDS snapshots or pg_dump of Harbor database
- **Config as code**: Registry config, policies, robot accounts in Git (Terraform/Pulumi)
- **RTO target**: < 1 hour from cross-region replica

### Image Promotion Workflow

```
dev (auto on merge)  ──►  staging (QA approval)  ──►  prod (release approval)
Gate: CI green + Trivy    Gate: QA sign-off +         Immutable semver tag
      clean + SLSA              security review +     Digest-pinned in manifests
      attestation               change ticket
```

### Immutable Tags and Rollback

```yaml
# Harbor: tag immutability for semver
immutable_tag_rules:
  - repo_matching: "**"
    tag_matching: "v*"  # v1.4.0 can never be overwritten
# Kubernetes: always pin to digest
containers:
  - name: app
    image: registry.prod/app@sha256:a1b2c3d4e5f6...
```

Rollback: identify last-known-good digest from ArgoCD/Flux/Helm history, update manifest
via GitOps merge, verify health checks. Tag bad image `revoked-YYYYMMDD`; do not delete.

---

## Scale Patterns

### 10K+ Images, 100K+ Pulls/Day

- **Horizontal scaling**: 3+ Harbor core replicas; 5+ registry replicas with shared S3 backend
- **Read replicas**: Read-only mirrors per AZ; write to primary, replication fans out in seconds
- **Connection pooling**: PgBouncer in front of Harbor metadata DB for concurrent pull spikes
- **Rate limiting**: Per-project pull rate limits (1000 pulls/min) to prevent CI pipeline saturation

### P2P Image Distribution

- **Dragonfly (CNCF Incubating)**: DaemonSet-based; nodes share layers P2P. 60-80% egress reduction.
  Configure containerd to use Dragonfly as mirror with registry fallback.
- **Uber Kraken**: Origin-based P2P with tracker nodes. Built for 10K+ node clusters;
  sub-minute distribution of 1GB images.

### Multi-Cluster Distribution

```
              Source Registry (us-east)
          push-based replication to regions
         ┌──────────┼──────────┐
         ▼          ▼          ▼
    eu-west     ap-east     us-west     ← regional replicas
    Cluster A   Cluster C   Cluster E   ← nodes pull from local registry
    Cluster B   Cluster D   Cluster F      + P2P (Dragonfly) within cluster
```

Nodes pull from regional registry first with source fallback. Combined with in-cluster
P2P, this sustains 100K+ pulls/day with minimal cross-region bandwidth.
