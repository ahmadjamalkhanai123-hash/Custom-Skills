# Container Security (4C Layer 3)

## Hardened Dockerfile Patterns

### Python — Distroless Final Stage

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ────────────────────────────────────────────
FROM gcr.io/distroless/python3-debian12:nonroot AS production

# distroless:nonroot runs as UID 65532 (nonroot)
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
COPY --chown=65532:65532 src/ ./

# Immutable: no shell, no package manager, no debug tools
EXPOSE 8080

ENTRYPOINT ["/usr/bin/python3", "main.py"]
```

### Go — Scratch Final Stage (Smallest + Most Secure)

```dockerfile
FROM golang:1.23-alpine3.21 AS builder

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .

# Build with security flags:
# CGO_ENABLED=0: static binary (no libc dependency)
# -trimpath: remove local paths from binary
# -ldflags: strip debug symbols + version info
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -trimpath \
    -ldflags="-w -s -extldflags=-static" \
    -o /app/server ./cmd/server

# Verify binary (no vulnerabilities)
RUN go install golang.org/x/vuln/cmd/govulncheck@latest && \
    govulncheck ./...

# ────────────────────────────────────────────
FROM scratch AS production

# Import CA certificates for HTTPS
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Import non-root user (scratch has no /etc/passwd)
COPY --from=builder /etc/passwd /etc/passwd
COPY --from=builder /etc/group /etc/group

COPY --from=builder --chown=65534:65534 /app/server /server

USER 65534:65534              # nobody:nogroup

EXPOSE 8080

ENTRYPOINT ["/server"]
```

### Node.js — Distroless Final Stage

```dockerfile
FROM node:22-alpine3.21 AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production --frozen-lockfile && \
    npm audit --audit-level=high

FROM node:22-alpine3.21 AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ────────────────────────────────────────────
FROM gcr.io/distroless/nodejs22-debian12:nonroot AS production
WORKDIR /app

COPY --from=builder --chown=65532:65532 /app/dist ./dist
COPY --from=deps   --chown=65532:65532 /app/node_modules ./node_modules

EXPOSE 3000
CMD ["dist/index.js"]
```

---

## Image Scanning with Trivy

### CI Integration (Block on CRITICAL/HIGH)

```bash
#!/bin/bash
# trivy-scan.sh — fail build on CRITICAL or HIGH vulnerabilities

IMAGE=$1
REPORT_FILE="trivy-report.json"

# Full scan: OS + library vulnerabilities + secrets + misconfigurations
trivy image \
  --exit-code 1 \
  --severity CRITICAL,HIGH \
  --format json \
  --output "${REPORT_FILE}" \
  --ignore-unfixed \
  --scanners vuln,secret,misconfig \
  "${IMAGE}"

EXIT_CODE=$?

# Upload report to security dashboard
trivy image --format sarif --output trivy.sarif "${IMAGE}"

if [ $EXIT_CODE -ne 0 ]; then
  echo "SECURITY GATE FAILED: CRITICAL or HIGH vulnerabilities found"
  jq '.Results[].Vulnerabilities[] | select(.Severity == "CRITICAL" or .Severity == "HIGH") | {VulnerabilityID, PkgName, Severity, Title}' "${REPORT_FILE}"
  exit 1
fi

echo "Security scan passed"
```

### GitHub Actions Trivy Integration

```yaml
- name: Trivy Vulnerability Scan
  uses: aquasecurity/trivy-action@0.28.0
  with:
    image-ref: ${{ env.IMAGE_TAG }}
    format: sarif
    output: trivy-results.sarif
    severity: CRITICAL,HIGH
    exit-code: 1
    ignore-unfixed: true
    scanners: vuln,secret,misconfig

- name: Upload Trivy SARIF to GitHub Security
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: trivy-results.sarif
```

### .trivyignore — Accepted Risk Documentation

```
# CVE-2023-XXXXX — accepted, no fix available, mitigated by network isolation
# expires: 2025-12-31
# owner: security-team
CVE-2023-XXXXX
```

---

## seccomp Profiles

### RuntimeDefault (Tier 2+)

```yaml
# Apply in pod spec
securityContext:
  seccompProfile:
    type: RuntimeDefault
```

### Custom Restricted Profile (Tier 3-4)

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"],
  "syscalls": [
    {
      "names": [
        "accept4", "access", "arch_prctl", "bind", "brk",
        "clone", "clone3", "close", "connect", "dup", "dup2",
        "epoll_create1", "epoll_ctl", "epoll_pwait", "epoll_wait",
        "execve", "exit", "exit_group", "faccessat", "fchown",
        "fcntl", "fstat", "fstatfs", "futex", "getdents64",
        "getgid", "getpid", "getppid", "getuid", "ioctl",
        "lseek", "madvise", "memfd_create", "mmap", "mprotect",
        "munmap", "nanosleep", "newfstatat", "open", "openat",
        "pipe2", "poll", "ppoll", "prctl", "pread64", "pwrite64",
        "read", "readlink", "readlinkat", "recvfrom", "recvmsg",
        "rt_sigaction", "rt_sigprocmask", "rt_sigreturn",
        "sched_yield", "sendmsg", "sendto", "set_robust_list",
        "set_tid_address", "setgid", "setgroups", "setuid",
        "sigaltstack", "socket", "stat", "statfs", "statx",
        "tgkill", "uname", "unlink", "unlinkat", "wait4", "write",
        "writev"
      ],
      "action": "SCMP_ACT_ALLOW"
    },
    {
      "names": ["ptrace", "mount", "umount2", "unshare"],
      "action": "SCMP_ACT_ERRNO",
      "comment": "Deny container escape vectors"
    }
  ]
}
```

---

## AppArmor Profiles

```
# /etc/apparmor.d/container-default
#include <tunables/global>

profile container-default flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>

  # Allow network communication
  network inet  tcp,
  network inet  udp,
  network inet6 tcp,
  network inet6 udp,

  # Deny raw sockets (prevent network sniffing)
  deny network raw,
  deny network packet,

  # Allow read of standard paths
  /etc/              r,
  /etc/**            r,
  /usr/              r,
  /usr/**            r,
  /lib/              r,
  /lib/**            r,

  # Deny kernel module loading
  deny @{PROC}/sysrq-trigger rwklx,
  deny @{PROC}/mem            rwklx,
  deny @{PROC}/kmem           rwklx,
  deny @{PROC}/kcore          rwklx,

  # Deny write to /proc (prevent privilege escalation)
  deny @{PROC}/{[0-9],[0-9][0-9],[0-9][0-9][0-9],[0-9][0-9][0-9][0-9]/**} wkx,
  deny @{PROC}/sys/kernel/{shm*,msg*,sem*,fs/mqueue/**} wkx,

  # Application tmpfs
  /tmp/              rw,
  /tmp/**            rwkl,
  /app/              r,
  /app/**            r,
}
```

```yaml
# Apply AppArmor in pod annotation
metadata:
  annotations:
    container.apparmor.security.beta.kubernetes.io/app: localhost/container-default
```

---

## Linux Capabilities

```yaml
# Default: drop ALL, add only what's required
securityContext:
  capabilities:
    drop: ["ALL"]
    add:
      # NET_BIND_SERVICE: bind ports < 1024 (use port > 1024 instead)
      # NET_ADMIN: network admin (only for CNI plugins)
      # SYS_PTRACE: debugging (never in production)
      []  # Empty = only if absolutely needed

# Common required capabilities by use case:
# Web server on port 80: NET_BIND_SERVICE (or use port 8080 + service)
# DNS resolver: NET_BIND_SERVICE (port 53)
# Service mesh sidecar: NET_ADMIN, NET_RAW (set by mesh itself)
# Monitoring agent: SYS_PTRACE (use eBPF alternative instead)
```

---

## Image Tag Pinning and Verification

```yaml
# WRONG — mutable tag (image may change after push)
image: python:3.12-slim

# WRONG — latest (unpredictable)
image: myapp:latest

# CORRECT — pin to digest (immutable reference)
image: python:3.12-slim@sha256:abc123def456...

# CORRECT — pin to digest in production (Kyverno can enforce this)
image: ghcr.io/myorg/myapp@sha256:abc123def456789...
```

```bash
# Get digest for an image
docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim
# python@sha256:abc123...

# Verify image signature (Cosign)
cosign verify \
  --certificate-identity=https://github.com/org/repo/.github/workflows/build.yaml@refs/heads/main \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  ghcr.io/myorg/myapp@sha256:abc123...
```

---

## Container Scanning Tools Comparison

| Tool | Scope | Best For |
|------|-------|----------|
| **Trivy** | OS, libs, IaC, secrets, licenses | All-in-one CI scanner |
| **Grype** | OS, libs (fast) | SBOM-based scanning |
| **Syft** | SBOM generation | Generating CycloneDX/SPDX |
| **Snyk** | Libs, container, IaC | Developer-focused, fix PRs |
| **Clair** | OS vulns | Registry-integrated scanning |
| **Falco** | Runtime behavior | Post-deployment detection |

### SBOM Generation with Syft

```bash
# Generate SBOM in CycloneDX format
syft packages ghcr.io/myorg/myapp:latest \
  -o cyclonedx-json=sbom.cdx.json \
  --source-name myapp \
  --source-version 1.2.3

# Generate SBOM in SPDX format
syft packages ghcr.io/myorg/myapp:latest \
  -o spdx-json=sbom.spdx.json

# Scan SBOM for vulnerabilities
grype sbom:sbom.cdx.json --fail-on high
```
