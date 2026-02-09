# Async Testing Patterns

## conftest.py — Core Fixtures

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from jose import jwt
from datetime import datetime, timedelta

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        yield ac


def _make_test_token(
    user_id: str = "test-user-001",
    scopes: list[str] | None = None,
    expires_minutes: int = 30,
) -> str:
    payload = {
        "sub": user_id,
        "scopes": scopes or ["agent:run", "agent:read"],
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, "test-secret-key", algorithm="HS256")


@pytest_asyncio.fixture
async def auth_client():
    token = _make_test_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_client():
    token = _make_test_token(
        user_id="admin-001",
        scopes=["agent:run", "agent:read", "agent:admin"],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac
```

## Endpoint Tests

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_run_agent_success(auth_client):
    mock_result = {
        "run_id": "run-abc-123",
        "agent_id": "summarizer",
        "status": "completed",
        "output": "This is the summary.",
        "token_usage": 350,
    }

    with patch(
        "app.services.agent_service.execute_agent",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await auth_client.post(
            "/api/v1/agents/run",
            json={
                "agent_id": "summarizer",
                "input_text": "Summarize this document about AI safety.",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "run-abc-123"
    assert data["status"] == "completed"
    assert data["token_usage"] == 350


@pytest.mark.asyncio
async def test_unauthorized_no_token(client):
    response = await client.post(
        "/api/v1/agents/run",
        json={"agent_id": "summarizer", "input_text": "test"},
    )
    assert response.status_code == 401
    assert "Authorization" in response.json()["detail"]


@pytest.mark.asyncio
async def test_unauthorized_invalid_token(client):
    response = await client.post(
        "/api/v1/agents/run",
        json={"agent_id": "summarizer", "input_text": "test"},
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rate_limit_exceeded(auth_client):
    for _ in range(61):
        await auth_client.get("/api/v1/agents")

    response = await auth_client.get("/api/v1/agents")
    assert response.status_code == 429
    assert "Retry-After" in response.headers


@pytest.mark.asyncio
async def test_validation_error(auth_client):
    response = await auth_client.post(
        "/api/v1/agents/run",
        json={"agent_id": "", "input_text": ""},
    )
    assert response.status_code == 422
```

## Agent Service Mock Pattern

```python
from unittest.mock import AsyncMock
import pytest


@pytest.fixture
def mock_agent_service():
    service = AsyncMock()
    service.execute_agent.return_value = {
        "run_id": "run-mock-001",
        "agent_id": "test-agent",
        "status": "completed",
        "output": "Mock agent output",
        "token_usage": 100,
    }
    service.get_agent_status.return_value = {
        "agent_id": "test-agent",
        "status": "completed",
    }
    service.list_agents.return_value = [
        {"agent_id": "summarizer", "name": "Summarizer Agent"},
        {"agent_id": "classifier", "name": "Classifier Agent"},
    ]
    return service
```

## pytest Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
filterwarnings = [
    "ignore::DeprecationWarning",
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks integration tests requiring external services",
]
```
