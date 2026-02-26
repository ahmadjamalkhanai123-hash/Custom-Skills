---
name: dapr-mastery
description: |
  Creates production-ready Dapr distributed applications from local sidecar dev setups to
  enterprise multi-cluster platforms with Actors, Workflow orchestration, all building blocks,
  mTLS zero-trust security, resiliency policies, and cloud-native observability.
  This skill should be used when users want to build Dapr applications, implement the virtual
  actor pattern, author durable workflows with compensation/saga, configure Dapr components
  (state stores, pub/sub, secrets, bindings, jobs, conversation), deploy Dapr on Kubernetes,
  apply resiliency policies, or architect enterprise-scale event-driven distributed systems
  using Dapr v1.15+.
---

# Dapr Mastery

Build production-grade distributed applications with the Dapr runtime — from local sidecar
development to hyperscale enterprise deployments.

## What This Skill Builds

| Tier | Scope | Use Case |
|------|-------|----------|
| **1 — Dev** | Self-hosted, docker-compose | Local dev, prototyping, demos |
| **2 — Production** | Kubernetes, HA control plane, mTLS | Cloud microservices, SaaS apps |
| **3 — Microservices** | Actors + Workflow + Event-driven | Complex business domains, CQRS/Saga |
| **4 — Enterprise** | Multi-cluster, multi-region, compliance | Global platforms, financial, healthcare |

## What This Skill Does NOT Do

- Manage or configure the underlying Kubernetes cluster itself (use `k8s-mastery`)
- Write domain-specific business logic (only Dapr integration code)
- Configure container images or Dockerfiles (use `docker-mastery`)
- Handle Dapr component source infrastructure (Redis/Kafka cluster setup)
- Guarantee compatibility with Dapr versions below v1.14

## Before Implementation

Gather context to ensure correct implementation:

| Source | Gather |
|--------|--------|
| **Codebase** | Existing services, languages, frameworks, Docker/K8s manifests |
| **Conversation** | Tier, languages, building blocks needed, cloud provider, compliance |
| **Skill References** | `references/` — building blocks, actors, workflow, security, components |
| **User Guidelines** | Team conventions, existing infra, secret management strategy |

Only ask users for THEIR requirements — domain expertise is embedded in `references/`.

## Required Clarifications

Ask in **two messages** — do not dump all questions at once.

**Message 1 (always ask):**
```
1. Deployment Tier (1-4)?
   1=Dev (local), 2=Production (K8s), 3=Microservices (Actors+Workflow), 4=Enterprise
2. Primary language(s): Python / .NET / Java / Go / JavaScript?
3. Building blocks needed (select all that apply)?
   □ State Management  □ Pub/Sub  □ Service Invocation  □ Actors
   □ Workflow  □ Secrets  □ Bindings  □ Configuration
   □ Distributed Lock  □ Jobs/Scheduler  □ Conversation (AI/LLM)
```

**Message 2 (ask only if tier ≥ 2 or ambiguous):**
```
4. Component backends (state store, broker, secret store)?
   Defaults: Redis / Redis / Kubernetes secrets
5. Existing Kubernetes cluster or starting fresh?
6. Any compliance requirements (HIPAA, SOC2, PCI-DSS)?
```

**If user skips optional questions**: Apply safe defaults shown above and proceed.
**If user is vague about tier**: Use decision tree below to recommend, then confirm.

## Tier Architecture Decision Tree

```
                      START
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
    Local/Demo    Cloud/SaaS    Complex Domain
         │              │              │
      TIER 1         TIER 2       Need Saga/Actor?
    Self-hosted     K8s + mTLS        │
    docker-compose  Resiliency    ┌───┴───┐
                                  ▼       ▼
                               TIER 3  Multi-region/
                             Actors +  Compliance?
                             Workflow       │
                                        TIER 4
                                       Enterprise
```

## Building Blocks Quick Reference

| Block | API | Stable? | Key Use |
|-------|-----|---------|---------|
| Service Invocation | `/v1.0/invoke/{appId}` | ✅ Stable | Sync RPC, mTLS auto |
| State Management | `/v1.0/state/{store}` | ✅ Stable | K/V, transactional |
| Pub/Sub | `/v1.0/publish/{topic}` | ✅ Stable | Async events |
| Bindings | `/v1.0/bindings/{name}` | ✅ Stable | External systems |
| Actors | `/v1.0/actors/{type}/{id}` | ✅ Stable | Stateful objects |
| Workflow | `/v1.0-beta1/workflows` | ✅ Stable v1.15 | Orchestration |
| Secrets | `/v1.0/secrets/{store}` | ✅ Stable | Secret retrieval |
| Configuration | `/v1.0/configuration/{store}` | ✅ Stable | Dynamic config |
| Distributed Lock | `/v1.0-alpha1/lock/{store}` | 🔶 Alpha | Leader election |
| Jobs | `/v1.0-alpha1/jobs/{name}` | 🔶 Alpha | Scheduling |
| Conversation | `/v1.0-alpha1/conversation` | 🔶 Alpha v1.15 | LLM integration |

> Full component configs and examples → `references/building-blocks.md`

## Actors (Virtual Actor Pattern)

### Core Rules
- Single-threaded per actor instance (turn-based concurrency)
- Activated on-demand, garbage-collected when idle (`actorIdleTimeout`)
- State persisted to configured state store
- Placement service distributes actors across pods

### Actor Configuration (in Dapr Configuration resource)
```yaml
spec:
  entities:
    - MyActor
  actorIdleTimeout: 1h
  actorScanInterval: 30s
  drainOngoingCallTimeout: 60s
  drainRebalancedActors: true
  reentrancy:
    enabled: true
    maxStackDepth: 32
  remindersStoragePartitions: 7   # For scale: set to number of partitions
```

### Timers vs Reminders
| | Timer | Reminder |
|--|-------|----------|
| Survives deactivation | ❌ No | ✅ Yes |
| Persisted | ❌ No | ✅ Yes (state store) |
| Use when | Ephemeral periodic work | Durable scheduled work |

### Actor State Best Practices
- Use **transactional state** for multi-key updates (ACID)
- Chunk large state: store separately keyed by `actorId+chunkIndex`
- Use `remindersStoragePartitions` (≥7) for >1M actors at scale

> Full Actor patterns, reentrancy, partitioning → `references/actors-patterns.md`

## Workflow (Durable Execution)

### Supported Patterns (Stable in v1.15)
| Pattern | Use Case |
|---------|----------|
| Task Chaining | Sequential steps, pass output as input |
| Fan-Out/Fan-In | Parallel tasks, aggregate results |
| Monitor | Polling loop with `continue_as_new` |
| Async HTTP API | Long-running with status endpoint |
| External Events | Pause until `raise_event` called |
| Compensation/Saga | Rollback on failure (reverse order) |
| Child Workflows | Modular sub-workflows |

### Workflow Determinism Rules (Critical)
```
✅ Allowed in orchestrator:       ❌ NEVER in orchestrator:
- Call activities                 - Random numbers / GUIDs
- Call child workflows            - DateTime.Now (use ctx.current_utc_datetime)
- Wait for external events        - I/O operations (HTTP, DB, files)
- Use workflow-provided time      - Non-deterministic code paths
- continue_as_new                 - Infinite while loops (use continue_as_new)
```

### Workflow Scale (v1.15+)
- Scale from **0 to N replicas** with durability guaranteed
- Scheduler service manages reminder delivery at scale
- Use `continue_as_new` for long-running eternal workflows

> Full patterns with code examples → `references/workflow-patterns.md`

## Security Standards

| Control | Implementation |
|---------|---------------|
| mTLS | Enabled by default via Sentry CA (SPIFFE X.509) |
| App token | `APP_API_TOKEN` env var for app-to-sidecar auth |
| Component scoping | `scopes:` field in component YAML |
| Secrets | Always use secret store, never hardcode in component YAML |
| Access control | `allowedOperations` in Configuration resource |
| Network | Kubernetes NetworkPolicy to restrict sidecar port 3500 |

> Full security config, certificates, OPA → `references/security-operations.md`

## Resiliency Policies

Every production Dapr app **must** define resiliency policies:
```yaml
# Apply to: services, components, actors
retries: exponential back-off + jitter, maxRetries: 3
timeouts: per-operation, sensible defaults (5s–30s)
circuitBreakers: trip at 50% failure, half-open recovery
```
> Full resiliency YAML specs → `references/resiliency-patterns.md`

## Output Specification

### Tier 1 (Dev) Delivers
- `dapr.yaml` multi-app run config
- `docker-compose.yml` with Redis sidecar
- App code with Dapr SDK integration
- Component YAML files

### Tier 2 (Production) Delivers
- Helm values override for `dapr/dapr` chart
- K8s Deployment manifests with sidecar annotations
- Resiliency policy YAML
- Component secrets via Kubernetes secret store
- Basic Zipkin/OpenTelemetry tracing config

### Tier 3 (Microservices) Delivers
- Everything in Tier 2 +
- Actor service implementation (language of choice)
- Workflow orchestration code (saga with compensation)
- Pub/Sub event-driven service mesh
- Dapr Configuration resource

### Tier 4 (Enterprise) Delivers
- Everything in Tier 3 +
- Multi-cluster component replication
- OPA/mTLS access policies
- Full observability (Prometheus + Grafana + Jaeger)
- Compliance annotations (HIPAA/SOC2 labels)
- Jobs/Scheduler for recurring tasks
- Conversation API integration (LLM)
- `scaffold_dapr.py` project generator

## Production Standards

### Sidecar Annotations (Required for Production)
```yaml
annotations:
  dapr.io/enabled: "true"
  dapr.io/app-id: "my-service"
  dapr.io/app-port: "8080"
  dapr.io/sidecar-cpu-request: "100m"
  dapr.io/sidecar-cpu-limit: "300m"
  dapr.io/sidecar-memory-request: "128Mi"
  dapr.io/sidecar-memory-limit: "256Mi"
  dapr.io/enable-metrics: "true"
  dapr.io/enable-api-logging: "true"
  dapr.io/log-level: "info"
```

### Component YAML Standards
```yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: my-component
  namespace: production
spec:
  type: state.redis          # Always specify exact type
  version: v1
  metadata:
    - name: redisHost
      secretKeyRef:          # ALWAYS use secretKeyRef, never plain value
        name: redis-secret
        key: redisHost
  scopes:                    # Limit to specific app IDs
    - my-service
    - my-worker
```

## Production Checklist

### Pre-Deployment
- [ ] Dapr v1.15+ runtime, matching SDK versions
- [ ] mTLS enabled (default), verify Sentry is healthy
- [ ] All component secrets in secret store (no plaintext)
- [ ] Resiliency policies defined for all services + components
- [ ] Sidecar resource limits set (CPU + memory)
- [ ] Components scoped to specific app IDs
- [ ] Actor `remindersStoragePartitions` set for scale

### Actors Specific
- [ ] `actorIdleTimeout` tuned (default 1h)
- [ ] `drainRebalancedActors: true` for graceful shutdown
- [ ] Transactional state for multi-key updates
- [ ] Reentrancy configured if call chains exist
- [ ] Reminder vs timer chosen correctly

### Workflow Specific
- [ ] Orchestrator code is deterministic
- [ ] No I/O in orchestrator (only in activities)
- [ ] Compensation activities registered for each step
- [ ] `continue_as_new` for long-running eternal workflows
- [ ] Workflow app scaled to ≥2 replicas in production

### Observability
- [ ] OpenTelemetry Collector deployed
- [ ] Prometheus scraping `:9090/metrics`
- [ ] Dapr Grafana dashboards imported (ID: 12216)
- [ ] Distributed tracing (Zipkin/Jaeger) configured
- [ ] Log level set to `warn` in production

### Testing & CI/CD
- [ ] Unit tests: Dapr client mocked, ≥80% coverage
- [ ] Actor tests: all state transitions covered
- [ ] Workflow tests: determinism verified via WorkflowTestHarness
- [ ] Integration tests: real sidecar + test containers
- [ ] CI pipeline: component YAML validated, no plaintext secrets
- [ ] GitOps: ArgoCD/Flux manages components + Helm release
- [ ] Image signed (cosign) and vulnerability scanned (Trivy)

## Reference Index

| File | Contents |
|------|----------|
| `references/building-blocks.md` | All 11 building blocks, API reference, YAML configs |
| `references/actors-patterns.md` | Virtual actor, reentrancy, timers/reminders, scale |
| `references/workflow-patterns.md` | All 7 patterns with Python + .NET examples |
| `references/security-operations.md` | mTLS, SPIFFE, token auth, ACL, OPA, scoping |
| `references/resiliency-patterns.md` | Retry, circuit-breaker, timeout, bulkhead specs |
| `references/kubernetes-production.md` | HA control plane, Helm, multi-cluster, resource tuning |
| `references/observability.md` | Tracing, metrics, logging, Grafana dashboards |
| `references/anti-patterns.md` | Common mistakes and production pitfalls |
| `references/testing-patterns.md` | Unit/integration/E2E testing, actor + workflow test harness |
| `references/cicd-gitops.md` | GitHub Actions, ArgoCD, Flux, component validation pipeline |

> Search within large references: `grep -n "keyword" references/building-blocks.md`

## Official Documentation

| Resource | URL | Use For |
|----------|-----|---------|
| Building Blocks | https://docs.dapr.io/developing-applications/building-blocks/ | Block API specs |
| Actors Overview | https://docs.dapr.io/developing-applications/building-blocks/actors/actors-overview/ | Actor concepts |
| Actor Runtime | https://docs.dapr.io/developing-applications/building-blocks/actors/actors-features-concepts/ | Config params |
| Workflow Overview | https://docs.dapr.io/developing-applications/building-blocks/workflow/workflow-overview/ | Workflow API |
| Workflow Patterns | https://docs.dapr.io/developing-applications/building-blocks/workflow/workflow-patterns/ | Pattern examples |
| Resiliency | https://docs.dapr.io/operations/resiliency/resiliency-overview/ | Policy spec |
| Security | https://docs.dapr.io/concepts/security-concept/ | mTLS, SPIFFE |
| K8s Production | https://docs.dapr.io/operations/hosting/kubernetes/kubernetes-production/ | K8s checklist |
| Component Specs | https://docs.dapr.io/reference/components-reference/ | All component YAMLs |
| v1.15 Release | https://blog.dapr.io/posts/2025/02/27/dapr-v1.15-is-now-available/ | Latest features |

**If a pattern is not in `references/`**: Fetch the relevant URL above before implementing.
**Version drift**: Always check `https://docs.dapr.io` for the latest stable component spec.
