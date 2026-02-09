"""{{PROJECT_NAME}} — Production FastAPI Application.

{{PROJECT_DESCRIPTION}}
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


# --- Config ---

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "{{PROJECT_NAME}}"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/db"
    DB_POOL_SIZE: int = 20
    JWT_SECRET: str = "change-me-in-production"
    RATE_LIMIT_PER_MINUTE: int = 60

settings = Settings()


# --- Database ---

engine = create_async_engine(settings.DATABASE_URL, pool_size=settings.DB_POOL_SIZE)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# --- Schemas ---

class HealthResponse(BaseModel):
    status: str
    checks: dict | None = None


class {{RESOURCE_NAME}}Request(BaseModel):
    """Request model — customize fields for your domain."""
    name: str = Field(..., min_length=1, max_length=200)
    data: dict | None = None


class {{RESOURCE_NAME}}Response(BaseModel):
    """Response model — customize fields for your domain."""
    id: str
    name: str
    status: str


# --- App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins={{ALLOWED_ORIGINS}},
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # --- Health ---

    @app.get("/health", response_model=HealthResponse)
    async def health():
        return {"status": "ok"}

    @app.get("/health/ready", response_model=HealthResponse)
    async def readiness(db: AsyncSession = Depends(get_db)):
        checks = {}
        try:
            await db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "failed"
        all_ok = all(v == "ok" for v in checks.values())
        return {"status": "ok" if all_ok else "degraded", "checks": checks}

    # --- Routes ---

    @app.post("/{{RESOURCE_PATH}}", response_model={{RESOURCE_NAME}}Response)
    async def create_resource(
        request: {{RESOURCE_NAME}}Request,
        db: AsyncSession = Depends(get_db),
    ):
        """Create a new resource."""
        import uuid
        resource_id = str(uuid.uuid4())
        # TODO: Save to database
        return {{RESOURCE_NAME}}Response(
            id=resource_id,
            name=request.name,
            status="created",
        )

    @app.get("/{{RESOURCE_PATH}}/{resource_id}", response_model={{RESOURCE_NAME}}Response)
    async def get_resource(
        resource_id: str,
        db: AsyncSession = Depends(get_db),
    ):
        """Get a resource by ID."""
        # TODO: Fetch from database
        raise HTTPException(404, "Resource not found")

    return app


app = create_app()
