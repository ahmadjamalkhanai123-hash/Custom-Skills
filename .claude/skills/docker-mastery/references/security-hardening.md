# Security Hardening

Production Docker security from image build through runtime enforcement.

---

## Base Image Selection

```
Need a full package manager?
  YES → Official image (debian-slim, ubuntu)
  NO  → Need a shell for debugging?
          YES → Alpine (musl libc, ~5MB)
          NO  → Is it a compiled binary (Go, Rust)?
                  YES → Scratch (0MB, zero attack surface)
                  NO  → Need glibc runtime (Java, Python, Node)?
                          YES → Distroless (Google, ~2-20MB)
                          NO  → Chainguard (signed, SBOMs, ~5-15MB)
```

| Base Image       | Size  | CVEs (typical) | Shell | Use Case                  |
|------------------|-------|----------------|-------|---------------------------|
| ubuntu:24.04     | ~78MB | 10-30          | Yes   | Development, legacy deps  |
| debian:bookworm-slim | ~52MB | 5-20       | Yes   | Production with apt needs |
| alpine:3.20      | ~5MB  | 0-5            | Yes   | Small images, shell access|
| gcr.io/distroless/static | ~2MB | 0-1    | No    | Go/Rust static binaries   |
| gcr.io/distroless/java21 | ~20MB | 0-3   | No    | JVM applications          |
| cgr.dev/chainguard/python | ~15MB | 0-1   | No    | Python, supply chain focus|
| scratch          | 0MB   | 0              | No    | Static binaries only      |

Start with Distroless or Chainguard. Fall back to Alpine only when you need a shell.

```dockerfile
# Preferred: multi-stage with Distroless
FROM python:3.12-slim AS builder
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt

FROM gcr.io/distroless/python3-debian12
COPY --from=builder /app/deps /app/deps
COPY src/ /app/src/
ENV PYTHONPATH=/app/deps
ENTRYPOINT ["python", "/app/src/main.py"]
```

---

## User Configuration

Never run containers as root. Create a dedicated user with fixed UID 1001.

```dockerfile
# Debian / Ubuntu
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/false --create-home appuser
COPY --chown=appuser:appgroup ./app /home/appuser/app
USER 1001

# Alpine
RUN addgroup -g 1001 -S appgroup && \
    adduser -u 1001 -S -G appgroup -s /sbin/nologin appuser
COPY --chown=appuser:appgroup ./app /home/appuser/app
USER 1001

# Distroless (nonroot user is built in)
FROM gcr.io/distroless/static:nonroot
COPY --chown=65532:65532 myapp /app/myapp
USER 65532
```

- Use numeric UID in `USER` directive -- Kubernetes `runAsUser` matches on UID.
- Set `--shell /bin/false` or `/sbin/nologin` to prevent interactive login.
- Use `--chown` on `COPY` to avoid extra `RUN chown` layers.

---

## Filesystem Hardening

```bash
# Docker run: read-only root with tmpfs for writable paths
docker run --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges:true myapp
```

```yaml
# Docker Compose equivalent
services:
  api:
    image: myapp:latest
    read_only: true
    tmpfs:
      - /tmp:size=64m,noexec,nosuid
      - /var/run:size=16m
      - /var/log/app:size=32m
    security_opt:
      - no-new-privileges:true
```

The `no-new-privileges` flag prevents privilege escalation via setuid/setgid binaries. Enable on every production container.

---

## Secret Management

### What NOT To Do

```dockerfile
# NEVER -- secrets persist in image layers and history
ENV DATABASE_URL=postgres://user:pass@host/db
ARG API_KEY=sk-secret-key
COPY .env /app/.env
```

### BuildKit Secrets (Build Time)

```dockerfile
# syntax=docker/dockerfile:1
RUN --mount=type=secret,id=pip_index_url \
    PIP_INDEX_URL=$(cat /run/secrets/pip_index_url) \
    pip install --no-cache-dir -r requirements.txt

RUN --mount=type=secret,id=github_token \
    GITHUB_TOKEN=$(cat /run/secrets/github_token) \
    git clone https://${GITHUB_TOKEN}@github.com/org/private-repo.git
```

```bash
DOCKER_BUILDKIT=1 docker build \
  --secret id=pip_index_url,src=.secrets/pip_index_url \
  --secret id=github_token,env=GITHUB_TOKEN \
  -t myapp .
```

### Docker Compose Secrets (Runtime)

```yaml
services:
  api:
    image: myapp:latest
    secrets: [db_password, api_key]
    environment:
      DB_PASSWORD_FILE: /run/secrets/db_password
secrets:
  db_password:
    file: ./secrets/db_password.txt
  api_key:
    file: ./secrets/api_key.txt
```

Application reads from `/run/secrets/<name>`:

```python
from pathlib import Path
def read_secret(name: str) -> str:
    return Path(f"/run/secrets/{name}").read_text().strip()
```

---

## Image Scanning

### Trivy CLI

```bash
trivy image --severity CRITICAL,HIGH --exit-code 1 myapp:latest
trivy image --format sarif --output trivy-results.sarif myapp:latest
trivy config --severity HIGH,CRITICAL Dockerfile      # misconfigurations
```

### False Positive Suppression (.trivyignore)

```
CVE-2024-12345    # does not apply: affected function not used
CVE-2024-67890    # disputed, no patch available
```

### CI Integration (GitHub Actions)

```yaml
- name: Scan image with Trivy
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
    format: sarif
    output: trivy-results.sarif
    severity: CRITICAL,HIGH
    exit-code: "1"
- name: Upload scan results
  uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: trivy-results.sarif
```

### Grype Alternative

```bash
grype myapp:latest --fail-on high
grype myapp:latest -o json > grype-results.json
```

---

## Image Signing

### Cosign Keyless Signing (Sigstore)

```bash
# Sign (uses OIDC identity, no key management)
cosign sign $REGISTRY/$IMAGE@$DIGEST

# Verify
cosign verify \
  --certificate-identity=user@example.com \
  --certificate-oidc-issuer=https://accounts.google.com \
  $REGISTRY/$IMAGE@$DIGEST
```

### GitHub Actions Integration

```yaml
- uses: sigstore/cosign-installer@v3
- name: Sign the container image
  run: cosign sign --yes ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}
```

### Docker Content Trust (DCT)

```bash
export DOCKER_CONTENT_TRUST=1
docker push myregistry/myapp:v1.2.3   # signs automatically
docker pull myregistry/myapp:v1.2.3   # verifies automatically
```

DCT uses Notary. Cosign with Sigstore is the modern replacement -- prefer it for new projects.

---

## SBOM Generation

### Syft

```bash
syft myapp:latest -o spdx-json > sbom-spdx.json       # SPDX format
syft myapp:latest -o cyclonedx-json > sbom-cdx.json    # CycloneDX format
syft dir:. -o spdx-json > sbom-source.json             # from build context
```

### Docker Native SBOM

```bash
docker sbom myapp:latest --format spdx-json > sbom.json
```

### Attaching SBOM to Image

```bash
cosign attest --predicate sbom-spdx.json --type spdxjson $REGISTRY/$IMAGE@$DIGEST

cosign verify-attestation --type spdxjson \
  --certificate-identity=user@example.com \
  --certificate-oidc-issuer=https://accounts.google.com \
  $REGISTRY/$IMAGE@$DIGEST
```

---

## SLSA Provenance

| Level | Requirement                          | What It Proves                   |
|-------|--------------------------------------|----------------------------------|
| L1    | Build process documented             | Source and build metadata exist  |
| L2    | Signed provenance from hosted build  | Build ran on a known CI system   |
| L3    | Hardened build platform              | Build cannot be tampered with    |

### GitHub Actions SLSA Generator

```yaml
- name: Generate SLSA provenance
  uses: slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml@v2.1.0
  with:
    image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
    digest: ${{ needs.build.outputs.digest }}
  secrets:
    registry-username: ${{ github.actor }}
    registry-password: ${{ secrets.GITHUB_TOKEN }}
```

### Verifying Provenance

```bash
slsa-verifier verify-image \
  --source-uri github.com/myorg/myrepo \
  --source-tag v1.2.3 \
  $REGISTRY/$IMAGE@$DIGEST
```

Target SLSA L2+ for production. GitHub Actions provides L3 with the official generator.

---

## Runtime Security

### Linux Capabilities

```bash
# Drop ALL, add only what is needed
docker run --cap-drop ALL --cap-add NET_BIND_SERVICE myapp:latest

# Common minimal sets:
# Web server:       NET_BIND_SERVICE
# Ping/healthcheck: NET_RAW
# Chown files:      CHOWN,DAC_OVERRIDE
# Workers:          none (--cap-drop ALL only)
```

### Seccomp Profiles

```bash
docker run --security-opt seccomp=default myapp:latest          # default (~44 blocked syscalls)
docker run --security-opt seccomp=custom-seccomp.json myapp     # custom profile
```

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [{
    "names": ["read","write","open","close","stat","fstat","mmap",
              "mprotect","munmap","brk","exit_group","futex",
              "epoll_wait","accept4","socket","bind","listen"],
    "action": "SCMP_ACT_ALLOW"
  }]
}
```

### AppArmor

```bash
sudo apparmor_parser -r /etc/apparmor.d/docker-myapp
docker run --security-opt apparmor=docker-myapp myapp:latest
```

### Combined Hardening (Docker Compose)

```yaml
services:
  api:
    image: myapp:latest
    read_only: true
    user: "1001:1001"
    security_opt: [no-new-privileges:true, seccomp:custom-seccomp.json]
    cap_drop: [ALL]
    cap_add: [NET_BIND_SERVICE]
    tmpfs: ["/tmp:size=64m,noexec,nosuid"]
```

---

## Network Security

### Avoid Privileged Ports

```bash
# App listens on 8080 inside, mapped to 443 outside
docker run -p 443:8080 --cap-drop ALL myapp:latest
```

### Internal-Only Networks

```yaml
networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true          # no external internet access
services:
  api:
    networks: [frontend, backend]
  database:
    networks: [backend]     # only reachable from backend
```

### Inter-Container TLS

```yaml
services:
  api:
    volumes:
      - ./certs/api:/etc/ssl/app:ro
    environment:
      TLS_CERT: /etc/ssl/app/tls.crt
      TLS_KEY: /etc/ssl/app/tls.key
      TLS_CA: /etc/ssl/app/ca.crt
```

Use a service mesh (Linkerd, Istio) for automatic mTLS in orchestrated environments rather than managing certificates manually.
