# Registry Management

## Docker Hub

Docker Hub is the default public registry. Organizations group repositories under a shared namespace.

```bash
docker login -u <username> --password-stdin <<< "$DOCKER_HUB_TOKEN"
docker tag myapp:latest myorg/myapp:v1.2.3
docker push myorg/myapp:v1.2.3
```

**Rate limits** by account tier:
- Anonymous: 100 pulls per 6 hours (by source IP)
- Authenticated (free): 200 pulls per 6 hours
- Pro/Team/Business: unlimited pulls

**Naming conventions**: lowercase, hyphens over underscores, include purpose (`myorg/api-gateway`, `myorg/worker-email`).

**Automated builds** from GitHub/Bitbucket are deprecated (June 2023). Use GitHub Actions or other CI pipelines instead.

Create **access tokens** at Hub > Account Settings > Security with scoped permissions (read, write, delete) rather than sharing credentials.

## Amazon ECR

ECR provides private registries per AWS account per region.

```bash
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
aws ecr create-repository --repository-name myapp --image-tag-mutability IMMUTABLE
```

**Lifecycle policies** automate cleanup:

```json
{"rules": [
  {"rulePriority": 1, "selection": {"tagStatus": "untagged", "countType": "sinceImagePushed", "countUnit": "days", "countNumber": 14}, "action": {"type": "expire"}},
  {"rulePriority": 2, "selection": {"tagStatus": "tagged", "tagPrefixList": ["v"], "countType": "imageCountMoreThan", "countNumber": 20}, "action": {"type": "expire"}}
]}
```

**Cross-account access**: repository policy granting `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage` to the target account principal.

**Replication**: replicate across regions or accounts via `aws ecr put-replication-configuration`.

**Image scanning**: basic scanning uses Clair (free); enhanced scanning integrates Amazon Inspector for OS and language-package vulnerabilities.

**Pull-through cache**: proxy Docker Hub to avoid rate limits: `aws ecr create-pull-through-cache-rule --ecr-repository-prefix docker-hub --upstream-registry-url registry-1.docker.io`.

## Google Artifact Registry

Artifact Registry replaces GCR and supports Docker, Maven, npm, Python, and more.

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
gcloud artifacts repositories create myrepo \
  --repository-format=docker --location=us-central1 --description="Production images"
docker tag myapp:latest us-central1-docker.pkg.dev/my-project/myrepo/myapp:v1.2.3
docker push us-central1-docker.pkg.dev/my-project/myrepo/myapp:v1.2.3
```

**IAM permissions**: `roles/artifactregistry.reader` for pull, `roles/artifactregistry.writer` for push. Use service accounts for CI/CD.

**Vulnerability scanning** via Container Analysis runs on push. Query: `gcloud artifacts docker images list --show-occurrences`.

**Binary Authorization** enforces deploy-time attestation, ensuring only signed and scanned images reach GKE.

**Cleanup policies**: `gcloud artifacts repositories set-cleanup-policies myrepo --location=us-central1 --policy=policy.json` -- delete images by age, tag status, or version count.

**Multi-region**: create repositories in `us`, `europe`, or `asia` locations for low-latency global pulls.

## Azure ACR

Azure Container Registry integrates deeply with the Azure ecosystem.

```bash
az acr create --name myregistry --resource-group mygroup --sku Premium
az acr login --name myregistry
az acr build --registry myregistry --image myapp:v1.2.3 .
```

**Geo-replication** distributes images across regions:

```bash
az acr replication create --registry myregistry --location westeurope
az acr replication create --registry myregistry --location southeastasia
```

**ACR Tasks** build images in the cloud, triggered by commits, base image updates, or schedules -- no local Docker needed.

**Content trust** (Notary v2): `az acr config content-trust update --registry myregistry --status enabled`.

**Retention policies**: `az acr config retention update --registry myregistry --status enabled --days 7 --type UntaggedManifests`.

**Connected registries** synchronize images to on-premises or edge locations for air-gapped and IoT scenarios.

## Harbor

Harbor is an open-source registry adding security, scanning, and policy management.

```bash
helm repo add harbor https://helm.goharbor.io && helm repo update
helm install harbor harbor/harbor \
  --namespace harbor --create-namespace \
  --set expose.type=ingress \
  --set expose.ingress.hosts.core=registry.example.com \
  --set externalURL=https://registry.example.com \
  --set persistence.persistentVolumeClaim.registry.size=100Gi \
  --set harborAdminPassword=changeme
```

**Project management**: projects group repositories with per-project access control, vulnerability allow lists, and tag retention. Projects can be public or private.

**Replication rules** synchronize images between Harbor instances or external registries (Docker Hub, ECR, GCR, ACR) via push-based or pull-based replication with tag/repository filters.

```yaml
# Pull replication from Docker Hub
Source: docker.io/library/nginx
Trigger: Scheduled (every 6 hours)
Filter: tag matching "1.*-alpine"
Destination: harbor-project/nginx
```

**Trivy integration**: embedded scanner runs on push or on demand. Project-level CVE allow lists suppress accepted vulnerabilities; policies block pulls of images with critical CVEs.

**Robot accounts** provide scoped, time-limited credentials for CI/CD:

```bash
curl -X POST "https://registry.example.com/api/v2.0/robots" \
  -H "Content-Type: application/json" \
  -d '{"name":"ci-pusher","duration":-1,"level":"project","permissions":[{"namespace":"myproject","access":[{"resource":"repository","action":"push"},{"resource":"repository","action":"pull"}]}]}'
```

**Quotas and retention**: per-project storage quotas and tag retention rules (keep most recent N tags, expire the rest).

## GitHub Container Registry (GHCR)

GHCR hosts container images alongside source code with GitHub-native access control.

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u <username> --password-stdin
docker tag myapp:latest ghcr.io/<owner>/myapp:v1.2.3
docker push ghcr.io/<owner>/myapp:v1.2.3
```

**Visibility**: default private; public packages get free unlimited storage and pulls. Private counts against GitHub storage allowances.

**Link to repos** with the OCI label so packages inherit repository permissions:

```dockerfile
LABEL org.opencontainers.image.source="https://github.com/owner/repo"
```

In GitHub Actions, use `GITHUB_TOKEN` for authentication -- no PAT required.

## Tagging Strategy

```bash
# Semver tags for releases
docker tag myapp:build-abc123 myorg/myapp:v1.2.3
docker tag myapp:build-abc123 myorg/myapp:1.2
docker tag myapp:build-abc123 myorg/myapp:1
# Git SHA tag for traceability
docker tag myapp:build-abc123 myorg/myapp:sha-abc123f
# Mutable branch tag for dev environments
docker tag myapp:build-abc123 myorg/myapp:main
```

**Immutable vs mutable**: semver (`v1.2.3`) and SHA tags must never be overwritten. Branch tags (`main`, `develop`) are mutable and repointed on each build.

**Digest pinning** for production guarantees exact image content regardless of tag changes:

```yaml
image: myorg/myapp@sha256:a1b2c3d4e5f6...
```

**Never use `latest` in production**: it is mutable, unpredictable, and makes rollbacks impossible.

Recommended CI pattern: push both a semver tag and a git SHA tag on release, branch tag on every commit.

## Retention & Cleanup

Unmanaged registries accumulate stale images that waste storage and expand the attack surface.

**Garbage collection** reclaims storage from deleted manifests:

```bash
# Self-hosted Docker Distribution registry
docker exec -it registry bin/registry garbage-collect /etc/docker/registry/config.yml --delete-untagged
```

**Retention policy template**:

| Rule | Scope | Action |
|------|-------|--------|
| Keep last 10 tagged | Tags matching `v*` | Retain |
| Expire untagged after 7 days | Untagged manifests | Delete |
| Expire dev tags after 30 days | Tags `dev-*`, `pr-*` | Delete |
| Keep 3 per semver minor | Tags `v1.2.*` | Retain newest 3 |

**Storage optimization**: multi-stage builds reduce image size; share base layers across images; audit with `crane manifest` to find bloated layers.
