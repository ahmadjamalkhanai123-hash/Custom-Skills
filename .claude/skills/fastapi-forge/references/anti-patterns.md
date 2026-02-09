# Common FastAPI Anti-Patterns

## 1. Sync Database Calls in Async Routes

BAD:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

engine = create_engine("postgresql://localhost/db")

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    with Session(engine) as session:
        return session.query(User).get(user_id)  # blocks the event loop
```

GOOD:
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine("postgresql+asyncpg://localhost/db")
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    async with async_session() as session:
        result = await session.get(User, user_id)
        return result
```

## 2. No Connection Pooling

BAD:
```python
engine = create_async_engine("postgresql+asyncpg://localhost/db")
```

GOOD:
```python
engine = create_async_engine(
    "postgresql+asyncpg://localhost/db",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)
```

## 3. Agent Execution in Request Thread

BAD:
```python
@app.post("/agents/run")
async def run_agent(request: AgentRunRequest):
    result = await call_llm(request.input_text)  # 30+ seconds, blocks response
    return {"output": result}
```

GOOD:
```python
from fastapi import BackgroundTasks
import uuid

@app.post("/agents/run", status_code=202)
async def run_agent(request: AgentRunRequest, background_tasks: BackgroundTasks):
    run_id = str(uuid.uuid4())
    background_tasks.add_task(execute_agent_async, run_id, request)
    return {"run_id": run_id, "status": "pending", "poll_url": f"/agents/runs/{run_id}"}

@app.get("/agents/runs/{run_id}")
async def get_run_status(run_id: str):
    status = await get_status_from_store(run_id)
    return status
```

## 4. No Rate Limiting

BAD:
```python
@app.post("/agents/run")
async def run_agent(request: AgentRunRequest):
    return await execute(request)  # no throttling, LLM API costs spike
```

GOOD:
```python
from collections import defaultdict
import time

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.rpm = requests_per_minute
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request, call_next):
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        self._requests[ip] = [t for t in self._requests[ip] if t > now - 60]
        if len(self._requests[ip]) >= self.rpm:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        self._requests[ip].append(now)
        return await call_next(request)

app.add_middleware(RateLimitMiddleware, requests_per_minute=30)
```

## 5. Raw Exceptions Returned to Client

BAD:
```python
@app.post("/agents/run")
async def run_agent(request: AgentRunRequest):
    result = await execute(request)  # raises KeyError, ValueError, etc.
    return result  # unhandled exceptions leak stack traces
```

GOOD:
```python
from fastapi import HTTPException
from fastapi.responses import JSONResponse

class AgentError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code

@app.exception_handler(AgentError)
async def agent_error_handler(request, exc: AgentError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "type": "agent_error"},
    )

@app.exception_handler(Exception)
async def generic_error_handler(request, exc: Exception):
    logger.error("unhandled_error", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "type": "internal_error"},
    )
```

## 6. No Health Checks

BAD:
```python
app = FastAPI()
# no health endpoint — K8s, load balancers, and monitoring have nothing to probe
```

GOOD:
```python
@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/ready")
async def readiness():
    checks = {}
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )
```

## 7. CORS allow_origins=["*"]

BAD:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allows any website to make requests
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

GOOD:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com", "https://admin.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

## 8. No Request Validation

BAD:
```python
@app.post("/agents/run")
async def run_agent(request: dict):  # accepts anything
    agent_id = request.get("agent_id", "")
    input_text = request.get("input_text", "")
    return await execute(agent_id, input_text)
```

GOOD:
```python
from pydantic import BaseModel, Field, field_validator

class AgentRunRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    input_text: str = Field(..., min_length=1, max_length=50000)

    @field_validator("input_text")
    @classmethod
    def sanitize(cls, v: str) -> str:
        return v.replace("\x00", "").strip()

@app.post("/agents/run")
async def run_agent(request: AgentRunRequest):
    return await execute(request.agent_id, request.input_text)
```

## 9. Single Uvicorn Worker

BAD:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# runs 1 worker — underutilizes multi-core servers
```

GOOD:
```bash
gunicorn app.main:app \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 120 \
    --graceful-timeout 30
```

## 10. No Graceful Shutdown

BAD:
```python
app = FastAPI()
db_engine = create_async_engine(DATABASE_URL)
# engine, connections, and clients are never cleaned up on shutdown
```

GOOD:
```python
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(DATABASE_URL, pool_size=20)
    redis = Redis.from_url(REDIS_URL)
    app.state.db_engine = engine
    app.state.redis = redis
    yield
    await redis.aclose()
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
```

## 11. Using print() for Logging

BAD:
```python
@app.post("/agents/run")
async def run_agent(request: AgentRunRequest):
    print(f"Running agent {request.agent_id}")  # no structure, no level, lost in stdout
    result = await execute(request)
    print(f"Agent done: {result.status}")
    return result
```

GOOD:
```python
import structlog

logger = structlog.get_logger()

@app.post("/agents/run")
async def run_agent(request: AgentRunRequest):
    logger.info("agent_started", agent_id=request.agent_id)
    result = await execute(request)
    logger.info(
        "agent_completed",
        agent_id=request.agent_id,
        status=result.status,
        tokens=result.token_usage,
        duration_ms=result.duration_ms,
    )
    return result
```

## 12. No Circuit Breaker on External Calls

BAD:
```python
import httpx

async def call_downstream_service(payload: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post("http://other-service/api", json=payload)
        return response.json()
    # if other-service is down, every request hangs and fails
```

GOOD:
```python
from enum import Enum
from datetime import datetime, timedelta


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: datetime | None = None

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN and self.last_failure_time:
            if datetime.utcnow() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = CircuitState.HALF_OPEN
                return True
        return self.state == CircuitState.HALF_OPEN

    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN


breaker = CircuitBreaker()

async def call_downstream_service(payload: dict):
    if not breaker.can_execute():
        raise ConnectionError("Circuit breaker is OPEN — downstream service unavailable")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post("http://other-service/api", json=payload)
            response.raise_for_status()
            breaker.record_success()
            return response.json()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
        breaker.record_failure()
        raise ConnectionError(f"Downstream call failed: {exc}") from exc
```
