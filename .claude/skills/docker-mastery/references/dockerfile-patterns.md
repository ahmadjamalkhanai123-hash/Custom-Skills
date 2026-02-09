# Dockerfile Patterns

Production-grade, multi-stage Dockerfiles for five languages. Every example is
a complete, copy-paste-ready file that follows current best practices:
specific image tags, non-root user, exec-form CMD, health checks, and
minimal final images.

---

## Python

Multi-stage build using **uv** (fast Rust-based installer) with a pip
fallback. Final stage runs on distroless for a minimal attack surface.

```dockerfile
# ---- build stage ----
FROM python:3.12-slim AS builder

# Install uv for fast, reproducible installs (falls back to pip if removed)
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv

WORKDIR /app

# Cache dependency layer separately from application code
COPY pyproject.toml uv.lock* requirements.txt* ./

# uv path: create venv, sync deps.  pip fallback if no pyproject.toml.
RUN if [ -f pyproject.toml ]; then \
      uv venv /app/.venv && uv pip install --python /app/.venv/bin/python -r pyproject.toml; \
    elif [ -f requirements.txt ]; then \
      python -m venv /app/.venv && /app/.venv/bin/pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . .

# ---- final stage ----
FROM gcr.io/distroless/python3-debian12:nonroot AS runtime

COPY --from=builder /app /app
COPY --from=builder /app/.venv /app/.venv

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

# Gunicorn with Uvicorn workers — adjust concurrency via WEB_CONCURRENCY
ENTRYPOINT ["gunicorn", "app.main:app", \
            "-k", "uvicorn.workers.UvicornWorker", \
            "--bind", "0.0.0.0:8000"]
CMD ["--workers", "4", "--timeout", "120"]
```

**.dockerignore**

```
__pycache__/
*.pyc
.venv/
.git/
.env
dist/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
```

---

## Node.js

Multi-stage build supporting both **npm ci** and **pnpm**. Alpine final
image keeps size small. PM2 optional; defaults to plain `node`.

```dockerfile
# ---- dependencies stage ----
FROM node:22-alpine AS deps

# Enable corepack for pnpm support
RUN corepack enable

WORKDIR /app

# Copy lock files first for layer caching
COPY package.json package-lock.json* pnpm-lock.yaml* ./

# Install with the lock file that exists
RUN if [ -f pnpm-lock.yaml ]; then \
      pnpm install --frozen-lockfile --prod; \
    else \
      npm ci --omit=dev; \
    fi

# ---- build stage (for TypeScript / bundled apps) ----
FROM node:22-alpine AS builder

RUN corepack enable
WORKDIR /app

COPY package.json package-lock.json* pnpm-lock.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; else npm ci; fi

COPY . .
RUN npm run build --if-present

# ---- final stage ----
FROM node:22-alpine AS runtime

RUN addgroup -g 1001 appgroup && \
    adduser -u 1001 -G appgroup -s /bin/sh -D appuser

WORKDIR /app

# Production deps only from deps stage; built output from builder
COPY --from=deps   --chown=appuser:appgroup /app/node_modules ./node_modules
COPY --from=builder --chown=appuser:appgroup /app/dist ./dist
COPY --from=builder --chown=appuser:appgroup /app/package.json ./

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD ["node", "-e", "require('http').get('http://localhost:3000/health', r => { process.exit(r.statusCode === 200 ? 0 : 1) })"]

ENTRYPOINT ["node"]
CMD ["dist/index.js"]
```

**.dockerignore**

```
node_modules/
dist/
.git/
.env
*.log
.next/
coverage/
.turbo/
```

---

## Go

Static binary compiled with `CGO_ENABLED=0`. Final image is **scratch** --
nothing but the binary and CA certificates.

```dockerfile
# ---- build stage ----
FROM golang:1.23-alpine AS builder

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /src

# Cache module downloads separately from source
COPY go.mod go.sum ./
RUN go mod download && go mod verify

COPY . .

# Static binary — no libc dependency, safe for scratch
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags="-s -w" -trimpath -o /app ./cmd/server

# ---- final stage ----
FROM scratch

COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo
COPY --from=builder /etc/passwd /etc/passwd

# Copy binary
COPY --from=builder /app /app

USER nobody

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD ["/app", "healthcheck"]

ENTRYPOINT ["/app"]
CMD ["serve"]
```

**.dockerignore**

```
*.exe
*.test
.git/
vendor/
bin/
tmp/
```

---

## Rust

Uses **cargo-chef** to cache compiled dependencies across builds so only
changed application code triggers a recompile.

```dockerfile
# ---- chef stage (dependency planner) ----
FROM rust:1.80-slim AS chef

RUN cargo install cargo-chef
WORKDIR /src

# ---- plan stage ----
FROM chef AS planner

COPY . .
RUN cargo chef prepare --recipe-path recipe.json

# ---- build stage ----
FROM chef AS builder

COPY --from=planner /src/recipe.json recipe.json

# Compile dependencies (cached unless Cargo.toml/lock changes)
RUN cargo chef cook --release --recipe-path recipe.json

COPY . .
RUN cargo build --release --bin server && \
    strip /src/target/release/server

# ---- final stage ----
FROM gcr.io/distroless/cc-debian12:nonroot AS runtime

COPY --from=builder /src/target/release/server /app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD ["/app", "--healthcheck"]

ENTRYPOINT ["/app"]
CMD ["--port", "8080"]
```

**.dockerignore**

```
target/
.git/
*.rs.bk
.cargo/registry/
.cargo/git/
```

---

## Java

Maven multi-stage build. Optional **jlink** custom JRE trims the runtime
to only the modules the application uses. Final image is distroless/java.

```dockerfile
# ---- build stage ----
FROM maven:3.9-eclipse-temurin-21-alpine AS builder

WORKDIR /src

# Cache Maven dependencies
COPY pom.xml .
RUN mvn dependency:go-offline -B

COPY src ./src
RUN mvn package -DskipTests -B && \
    mv target/*.jar /app.jar

# Optional: create a minimal JRE with jlink
RUN jlink \
      --add-modules $(jdeps --ignore-missing-deps --print-module-deps /app.jar) \
      --strip-debug --no-man-pages --no-header-files \
      --compress=zip-6 --output /custom-jre

# ---- final stage ----
FROM gcr.io/distroless/java21-debian12:nonroot AS runtime

# If using jlink custom JRE, copy it instead:
# COPY --from=builder /custom-jre /opt/java
# ENV JAVA_HOME=/opt/java PATH="/opt/java/bin:$PATH"

COPY --from=builder /app.jar /app.jar

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD ["java", "-cp", "/app.jar", "com.example.HealthCheck"]

ENTRYPOINT ["java"]
CMD ["-XX:MaxRAMPercentage=75.0", "-jar", "/app.jar"]
```

**.dockerignore**

```
target/
.git/
*.class
*.jar
.idea/
.gradle/
build/
```

---

## General Patterns

### ARG and ENV usage

Use `ARG` for build-time values and `ENV` for runtime. Combine them to
let operators override defaults without editing the Dockerfile.

```dockerfile
# Build-time argument with a sensible default
ARG APP_VERSION=0.0.0-dev

# Promote to runtime env so the app can read it
ENV APP_VERSION=${APP_VERSION}

# Example: pin a base image digest via ARG for reproducibility
ARG PYTHON_IMAGE=python:3.12-slim@sha256:abc123...
FROM ${PYTHON_IMAGE} AS builder
```

### ENTRYPOINT + CMD combo

ENTRYPOINT defines the executable; CMD supplies default arguments that
operators can override at `docker run` time.

```dockerfile
# The binary is always "gunicorn"; the flags are defaults
ENTRYPOINT ["gunicorn", "app:create_app()"]
CMD ["--workers", "4", "--bind", "0.0.0.0:8000"]

# Override at runtime:  docker run myimage --workers 8
```

### HEALTHCHECK per language

```dockerfile
# Python  — stdlib only, no curl needed
HEALTHCHECK CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

# Node.js — no extra binary
HEALTHCHECK CMD ["node", "-e", "require('http').get('http://localhost:3000/health', r=>{process.exit(r.statusCode===200?0:1)})"]

# Go / Rust — built-in subcommand (binary is already present)
HEALTHCHECK CMD ["/app", "healthcheck"]

# Java    — dedicated lightweight class on the classpath
HEALTHCHECK CMD ["java", "-cp", "/app.jar", "com.example.HealthCheck"]
```

### LABEL / OCI annotations

Standard labels that registries and tooling understand.

```dockerfile
LABEL org.opencontainers.image.title="my-service" \
      org.opencontainers.image.description="Production API service" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/org/repo" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.created="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```
