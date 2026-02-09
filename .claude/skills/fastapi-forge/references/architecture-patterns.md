# Architecture Patterns

Project structures and system diagrams for all 3 tiers.

---

## Tier 1: Single API

```
Client (Web/Mobile/CLI)
    ↓ REST/WebSocket/SSE
┌──────────────────────────┐
│   FastAPI Application     │
│  ├─ routes/              │
│  ├─ services/            │
│  ├─ middleware/           │
│  └─ db/                  │
└──────────┬───────────────┘
           ↓
┌──────────────────────────┐
│   PostgreSQL + Redis      │
└──────────────────────────┘
```

### Project Structure

```
{project}/
├── src/{package}/
│   ├── __init__.py
│   ├── main.py              ← App factory + lifespan
│   ├── config.py            ← Pydantic Settings
│   ├── dependencies.py      ← FastAPI Depends()
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── agents.py        ← Agent orchestration
│   │   └── health.py        ← Health checks
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py       ← Pydantic request/response
│   │   └── database.py      ← SQLAlchemy ORM models
│   ├── services/
│   │   ├── __init__.py
│   │   └── agent_service.py ← Business logic
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py          ← JWT/API key
│   │   ├── rate_limit.py    ← Rate limiting
│   │   └── logging.py       ← Request logging
│   └── db/
│       ├── __init__.py
│       ├── session.py       ← Async session factory
│       └── migrations/      ← Alembic
├── tests/
│   ├── conftest.py
│   ├── test_agents.py
│   └── test_health.py
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── alembic.ini
```

---

## Tier 2: Microservices

```
API Gateway (FastAPI)
    ├─ /users     → User Service (FastAPI + PostgreSQL)
    ├─ /orders    → Order Service (FastAPI + PostgreSQL)
    ├─ /agents    → Agent Service (FastAPI + Redis)
    └─ /notify    → Notification Service (FastAPI + RabbitMQ)

Inter-service: async messaging (Redis Pub/Sub / RabbitMQ)
Service discovery: K8s DNS / Consul
```

### Project Structure

```
{system}/
├── gateway/
│   ├── src/gateway/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── routes/
│   │   │   └── proxy.py     ← Route to downstream services
│   │   └── middleware/
│   │       ├── auth.py
│   │       └── rate_limit.py
│   ├── pyproject.toml
│   └── Dockerfile
├── services/
│   ├── agent-service/
│   │   ├── src/agent_service/
│   │   │   ├── main.py
│   │   │   ├── routes/agents.py
│   │   │   ├── services/agent_service.py
│   │   │   └── db/session.py
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   ├── user-service/
│   │   └── ...
│   └── notification-service/
│       └── ...
├── shared/
│   └── common/
│       ├── schemas.py       ← Shared Pydantic models
│       └── events.py        ← Event definitions
├── docker-compose.yml
├── docker-compose.dev.yml
└── k8s/
    ├── gateway.yaml
    ├── agent-service.yaml
    └── ingress.yaml
```

---

## Tier 3: Enterprise (CQRS + Event-Driven)

```
                    ┌─ Command API (FastAPI) ──→ Write DB
Client ──→ Gateway ─┤
                    └─ Query API (FastAPI)  ──→ Read DB (replica/cache)

Events: Kafka / Redis Streams
        ↓
┌─────────────────────┐
│ Event Consumers      │
│ ├─ Projection Worker │ ← Updates read models
│ ├─ Agent Worker      │ ← Triggers agent workflows
│ └─ Notification      │ ← Sends alerts
└─────────────────────┘
```

### Additional Structure (on top of Tier 2)

```
├── infrastructure/
│   ├── terraform/           ← IaC
│   ├── helm/                ← Helm charts
│   └── monitoring/
│       ├── prometheus.yml
│       ├── grafana/
│       └── alerts.yml
├── event-bus/
│   └── kafka-config/
├── docs/
│   ├── architecture.md
│   ├── api-spec.yaml        ← OpenAPI
│   └── runbook.md
```

---

## When to Scale Up

| Signal | Action |
|--------|--------|
| Single service hitting resource limits | Scale vertically first (more workers) |
| Teams stepping on each other's code | Split into Tier 2 services by domain |
| Need independent deployment cycles | Split into Tier 2 |
| Need CQRS or event sourcing | Move to Tier 3 |
| Multi-region requirements | Tier 3 with load balancing |
