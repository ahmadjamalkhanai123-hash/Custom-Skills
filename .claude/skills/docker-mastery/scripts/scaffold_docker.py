#!/usr/bin/env python3
"""
Docker Mastery — Project Scaffolder

Generates a complete Docker setup for any project based on tier, language, and options.

Usage:
    python scaffold_docker.py <name> --tier <1|2|3|4> --lang <python|node|go|rust|java>
        --path <output-dir> [--registry <hub|ecr|gcr|acr|harbor|ghcr>]
        [--ci <github|gitlab|jenkins|none>] [--compose] [--multi-arch]

Examples:
    python scaffold_docker.py myapp --tier 1 --lang python --path ./myapp
    python scaffold_docker.py api --tier 2 --lang node --path ./api --compose
    python scaffold_docker.py svc --tier 3 --lang go --path ./svc --ci github --registry ecr
    python scaffold_docker.py platform --tier 4 --lang python --path ./platform --multi-arch
"""

import argparse
import os
import sys
import textwrap
from pathlib import Path

# ── Dockerfile Templates ─────────────────────────────────────────────────────

DOCKERFILES = {
    "python": textwrap.dedent("""\
        # syntax=docker/dockerfile:1
        ARG PYTHON_VERSION=3.12

        FROM python:${{PYTHON_VERSION}}-slim AS builder
        WORKDIR /app
        RUN pip install --no-cache-dir uv
        COPY pyproject.toml uv.lock* ./
        RUN --mount=type=cache,target=/root/.cache/uv \\
            uv sync --frozen --no-dev --no-editable
        COPY src/ ./src/

        FROM python:${{PYTHON_VERSION}}-slim AS test
        WORKDIR /app
        COPY --from=builder /app /app
        RUN pip install --no-cache-dir uv && uv sync --frozen
        COPY tests/ ./tests/
        RUN uv run pytest tests/ -v

        FROM gcr.io/distroless/python3-debian12:nonroot AS production
        WORKDIR /app
        COPY --from=builder /app/.venv/lib/python3.12/site-packages /usr/lib/python3.12/site-packages
        COPY --from=builder /app/src ./src
        LABEL org.opencontainers.image.title="{name}"
        EXPOSE 8000
        USER nonroot
        HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \\
            CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
        ENTRYPOINT ["python", "-m", "src.main"]
        CMD ["--host", "0.0.0.0", "--port", "8000"]
    """),
    "node": textwrap.dedent("""\
        # syntax=docker/dockerfile:1
        ARG NODE_VERSION=22

        FROM node:${{NODE_VERSION}}-alpine AS deps
        WORKDIR /app
        COPY package.json package-lock.json ./
        RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev

        FROM node:${{NODE_VERSION}}-alpine AS builder
        WORKDIR /app
        COPY package.json package-lock.json ./
        RUN --mount=type=cache,target=/root/.npm npm ci
        COPY . .
        RUN npm run build

        FROM builder AS test
        RUN npm test

        FROM node:${{NODE_VERSION}}-alpine AS production
        RUN addgroup -g 1001 -S appgroup && adduser -u 1001 -S appuser -G appgroup
        WORKDIR /app
        COPY --from=deps --chown=appuser:appgroup /app/node_modules ./node_modules
        COPY --from=builder --chown=appuser:appgroup /app/dist ./dist
        COPY --from=builder --chown=appuser:appgroup /app/package.json ./
        LABEL org.opencontainers.image.title="{name}"
        EXPOSE 3000
        HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \\
            CMD ["wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3000/health"]
        USER appuser
        ENTRYPOINT ["node", "dist/index.js"]
    """),
    "go": textwrap.dedent("""\
        # syntax=docker/dockerfile:1
        ARG GO_VERSION=1.23

        FROM golang:${{GO_VERSION}}-alpine AS builder
        RUN apk add --no-cache ca-certificates tzdata
        WORKDIR /app
        COPY go.mod go.sum ./
        RUN --mount=type=cache,target=/go/pkg/mod go mod download
        COPY . .
        RUN --mount=type=cache,target=/go/pkg/mod \\
            --mount=type=cache,target=/root/.cache/go-build \\
            CGO_ENABLED=0 GOOS=linux go build \\
            -ldflags="-s -w" -o /bin/server ./cmd/server

        FROM builder AS test
        RUN CGO_ENABLED=0 go test -v ./...

        FROM scratch AS production
        COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
        COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo
        COPY --from=builder /bin/server /server
        LABEL org.opencontainers.image.title="{name}"
        EXPOSE 8080
        USER 65534:65534
        ENTRYPOINT ["/server"]
    """),
    "rust": textwrap.dedent("""\
        # syntax=docker/dockerfile:1
        ARG RUST_VERSION=1.80

        FROM rust:${{RUST_VERSION}}-slim AS planner
        RUN cargo install cargo-chef --locked
        WORKDIR /app
        COPY . .
        RUN cargo chef prepare --recipe-path recipe.json

        FROM rust:${{RUST_VERSION}}-slim AS builder
        RUN cargo install cargo-chef --locked && \\
            apt-get update && apt-get install -y --no-install-recommends \\
            pkg-config libssl-dev ca-certificates && \\
            rm -rf /var/lib/apt/lists/*
        WORKDIR /app
        COPY --from=planner /app/recipe.json recipe.json
        RUN --mount=type=cache,target=/usr/local/cargo/registry \\
            cargo chef cook --release --recipe-path recipe.json
        COPY . .
        RUN --mount=type=cache,target=/usr/local/cargo/registry \\
            --mount=type=cache,target=/app/target \\
            cargo build --release && cp target/release/{name} /usr/local/bin/server

        FROM gcr.io/distroless/cc-debian12:nonroot AS production
        COPY --from=builder /usr/local/bin/server /server
        COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
        LABEL org.opencontainers.image.title="{name}"
        EXPOSE 8080
        USER nonroot
        ENTRYPOINT ["/server"]
    """),
    "java": textwrap.dedent("""\
        # syntax=docker/dockerfile:1
        ARG JAVA_VERSION=21

        FROM eclipse-temurin:${{JAVA_VERSION}}-jdk AS builder
        WORKDIR /app
        COPY pom.xml ./
        RUN --mount=type=cache,target=/root/.m2/repository mvn dependency:go-offline -B
        COPY src/ ./src/
        RUN --mount=type=cache,target=/root/.m2/repository mvn package -DskipTests -B && \\
            mv target/*.jar app.jar

        FROM builder AS test
        RUN mvn test -B

        FROM gcr.io/distroless/java${{JAVA_VERSION}}-debian12:nonroot AS production
        WORKDIR /app
        COPY --from=builder /app/app.jar ./app.jar
        LABEL org.opencontainers.image.title="{name}"
        EXPOSE 8080
        USER nonroot
        ENV JAVA_OPTS="-XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0"
        ENTRYPOINT ["java", "-jar", "app.jar"]
    """),
}

# ── .dockerignore Templates ─────────────────────────────────────────────────

DOCKERIGNORES = {
    "python": textwrap.dedent("""\
        __pycache__/
        *.pyc
        .venv/
        .env
        .git/
        .github/
        .mypy_cache/
        .pytest_cache/
        .ruff_cache/
        dist/
        *.egg-info/
        tests/
        docs/
        *.md
        Dockerfile*
        docker-compose*
    """),
    "node": textwrap.dedent("""\
        node_modules/
        .env
        .git/
        .github/
        dist/
        coverage/
        .next/
        *.md
        Dockerfile*
        docker-compose*
        .eslintrc*
        .prettierrc*
        tsconfig*.json
    """),
    "go": textwrap.dedent("""\
        .env
        .git/
        .github/
        *.md
        Dockerfile*
        docker-compose*
        vendor/
        tmp/
    """),
    "rust": textwrap.dedent("""\
        target/
        .env
        .git/
        .github/
        *.md
        Dockerfile*
        docker-compose*
    """),
    "java": textwrap.dedent("""\
        target/
        .env
        .git/
        .github/
        *.md
        *.class
        *.jar
        *.war
        .idea/
        *.iml
        Dockerfile*
        docker-compose*
    """),
}

# ── Compose Template ─────────────────────────────────────────────────────────

COMPOSE_TEMPLATE = textwrap.dedent("""\
    # Docker Compose — {name}
    services:
      app:
        build:
          context: .
          target: production
        ports:
          - "${{APP_PORT:-{port}}}:{port}"
        environment:
          - DATABASE_URL=postgresql+asyncpg://${{DB_USER:-app}}:${{DB_PASSWORD}}@db:5432/${{DB_NAME:-{name}db}}
          - REDIS_URL=redis://redis:6379/0
          - SECRET_KEY=${{SECRET_KEY}}
        depends_on:
          db:
            condition: service_healthy
          redis:
            condition: service_healthy
        networks:
          - frontend
          - backend
        restart: unless-stopped
        deploy:
          resources:
            limits:
              cpus: "2.0"
              memory: 512M
        healthcheck:
          test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:{port}/health"]
          interval: 30s
          timeout: 5s
          start_period: 15s
          retries: 3

      db:
        image: postgres:16-alpine
        environment:
          POSTGRES_USER: ${{DB_USER:-app}}
          POSTGRES_PASSWORD: ${{DB_PASSWORD}}
          POSTGRES_DB: ${{DB_NAME:-{name}db}}
        volumes:
          - pgdata:/var/lib/postgresql/data
        networks:
          - backend
        restart: unless-stopped
        deploy:
          resources:
            limits:
              cpus: "1.0"
              memory: 1G
        healthcheck:
          test: ["CMD-SHELL", "pg_isready -U ${{DB_USER:-app}}"]
          interval: 10s
          timeout: 5s
          start_period: 30s
          retries: 5

      redis:
        image: redis:7-alpine
        command: ["redis-server", "--maxmemory", "128mb", "--maxmemory-policy", "allkeys-lru"]
        volumes:
          - redisdata:/data
        networks:
          - backend
        restart: unless-stopped
        healthcheck:
          test: ["CMD", "redis-cli", "ping"]
          interval: 10s
          timeout: 3s
          retries: 3

    networks:
      frontend:
        driver: bridge
      backend:
        driver: bridge
        internal: true

    volumes:
      pgdata:
      redisdata:
""")

COMPOSE_DEV = textwrap.dedent("""\
    # Development Override
    # Usage: docker compose -f docker-compose.yml -f docker-compose.override.yml up
    services:
      app:
        build:
          target: builder
        volumes:
          - ./{src_dir}:/app/{src_dir}:cached
        ports:
          - "${{DEBUG_PORT:-5678}}:5678"
        environment:
          - LOG_LEVEL=debug
        deploy:
          replicas: 1
        healthcheck:
          disable: true

      db:
        ports:
          - "${{DB_PORT:-5432}}:5432"

      redis:
        ports:
          - "${{REDIS_PORT:-6379}}:6379"
""")

# ── ENV Template ─────────────────────────────────────────────────────────────

ENV_TEMPLATE = textwrap.dedent("""\
    # {name} — Environment Variables
    # Copy to .env and fill in values: cp .env.example .env

    # Application
    APP_PORT={port}
    SECRET_KEY=change-me-in-production
    LOG_LEVEL=info

    # Database
    DB_USER=app
    DB_PASSWORD=change-me
    DB_NAME={name}db

    # Redis
    REDIS_URL=redis://redis:6379/0

    # Registry (Tier 3+)
    REGISTRY={registry}
    IMAGE_NAME={name}
""")

# ── CI/CD Templates ──────────────────────────────────────────────────────────

GITHUB_ACTIONS = textwrap.dedent("""\
    name: Docker CI/CD
    on:
      push:
        branches: [main]
        tags: ["v*"]
      pull_request:
        branches: [main]

    env:
      REGISTRY: {registry_url}
      IMAGE_NAME: ${{{{ github.repository }}}}

    permissions:
      contents: read
      packages: write
      id-token: write
      security-events: write

    jobs:
      lint:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: hadolint/hadolint-action@v3.1.0
            with:
              dockerfile: Dockerfile

      build:
        runs-on: ubuntu-latest
        needs: lint
        steps:
          - uses: actions/checkout@v4
          - uses: docker/setup-buildx-action@v3
          - uses: docker/login-action@v3
            if: github.event_name != 'pull_request'
            with:
              registry: ${{{{ env.REGISTRY }}}}
              username: ${{{{ github.actor }}}}
              password: ${{{{ secrets.GITHUB_TOKEN }}}}
          - id: meta
            uses: docker/metadata-action@v5
            with:
              images: ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}
              tags: |
                type=semver,pattern={{{{version}}}}
                type=sha,prefix=sha-
                type=ref,event=branch
          - uses: docker/build-push-action@v6
            with:
              context: .
              target: production
              push: ${{{{ github.event_name != 'pull_request' }}}}
              tags: ${{{{ steps.meta.outputs.tags }}}}
              labels: ${{{{ steps.meta.outputs.labels }}}}
              cache-from: type=gha
              cache-to: type=gha,mode=max

      scan:
        runs-on: ubuntu-latest
        needs: build
        if: github.event_name != 'pull_request'
        steps:
          - uses: actions/checkout@v4
          - uses: aquasecurity/trivy-action@master
            with:
              image-ref: ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:sha-${{{{ github.sha }}}}
              format: sarif
              output: trivy-results.sarif
              severity: CRITICAL,HIGH
          - uses: github/codeql-action/upload-sarif@v3
            if: always()
            with:
              sarif_file: trivy-results.sarif

      sign:
        runs-on: ubuntu-latest
        needs: [build, scan]
        if: github.event_name != 'pull_request'
        steps:
          - uses: sigstore/cosign-installer@v3
          - uses: docker/login-action@v3
            with:
              registry: ${{{{ env.REGISTRY }}}}
              username: ${{{{ github.actor }}}}
              password: ${{{{ secrets.GITHUB_TOKEN }}}}
          - run: cosign sign --yes ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:sha-${{{{ github.sha }}}}
""")

GITLAB_CI = textwrap.dedent("""\
    stages:
      - lint
      - build
      - test
      - scan
      - push

    variables:
      DOCKER_IMAGE: $CI_REGISTRY_IMAGE
      DOCKER_TLS_CERTDIR: "/certs"

    lint:
      stage: lint
      image: hadolint/hadolint:latest-debian
      script:
        - hadolint Dockerfile

    build:
      stage: build
      image: docker:27
      services:
        - docker:27-dind
      script:
        - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
        - docker build --target production -t $DOCKER_IMAGE:$CI_COMMIT_SHORT_SHA .
        - docker push $DOCKER_IMAGE:$CI_COMMIT_SHORT_SHA

    scan:
      stage: scan
      image:
        name: aquasec/trivy:latest
        entrypoint: [""]
      script:
        - trivy image --severity CRITICAL,HIGH --exit-code 1 $DOCKER_IMAGE:$CI_COMMIT_SHORT_SHA

    push:
      stage: push
      image: docker:27
      services:
        - docker:27-dind
      script:
        - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
        - docker pull $DOCKER_IMAGE:$CI_COMMIT_SHORT_SHA
        - docker tag $DOCKER_IMAGE:$CI_COMMIT_SHORT_SHA $DOCKER_IMAGE:latest
        - docker push $DOCKER_IMAGE:latest
      only:
        - main
""")

# ── Trivy Config ─────────────────────────────────────────────────────────────

TRIVY_YAML = textwrap.dedent("""\
    # Trivy scanner configuration
    severity:
      - CRITICAL
      - HIGH
    exit-code: 1
    ignore-unfixed: true
    format: table
""")

# ── Bake Template (Tier 4) ──────────────────────────────────────────────────

BAKE_HCL = textwrap.dedent("""\
    variable "REGISTRY" {{
      default = "{registry_url}"
    }}
    variable "APP_NAME" {{
      default = "{name}"
    }}
    variable "VERSION" {{
      default = "latest"
    }}

    group "default" {{
      targets = ["app"]
    }}

    target "_base" {{
      dockerfile = "Dockerfile"
      context    = "."
      cache-from = ["type=registry,ref=${{REGISTRY}}/${{APP_NAME}}:buildcache"]
      cache-to   = ["type=registry,ref=${{REGISTRY}}/${{APP_NAME}}:buildcache,mode=max"]
    }}

    target "app" {{
      inherits = ["_base"]
      target   = "production"
      tags     = ["${{REGISTRY}}/${{APP_NAME}}:${{VERSION}}"]
    }}

    target "app-multiarch" {{
      inherits  = ["app"]
      platforms = ["linux/amd64", "linux/arm64"]
    }}
""")

# ── Port Mapping ─────────────────────────────────────────────────────────────

LANG_PORTS = {
    "python": 8000,
    "node": 3000,
    "go": 8080,
    "rust": 8080,
    "java": 8080,
}

LANG_SRC = {
    "python": "src",
    "node": "src",
    "go": "cmd",
    "rust": "src",
    "java": "src",
}

REGISTRY_URLS = {
    "hub": "docker.io",
    "ecr": "123456789.dkr.ecr.us-east-1.amazonaws.com",
    "gcr": "us-docker.pkg.dev/PROJECT_ID",
    "acr": "myregistry.azurecr.io",
    "harbor": "registry.example.com",
    "ghcr": "ghcr.io",
}


def scaffold(args: argparse.Namespace) -> None:
    """Generate Docker project files based on tier and language."""
    output = Path(args.path)
    output.mkdir(parents=True, exist_ok=True)

    name = args.name
    lang = args.lang
    tier = args.tier
    port = LANG_PORTS[lang]
    registry_url = REGISTRY_URLS.get(args.registry, "ghcr.io")
    src_dir = LANG_SRC[lang]

    files_created = []

    # ── Tier 1: Dockerfile + .dockerignore ───────────────────────────────
    dockerfile = DOCKERFILES[lang].format(name=name)
    write(output / "Dockerfile", dockerfile)
    files_created.append("Dockerfile")

    write(output / ".dockerignore", DOCKERIGNORES[lang])
    files_created.append(".dockerignore")

    # ── Tier 2+: Compose ─────────────────────────────────────────────────
    if tier >= 2 or args.compose:
        compose = COMPOSE_TEMPLATE.format(name=name, port=port)
        write(output / "docker-compose.yml", compose)
        files_created.append("docker-compose.yml")

        dev = COMPOSE_DEV.format(src_dir=src_dir)
        write(output / "docker-compose.override.yml", dev)
        files_created.append("docker-compose.override.yml")

        env = ENV_TEMPLATE.format(name=name, port=port, registry=registry_url)
        write(output / ".env.example", env)
        files_created.append(".env.example")

    # ── Tier 3+: CI/CD + Scanning + Signing ──────────────────────────────
    if tier >= 3:
        write(output / ".trivyignore", "# Add CVE IDs to ignore (one per line)\n")
        write(output / "trivy.yaml", TRIVY_YAML)
        files_created.extend(["trivy.yaml", ".trivyignore"])

        ci = args.ci
        if ci == "github":
            ci_dir = output / ".github" / "workflows"
            ci_dir.mkdir(parents=True, exist_ok=True)
            write(ci_dir / "docker.yml", GITHUB_ACTIONS.format(registry_url=registry_url))
            files_created.append(".github/workflows/docker.yml")
        elif ci == "gitlab":
            write(output / ".gitlab-ci.yml", GITLAB_CI)
            files_created.append(".gitlab-ci.yml")

    # ── Tier 4: Multi-arch + Bake ────────────────────────────────────────
    if tier >= 4 or args.multi_arch:
        bake = BAKE_HCL.format(name=name, registry_url=registry_url)
        write(output / "docker-bake.hcl", bake)
        files_created.append("docker-bake.hcl")

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n  Docker Mastery — Project Scaffolded")
    print(f"  {'=' * 40}")
    print(f"  Name:     {name}")
    print(f"  Tier:     {tier}")
    print(f"  Language: {lang}")
    print(f"  Path:     {output.resolve()}")
    print(f"  Registry: {registry_url}")
    print(f"\n  Files created:")
    for f in files_created:
        print(f"    - {f}")
    print(f"\n  Quick start:")
    print(f"    docker build -t {name}:latest {output}")
    if tier >= 2:
        print(f"    docker compose -f {output}/docker-compose.yml up -d")
    if tier >= 4:
        print(f"    docker buildx bake -f {output}/docker-bake.hcl app-multiarch")
    print()


def write(path: Path, content: str) -> None:
    """Write content to file, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Docker Mastery — Scaffold Docker setup for any project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              %(prog)s myapp --tier 1 --lang python --path ./myapp
              %(prog)s api --tier 2 --lang node --path ./api --compose
              %(prog)s svc --tier 3 --lang go --path ./svc --ci github
              %(prog)s platform --tier 4 --lang rust --path ./platform --multi-arch
        """),
    )

    parser.add_argument("name", help="Project name")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], default=1,
                        help="Tier level: 1=Single, 2=Compose, 3=Production, 4=Enterprise")
    parser.add_argument("--lang", choices=["python", "node", "go", "rust", "java"],
                        required=True, help="Application language")
    parser.add_argument("--path", default=".", help="Output directory (default: current)")
    parser.add_argument("--registry", choices=["hub", "ecr", "gcr", "acr", "harbor", "ghcr"],
                        default="ghcr", help="Container registry (default: ghcr)")
    parser.add_argument("--ci", choices=["github", "gitlab", "jenkins", "none"],
                        default="github", help="CI/CD platform (default: github)")
    parser.add_argument("--compose", action="store_true",
                        help="Generate compose files even at Tier 1")
    parser.add_argument("--multi-arch", action="store_true",
                        help="Generate multi-arch build config")

    args = parser.parse_args()
    scaffold(args)


if __name__ == "__main__":
    main()
