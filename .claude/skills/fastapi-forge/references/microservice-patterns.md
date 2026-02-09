# Microservice Communication Patterns

## Service Client with Circuit Breaker

```python
import httpx
import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.half_open_calls = 0

    def record_success(self):
        self.failure_count = 0
        self.half_open_calls = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (
                datetime.utcnow() - self.last_failure_time
                > timedelta(seconds=self.recovery_timeout)
            ):
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls


class ServiceClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.circuit = CircuitBreaker()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def request(
        self, method: str, path: str, **kwargs
    ) -> dict[str, Any]:
        if not self.circuit.can_execute():
            raise ConnectionError(
                f"Circuit breaker OPEN for {self.base_url} — "
                f"failures: {self.circuit.failure_count}"
            )
        try:
            client = await self._get_client()
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            self.circuit.record_success()
            return response.json()
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
            self.circuit.record_failure()
            raise ConnectionError(f"Service call failed: {exc}") from exc

    async def get(self, path: str, **kwargs) -> dict[str, Any]:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> dict[str, Any]:
        return await self.request("POST", path, **kwargs)

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
```

## Redis Pub/Sub Event Messaging

```python
import redis.asyncio as redis
import json
from typing import Callable, Awaitable

EventHandler = Callable[[dict], Awaitable[None]]


class EventBus:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self._handlers: dict[str, list[EventHandler]] = {}

    async def publish(self, channel: str, event: dict) -> int:
        payload = json.dumps(event)
        return await self.redis.publish(channel, payload)

    def subscribe(self, channel: str, handler: EventHandler):
        self._handlers.setdefault(channel, []).append(handler)

    async def listen(self):
        pubsub = self.redis.pubsub()
        channels = list(self._handlers.keys())
        if not channels:
            return
        await pubsub.subscribe(*channels)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            channel = message["channel"]
            data = json.loads(message["data"])
            for handler in self._handlers.get(channel, []):
                await handler(data)

    async def close(self):
        await self.redis.aclose()


# Usage in FastAPI lifespan
event_bus = EventBus()

async def on_agent_complete(event: dict):
    print(f"Agent {event['agent_id']} completed with status {event['status']}")

event_bus.subscribe("agent.completed", on_agent_complete)
```

## Shared Schema Pattern

```python
# shared_schemas/models.py — installable package used by multiple services
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRunRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=64)
    input_text: str = Field(..., max_length=10000)
    parameters: dict[str, str] = Field(default_factory=dict)


class AgentRunResponse(BaseModel):
    run_id: str
    agent_id: str
    status: AgentStatus
    output: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    token_usage: int = 0
```

## Service Discovery

```python
import os

class ServiceRegistry:
    """Resolves service URLs from environment or Kubernetes DNS."""

    DEFAULTS = {
        "agent-service": "http://agent-service:8001",
        "auth-service": "http://auth-service:8002",
        "billing-service": "http://billing-service:8003",
    }

    @classmethod
    def get_url(cls, service_name: str) -> str:
        env_key = f"{service_name.upper().replace('-', '_')}_URL"
        return os.getenv(env_key, cls.DEFAULTS.get(service_name, ""))

    @classmethod
    def get_client(cls, service_name: str) -> "ServiceClient":
        url = cls.get_url(service_name)
        if not url:
            raise ValueError(f"No URL configured for service: {service_name}")
        return ServiceClient(base_url=url)
```
