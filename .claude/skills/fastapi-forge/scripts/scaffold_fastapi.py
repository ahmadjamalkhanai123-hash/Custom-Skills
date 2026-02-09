#!/usr/bin/env python3
"""
FastAPI Project Scaffolder — Generate production-ready FastAPI project structure.

Usage:
    python scaffold_fastapi.py <project-name> --tier <1|2|3> --path <output-dir> [options]

Options:
    --db <postgres|mongo|redis|none>    Database (default: postgres)
    --auth <jwt|apikey|none>            Authentication (default: jwt)
    --agents                            Include agent orchestration endpoints

Examples:
    python scaffold_fastapi.py my-api --tier 1 --path ./projects
    python scaffold_fastapi.py my-api --tier 1 --path ./projects --agents --db postgres
    python scaffold_fastapi.py my-system --tier 2 --path ./projects --agents
    python scaffold_fastapi.py enterprise --tier 3 --path ./projects --agents --db postgres
"""

import sys
from pathlib import Path
from textwrap import dedent


def to_package(name: str) -> str:
    return name.replace("-", "_")


# --- Generators ---

def gen_pyproject(name: str, pkg: str, db: str, agents: bool) -> str:
    deps = ['"fastapi>=0.115.0"', '"uvicorn[standard]>=0.32.0"', '"pydantic-settings>=2.6.0"',
            '"structlog>=24.4.0"', '"python-jose[cryptography]>=3.3.0"', '"httpx>=0.28.0"']
    if db == "postgres":
        deps.extend(['"sqlalchemy[asyncio]>=2.0.36"', '"asyncpg>=0.30.0"', '"alembic>=1.14.0"'])
    elif db == "mongo":
        deps.append('"motor>=3.6.0"')
    if "redis" in db or agents:
        deps.append('"redis>=5.2.0"')
    if agents:
        deps.append('"arq>=0.26.0"')
    deps_str = ",\n    ".join(deps)
    return dedent(f'''\
[project]
name = "{name}"
version = "0.1.0"
description = "FastAPI service"
requires-python = ">=3.12"
dependencies = [
    {deps_str},
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "httpx>=0.28.0"]

[project.scripts]
{name} = "{pkg}.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{pkg}"]
''')


def gen_main(pkg: str, db: str, agents: bool) -> str:
    imports = ["from contextlib import asynccontextmanager", "from fastapi import FastAPI",
               f"from .config import settings"]
    startup, shutdown = "", ""
    if db == "postgres":
        imports.append("from .db.session import init_db, close_db")
        startup = "    await init_db()"
        shutdown = "    await close_db()"
    routers = ['    app.include_router(health.router, tags=["health"])']
    route_imports = ["from .routes import health"]
    if agents:
        route_imports.append("from .routes import agents")
        routers.append('    app.include_router(agents.router, prefix="/agents", tags=["agents"])')
    return dedent(f'''\
"""{pkg} — FastAPI Application."""

{chr(10).join(imports)}
{chr(10).join(route_imports)}


@asynccontextmanager
async def lifespan(app: FastAPI):
{startup or "    pass"}
    yield
{shutdown or "    pass"}


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
    )
{chr(10).join(routers)}
    return app


app = create_app()
''')


def gen_config(db: str) -> str:
    fields = ['    APP_NAME: str = "fastapi-service"', '    APP_VERSION: str = "0.1.0"',
              '    DEBUG: bool = False']
    if db == "postgres":
        fields.append('    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/db"')
        fields.append('    DB_POOL_SIZE: int = 20')
    elif db == "mongo":
        fields.append('    MONGO_URL: str = "mongodb://localhost:27017"')
        fields.append('    MONGO_DB: str = "app"')
    fields.extend(['    REDIS_URL: str = "redis://localhost:6379/0"',
                   '    JWT_SECRET: str = "change-me-in-production"',
                   '    ANTHROPIC_API_KEY: str = ""',
                   '    RATE_LIMIT_PER_MINUTE: int = 60'])
    return dedent(f'''\
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

{chr(10).join(fields)}


settings = Settings()
''')


def gen_db_session() -> str:
    return dedent('''\
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from ..config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    echo=settings.DEBUG,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    pass  # Use Alembic migrations


async def close_db():
    await engine.dispose()


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
''')


def gen_health() -> str:
    return dedent('''\
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    return {"status": "ok", "checks": {}}
''')


def gen_agents_route() -> str:
    return dedent('''\
"""Agent orchestration endpoints."""

import asyncio
import uuid
import time

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from enum import Enum

router = APIRouter()


class AgentRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=50000)
    model: str = "claude-sonnet-4-5-20250929"
    max_turns: int = Field(default=15, ge=1, le=100)
    timeout: int = Field(default=300, ge=10, le=3600)


class AgentResponse(BaseModel):
    result: str
    steps: int
    duration_seconds: float


@router.post("/run", response_model=AgentResponse)
async def run_agent(request: AgentRequest):
    start = time.time()
    # TODO: Replace with actual agent SDK call
    await asyncio.sleep(0.1)
    return AgentResponse(
        result="Agent response",
        steps=1,
        duration_seconds=round(time.time() - start, 2),
    )


@router.post("/run/async")
async def run_agent_async(request: AgentRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    return {"job_id": job_id, "status": "queued"}
''')


def gen_test_conftest(pkg: str) -> str:
    return dedent(f'''\
import pytest
from httpx import AsyncClient, ASGITransport
from src.{pkg}.main import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
''')


def gen_test_health() -> str:
    return dedent('''\
import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
''')


def gen_env_example(db: str) -> str:
    lines = ["# Required", "JWT_SECRET=change-me-in-production", "ANTHROPIC_API_KEY="]
    if db == "postgres":
        lines.append("DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db")
    elif db == "mongo":
        lines.extend(["MONGO_URL=mongodb://localhost:27017", "MONGO_DB=app"])
    lines.extend(["REDIS_URL=redis://localhost:6379/0", "", "# Optional", "DEBUG=false"])
    return "\n".join(lines) + "\n"


def gen_dockerfile(pkg: str) -> str:
    return dedent(f'''\
FROM python:3.12-slim AS base
WORKDIR /app

FROM base AS deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

FROM deps AS runtime
COPY src/ src/
EXPOSE 8000
CMD ["uvicorn", "src.{pkg}.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
''')


# --- Tier 2: Gateway + Services ---

def gen_gateway_main(name: str) -> str:
    return dedent(f'''\
"""{name} API Gateway — Routes requests to downstream services."""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .config import settings


class ServiceClient:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self._failure_counts: dict[str, int] = {{}}
        self._threshold = 5

    async def call(self, base_url: str, method: str, path: str, **kwargs) -> dict:
        service = base_url
        if self._failure_counts.get(service, 0) >= self._threshold:
            raise HTTPException(503, "Service temporarily unavailable")
        try:
            response = await self.client.request(method, f"{{base_url}}{{path}}", **kwargs)
            response.raise_for_status()
            self._failure_counts[service] = 0
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)
        except httpx.HTTPError:
            self._failure_counts[service] = self._failure_counts.get(service, 0) + 1
            raise HTTPException(502, "Downstream service error")

    async def close(self):
        await self.client.aclose()


service_client = ServiceClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await service_client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://app.example.com"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health")
    async def health():
        return {{"status": "ok", "service": "gateway"}}

    @app.post("/api/run")
    async def proxy_run(request: Request):
        body = await request.json()
        return await service_client.call(
            settings.API_SERVICE_URL, "POST", "/agents/run",
            json=body,
            headers={{"Authorization": request.headers.get("Authorization", "")}},
        )

    return app


app = create_app()
''')


def gen_gateway_config(name: str) -> str:
    return dedent(f'''\
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "{name}-gateway"
    DEBUG: bool = False
    API_SERVICE_URL: str = "http://api-service:8001"
    JWT_SECRET: str = "change-me-in-production"
    RATE_LIMIT_PER_MINUTE: int = 60


settings = Settings()
''')


def gen_docker_compose(name: str, pkg: str, db: str) -> str:
    db_service = ""
    db_env = ""
    db_depends = ""
    if db == "postgres":
        db_env = f'      DATABASE_URL: postgresql+asyncpg://app:secret@postgres:5432/{pkg}\n'
        db_depends = dedent('''\
    depends_on:
      postgres:
        condition: service_healthy''')
        db_service = dedent(f'''\

  postgres:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: {pkg}
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d {pkg}"]
      interval: 10s
      timeout: 5s
      retries: 5''')
    return dedent(f'''\
# {name} — Docker Compose (Tier 2: Microservices)

services:
  gateway:
    build:
      context: ./gateway
    ports:
      - "8000:8000"
    environment:
      API_SERVICE_URL: http://api-service:8001
      JWT_SECRET: ${{{{JWT_SECRET:-change-me-in-production}}}}
      DEBUG: "false"

  api-service:
    build:
      context: ./services/api-service
    ports:
      - "8001:8000"
{db_depends}
    environment:
{db_env}      REDIS_URL: redis://redis:6379/0
      JWT_SECRET: ${{{{JWT_SECRET:-change-me-in-production}}}}
      ANTHROPIC_API_KEY: ${{{{ANTHROPIC_API_KEY:-}}}}

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
{db_service}
volumes:
  postgres_data:
''')


# --- Tier 3: Enterprise (k8s + event bus) ---

def gen_k8s_deployment(name: str) -> str:
    return dedent(f'''\
# {name} — Kubernetes Deployment + Service
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
      - name: api
        image: registry.example.com/{name}:latest
        ports:
        - containerPort: 8000
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: {name}-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: {name}-secrets
              key: redis-url
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: {name}-secrets
              key: jwt-secret

---

apiVersion: v1
kind: Service
metadata:
  name: {name}
spec:
  selector:
    app: {name}
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP
''')


def gen_event_bus() -> str:
    return dedent('''\
"""Event bus configuration for inter-service communication."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine
from uuid import uuid4

import redis.asyncio as redis


@dataclass
class Event:
    type: str
    data: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventBus:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self._handlers: dict[str, list[Callable]] = {}

    async def publish(self, event: Event):
        await self.redis.publish(event.type, json.dumps({
            "id": event.id,
            "type": event.type,
            "data": event.data,
            "timestamp": event.timestamp,
        }))

    def subscribe(self, event_type: str):
        def decorator(func: Callable[..., Coroutine]):
            self._handlers.setdefault(event_type, []).append(func)
            return func
        return decorator

    async def listen(self):
        pubsub = self.redis.pubsub()
        channels = list(self._handlers.keys())
        if not channels:
            return
        await pubsub.subscribe(*channels)
        async for message in pubsub.listen():
            if message["type"] == "message":
                event_type = message["channel"].decode()
                data = json.loads(message["data"])
                for handler in self._handlers.get(event_type, []):
                    await handler(Event(**data))

    async def close(self):
        await self.redis.aclose()
''')


# --- Scaffolder ---

def _scaffold_service(project: Path, name: str, pkg: str, db: str,
                      agents: bool, service_dir: Path | None = None):
    """Scaffold a single FastAPI service (shared by all tiers)."""
    src = service_dir or (project / "src" / pkg)
    for d in ["routes", "models", "services", "middleware"]:
        (src / d).mkdir(parents=True, exist_ok=True)
        (src / d / "__init__.py").write_text("")
    if db == "postgres":
        (src / "db").mkdir(exist_ok=True)
        (src / "db" / "__init__.py").write_text("")
        (src / "db" / "session.py").write_text(gen_db_session())

    (src / "__init__.py").write_text(f'"""{name} FastAPI service."""\n')
    (src / "main.py").write_text(gen_main(pkg, db, agents))
    (src / "config.py").write_text(gen_config(db))
    (src / "routes" / "health.py").write_text(gen_health())
    if agents:
        (src / "routes" / "agents.py").write_text(gen_agents_route())


def scaffold(name: str, tier: int, output_dir: str, db: str = "postgres",
             auth: str = "jwt", agents: bool = False):
    pkg = to_package(name)
    project = Path(output_dir).resolve() / name

    if project.exists():
        print(f"Error: {project} already exists")
        return None

    if tier == 1:
        # --- Tier 1: Single API ---
        _scaffold_service(project, name, pkg, db, agents)
        (project / "tests").mkdir()
        (project / "pyproject.toml").write_text(gen_pyproject(name, pkg, db, agents))
        (project / ".env.example").write_text(gen_env_example(db))
        (project / "Dockerfile").write_text(gen_dockerfile(pkg))
        (project / "tests" / "__init__.py").write_text("")
        (project / "tests" / "conftest.py").write_text(gen_test_conftest(pkg))
        (project / "tests" / "test_health.py").write_text(gen_test_health())

    elif tier == 2:
        # --- Tier 2: Gateway + Services ---
        # Gateway
        gw_src = project / "gateway" / "src" / f"{pkg}_gateway"
        gw_src.mkdir(parents=True)
        (gw_src / "__init__.py").write_text(f'"""{name} gateway."""\n')
        (gw_src / "main.py").write_text(gen_gateway_main(name))
        (gw_src / "config.py").write_text(gen_gateway_config(name))
        gw_pkg = f"{pkg}_gateway"
        (project / "gateway" / "pyproject.toml").write_text(
            gen_pyproject(f"{name}-gateway", gw_pkg, "none", False))
        (project / "gateway" / "Dockerfile").write_text(gen_dockerfile(gw_pkg))

        # API Service
        svc_src = project / "services" / "api-service" / "src" / f"{pkg}_api"
        _scaffold_service(project, name, f"{pkg}_api", db, agents, service_dir=svc_src)
        svc_pkg = f"{pkg}_api"
        (project / "services" / "api-service" / "pyproject.toml").write_text(
            gen_pyproject(f"{name}-api", svc_pkg, db, agents))
        (project / "services" / "api-service" / "Dockerfile").write_text(gen_dockerfile(svc_pkg))
        (project / "services" / "api-service" / ".env.example").write_text(gen_env_example(db))

        # Tests
        (project / "tests").mkdir()
        (project / "tests" / "__init__.py").write_text("")
        (project / "tests" / "conftest.py").write_text(gen_test_conftest(svc_pkg))
        (project / "tests" / "test_health.py").write_text(gen_test_health())

        # Docker Compose
        (project / "docker-compose.yml").write_text(gen_docker_compose(name, pkg, db))
        (project / ".env.example").write_text(gen_env_example(db))

    elif tier == 3:
        # --- Tier 3: Enterprise (Tier 2 + k8s + event bus) ---
        # Gateway (same as Tier 2)
        gw_src = project / "gateway" / "src" / f"{pkg}_gateway"
        gw_src.mkdir(parents=True)
        (gw_src / "__init__.py").write_text(f'"""{name} gateway."""\n')
        (gw_src / "main.py").write_text(gen_gateway_main(name))
        (gw_src / "config.py").write_text(gen_gateway_config(name))
        gw_pkg = f"{pkg}_gateway"
        (project / "gateway" / "pyproject.toml").write_text(
            gen_pyproject(f"{name}-gateway", gw_pkg, "none", False))
        (project / "gateway" / "Dockerfile").write_text(gen_dockerfile(gw_pkg))

        # API Service
        svc_src = project / "services" / "api-service" / "src" / f"{pkg}_api"
        _scaffold_service(project, name, f"{pkg}_api", db, agents, service_dir=svc_src)
        svc_pkg = f"{pkg}_api"
        (project / "services" / "api-service" / "pyproject.toml").write_text(
            gen_pyproject(f"{name}-api", svc_pkg, db, agents))
        (project / "services" / "api-service" / "Dockerfile").write_text(gen_dockerfile(svc_pkg))
        (project / "services" / "api-service" / ".env.example").write_text(gen_env_example(db))

        # Tests
        (project / "tests").mkdir()
        (project / "tests" / "__init__.py").write_text("")
        (project / "tests" / "conftest.py").write_text(gen_test_conftest(svc_pkg))
        (project / "tests" / "test_health.py").write_text(gen_test_health())

        # Infrastructure
        infra = project / "infrastructure"
        infra.mkdir()
        (infra / "docker-compose.yml").write_text(gen_docker_compose(name, pkg, db))
        k8s = infra / "k8s"
        k8s.mkdir()
        (k8s / "gateway-deployment.yaml").write_text(gen_k8s_deployment(f"{name}-gateway"))
        (k8s / "api-deployment.yaml").write_text(gen_k8s_deployment(f"{name}-api"))

        # Event Bus
        event_bus = project / "event-bus"
        event_bus.mkdir()
        (event_bus / "__init__.py").write_text("")
        (event_bus / "bus.py").write_text(gen_event_bus())

        (project / ".env.example").write_text(gen_env_example(db))

    else:
        print(f"Error: Invalid tier {tier}. Must be 1, 2, or 3.")
        return None

    print(f"Created FastAPI project: {project}")
    print(f"  Tier: {tier} | DB: {db} | Auth: {auth} | Agents: {agents}")
    if tier == 1:
        print(f"\nNext steps:")
        print(f"  cd {project}")
        print(f"  uv sync")
        print(f"  cp .env.example .env")
        print(f"  uv run uvicorn src.{pkg}.main:app --reload")
    elif tier == 2:
        print(f"\nNext steps:")
        print(f"  cd {project}")
        print(f"  cp .env.example .env")
        print(f"  docker compose up -d")
    elif tier == 3:
        print(f"\nNext steps:")
        print(f"  cd {project}")
        print(f"  cp .env.example .env")
        print(f"  docker compose -f infrastructure/docker-compose.yml up -d")
        print(f"  # For k8s: kubectl apply -f infrastructure/k8s/")
    return project


def main():
    if len(sys.argv) < 5 or "--tier" not in sys.argv or "--path" not in sys.argv:
        print(__doc__)
        sys.exit(1)

    name = sys.argv[1]
    tier = int(sys.argv[sys.argv.index("--tier") + 1])
    path = sys.argv[sys.argv.index("--path") + 1]

    db = "postgres"
    auth = "jwt"
    agents = "--agents" in sys.argv
    if "--db" in sys.argv:
        db = sys.argv[sys.argv.index("--db") + 1]
    if "--auth" in sys.argv:
        auth = sys.argv[sys.argv.index("--auth") + 1]

    scaffold(name, tier, path, db, auth, agents)


if __name__ == "__main__":
    main()
