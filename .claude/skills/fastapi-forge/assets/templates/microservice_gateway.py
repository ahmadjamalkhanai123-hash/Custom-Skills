"""{{SYSTEM_NAME}} API Gateway — Routes requests to downstream services.

Central entry point for the microservice system. Handles auth, rate limiting,
and proxies requests to domain-specific services.
"""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict


# --- Config ---

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "{{SYSTEM_NAME}}-gateway"
    DEBUG: bool = False

    # Downstream service URLs
    AGENT_SERVICE_URL: str = "http://agent-service:8001"
    USER_SERVICE_URL: str = "http://user-service:8002"
    NOTIFICATION_SERVICE_URL: str = "http://notification-service:8003"

    # Auth
    JWT_SECRET: str = "change-me-in-production"
    RATE_LIMIT_PER_MINUTE: int = 60

settings = Settings()


# --- Service Client with Circuit Breaker ---

class ServiceClient:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self._failure_counts: dict[str, int] = {}
        self._threshold = 5

    async def call(self, base_url: str, method: str, path: str, **kwargs) -> dict:
        service = base_url
        if self._failure_counts.get(service, 0) >= self._threshold:
            raise HTTPException(503, f"Service temporarily unavailable")

        try:
            response = await self.client.request(method, f"{base_url}{path}", **kwargs)
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


# --- App ---

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
        allow_origins={{ALLOWED_ORIGINS}},
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # --- Health ---

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "gateway"}

    # --- Agent Service Proxy ---

    @app.post("/agents/run")
    async def proxy_agent_run(request: Request):
        body = await request.json()
        return await service_client.call(
            settings.AGENT_SERVICE_URL, "POST", "/agents/run",
            json=body,
            headers={"Authorization": request.headers.get("Authorization", "")},
        )

    @app.post("/agents/run/async")
    async def proxy_agent_async(request: Request):
        body = await request.json()
        return await service_client.call(
            settings.AGENT_SERVICE_URL, "POST", "/agents/run/async",
            json=body,
            headers={"Authorization": request.headers.get("Authorization", "")},
        )

    @app.get("/agents/jobs/{job_id}")
    async def proxy_agent_job(job_id: str, request: Request):
        return await service_client.call(
            settings.AGENT_SERVICE_URL, "GET", f"/agents/jobs/{job_id}",
            headers={"Authorization": request.headers.get("Authorization", "")},
        )

    # --- User Service Proxy ---

    @app.get("/users/{user_id}")
    async def proxy_user(user_id: str, request: Request):
        return await service_client.call(
            settings.USER_SERVICE_URL, "GET", f"/users/{user_id}",
            headers={"Authorization": request.headers.get("Authorization", "")},
        )

    return app


app = create_app()
