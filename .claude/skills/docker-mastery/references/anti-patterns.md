# Anti-Patterns

Common Docker mistakes that compromise security, performance, and maintainability.

---

### 1. Running as Root
**Problem**: Container processes run as root by default, giving attackers full control if compromised.
**Bad**:
```dockerfile
FROM python:3.12-slim
COPY app.py /app/
CMD ["python", "/app/app.py"]
```
**Good**:
```dockerfile
FROM python:3.12-slim
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser
COPY --chown=appuser:appuser app.py /app/
USER appuser
CMD ["python", "/app/app.py"]
```
**Why**: The USER directive drops privileges so a container compromise does not grant root on the host.

---

### 2. Using :latest Tag
**Problem**: Builds are non-reproducible; a new upstream push silently changes your base image.
**Bad**:
```dockerfile
FROM python:latest
```
**Good**:
```dockerfile
FROM python:3.12.4-slim-bookworm@sha256:a1b2c3d4...
```
**Why**: Pinning the version and digest guarantees the exact same image across builds and environments.

---

### 3. Fat Images with Build Tools
**Problem**: Compilers, headers, and build tools ship to production, inflating image size and attack surface.
**Bad**:
```dockerfile
FROM python:3.12
RUN apt-get update && apt-get install -y gcc libpq-dev
RUN pip install psycopg2
COPY . /app
CMD ["python", "/app/main.py"]
```
**Good**:
```dockerfile
FROM python:3.12 AS builder
RUN apt-get update && apt-get install -y gcc libpq-dev
RUN pip install --prefix=/install psycopg2

FROM python:3.12-slim
COPY --from=builder /install /usr/local
COPY . /app
CMD ["python", "/app/main.py"]
```
**Why**: Multi-stage builds keep build-time dependencies out of the final image, often cutting size by 80%.

---

### 4. Secrets in ENV/ARG
**Problem**: Secrets baked into image layers are visible via `docker history` and persist forever.
**Bad**:
```dockerfile
FROM python:3.12-slim
ENV API_KEY=sk-xxx-production-key
ARG DB_PASSWORD=supersecret
RUN echo "machine github.com password ${DB_PASSWORD}" > ~/.netrc
```
**Good**:
```dockerfile
FROM python:3.12-slim
# Pass secrets at runtime, never at build time
# docker run -e API_KEY --env-file .env myapp
# Or use BuildKit secrets for build-time needs:
RUN --mount=type=secret,id=db_password \
    cat /run/secrets/db_password > /tmp/pw && setup_db.sh && rm /tmp/pw
```
**Why**: BuildKit secrets are never written to image layers; runtime env vars keep secrets out of the image entirely.

---

### 5. Single-Layer RUN
**Problem**: Splitting `apt-get update` and `apt-get install` into separate RUN instructions causes stale package lists when the cache is reused.
**Bad**:
```dockerfile
RUN apt-get update
RUN apt-get install -y curl
RUN apt-get install -y nginx
```
**Good**:
```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      curl \
      nginx && \
    rm -rf /var/lib/apt/lists/*
```
**Why**: A cached `apt-get update` layer may contain outdated indices, causing install failures. Combining them ensures freshness.

---

### 6. No .dockerignore
**Problem**: The entire working directory -- .git, node_modules, __pycache__, .env -- is sent as build context, leaking secrets and slowing builds.
**Bad**:
```dockerfile
# No .dockerignore file present
COPY . /app
```
**Good**:
```
# .dockerignore
.git
.env
node_modules
__pycache__
*.pyc
.venv
docker-compose*.yml
```
**Why**: A proper .dockerignore reduces context size, speeds up builds, and prevents accidental inclusion of credentials.

---

### 7. ADD Instead of COPY
**Problem**: ADD auto-extracts archives and supports remote URLs, introducing unexpected behavior and security risk.
**Bad**:
```dockerfile
ADD https://example.com/app.tar.gz /opt/
ADD config.json /app/config.json
```
**Good**:
```dockerfile
RUN curl -fsSL https://example.com/app.tar.gz -o /tmp/app.tar.gz && \
    tar -xzf /tmp/app.tar.gz -C /opt/ && \
    rm /tmp/app.tar.gz
COPY config.json /app/config.json
```
**Why**: COPY is explicit and predictable. ADD's implicit extraction and remote fetch make builds harder to reason about.

---

### 8. Not Handling PID 1
**Problem**: Shell form CMD wraps the process in `/bin/sh -c`, which does not forward SIGTERM; containers take 10s to force-kill.
**Bad**:
```dockerfile
CMD python app.py
# Runs as: /bin/sh -c "python app.py"
# SIGTERM goes to sh, python never receives it
```
**Good**:
```dockerfile
# Option A: exec form
CMD ["python", "app.py"]

# Option B: use tini as init
RUN apt-get update && apt-get install -y tini
ENTRYPOINT ["tini", "--"]
CMD ["python", "app.py"]
```
**Why**: Exec form or an init process ensures signals reach the application for graceful shutdown and proper zombie reaping.

---

### 9. No Health Checks
**Problem**: Docker reports the container as running even when the application inside has crashed or is deadlocked.
**Bad**:
```dockerfile
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/nginx.conf
# No health check -- orchestrator cannot detect failures
```
**Good**:
```dockerfile
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/nginx.conf
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/ || exit 1
```
**Why**: HEALTHCHECK lets Docker and orchestrators detect unresponsive containers and restart them automatically.

---

### 10. Hardcoded Configuration
**Problem**: Embedded config values require a rebuild to change between environments.
**Bad**:
```dockerfile
FROM python:3.12-slim
COPY app.py /app/
ENV DATABASE_URL=postgres://prod-db:5432/mydb
ENV LOG_LEVEL=WARNING
CMD ["python", "/app/app.py"]
```
**Good**:
```dockerfile
FROM python:3.12-slim
COPY app.py /app/
# Defaults are safe; overrides supplied at runtime
ENV DATABASE_URL=postgres://localhost:5432/mydb
ENV LOG_LEVEL=INFO
CMD ["python", "/app/app.py"]
# Run: docker run -e DATABASE_URL=postgres://prod-db:5432/mydb myapp
```
**Why**: Environment variables and mounted config files allow the same image to run in dev, staging, and production without rebuilding.

---

### 11. Installing Unnecessary Tools
**Problem**: Debug tools like curl, wget, vim, and net-tools widen the attack surface and bloat the image.
**Bad**:
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y \
    curl wget vim net-tools htop strace
COPY . /app
```
**Good**:
```dockerfile
FROM python:3.12-slim
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
# Debug when needed: docker exec --debug or ephemeral sidecar
```
**Why**: Production images should contain only what the application needs. Use `docker debug` or sidecar containers for troubleshooting.

---

### 12. Not Pinning Versions
**Problem**: Unpinned packages silently upgrade on rebuild, causing breakage or untested behavior.
**Bad**:
```dockerfile
RUN apt-get update && apt-get install -y \
    python3 \
    postgresql-client \
    libpq-dev
```
**Good**:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3=3.12.4-1 \
    postgresql-client=16+257 \
    libpq-dev=16.3-1 && \
    rm -rf /var/lib/apt/lists/*
```
**Why**: Pinned versions ensure every build produces the same image, making deployments predictable and rollbacks reliable.

---

### 13. Ignoring Build Cache Order
**Problem**: Copying all source code before installing dependencies invalidates the pip/npm install cache on every code change.
**Bad**:
```dockerfile
FROM python:3.12-slim
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "main.py"]
```
**Good**:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```
**Why**: Copying dependency manifests first lets Docker cache the expensive install layer; only source code changes trigger a fast re-copy.

---

### 14. docker commit for Production
**Problem**: Manual `docker commit` creates opaque, unreproducible images with no audit trail.
**Bad**:
```bash
docker run -it ubuntu:22.04 bash
# (inside container) apt-get install -y python3 nginx ...
# (from host)
docker commit abc123 myapp:production
docker push registry.example.com/myapp:production
```
**Good**:
```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 nginx && \
    rm -rf /var/lib/apt/lists/*
COPY app/ /opt/app/
CMD ["python3", "/opt/app/main.py"]
```
```bash
docker build -t registry.example.com/myapp:1.2.0 .
docker push registry.example.com/myapp:1.2.0
```
**Why**: Dockerfiles are version-controlled, reviewable, and produce identical images on every build.

---

### 15. Privileged Containers
**Problem**: `--privileged` grants all Linux capabilities, device access, and bypasses seccomp/AppArmor.
**Bad**:
```bash
docker run --privileged myapp
# Container can load kernel modules, access all devices, escape to host
```
**Good**:
```bash
docker run \
    --cap-drop=ALL \
    --cap-add=NET_BIND_SERVICE \
    --security-opt=no-new-privileges:true \
    --read-only \
    myapp
```
**Why**: Drop all capabilities and add back only what the application requires. Never use --privileged in production.

---

### 16. Mounting Docker Socket
**Problem**: Mounting the Docker socket gives the container full control over the Docker daemon, equivalent to root on the host.
**Bad**:
```yaml
services:
  ci-runner:
    image: myrunner:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```
**Good**:
```yaml
services:
  ci-runner:
    image: myrunner:latest
    # Use Docker-in-Docker with TLS
  dind:
    image: docker:27-dind
    privileged: true  # isolated dind, not host socket
    environment:
      - DOCKER_TLS_CERTDIR=/certs
    volumes:
      - docker-certs:/certs
volumes:
  docker-certs:
```
**Why**: Socket mounting lets a compromised container spawn privileged containers or read host files. Use DinD with TLS or a purpose-built API proxy.

---

### 17. Not Cleaning Package Cache
**Problem**: Package manager caches remain in the layer, adding hundreds of MB to the image.
**Bad**:
```dockerfile
RUN apt-get update
RUN apt-get install -y python3 nginx
# /var/lib/apt/lists/* still present (~40MB)
# pip cache still present
```
**Good**:
```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 \
      nginx && \
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false && \
    rm -rf /var/lib/apt/lists/*
# For pip:
RUN pip install --no-cache-dir -r requirements.txt
```
**Why**: Cleaning caches in the same RUN layer prevents them from being stored, keeping images lean.

---

### 18. Using VOLUME in Dockerfile
**Problem**: VOLUME in a Dockerfile creates anonymous volumes that are hard to manage and cannot be overridden in compose.
**Bad**:
```dockerfile
FROM postgres:16
VOLUME /var/lib/postgresql/data
# Creates anonymous volume on every `docker run`
# Cannot be removed from child images
```
**Good**:
```dockerfile
FROM postgres:16
# Do NOT declare VOLUME in the Dockerfile
```
```yaml
# Declare volumes explicitly in compose
services:
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
    driver: local
```
**Why**: Compose-managed named volumes are explicit, discoverable, and controllable. Dockerfile VOLUME creates invisible state.

---

### 19. No Resource Limits
**Problem**: Without limits a single container can exhaust all host CPU and memory, starving other services.
**Bad**:
```yaml
services:
  worker:
    image: myworker:latest
    # No resource constraints -- can consume entire host
```
**Good**:
```yaml
services:
  worker:
    image: myworker:latest
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 512M
        reservations:
          cpus: "0.5"
          memory: 128M
    # Or with docker run:
    # docker run --memory=512m --cpus=2.0 myworker
```
**Why**: Resource limits prevent runaway processes from causing host-wide outages and enable fair scheduling across containers.

---

### 20. Ignoring Scan Results
**Problem**: Building and deploying images with known critical CVEs exposes the application to exploits.
**Bad**:
```bash
docker build -t myapp:1.0 .
# Scan shows 12 critical, 47 high vulnerabilities
docker scout cves myapp:1.0
# Output ignored, image pushed anyway
docker push registry.example.com/myapp:1.0
```
**Good**:
```bash
docker build -t myapp:1.0 .
docker scout cves --only-severity critical,high myapp:1.0
# Gate deployment on scan results
docker scout cves --exit-code --only-severity critical myapp:1.0 || {
    echo "Critical CVEs found -- blocking push"
    exit 1
}
# In CI pipeline: fail the build on critical findings
docker push registry.example.com/myapp:1.0
```
**Why**: Scanning without enforcement is security theater. Gate your CI pipeline to block images with critical vulnerabilities.
