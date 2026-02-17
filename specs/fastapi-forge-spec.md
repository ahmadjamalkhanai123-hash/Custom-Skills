# FastAPI Forge — Production Skill Spec

## Spec Metadata

| Field | Value |
|-------|-------|
| **Skill Name** | `fastapi-forge` |
| **Type** | Builder |
| **Domain** | FastAPI — Multi-Agent Orchestration, Microservices, Large-Scale Systems |
| **Target Score** | 90+ (Production) |
| **Pattern** | Follows mcp-skills / hybrid-sdk-agents structure |

---

## 1. Purpose & Scope

### What This Skill Creates

Production-ready FastAPI applications for three tiers:

| Tier | Scale | Architecture |
|------|-------|-------------|
| **Agent Backend** | Single service | FastAPI serving AI agents via REST/WebSocket/SSE |
| **Microservice** | Multi-service | Domain-bounded FastAPI services with async messaging |
| **Large System** | Enterprise-scale | Event-driven architecture, CQRS, service mesh, multi-region |

### What This Skill Does

- Scaffolds FastAPI projects at any tier (single API → enterprise system)
- Builds multi-agent orchestration endpoints (REST + WebSocket + SSE streaming)
- Creates microservice architectures with async inter-service communication
- Implements production patterns: auth, rate limiting, observability, circuit breakers
- Generates database integration (async SQLAlchemy, Redis, MongoDB)
- Configures deployment (Docker, K8s, Cloud Run, Serverless)
- Handles background task processing for long-running agent jobs

### What This Skill Does NOT Do

- Build frontend UIs (only API layer)
- Create MCP servers (use `mcp-skills` for that)
- Build the agents themselves (use `hybrid-sdk-agents` for that)
- Manage cloud infrastructure provisioning (scaffolds configs only)
- Handle DNS, SSL certificates, or domain management

---

## 2. Required Clarifications

### Must Ask

1. **Application Type**: "What are you building?"
   - Agent orchestration API (serve AI agents over HTTP)
   - REST/GraphQL microservice (domain-specific service)
   - Multi-service system (multiple coordinated services)
   - Real-time streaming backend (WebSocket/SSE for agent responses)

2. **Scale Tier**: "What scale?"
   - Single API (1 service, <100 req/s)
   - Multi-service (2-10 services, <1K req/s)
   - Enterprise (10+ services, 1K+ req/s, multi-region)

3. **Database**: "What storage?"
   - PostgreSQL (Recommended — async SQLAlchemy)
   - MongoDB (async Motor)
   - Redis (caching + pub/sub)
   - None (stateless API)
   - Multiple (polyglot persistence)

### Optional (Ask Based on Context)

4. **Auth**: "Authentication method?"
   - JWT Bearer tokens (default)
   - OAuth2 / OIDC
   - API Key
   - None (internal service)

5. **Agent Framework**: "Which agent SDK will this serve?"
   - Anthropic Agent SDK
   - OpenAI Agents SDK
   - LangGraph
   - CrewAI
   - Custom / Multiple
   - None (pure API, no agents)

6. **Deployment Target**: "Where will this deploy?"
   - Docker Compose (local/team) — default
   - Kubernetes (production)
   - Cloud Run / ECS (managed)
   - Serverless (Lambda + Mangum)

### Defaults (If Not Specified)

| Clarification | Default |
|---------------|---------|
| Application Type | Infer from conversation |
| Scale Tier | Single API |
| Database | PostgreSQL (async) |
| Auth | JWT Bearer |
| Agent Framework | Anthropic Agent SDK |
| Deployment | Docker Compose |
| Python Version | 3.12+ |
| Package Manager | uv |

---

## 3. SDK/Library Versions (February 2026)

| Library | Version | Purpose |
|---------|---------|---------|
| FastAPI | >=0.115.0 | Web framework |
| Uvicorn | >=0.32.0 | ASGI server |
| Pydantic | >=2.10.0 | Data validation |
| SQLAlchemy | >=2.0.36 | Async ORM |
| asyncpg | >=0.30.0 | PostgreSQL async driver |
| Redis (redis-py) | >=5.2.0 | Cache + pub/sub |
| httpx | >=0.28.0 | Async HTTP client |
| Celery / ARQ | >=5.4.0 / >=0.26 | Background tasks |
| Pydantic-Settings | >=2.6.0 | Config management |
| python-jose | >=3.3.0 | JWT handling |
| Prometheus-client | >=0.21.0 | Metrics |
| structlog | >=24.4.0 | Structured logging |
| pytest-asyncio | >=0.24.0 | Async testing |
| Alembic | >=1.14.0 | Database migrations |

---

## 4. Architecture Patterns (Reference Content)

### Pattern 1: Agent Orchestration API

```
Client (Web/Mobile/CLI)
    ↓ REST/WebSocket/SSE
┌─────────────────────────┐
│   FastAPI Gateway        │
│  ├─ /agents/run (POST)  │ ← Trigger agent execution
│  ├─ /agents/stream (WS) │ ← Real-time agent output
│  ├─ /agents/status (GET)│ ← Check job status
│  └─ /agents/cancel (DEL)│ ← Cancel running agent
└─────────┬───────────────┘
          ↓
┌─────────────────────────┐
│   Agent Execution Layer  │
│  ├─ Anthropic Agent SDK │
│  ├─ OpenAI Agents SDK   │
│  ├─ LangGraph           │
│  └─ CrewAI              │
└─────────┬───────────────┘
          ↓
┌─────────────────────────┐
│   Infrastructure         │
│  ├─ PostgreSQL (state)  │
│  ├─ Redis (cache/queue) │
│  └─ S3/GCS (artifacts)  │
└─────────────────────────┘
```

### Pattern 2: Microservices

```
API Gateway (FastAPI)
    ├─ /users     → User Service (FastAPI + PostgreSQL)
    ├─ /orders    → Order Service (FastAPI + PostgreSQL)
    ├─ /agents    → Agent Service (FastAPI + Redis)
    └─ /notify    → Notification Service (FastAPI + RabbitMQ)

Inter-service: async messaging (Redis Pub/Sub / RabbitMQ / Kafka)
Service discovery: K8s DNS / Consul
```

### Pattern 3: Large-Scale System (CQRS + Event-Driven)

```
                    ┌─ Command API (FastAPI) ──→ Write DB
Client ──→ Gateway ─┤
                    └─ Query API (FastAPI)  ──→ Read DB (replica/cache)

Events: Kafka / Redis Streams
        ↓
┌─────────────────────┐
│ Event Consumers      │
│ ├─ Projection Worker │ ← Updates read models
│ ├─ Agent Worker      │ ← Triggers agent workflows
│ └─ Notification      │ ← Sends alerts
└─────────────────────┘
```

---

## 5. Project Structures (Reference Content)

### Tier 1: Single API

```
{project}/
├── src/{package}/
│   ├── __init__.py
│   ├── main.py              ← FastAPI app factory
│   ├── config.py            ← Pydantic Settings
│   ├── dependencies.py      ← Dependency injection
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── agents.py        ← Agent orchestration endpoints
│   │   └── health.py        ← Health check
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py       ← Pydantic request/response models
│   │   └── database.py      ← SQLAlchemy models
│   ├── services/
│   │   ├── __init__.py
│   │   └── agent_service.py ← Business logic
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py          ← JWT/API key auth
│   │   ├── rate_limit.py    ← Rate limiting
│   │   └── logging.py       ← Request logging
│   └── db/
│       ├── __init__.py
│       ├── session.py       ← Async session factory
│       └── migrations/      ← Alembic
├── tests/
│   ├── conftest.py          ← Fixtures, test client
│   ├── test_agents.py
│   └── test_health.py
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── alembic.ini
```

### Tier 2: Multi-Service

```
{system}/
├── gateway/                 ← API Gateway (FastAPI)
│   ├── src/gateway/
│   └── Dockerfile
├── services/
│   ├── agent-service/       ← Agent orchestration
│   │   ├── src/agent_service/
│   │   └── Dockerfile
│   ├── user-service/        ← User management
│   │   ├── src/user_service/
│   │   └── Dockerfile
│   └── notification-service/
│       ├── src/notification_service/
│       └── Dockerfile
├── shared/
│   └── common/              ← Shared models, utils
│       ├── schemas.py
│       └── events.py
├── docker-compose.yml       ← Full system
├── docker-compose.dev.yml   ← Dev overrides
└── k8s/                     ← Kubernetes manifests
    ├── gateway.yaml
    ├── agent-service.yaml
    └── ingress.yaml
```

### Tier 3: Enterprise

```
(Same as Tier 2 + additions)
├── infrastructure/
│   ├── terraform/           ← IaC
│   ├── helm/                ← Helm charts
│   └── monitoring/
│       ├── prometheus.yml
│       ├── grafana/
│       └── alerts.yml
├── event-bus/
│   └── kafka-config/
├── docs/
│   ├── architecture.md
│   ├── api-spec.yaml        ← OpenAPI
│   └── runbook.md
```

---

## 6. Core Implementation Patterns (Reference Content)

### 6.1 App Factory

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .config import settings
from .routes import agents, health
from .middleware.auth import AuthMiddleware
from .middleware.logging import RequestLoggingMiddleware
from .db.session import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
    )

    # Middleware (order matters — outermost first)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(AuthMiddleware)

    # Routes
    app.include_router(health.router, tags=["health"])
    app.include_router(agents.router, prefix="/agents", tags=["agents"])

    return app


app = create_app()
```

### 6.2 Config (Pydantic Settings)

```python
# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "fastapi-service"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 30

    # Agent
    ANTHROPIC_API_KEY: str = ""
    AGENT_MAX_TURNS: int = 15
    AGENT_TIMEOUT_SECONDS: int = 300

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60


settings = Settings()
```

### 6.3 Agent Orchestration Endpoints

```python
# routes/agents.py
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from starlette.websockets import WebSocket, WebSocketDisconnect
from ..models.schemas import AgentRequest, AgentResponse, AgentStatus
from ..services.agent_service import AgentService
from ..dependencies import get_agent_service, get_current_user

router = APIRouter()


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    request: AgentRequest,
    service: AgentService = Depends(get_agent_service),
    user=Depends(get_current_user),
):
    """Run agent synchronously — waits for completion."""
    try:
        result = await asyncio.wait_for(
            service.execute(request, user_id=user.id),
            timeout=request.timeout or 300,
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(408, "Agent execution timed out")


@router.post("/run/async", response_model=AgentStatus)
async def run_agent_async(
    request: AgentRequest,
    background_tasks: BackgroundTasks,
    service: AgentService = Depends(get_agent_service),
    user=Depends(get_current_user),
):
    """Run agent asynchronously — returns job ID immediately."""
    job = await service.create_job(request, user_id=user.id)
    background_tasks.add_task(service.execute_job, job.id)
    return AgentStatus(job_id=job.id, status="queued")


@router.get("/run/stream")
async def stream_agent(
    prompt: str,
    service: AgentService = Depends(get_agent_service),
    user=Depends(get_current_user),
):
    """Stream agent output via Server-Sent Events (SSE)."""
    async def event_generator():
        async for chunk in service.stream(prompt, user_id=user.id):
            yield f"data: {chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.websocket("/ws")
async def agent_websocket(
    websocket: WebSocket,
    service: AgentService = Depends(get_agent_service),
):
    """WebSocket for bidirectional agent communication."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            async for chunk in service.stream(data["prompt"]):
                await websocket.send_json(chunk.model_dump())
            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass


@router.get("/jobs/{job_id}", response_model=AgentStatus)
async def get_job_status(
    job_id: str,
    service: AgentService = Depends(get_agent_service),
):
    """Check async agent job status."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    service: AgentService = Depends(get_agent_service),
):
    """Cancel a running agent job."""
    await service.cancel_job(job_id)
    return {"status": "cancelled"}
```

### 6.4 Pydantic Schemas

```python
# models/schemas.py
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class AgentSDK(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    LANGGRAPH = "langgraph"
    CREWAI = "crewai"


class AgentRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=50000)
    sdk: AgentSDK = AgentSDK.ANTHROPIC
    model: str = "claude-sonnet-4-5-20250929"
    max_turns: int = Field(default=15, ge=1, le=100)
    timeout: int = Field(default=300, ge=10, le=3600)
    tools: list[str] = Field(default=["Read", "Grep", "Glob"])
    system_prompt: str | None = None
    metadata: dict | None = None


class AgentResponse(BaseModel):
    result: str
    steps: int
    tokens_used: int
    duration_seconds: float
    model: str
    tools_called: list[str]


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStatus(BaseModel):
    job_id: str
    status: JobStatus
    result: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)


class AgentStreamChunk(BaseModel):
    type: str  # "text", "tool_call", "tool_result", "error"
    content: str
    metadata: dict | None = None
```

### 6.5 Async Database (SQLAlchemy 2.0)

```python
# db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from ..config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        # Create tables (use Alembic in production)
        pass


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
```

### 6.6 Middleware Stack

```python
# middleware/auth.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
from ..config import settings

PUBLIC_PATHS = {"/health", "/docs", "/openapi.json"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not token:
            raise HTTPException(401, "Missing authorization token")

        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            request.state.user_id = payload["sub"]
        except JWTError:
            raise HTTPException(401, "Invalid token")

        return await call_next(request)
```

```python
# middleware/rate_limit.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
from time import time
from ..config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        now = time()
        window = 60

        # Clean old entries
        self.requests[client_ip] = [
            t for t in self.requests[client_ip] if t > now - window
        ]

        if len(self.requests[client_ip]) >= settings.RATE_LIMIT_PER_MINUTE:
            raise HTTPException(429, "Rate limit exceeded")

        self.requests[client_ip].append(now)
        return await call_next(request)
```

### 6.7 Dependency Injection

```python
# dependencies.py
from fastapi import Depends, Request
from .services.agent_service import AgentService
from .db.session import get_db, AsyncSession


async def get_current_user(request: Request):
    """Extract user from auth middleware state."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    return {"id": user_id}


async def get_agent_service(db: AsyncSession = Depends(get_db)) -> AgentService:
    return AgentService(db=db)
```

### 6.8 Inter-Service Communication (Microservices)

```python
# services/service_client.py
import httpx
from ..config import settings


class ServiceClient:
    """Async HTTP client for inter-service calls with circuit breaker."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self._failure_counts: dict[str, int] = {}
        self._circuit_open: dict[str, float] = {}

    async def call(self, service: str, method: str, path: str, **kwargs) -> dict:
        url = f"{settings.SERVICE_URLS[service]}{path}"

        # Circuit breaker check
        if self._is_circuit_open(service):
            raise ServiceUnavailableError(f"{service} circuit is open")

        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            self._reset_failures(service)
            return response.json()
        except httpx.HTTPError as e:
            self._record_failure(service)
            raise ServiceCallError(f"{service} call failed: {e}")

    def _is_circuit_open(self, service: str) -> bool:
        return self._failure_counts.get(service, 0) >= 5

    def _record_failure(self, service: str):
        self._failure_counts[service] = self._failure_counts.get(service, 0) + 1

    def _reset_failures(self, service: str):
        self._failure_counts[service] = 0
```

### 6.9 Background Task Processing

```python
# services/task_queue.py
from arq import create_pool
from arq.connections import RedisSettings
from ..config import settings


async def get_redis_pool():
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))


async def execute_agent_job(ctx, job_id: str):
    """ARQ worker function for async agent execution."""
    db = ctx["db"]
    job = await db.get_job(job_id)

    try:
        await db.update_job_status(job_id, "running")
        result = await run_agent(job.prompt, job.sdk, job.tools)
        await db.complete_job(job_id, result)
    except Exception as e:
        await db.fail_job(job_id, str(e))


class WorkerSettings:
    functions = [execute_agent_job]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
```

### 6.10 Health Check

```python
# routes/health.py
from fastapi import APIRouter, Depends
from ..db.session import get_db

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db=Depends(get_db)):
    """Checks all dependencies are available."""
    checks = {}
    try:
        await db.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "failed"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
```

---

## 7. Observability Patterns (Reference Content)

### Structured Logging

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()

# Usage in routes/services
logger.info("agent_execution_started", prompt_length=len(prompt), sdk=sdk)
logger.info("agent_execution_completed", steps=steps, tokens=tokens, duration=duration)
logger.error("agent_execution_failed", error=str(e), job_id=job_id)
```

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

REQUESTS_TOTAL = Counter("http_requests_total", "Total requests", ["method", "endpoint", "status"])
REQUEST_DURATION = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"])
AGENT_EXECUTIONS = Counter("agent_executions_total", "Agent runs", ["sdk", "status"])
AGENT_DURATION = Histogram("agent_execution_seconds", "Agent execution time", ["sdk"])
ACTIVE_AGENTS = Gauge("active_agent_executions", "Currently running agents")
TOKEN_USAGE = Counter("agent_tokens_total", "Tokens consumed", ["sdk", "model"])
```

### OpenTelemetry Integration

```python
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

tracer = trace.get_tracer("fastapi-service")
FastAPIInstrumentor.instrument_app(app)
```

---

## 8. Deployment Patterns (Reference Content)

### Dockerfile

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app

FROM base AS deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

FROM deps AS runtime
COPY src/ src/
EXPOSE 8000
CMD ["uvicorn", "src.{package}.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Docker Compose (Multi-Service)

```yaml
services:
  gateway:
    build: ./gateway
    ports: ["8000:8000"]
    depends_on: [postgres, redis]
    environment:
      DATABASE_URL: postgresql+asyncpg://user:pass@postgres:5432/db
      REDIS_URL: redis://redis:6379/0

  agent-service:
    build: ./services/agent-service
    depends_on: [postgres, redis]
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}

  worker:
    build: ./services/agent-service
    command: arq src.agent_service.services.task_queue.WorkerSettings
    depends_on: [redis]

  postgres:
    image: postgres:16-alpine
    volumes: [postgres_data:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: db
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass

  redis:
    image: redis:7-alpine

volumes:
  postgres_data:
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-service
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: api
        image: fastapi-service:latest
        ports:
        - containerPort: 8000
        resources:
          requests: { memory: "512Mi", cpu: "250m" }
          limits: { memory: "2Gi", cpu: "1000m" }
        readinessProbe:
          httpGet: { path: /health/ready, port: 8000 }
        livenessProbe:
          httpGet: { path: /health, port: 8000 }
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef: { name: db-secret, key: url }
```

---

## 9. Testing Patterns (Reference Content)

### Async Test Client

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from src.{package}.main import create_app

@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def auth_client(client):
    """Client with valid JWT token."""
    token = create_test_token(user_id="test-user")
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
```

### Endpoint Tests

```python
# tests/test_agents.py
import pytest

@pytest.mark.asyncio
async def test_run_agent(auth_client):
    response = await auth_client.post("/agents/run", json={
        "prompt": "Hello",
        "sdk": "anthropic",
        "max_turns": 5,
    })
    assert response.status_code == 200
    data = response.json()
    assert "result" in data

@pytest.mark.asyncio
async def test_run_agent_unauthorized(client):
    response = await client.post("/agents/run", json={"prompt": "Hello"})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_rate_limit(auth_client):
    for _ in range(61):
        await auth_client.get("/agents/jobs/test")
    response = await auth_client.get("/agents/jobs/test")
    assert response.status_code == 429
```

---

## 10. Security Patterns (Reference Content)

### CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # Never ["*"] in production
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)
```

### Input Sanitization

```python
from pydantic import field_validator

class AgentRequest(BaseModel):
    prompt: str

    @field_validator("prompt")
    @classmethod
    def sanitize_prompt(cls, v: str) -> str:
        if len(v) > 50000:
            raise ValueError("Prompt too long")
        # Strip null bytes and control characters
        return v.replace("\x00", "").strip()
```

### Secret Management

```
NEVER: Hardcoded in source code
NEVER: In docker-compose.yml committed to git
OK:    .env file (gitignored) for local dev
GOOD:  K8s Secrets / AWS Secrets Manager / Vault for production
```

---

## 11. Anti-Patterns (Reference Content)

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Sync DB calls in async routes | Blocks event loop | Use async SQLAlchemy/Motor |
| No connection pooling | DB connection exhaustion | Configure pool_size, max_overflow |
| Agent execution in request thread | Timeout on long tasks | Use background tasks (ARQ/Celery) |
| No rate limiting | API abuse, cost explosion | Add per-user rate limiting middleware |
| Returning raw exceptions | Leaks internals | Return structured error responses |
| No health checks | K8s can't manage pods | Add /health and /health/ready |
| Hardcoded CORS: ["*"] | Security vulnerability | Whitelist specific origins |
| No request validation | Injection attacks | Use Pydantic models for all inputs |
| Single Uvicorn worker | Can't use multiple cores | --workers N or Gunicorn + Uvicorn |
| No graceful shutdown | Lost in-flight requests | Use lifespan context manager |
| print() for logging | Unstructured, lost in prod | Use structlog with JSON output |
| No circuit breaker | Cascading failures | Implement circuit breaker for service calls |

---

## 12. Output Specification

### Required Components

- [ ] FastAPI app with lifespan context manager
- [ ] Pydantic Settings for all configuration
- [ ] Typed Pydantic schemas for all request/response models
- [ ] Async database session management
- [ ] Authentication middleware (JWT or API key)
- [ ] Rate limiting middleware
- [ ] Health check endpoints (/health, /health/ready)
- [ ] Structured logging (structlog)
- [ ] Error handling with structured responses

### Required for Agent Orchestration

- [ ] POST /agents/run — synchronous execution
- [ ] POST /agents/run/async — background job
- [ ] GET /agents/run/stream — SSE streaming
- [ ] WebSocket /agents/ws — bidirectional
- [ ] GET /agents/jobs/{id} — job status
- [ ] DELETE /agents/jobs/{id} — cancel job
- [ ] Agent timeout handling
- [ ] Token usage tracking

### Required for Microservices

- [ ] Service client with circuit breaker
- [ ] Async inter-service communication
- [ ] Shared schema package
- [ ] Docker Compose for full system
- [ ] Service-specific health checks

---

## 13. Output Checklist

### Architecture
- [ ] Tier appropriate for scale requirements
- [ ] App factory pattern (create_app)
- [ ] Lifespan context manager for startup/shutdown
- [ ] Dependency injection for services and DB

### Code Quality
- [ ] All routes use Pydantic models for input/output
- [ ] All DB operations are async
- [ ] No hardcoded secrets
- [ ] Structured error responses (never raw exceptions)
- [ ] Type hints on all functions

### Security
- [ ] Auth middleware on all non-public routes
- [ ] Rate limiting configured
- [ ] CORS properly restricted
- [ ] Input validation via Pydantic
- [ ] Secrets via environment variables

### Observability
- [ ] Structured logging (structlog/JSON)
- [ ] Prometheus metrics exported
- [ ] Health check endpoints
- [ ] Request tracing (OpenTelemetry)

### Deployment
- [ ] Dockerfile with multi-stage build
- [ ] docker-compose.yml for local dev
- [ ] .env.example with all variables
- [ ] pyproject.toml with correct dependencies
- [ ] K8s manifests if enterprise tier

### Testing
- [ ] Async test client configured
- [ ] Tests for all endpoints
- [ ] Auth test coverage (valid/invalid/missing)
- [ ] Rate limit test

---

## 14. Skill Structure (For skill-creator-pro)

```
fastapi-forge/
├── SKILL.md                              ← <500 lines, workflow + decision trees
├── references/
│   ├── architecture-patterns.md          ← Tier 1/2/3 architectures (from Section 4)
│   ├── core-patterns.md                  ← App factory, config, DI, DB (from Section 6)
│   ├── agent-orchestration.md            ← REST/WS/SSE endpoints (from Section 6.3)
│   ├── microservice-patterns.md          ← Service client, messaging (from Section 6.8)
│   ├── middleware-patterns.md            ← Auth, rate limit, logging (from Section 6.6)
│   ├── observability.md                  ← Logging, metrics, tracing (from Section 7)
│   ├── deployment.md                     ← Docker, K8s, serverless (from Section 8)
│   ├── testing-patterns.md              ← Async tests, fixtures (from Section 9)
│   ├── security.md                       ← CORS, sanitization, secrets (from Section 10)
│   └── anti-patterns.md                 ← Common mistakes + fixes (from Section 11)
├── assets/templates/
│   ├── single_api.py                    ← Tier 1 starter (complete runnable app)
│   ├── agent_routes.py                  ← Agent orchestration endpoints template
│   ├── microservice_gateway.py          ← Tier 2 gateway template
│   ├── docker_compose.yml               ← Multi-service compose template
│   └── k8s_deployment.yaml             ← Kubernetes manifest template
└── scripts/
    └── scaffold_fastapi.py              ← Project generator for all 3 tiers
```

---

## 15. Official Documentation Links

| Resource | URL |
|----------|-----|
| FastAPI Docs | https://fastapi.tiangolo.com |
| Pydantic V2 | https://docs.pydantic.dev/latest/ |
| SQLAlchemy 2.0 Async | https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html |
| Uvicorn | https://www.uvicorn.org |
| ARQ (async Redis queue) | https://arq-docs.helpmanual.io |
| Alembic | https://alembic.sqlalchemy.org |
| structlog | https://www.structlog.org |
| httpx | https://www.python-httpx.org |
| OpenTelemetry Python | https://opentelemetry.io/docs/languages/python/ |
| Prometheus Python | https://prometheus.github.io/client_python/ |

---

*Spec version: 1.0 — February 2026*
*Target: skill-creator-pro → fastapi-forge skill*
