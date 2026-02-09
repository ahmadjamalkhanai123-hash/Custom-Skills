# Multi-Stage Builds

Optimization patterns for multi-stage Docker builds using BuildKit.
All examples require BuildKit (Docker 23.0+ default). Use `# syntax=docker/dockerfile:1` as the first line.

## Stage Naming

Use `AS` to name stages. Reference with `COPY --from=<name>`.

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry build --format wheel

FROM python:3.12-slim AS test
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install /tmp/*.whl && pytest

FROM gcr.io/distroless/python3-debian12 AS production
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
```

Named stages preferred over index-based (`COPY --from=0`) -- indices break on reorder.
External images work too: `COPY --from=busybox:1.36 /bin/wget /usr/local/bin/wget`.

## Cache Mount Patterns

BuildKit cache mounts persist package caches across builds, never included in final layers.
Syntax: `RUN --mount=type=cache,target=<path> <command>`

**Python (pip / uv):**
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-compile -r requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt
```
**Node.js (npm / pnpm):**
```dockerfile
RUN --mount=type=cache,target=/root/.npm npm ci --prefer-offline
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
```
**Go:**
```dockerfile
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /app ./cmd/server
```
**APT (Debian/Ubuntu):**
```dockerfile
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends build-essential
```

## Secret Mounts

Inject build-time secrets without leaking into image layers. Available only during the mounting RUN.

```dockerfile
# syntax=docker/dockerfile:1
RUN --mount=type=secret,id=pip_conf,target=/etc/pip.conf \
    pip install -r requirements.txt
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
    npm ci
RUN --mount=type=secret,id=api_key \
    API_KEY=$(cat /run/secrets/api_key) && ./configure --api-key="$API_KEY"
```
Build command:
```bash
docker buildx build \
  --secret id=pip_conf,src=$HOME/.pip/pip.conf \
  --secret id=npmrc,src=$HOME/.npmrc \
  --secret id=api_key,src=./api_key.txt -t myapp .
```

## SSH Forwarding

Forward host SSH agent for private repos. The socket is never written to layers.

```dockerfile
# syntax=docker/dockerfile:1
FROM golang:1.23 AS builder
RUN mkdir -p -m 0700 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts
RUN --mount=type=ssh git clone git@github.com:org/private-repo.git /src/repo
RUN --mount=type=ssh GOPRIVATE=github.com/org/* go mod download
```
```bash
docker buildx build --ssh default=$SSH_AUTH_SOCK -t myapp .
```

## Conditional Stages

Use `--target` to select stages. One Dockerfile for dev, test, and production.

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM base AS development
RUN pip install debugpy pytest ipdb
COPY . .
CMD ["python", "-m", "debugpy", "--listen", "0.0.0.0:5678", "app.py"]

FROM base AS test
COPY . .
CMD ["pytest", "--cov=app", "tests/"]

FROM gcr.io/distroless/python3-debian12 AS production
COPY --from=base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY app/ /app/
CMD ["app/main.py"]
```
```bash
docker buildx build --target development -t myapp:dev .
docker buildx build --target production -t myapp:prod .
```

## Size Comparison

Image sizes for a minimal HTTP server. Multi-stage builds copy artifacts into small final images.

| Language | Base Image | Size | Notes |
|---|---|---|---|
| Python | python:3.12 | ~1020 MB | Full Debian with build tools |
| Python | python:3.12-slim | ~155 MB | Minimal Debian |
| Python | python:3.12-alpine | ~60 MB | musl libc, some C ext issues |
| Python | distroless/python3-debian12 | ~52 MB | No shell, no package manager |
| Node | node:22 | ~1100 MB | Full Debian |
| Node | node:22-slim | ~220 MB | Minimal Debian |
| Node | node:22-alpine | ~135 MB | Common production choice |
| Node | distroless/nodejs22-debian12 | ~130 MB | No shell, no npm |
| Go | golang:1.23 | ~820 MB | Build stage only, never ship |
| Go | alpine:3.20 | ~13 MB | Static binary + alpine |
| Go | distroless/static-debian12 | ~2.5 MB | Static binary + CA certs |
| Go | scratch | ~8 MB | Binary only, add CA certs manually |

Go with `CGO_ENABLED=0` produces static binaries for scratch. For TLS:
`COPY --from=builder /etc/ssl/certs /etc/ssl/certs`.

## Layer Analysis

Tools for finding bloat and optimization opportunities.

**docker history** -- layer sizes and instructions:
```bash
docker history --no-trunc --format "{{.Size}}\t{{.CreatedBy}}" myapp:latest
```
**dive** -- interactive TUI for layer diffs and efficiency scoring:
```bash
dive myapp:latest
CI=true dive myapp:latest --highestWastedBytes 20MB --lowestEfficiency 0.95
```
**BuildKit disk usage** -- inspect and prune build cache:
```bash
docker buildx du                        # cache disk usage
docker buildx prune --filter until=72h  # prune old cache
```

## BuildKit Bake

`docker buildx bake` reads HCL files for multi-target, multi-platform builds with shared config.

```hcl
// docker-bake.hcl
variable "REGISTRY" { default = "ghcr.io/myorg" }
variable "VERSION"  { default = "latest" }

group "default" {
  targets = ["api", "worker", "frontend"]
}

target "_common" {
  dockerfile = "Dockerfile"
  args   = { BUILD_DATE = timestamp(), VERSION = VERSION }
  labels = { "org.opencontainers.image.source" = "https://github.com/myorg/myapp" }
}

target "api" {
  inherits   = ["_common"]
  context    = "./services/api"
  tags       = ["${REGISTRY}/api:${VERSION}"]
  platforms  = ["linux/amd64", "linux/arm64"]
  cache-from = ["type=gha"]
  cache-to   = ["type=gha,mode=max"]
}

target "worker" {
  inherits = ["_common"]
  context  = "./services/worker"
  tags     = ["${REGISTRY}/worker:${VERSION}"]
}

target "frontend" {
  inherits   = ["_common"]
  context    = "./services/frontend"
  dockerfile = "Dockerfile.prod"
  tags       = ["${REGISTRY}/frontend:${VERSION}"]
  target     = "production"
}

target "api-dev" {
  inherits = ["api"]
  tags     = ["${REGISTRY}/api:dev"]
  target   = "development"
}
```
Commands:
```bash
docker buildx bake                # build all targets in default group
docker buildx bake api            # build single target
docker buildx bake --set VERSION=1.2.3 --push  # override vars and push
docker buildx bake --print        # dry run: resolved build plan
```

For matrix builds, use `for_each` or generate bake files from CI (`docker/bake-action`).
