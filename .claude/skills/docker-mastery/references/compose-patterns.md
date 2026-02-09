# Compose Patterns

## Compose File Structure

Docker Compose uses the **Compose Specification** (compose-spec.io). The legacy `version` field is
deprecated and ignored by modern Docker Compose (v2.x+). Omit it entirely.

Top-level keys:

```yaml
services:       # Container definitions (required)
networks:       # Custom network definitions
volumes:        # Named volume definitions
configs:        # Configuration objects (Swarm / Compose v2.23+)
secrets:        # Sensitive data objects
```

File naming priority (checked in order):
1. `compose.yaml` (preferred by the spec)
2. `compose.yml`
3. `docker-compose.yaml`
4. `docker-compose.yml`

Override layering with multiple files:

```bash
# Base + environment-specific overlay
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

Fields in later files merge into and override earlier files. Use `compose.override.yaml`
for automatic local-dev overrides (loaded implicitly when present).

---

## Service Patterns

A production service definition uses these common keys:

```yaml
services:
  web:
    image: myapp:1.4.2                       # Pin exact tag, never use :latest in prod
    build:
      context: .
      dockerfile: Dockerfile
      target: production                      # Multi-stage target
      args:
        PYTHON_VERSION: "3.12"
    ports:
      - "127.0.0.1:8000:8000"                # Bind to loopback when behind a reverse proxy
    volumes:
      - app-data:/app/data                    # Named volume for persistent state
    environment:
      DATABASE_URL: "postgresql+asyncpg://app:${DB_PASSWORD}@db:5432/myapp"
      REDIS_URL: "redis://redis:6379/0"
    env_file:
      - .env                                  # Bulk env vars from file
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
        reservations:
          cpus: "0.25"
          memory: 128M
    restart: unless-stopped
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
```

Key rules:
- Always pin image tags to a specific version.
- Bind published ports to `127.0.0.1` when a reverse proxy sits in front.
- Set both resource `limits` and `reservations` to prevent OOM kills and ensure scheduling.
- Use `restart: unless-stopped` so containers survive host reboots but respect manual stops.

---

## Dependency Ordering

`depends_on` alone only controls **start order**, not readiness. Use the `condition` field
to wait for actual health:

```yaml
services:
  app:
    depends_on:
      db:
        condition: service_healthy            # Waits for db healthcheck to pass
        restart: true                         # Restart app if db restarts (Compose v2.21+)
      redis:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
```

For images that lack a CLI health tool, embed a lightweight check in the Dockerfile
or use a small wait script in the dependent service's entrypoint:

```bash
# Entrypoint snippet -- prefer healthcheck conditions over this approach
until pg_isready -h db -p 5432; do sleep 1; done
exec "$@"
```

---

## Network Isolation

Separate frontend (public-facing) from backend (internal) traffic so the database
is never reachable from the reverse proxy:

```yaml
services:
  nginx:
    image: nginx:1.27-alpine
    ports:
      - "80:80"
      - "443:443"
    networks:
      - frontend                              # Nginx only sees the frontend network

  app:
    image: myapp:1.4.2
    networks:
      - frontend                              # Receives traffic from nginx
      - backend                               # Talks to db and redis
    expose:
      - "8000"                                # Only accessible inside Docker networks

  db:
    image: postgres:16-alpine
    networks:
      - backend                               # Isolated -- nginx cannot reach it
    volumes:
      - pg-data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    networks:
      - backend

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true                            # No outbound internet access for backend
```

Setting `internal: true` on the backend network prevents containers on that network
from reaching the public internet, adding a second layer of isolation.

---

## Volume Management

**Named volumes** are managed by Docker and persist across container restarts:

```yaml
volumes:
  pg-data:                                    # Default local driver
  app-uploads:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/nfs/uploads                # Back a named volume with NFS or host path
```

**Bind mounts** map a host path directly -- use only for development or config injection:

```yaml
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro   # Read-only config injection
  - ./src:/app/src                                 # Live-reload in development
```

**tmpfs** for ephemeral or sensitive data that must never be written to disk:

```yaml
services:
  app:
    tmpfs:
      - /tmp:size=64M
      - /run/secrets:size=1M,uid=1000
```

In production, prefer named volumes over bind mounts for portability and to avoid
host-path coupling.

---

## Environment Management

Load variables from a `.env` file at the project root (auto-loaded by Compose):

```env
# .env
POSTGRES_PASSWORD=changeme_in_prod
APP_ENV=production
```

Reference them with substitution syntax:

```yaml
services:
  app:
    environment:
      APP_ENV: ${APP_ENV:-production}         # Default if unset
      DB_POOL_SIZE: ${DB_POOL_SIZE:?error: DB_POOL_SIZE required}  # Fail if unset
    env_file:
      - path: .env
        required: true
      - path: .env.local
        required: false                       # Optional override (Compose v2.24+)
```

For true secrets (passwords, API keys), use the `secrets` top-level key which mounts
files into `/run/secrets/<name>` instead of environment variables:

```yaml
secrets:
  db_password:
    file: ./secrets/db_password.txt           # File-based secret
```

---

## Profiles

Mark optional services with `profiles` so they only start when explicitly activated:

```yaml
services:
  app:
    image: myapp:1.4.2                        # No profile -- always starts

  debug:
    image: busybox
    profiles: [debug]                         # Only with --profile debug
    command: sleep infinity

  prometheus:
    image: prom/prometheus:v2.53.0
    profiles: [monitoring]

  test-runner:
    image: myapp:1.4.2
    profiles: [testing]
    command: pytest
```

```bash
docker compose up -d                          # Starts only app
docker compose --profile monitoring up -d     # Starts app + prometheus
docker compose --profile debug --profile monitoring up -d  # Multiple profiles
```

---

## Full-Stack Example

A production-grade stack with FastAPI, PostgreSQL, Redis, and Nginx:

```yaml
services:
  nginx:
    image: nginx:1.27-alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    networks:
      - frontend
    depends_on:
      app:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 128M
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost/health || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3

  app:
    build:
      context: .
      target: production
    expose:
      - "8000"
    environment:
      DATABASE_URL: "postgresql+asyncpg://app:${POSTGRES_PASSWORD}@db:5432/myapp"
      REDIS_URL: "redis://redis:6379/0"
    networks:
      - frontend
      - backend
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
        reservations:
          cpus: "0.25"
          memory: 128M
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 10s

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}
      POSTGRES_DB: myapp
    volumes:
      - pg-data:/var/lib/postgresql/data
    networks:
      - backend
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 1G
        reservations:
          memory: 256M
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d myapp"]
      interval: 10s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 128mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    networks:
      - backend
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 256M
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

volumes:
  pg-data:
  redis-data:

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true
```
