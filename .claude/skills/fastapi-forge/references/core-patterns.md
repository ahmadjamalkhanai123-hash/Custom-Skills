# Core Patterns

App factory, Pydantic Settings, dependency injection, async database.

---

## App Factory

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .config import settings
from .routes import agents, health
from .middleware.auth import AuthMiddleware
from .middleware.logging import RequestLoggingMiddleware
from .db.session import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
    )

    # Middleware (outermost first)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(AuthMiddleware)

    # Routes
    app.include_router(health.router, tags=["health"])
    app.include_router(agents.router, prefix="/agents", tags=["agents"])

    return app


app = create_app()
```

---

## Pydantic Settings

```python
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

---

## Dependency Injection

```python
from fastapi import Depends, Request, HTTPException
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

---

## Async Database (SQLAlchemy 2.0)

```python
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
        pass  # Use Alembic migrations in production


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

---

## Pydantic Schemas

```python
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

---

## Health Check

```python
from fastapi import APIRouter, Depends
from sqlalchemy import text
from ..db.session import get_db

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db=Depends(get_db)):
    checks = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "failed"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
```
