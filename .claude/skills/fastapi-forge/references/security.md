# Security Patterns

## CORS Configuration

Never use `allow_origins=["*"]` in production. Always whitelist specific origins.

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

PRODUCTION_ORIGINS = [
    "https://app.example.com",
    "https://admin.example.com",
]

DEVELOPMENT_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
]

allowed_origins = PRODUCTION_ORIGINS.copy()
if ENVIRONMENT == "development":
    allowed_origins.extend(DEVELOPMENT_ORIGINS)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)
```

## Input Sanitization with Pydantic

```python
from pydantic import BaseModel, Field, field_validator
import re


class AgentRunRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=64)
    input_text: str = Field(..., min_length=1, max_length=50000)
    parameters: dict[str, str] = Field(default_factory=dict)

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("agent_id must be alphanumeric with hyphens/underscores only")
        return v

    @field_validator("input_text")
    @classmethod
    def sanitize_input_text(cls, v: str) -> str:
        v = v.replace("\x00", "")
        if len(v.encode("utf-8")) > 200_000:
            raise ValueError("Input text exceeds maximum byte length")
        return v.strip()

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20:
            raise ValueError("Too many parameters (max 20)")
        for key, value in v.items():
            if "\x00" in key or "\x00" in value:
                raise ValueError("Null bytes not allowed in parameters")
            if len(key) > 64 or len(value) > 1000:
                raise ValueError("Parameter key or value too long")
        return v
```

## Secret Management

| Environment | Method | Example |
|-------------|--------|---------|
| Development | `.env` file + python-dotenv | `DATABASE_URL=postgresql://...` |
| CI/CD | Pipeline secrets | GitHub Actions secrets, GitLab CI variables |
| Staging | K8s Secrets | `kubectl create secret generic ...` |
| Production | Vault / Cloud KMS | HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager |

**Rule: NEVER hardcode secrets in source code, Dockerfiles, or docker-compose files.**

```python
# settings.py — centralized secret loading
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    environment: str = "development"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


settings = Settings()
```

## JWT Token Generation and Validation

```python
from jose import jwt, JWTError
from datetime import datetime, timedelta
from pydantic import BaseModel


class TokenPayload(BaseModel):
    sub: str
    scopes: list[str] = []
    exp: datetime
    iat: datetime


def create_access_token(
    user_id: str,
    scopes: list[str],
    secret_key: str,
    algorithm: str = "HS256",
    expire_minutes: int = 30,
) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": user_id,
        "scopes": scopes,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def verify_access_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
) -> TokenPayload:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        return TokenPayload(**payload)
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc
```

## API Key Authentication

```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
import hashlib
import hmac
import os

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

VALID_API_KEY_HASHES: set[str] = set()


def _load_api_keys():
    raw_keys = os.getenv("API_KEYS", "")
    for key in raw_keys.split(","):
        key = key.strip()
        if key:
            VALID_API_KEY_HASHES.add(
                hashlib.sha256(key.encode()).hexdigest()
            )


_load_api_keys()


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def verify_api_key(
    api_key: str | None = Security(API_KEY_HEADER),
) -> str:
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    key_hash = _hash_key(api_key)
    if not hmac.compare_digest(
        key_hash,
        next((h for h in VALID_API_KEY_HASHES if hmac.compare_digest(h, key_hash)), ""),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return api_key
```

## Scope-Based Authorization

```python
from fastapi import Depends, HTTPException, Request, status


def require_scopes(*required_scopes: str):
    async def _check(request: Request):
        user_scopes = getattr(request.state, "scopes", [])
        missing = [s for s in required_scopes if s not in user_scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {', '.join(missing)}",
            )
    return Depends(_check)


# Usage on routes
@app.post("/api/v1/agents/run", dependencies=[require_scopes("agent:run")])
async def run_agent(request: AgentRunRequest):
    pass

@app.delete("/api/v1/agents/{agent_id}", dependencies=[require_scopes("agent:admin")])
async def delete_agent(agent_id: str):
    pass
```
