# Middleware Patterns

## Auth Middleware (JWT Bearer)

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from jose import jwt, JWTError
import os

PUBLIC_PATHS = {
    "/health",
    "/healthz",
    "/ready",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.secret_key = os.environ["JWT_SECRET_KEY"]
        self.algorithm = os.getenv("JWT_ALGORITHM", "HS256")

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"},
            )

        token = auth_header.removeprefix("Bearer ").strip()
        try:
            payload = jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm]
            )
            request.state.user_id = payload.get("sub")
            request.state.scopes = payload.get("scopes", [])
        except JWTError as exc:
            return JSONResponse(
                status_code=401,
                content={"detail": f"Invalid token: {exc}"},
            )

        return await call_next(request)
```

## Rate Limit Middleware (Per-IP Sliding Window)

> **Note**: This in-memory implementation is suitable for **development and single-worker deployments only**.
> With `--workers N`, each worker has its own dict, so a user gets N times the actual rate limit.
> For production multi-worker deployments, use Redis-backed rate limiting (e.g., `slowapi` or a custom Redis sliding window).

```python
import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

PUBLIC_PATHS = {
    "/health",
    "/healthz",
    "/ready",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        window_seconds: int = 60,
    ):
        super().__init__(app)
        self.max_requests = requests_per_minute
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _clean_old_requests(self, ip: str, now: float):
        cutoff = now - self.window
        self._requests[ip] = [
            ts for ts in self._requests[ip] if ts > cutoff
        ]

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        ip = self._get_client_ip(request)
        now = time.time()
        self._clean_old_requests(ip, now)

        if len(self._requests[ip]) >= self.max_requests:
            retry_after = int(
                self.window - (now - self._requests[ip][0])
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(max(retry_after, 1))},
            )

        self._requests[ip].append(now)
        return await call_next(request)
```

## Request Logging Middleware

```python
import time
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(
            "X-Request-ID", str(uuid.uuid4())
        )
        request.state.request_id = request_id

        start_time = time.perf_counter()

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        )

        logger.info("request_started")

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "request_failed",
                duration_ms=round(duration_ms, 2),
                error=str(exc),
            )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        return response
```

## CORS Configuration

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

ALLOWED_ORIGINS = [
    "https://app.example.com",
    "https://admin.example.com",
]

# Add localhost only in development
import os
if os.getenv("ENVIRONMENT", "production") == "development":
    ALLOWED_ORIGINS.extend([
        "http://localhost:3000",
        "http://localhost:5173",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)
```

## Middleware Registration Order

Register middleware in reverse execution order. The last added middleware runs first.

```python
from fastapi import FastAPI

app = FastAPI()

# 3rd to run: CORS (outermost — runs first on request)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# 2nd to run: logging
app.add_middleware(RequestLoggingMiddleware)

# 1st to run: rate limiting (innermost — runs last on request, first on response)
app.add_middleware(RateLimitMiddleware, requests_per_minute=100)

# Auth sits between logging and route handlers
app.add_middleware(AuthMiddleware)
```

Execution order on an incoming request:
1. CORSMiddleware (handles preflight, adds headers)
2. RequestLoggingMiddleware (assigns request_id, starts timer)
3. AuthMiddleware (validates JWT, sets request.state.user_id)
4. RateLimitMiddleware (checks per-IP window)
5. Route handler
