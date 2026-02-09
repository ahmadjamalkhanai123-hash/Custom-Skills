# Agent Orchestration

REST, WebSocket, and SSE endpoints for serving AI agents via FastAPI.

---

## Complete Agent Routes

```python
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
    """Synchronous agent execution — waits for completion."""
    try:
        result = await asyncio.wait_for(
            service.execute(request, user_id=user["id"]),
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
    """Async agent execution — returns job ID immediately."""
    job = await service.create_job(request, user_id=user["id"])
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
        async for chunk in service.stream(prompt, user_id=user["id"]):
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
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    service: AgentService = Depends(get_agent_service),
):
    await service.cancel_job(job_id)
    return {"status": "cancelled"}
```

---

## Background Task Processing (ARQ)

```python
from arq import create_pool
from arq.connections import RedisSettings
from ..config import settings


async def get_redis_pool():
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))


async def execute_agent_job(ctx, job_id: str):
    """ARQ worker for async agent execution."""
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

---

## Agent Service Pattern

```python
import time
import uuid
from ..config import settings
from ..models.schemas import AgentRequest, AgentResponse, AgentStreamChunk


class AgentService:
    def __init__(self, db):
        self.db = db

    async def execute(self, request: AgentRequest, user_id: str) -> AgentResponse:
        start = time.time()
        # SDK-specific execution here
        result = await self._run_sdk(request)
        duration = time.time() - start
        return AgentResponse(
            result=result["text"],
            steps=result["steps"],
            tokens_used=result["tokens"],
            duration_seconds=round(duration, 2),
            model=request.model,
            tools_called=result.get("tools_called", []),
        )

    async def stream(self, prompt: str, user_id: str):
        # Yield AgentStreamChunk objects
        yield AgentStreamChunk(type="text", content="Processing...")

    async def create_job(self, request: AgentRequest, user_id: str):
        job_id = str(uuid.uuid4())
        # Store job in DB
        return type("Job", (), {"id": job_id})()

    async def get_job(self, job_id: str):
        # Fetch from DB
        pass

    async def cancel_job(self, job_id: str):
        # Cancel running job
        pass

    async def _run_sdk(self, request: AgentRequest) -> dict:
        # Dispatch to correct SDK
        if request.sdk == "anthropic":
            return await self._run_anthropic(request)
        elif request.sdk == "openai":
            return await self._run_openai(request)
        raise ValueError(f"Unsupported SDK: {request.sdk}")

    async def _run_anthropic(self, request: AgentRequest) -> dict:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=request.model,
            max_tokens=8096,
            system=request.system_prompt or "You are a helpful assistant.",
            messages=[{"role": "user", "content": request.prompt}],
        )
        result_text = response.content[0].text if response.content else ""
        return {
            "text": result_text,
            "steps": 1,
            "tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

    async def _run_openai(self, request: AgentRequest) -> dict:
        from agents import Agent, Runner
        agent = Agent(name="api-agent", instructions=request.system_prompt or "You are helpful.")
        result = await Runner.run(agent, request.prompt, max_turns=request.max_turns)
        return {"text": result.final_output, "steps": 1, "tokens": 0}
```
