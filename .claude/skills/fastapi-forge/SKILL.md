---
name: fastapi-forge
description: |
  Creates production-ready FastAPI applications for multi-agent orchestration,
  microservices, and large-scale systems with async-first architecture.
  This skill should be used when users want to build FastAPI APIs, create agent
  backend services, scaffold microservice systems, add REST/WebSocket/SSE endpoints,
  or architect enterprise-scale Python web services.
---

# FastAPI Forge

Build production-ready FastAPI applications — from single APIs to enterprise-scale multi-agent systems.

## What This Skill Does

- Scaffolds FastAPI projects at 3 tiers: single API, microservices, enterprise
- Builds agent orchestration backends (REST + WebSocket + SSE streaming)
- Creates microservice architectures with async inter-service communication
- Implements production patterns: auth, rate limiting, observability, circuit breakers
- Generates async database integration (SQLAlchemy 2.0, Redis, MongoDB)
- Configures deployment (Docker, Kubernetes, Cloud Run, Serverless)
- Handles background task processing for long-running agent jobs

## What This Skill Does NOT Do

- Build frontend UIs (only API layer)
- Create MCP servers (use `mcp-skills` for that)
- Build AI agents themselves (use `hybrid-sdk-agents` for that)
- Manage cloud infrastructure provisioning (scaffolds configs only)
- Handle DNS, SSL certificates, or domain management

---

## Before Implementation

Gather context to ensure successful implementation:

| Source | Gather |
|--------|--------|
| **Codebase** | Existing project structure, Python version, package manager, frameworks |
| **Conversation** | User's API requirements, scale targets, database needs, deployment target |
| **Skill References** | Patterns from `references/` (architecture, middleware, deployment, testing) |
| **User Guidelines** | Team conventions, security requirements, compliance constraints |

Ensure all required context is gathered before implementing.
Only ask user for THEIR specific requirements (FastAPI expertise is in this skill).

---

## Required Clarifications

Before building, ask:

1. **Application Type**: "What are you building?"
   - Agent orchestration API (serve AI agents over HTTP)
   - REST microservice (domain-specific service)
   - Multi-service system (multiple coordinated services)
   - Real-time streaming backend (WebSocket/SSE)

2. **Scale Tier**: "What scale?"
   - Single API (1 service, <100 req/s)
   - Multi-service (2-10 services, <1K req/s)
   - Enterprise (10+ services, 1K+ req/s, multi-region)

3. **Database**: "What storage?"
   - PostgreSQL (Recommended — async SQLAlchemy)
   - MongoDB (async Motor)
   - Redis (caching + pub/sub)
   - None (stateless API)

## Optional Clarifications

4. **Auth**: JWT Bearer (default), OAuth2/OIDC, API Key, None
5. **Agent SDK**: Anthropic (default), OpenAI, LangGraph, CrewAI, None
6. **Deployment**: Docker Compose (default), Kubernetes, Cloud Run, Serverless

Note: Start with questions 1-2. Follow up with 3-6 based on context.

### Defaults (If Not Specified)

| Clarification | Default |
|---------------|---------|
| Application Type | Infer from conversation |
| Scale Tier | Single API |
| Database | PostgreSQL (async) |
| Auth | JWT Bearer |
| Agent SDK | Anthropic Agent SDK |
| Deployment | Docker Compose |
| Python Version | 3.12+ |
| Package Manager | uv |

### Before Asking

1. Check conversation history for prior answers
2. Infer from existing project files (pyproject.toml, requirements.txt)
3. Only ask what cannot be determined from context

---

## Tier Selection Decision Tree

```
What's the primary need?

Single API with agents/tools?
  → Tier 1: Single API (references/core-patterns.md)

Multiple domain services with messaging?
  → Tier 2: Microservices (references/microservice-patterns.md)

Enterprise with CQRS, event-driven, multi-region?
  → Tier 3: Enterprise (references/architecture-patterns.md)

Not sure?
  → Start Tier 1, scale up when needed
```

### Tier Comparison

| Factor | Tier 1 | Tier 2 | Tier 3 |
|--------|--------|--------|--------|
| Services | 1 | 2-10 | 10+ |
| Database | Single | Per-service | Polyglot |
| Messaging | None | Redis Pub/Sub | Kafka/Streams |
| Deploy | Docker | Docker Compose | Kubernetes |
| Complexity | Low | Medium | High |
| Best for | MVPs, agents | Growing products | Enterprise |

---

## Workflow

```
Tier → Structure → Implement → Middleware → Test → Deploy
```

### Step 1: Select Tier

Use decision tree above. Read the relevant reference files.

### Step 2: Generate Project Structure

Read `references/architecture-patterns.md` for tier-specific layouts.

**Tier 1 — Single API:**
```
{project}/
├── src/{package}/
│   ├── __init__.py
│   ├── main.py            ← App factory + lifespan
│   ├── config.py           ← Pydantic Settings
│   ├── dependencies.py     ← Dependency injection
│   ├── routes/
│   │   ├── agents.py       ← Agent endpoints
│   │   └── health.py       ← Health checks
│   ├── models/
│   │   ├── schemas.py      ← Pydantic models
│   │   └── database.py     ← SQLAlchemy models
│   ├── services/
│   │   └── agent_service.py
│   ├── middleware/
│   │   ├── auth.py
│   │   └── rate_limit.py
│   └── db/
│       └── session.py      ← Async session
├── tests/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

For Tier 2/3 structures, see `references/architecture-patterns.md`.

### Step 3: Implement Core Code

Read reference files for implementation patterns:
- `references/core-patterns.md` → App factory, config, DI, async DB
- `references/agent-orchestration.md` → REST/WS/SSE agent endpoints
- `references/microservice-patterns.md` → Service client, circuit breaker
- `references/middleware-patterns.md` → Auth, rate limiting, logging

### Step 4: Add Production Middleware

From `references/middleware-patterns.md`:
- **Auth**: JWT Bearer or API Key middleware
- **Rate Limiting**: Per-user/IP rate limiting
- **Logging**: Structured logging with structlog
- **CORS**: Restricted origin whitelist

### Step 5: Test

From `references/testing-patterns.md`:
- Async test client (httpx + ASGITransport)
- Endpoint tests with auth coverage
- Rate limit verification tests

### Step 6: Deploy

From `references/deployment.md`:
- Dockerfile (multi-stage build)
- Docker Compose (multi-service)
- Kubernetes manifests (production)

---

## Agent Orchestration Endpoints

When building agent backends, include these endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/agents/run` | POST | Synchronous agent execution |
| `/agents/run/async` | POST | Background job, returns job ID |
| `/agents/run/stream` | GET | SSE streaming agent output |
| `/agents/ws` | WebSocket | Bidirectional agent communication |
| `/agents/jobs/{id}` | GET | Check async job status |
| `/agents/jobs/{id}` | DELETE | Cancel running job |

See `references/agent-orchestration.md` for complete implementation.

---

## Output Specification

Every generated FastAPI project includes:

### Required Components
- [ ] FastAPI app with lifespan context manager (async startup/shutdown)
- [ ] Pydantic Settings for all configuration (no hardcoded values)
- [ ] Typed Pydantic schemas for all request/response models
- [ ] Async database session management (SQLAlchemy 2.0+)
- [ ] Authentication middleware (JWT or API key)
- [ ] Rate limiting middleware
- [ ] Health check endpoints (/health, /health/ready)
- [ ] Structured logging (structlog with JSON output)
- [ ] Error handling with structured responses

### Required Patterns
- [ ] Async-first (all handlers, DB calls, HTTP clients are async)
- [ ] Dependency injection via FastAPI Depends()
- [ ] App factory pattern (create_app function)
- [ ] Clean separation: routes / models / services / middleware / config

---

## Domain Standards

### Must Follow

- [ ] Use Pydantic v2 models for all request/response schemas
- [ ] Use async/await for all route handlers and DB operations
- [ ] Use Pydantic Settings for configuration (env vars, .env files)
- [ ] Store all secrets in environment variables
- [ ] Use lifespan context manager (not deprecated @app.on_event)
- [ ] Use httpx.AsyncClient for outbound HTTP (not requests)
- [ ] Return structured error responses (not raw exceptions)
- [ ] Use structlog for logging (not print() or logging.basicConfig)

### Must Avoid

- Synchronous DB calls in async routes (blocks event loop)
- Hardcoded API keys or secrets in source code
- `@app.on_event("startup")` (deprecated — use lifespan)
- `requests` library in async code (use httpx)
- CORS `allow_origins=["*"]` in production
- Single Uvicorn worker in production (use --workers N)
- print() for logging (unstructured, lost in production)
- Catching all exceptions silently (log and return structured error)

---

## Error Handling

| Scenario | Detection | Action |
|----------|-----------|--------|
| Invalid request body | Pydantic ValidationError | 422 with field-level errors (automatic) |
| Authentication failure | Missing/invalid JWT | 401 with clear message |
| Rate limit exceeded | Request count > threshold | 429 with retry-after header |
| Agent execution timeout | asyncio.TimeoutError | 408 with partial results if available |
| Database connection error | ConnectionRefusedError | 503 with retryable flag |
| Agent SDK error | SDK-specific exception | 502 with structured error, no internals leaked |

---

## Output Checklist

Before delivering any FastAPI project, verify ALL items:

### Architecture
- [ ] Tier appropriate for scale requirements
- [ ] App factory pattern (create_app function)
- [ ] Lifespan context manager for startup/shutdown
- [ ] Dependency injection for services and DB sessions

### Code Quality
- [ ] All routes use Pydantic models for input/output
- [ ] All DB operations are async
- [ ] No hardcoded secrets
- [ ] Structured error responses (never raw exceptions)
- [ ] Type hints on all functions

### Security
- [ ] Auth middleware on all non-public routes
- [ ] Rate limiting configured
- [ ] CORS restricted to specific origins
- [ ] Input validation via Pydantic
- [ ] Secrets via environment variables only

### Observability
- [ ] Structured logging (structlog/JSON)
- [ ] Health check endpoints (/health, /health/ready)
- [ ] Prometheus metrics (if production tier)
- [ ] Request tracing (OpenTelemetry if enterprise)

### Deployment
- [ ] Dockerfile with multi-stage build
- [ ] docker-compose.yml for local dev
- [ ] .env.example with all required variables
- [ ] pyproject.toml with correct dependencies
- [ ] K8s manifests if enterprise tier

### Testing
- [ ] Async test client configured (httpx + ASGITransport)
- [ ] Tests for all endpoints
- [ ] Auth test coverage (valid/invalid/missing token)
- [ ] Rate limit test

---

## Reference Files

| File | When to Read |
|------|--------------|
| `references/architecture-patterns.md` | Tier 1/2/3 project structures and system diagrams |
| `references/core-patterns.md` | App factory, Pydantic Settings, DI, async DB session |
| `references/agent-orchestration.md` | REST/WebSocket/SSE agent endpoints, Pydantic schemas |
| `references/microservice-patterns.md` | Service client, circuit breaker, async messaging |
| `references/middleware-patterns.md` | Auth (JWT), rate limiting, request logging, CORS |
| `references/observability.md` | structlog, Prometheus metrics, OpenTelemetry tracing |
| `references/deployment.md` | Dockerfile, Docker Compose, Kubernetes, Serverless |
| `references/testing-patterns.md` | Async test client, fixtures, endpoint tests |
| `references/security.md` | CORS, input sanitization, secret management |
| `references/anti-patterns.md` | 12 common FastAPI mistakes with fixes |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scaffold_fastapi.py` | Generate full project for any tier. Usage: `python scaffold_fastapi.py <name> --tier <1\|2\|3> --path <dir> [--db postgres\|mongo\|redis\|none] [--auth jwt\|apikey\|none]` |

## Asset Templates

| Template | Purpose |
|----------|---------|
| `assets/templates/single_api.py` | Tier 1 complete runnable app (app factory + routes + config) |
| `assets/templates/agent_routes.py` | Agent orchestration endpoints (POST/WS/SSE) |
| `assets/templates/microservice_gateway.py` | Tier 2 API gateway with service routing |
| `assets/templates/docker_compose.yml` | Multi-service Docker Compose |
| `assets/templates/k8s_deployment.yaml` | Kubernetes deployment + service manifest |

## Official Documentation

| Resource | URL | Use For |
|----------|-----|---------|
| FastAPI | https://fastapi.tiangolo.com | Framework reference |
| Pydantic V2 | https://docs.pydantic.dev/latest/ | Data validation |
| SQLAlchemy Async | https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html | Async ORM |
| Uvicorn | https://www.uvicorn.org | ASGI server |
| httpx | https://www.python-httpx.org | Async HTTP client |
| structlog | https://www.structlog.org | Structured logging |
| ARQ | https://arq-docs.helpmanual.io | Async task queue |

Last verified: February 2026.

For patterns not covered in references, fetch from official FastAPI documentation.
