---
name: obs-cost-traffic
version: 1.0.0
type: Builder
description: >
  Creates production-ready Observability stacks, Traffic Engineering configurations,
  and Cost Intelligence frameworks for autonomous microservices and AI agents.
  This skill should be used when teams need full-stack telemetry (logs, metrics,
  traces, events), load balancer or service mesh configurations, cloud cost governance,
  or AI/LLM agent observability — from local Docker Compose dev stacks to global
  multi-cloud enterprise platforms. Covers every vendor (OSS, AWS, GCP, Azure,
  Datadog, Cloudflare), every environment, and every language stack (Python, Node,
  Go, Java, .NET) with OpenTelemetry as the universal instrumentation standard.
author: Claude Code Skills Lab
last_verified: 2026-02-25
tags:
  [observability, monitoring, tracing, logging, traffic-engineering, cost-engineering,
   finops, opentelemetry, load-balancing, microservices, ai-agents, multi-cloud,
   prometheus, grafana, datadog, istio, cloudflare]
---

# OBS·COST·TRAFFIC
## Observability · Traffic Engineering · Cost Intelligence — Production Platform Skill

This skill builds the full operational intelligence layer for autonomous microservices
and AI agent systems. It unifies three deeply linked engineering domains:

- **Observability (O11y)**: Logs · Metrics · Traces · Events · Profiling
- **Traffic Engineering**: Load balancing · Service mesh · Global routing · Resilience
- **Cost Intelligence**: Cloud FinOps · Per-service attribution · Budget governance

All three pillars are interconnected — traffic patterns drive egress cost, observability
enables per-service cost attribution, and cost governs what tooling tiers are viable.
This skill treats the three as a unified operational platform, not separate concerns.

---

## What This Skill Delivers

- Full OpenTelemetry instrumentation pipelines (collector, SDK, exporters) for every language
- Structured logging aggregation (Loki, ELK/EFK, CloudWatch Logs, Cloud Logging, Azure Log Analytics)
- Distributed tracing across async services, queues, and AI agent tool calls
- Prometheus + Grafana SLO/SLI dashboards with golden-signal alerts and error budgets
- Load balancer configurations for NGINX, HAProxy, Traefik, Envoy, Istio, and all cloud LBs
- Global traffic management (Cloudflare, AWS Global Accelerator, GCP Traffic Director)
- Cloud cost dashboards: AWS Cost Explorer, GCP Billing, Azure Cost Management
- Kubernetes cost attribution: Kubecost, OpenCost, Goldilocks right-sizing
- AI/LLM observability: token tracking, agent step telemetry, model cost attribution
- FinOps governance: tagging strategies, budgets, alerts, showback/chargeback

---

## Does NOT Do

- Does not provision cloud infrastructure (use k8s-mastery or fastapi-forge for that)
- Does not build CI/CD pipelines (use cicd-pipeline skill)
- Does not write application business logic
- Does not replace Terraform/Pulumi/CDK for infra-as-code
- Does not manage secrets rotation (defers to Vault, AWS Secrets Manager, etc.)
- Does not provide SLA guarantees on third-party vendor tools

---

## Clarifications — First Message

When invoked, ask these two questions before generating anything:

**Q1 — Environment & Tier** (determines tooling scope):
> "Which environment are you targeting? *(pick closest)*
> A) Local Dev (Docker Compose, zero cloud cost)
> B) VPS / Self-Hosted (1–10 servers, open-source stack)
> C) Cloud Production (AWS / GCP / Azure — single cloud)
> D) Enterprise / Multi-Cloud (Datadog, Dynatrace, global traffic, FinOps team)
> Or describe your setup and I'll recommend the right tier."

**Q2 — Focus Pillars** (scope narrowing):
> "Which pillars do you need? *(all three is the default)*
> 1) Observability only (logs, metrics, traces)
> 2) Traffic Engineering only (load balancers, routing)
> 3) Cost Intelligence only (FinOps, cloud spend)
> 4) All three pillars (recommended for production microservices)
> Also: Are you observing AI agents / LLMs? (adds agent telemetry layer)"

**Q3 — Language Stack** *(ask only if not evident from existing codebase files)*:
> "What languages/frameworks do your services use?
> Python / Node.js / Go / Java / .NET / Mixed — determines which OTel SDK code is generated.
> Also: are any observability tools already deployed? (Prometheus? Datadog agent? Grafana?)"

**Graceful defaults if user says "just build it":**
- Tier 3 (Cloud Production) + All pillars + AWS + Python/Node instrumentation + No AI agents
- Language default: Python + Node.js examples when stack not specified
- Skip Q3 if language is obvious from Dockerfiles, package.json, requirements.txt, go.mod

---

## Before Implementation

Gather context before generating any output:

| Source | What to Gather |
|--------|----------------|
| **Codebase** | Language/framework stack, existing monitoring configs, Dockerfiles, K8s manifests |
| **Conversation** | Target tier, pillars needed, AI agents present, existing tools already deployed |
| **Skill References** | Load tier-matching files from `references/` — no runtime discovery needed |
| **User Guidelines** | CLAUDE.md conventions, naming standards, secret/credentials approach |

**Context checklist before generating**:
- [ ] Language stack identified (Python / Node.js / Go / Java / .NET — determines OTel SDK code)
- [ ] Environment tier confirmed (1=Local Docker / 2=VPS / 3=Cloud K8s / 4=Enterprise)
- [ ] Existing tools inventoried — never duplicate what's already running
- [ ] Service count estimated (<10 / 10–100 / 100–500 / 500+)
- [ ] AI/LLM agents present? → load `agent-ai-observability.md` patterns
- [ ] Compliance scope? (HIPAA/SOC2/PCI affects log retention and PII masking rules)

---

## Four-Tier Architecture

### Tier 1 — Local Development
**Target**: Single developer, Docker Compose, zero cost
**Observability**: OTel Collector → Prometheus + Grafana + Loki + Tempo
**Traffic**: Traefik reverse proxy with automatic service discovery
**Cost**: Infracost for IaC cost estimation, Docker stats resource limits
**Stack size**: ~8 containers, ~2GB RAM

```
App Services → OTel SDK → OTel Collector → Prometheus (metrics)
                                          → Loki (logs via Promtail)
                                          → Tempo (traces)
                                          → Grafana (all-in-one UI)
              → Traefik (traffic routing + dashboard)
```

### Tier 2 — VPS / Self-Hosted Production
**Target**: 1–20 VMs, bare metal or VPS, minimal cloud dependency
**Observability**: Prometheus + Alertmanager + Grafana + Loki + Jaeger/Tempo + OTel
**Traffic**: HAProxy (L4/L7) + Keepalived (VIP failover) + NGINX (L7)
**Cost**: Self-hosted OpenCost, cloud provider budgets, Infracost in CI
**Additions**: Alertmanager PagerDuty/Slack routing, Grafana OnCall

### Tier 3 — Cloud Production (Single Cloud)
**Target**: Kubernetes on EKS/GKE/AKS, managed services, 10–500 microservices
**Observability**:
- AWS: CloudWatch + X-Ray + AWS Distro for OTel (ADOT) + Container Insights
- GCP: Cloud Monitoring + Cloud Trace + Cloud Logging + Cloud Profiler
- Azure: Azure Monitor + Application Insights + Log Analytics Workspace
- Universal: kube-prometheus-stack + OTel Operator + Grafana OSS/Cloud
**Traffic**:
- AWS: ALB + NLB + Route 53 + Global Accelerator + CloudFront
- GCP: Cloud Load Balancing (Global HTTP/TCP) + Traffic Director + Cloud CDN
- Azure: Application Gateway + Azure Load Balancer + Azure Front Door + CDN
- Mesh: Istio or Linkerd for east-west traffic
**Cost**: Cloud-native cost tools + Kubecost/OpenCost + tagging enforcement

### Tier 4 — Enterprise / Multi-Cloud
**Target**: 500+ services, multi-region, multi-cloud, FinOps team
**Observability**: Datadog / New Relic / Dynatrace (APM, logs, traces, synthetics)
**Traffic**: Cloudflare (Load Balancing + Workers + Argo Smart Routing) +
            AWS Global Accelerator + Istio/Envoy control plane + Envoy Gateway
**Cost**: CloudHealth by VMware / Apptio Cloudability / Spot.io +
          FOCUS-spec normalization + showback/chargeback dashboards

---

## Tool Ecosystem Matrix

| Domain | Local Dev | VPS | Cloud | Enterprise |
|--------|-----------|-----|-------|------------|
| **Metrics** | Prometheus | Prometheus + Alertmanager | CloudWatch / Cloud Monitoring / Azure Monitor | Datadog / New Relic / Dynatrace |
| **Logs** | Loki + Promtail | Loki + Promtail / EFK | CloudWatch Logs / Cloud Logging / Log Analytics | Datadog Logs / Splunk / Elastic Cloud |
| **Traces** | Tempo + Jaeger | Jaeger / Tempo | X-Ray / Cloud Trace / App Insights | Datadog APM / New Relic / Dynatrace |
| **Events** | Alertmanager | Alertmanager + PagerDuty | CloudWatch Events / Eventarc / Event Grid | Datadog Events + PagerDuty/OpsGenie |
| **Profiling** | pyspy / async-profiler | pyspy | Cloud Profiler | Datadog Continuous Profiler |
| **UI/Dashboards** | Grafana OSS | Grafana OSS | Grafana OSS + Cloud | Datadog / Grafana Enterprise |
| **OTel Collector** | otelcol-contrib | otelcol-contrib | ADOT / OTel Operator | Datadog Agent / OTel Contrib |
| **Traffic L4** | — | HAProxy + Keepalived | NLB / TCP LB / Azure LB | AWS Global Accelerator / NLB |
| **Traffic L7** | Traefik | NGINX + HAProxy | ALB / Cloud HTTP LB / App Gateway | Cloudflare + App Gateway / ALB |
| **Service Mesh** | — | Consul Connect | Istio / Linkerd | Istio + Envoy Gateway |
| **Global Traffic** | — | — | Route 53 / Cloud DNS / Azure Traffic Mgr | Cloudflare / Argo / AWS Global Accelerator |
| **Cost Tools** | Infracost | OpenCost | Kubecost + Cloud Cost Explorer | CloudHealth / Apptio / Spot.io |
| **Cost Tagging** | docker labels | Prometheus labels | Cloud tags + IAM policies | FOCUS spec + automated enforcement |
| **AI Observability** | Langfuse OSS | Langfuse OSS | Langfuse Cloud / Arize Phoenix | Datadog LLM Observability / Arize |

---

## 12-Step Delivery Workflow

1. **Discover** — Inventory the service landscape (languages, frameworks, deployment targets)
2. **Instrument** — Add OTel SDK to each service with semantic conventions
3. **Collect** — Deploy OTel Collector with environment-appropriate receivers/exporters
4. **Aggregate Logs** — Deploy log aggregator (Loki/EFK/cloud) with structured JSON format
5. **Emit Metrics** — Configure Prometheus scraping or push-based metrics pipeline
6. **Trace** — Enable distributed trace context propagation including async/queue boundaries
7. **Alert** — Define SLOs, error budgets, and golden-signal alerting rules
8. **Traffic** — Deploy and configure load balancer tier for the target environment
9. **Mesh** — Apply service mesh for east-west traffic visibility and resilience policies
10. **Cost Tag** — Enforce tagging strategy for per-service/team cost attribution
11. **Cost Dashboard** — Connect cloud billing APIs to cost visibility dashboards
12. **Govern** — Set budgets, anomaly alerts, and FinOps review cadence

---

## Output Specification

For every engagement, deliver:

### Observability Layer
- `otel-collector-config.yaml` — Full OTel Collector pipeline config
- `prometheus-rules.yaml` — Recording rules + SLO alerts + golden signal alerts
- `grafana-dashboard.json` — Golden signals + SLO dashboard
- `instrumentation/` — Per-language OTel SDK setup (Python / Node / Go / Java)
- `logging/` — Log aggregation configs (Promtail / Fluent Bit / CloudWatch agent)

### Traffic Layer
- `nginx/nginx.conf` or `haproxy/haproxy.cfg` or `traefik/dynamic.yaml`
- `service-mesh/` — Istio VirtualService + DestinationRule or Linkerd profiles
- `health-checks/` — Readiness/liveness probe definitions

### Cost Layer
- `cost/tagging-policy.yaml` — Mandatory tag keys per cloud
- `cost/budget-alerts.yaml` — Cloud budget + anomaly alert configs
- `cost/kubecost-values.yaml` (K8s tiers) — Kubecost/OpenCost deployment config

### Environment Compose (Tier 1)
- `docker-compose.observability.yaml` — Full local dev stack

### AI Agents (when enabled)
- `agent-telemetry/` — OpenLLMetry or Langfuse integration code
- `cost/llm-cost-tracker.py` — Token usage + cost tracking per agent

---

## Production Standards

### Observability Standards
- **All services MUST emit OTel traces** with W3C `traceparent` propagation
- **Structured JSON logs** with `trace_id`, `span_id`, `service.name`, `environment`
- **Cardinality limit**: max 50 unique label values per metric dimension
- **Sampling**: head-based 10% default, tail-based 100% for errors; never 100% in production
- **SLOs**: define at minimum Availability SLO (99.9%) and Latency SLO (p99 < Xms) per service
- **Alert fatigue prevention**: alert on symptoms (SLO burn rate), not causes
- **Retention**: metrics 15 days hot, 90 days warm; traces 7 days; logs 30 days (adjust per compliance)

### Traffic Standards
- **Health checks** on every backend: `/health` (liveness) + `/ready` (readiness)
- **Circuit breaker** on every service-to-service call (Istio OutlierDetection or Resilience4j)
- **Rate limiting** at edge: per-IP and per-user-token limits
- **TLS termination** at load balancer; mTLS inside service mesh
- **Connection timeouts**: connect 5s, read 30s, write 30s (adjust per SLA)
- **Retry policy**: max 3 retries with exponential backoff on 5xx; never retry POST unless idempotent

### Cost Standards
- **100% resource tagging** enforced via cloud policy (SCP/Org Policy/Azure Policy)
- **Required tags**: `env`, `team`, `service`, `project`, `cost-center`
- **Budget alerts** at 50%, 80%, 100% of monthly forecast
- **Weekly FinOps review** of top-10 cost drivers
- **Idle resource cleanup**: auto-stop dev/staging after business hours
- **Observability cost budget**: target <5% of total cloud spend on monitoring

### AI Agent Standards (when enabled)
- **Trace every LLM call** with: model, prompt_tokens, completion_tokens, latency, cost
- **Agent step spans**: tool calls, handoffs, and retries as child spans
- **Token budget alerts**: alert when agent exceeds 2× expected token budget
- **Cost attribution**: tag LLM calls with `agent.name`, `workflow.id`, `tenant.id`

---

## Official Documentation URLs

### Observability Tools
- OpenTelemetry: https://opentelemetry.io/docs/
- Prometheus: https://prometheus.io/docs/
- Grafana: https://grafana.com/docs/grafana/latest/
- Loki: https://grafana.com/docs/loki/latest/
- Tempo: https://grafana.com/docs/tempo/latest/
- Jaeger: https://www.jaegertracing.io/docs/latest/
- Datadog: https://docs.datadoghq.com/
- New Relic: https://docs.newrelic.com/
- Dynatrace: https://docs.dynatrace.com/
- Langfuse: https://langfuse.com/docs
- Arize Phoenix: https://docs.arize.com/phoenix

### Cloud-Native Observability
- AWS CloudWatch: https://docs.aws.amazon.com/cloudwatch/
- AWS X-Ray: https://docs.aws.amazon.com/xray/
- AWS Distro for OTel: https://aws-otel.github.io/docs/
- GCP Cloud Monitoring: https://cloud.google.com/monitoring/docs
- GCP Cloud Trace: https://cloud.google.com/trace/docs
- Azure Monitor: https://learn.microsoft.com/en-us/azure/azure-monitor/
- Azure Application Insights: https://learn.microsoft.com/en-us/azure/azure-monitor/app/

### Traffic Engineering
- NGINX: https://nginx.org/en/docs/
- HAProxy: https://cbonte.github.io/haproxy-dconv/2.8/configuration.html
- Traefik: https://doc.traefik.io/traefik/
- Envoy: https://www.envoyproxy.io/docs/envoy/latest/
- Istio: https://istio.io/latest/docs/
- Linkerd: https://linkerd.io/2.15/reference/
- AWS Load Balancing: https://docs.aws.amazon.com/elasticloadbalancing/
- GCP Load Balancing: https://cloud.google.com/load-balancing/docs
- Azure Load Balancer: https://learn.microsoft.com/en-us/azure/load-balancer/
- Azure Application Gateway: https://learn.microsoft.com/en-us/azure/application-gateway/
- Cloudflare Load Balancing: https://developers.cloudflare.com/load-balancing/

### Cost Engineering
- AWS Cost Management: https://docs.aws.amazon.com/cost-management/
- GCP Cloud Billing: https://cloud.google.com/billing/docs
- Azure Cost Management: https://learn.microsoft.com/en-us/azure/cost-management-billing/
- Kubecost: https://docs.kubecost.com/
- OpenCost: https://www.opencost.io/docs/
- Infracost: https://www.infracost.io/docs/
- FinOps Foundation: https://www.finops.org/framework/

---

## Implementation Checklist

### Observability
- [ ] OTel SDK added to all services (auto-instrumentation where available)
- [ ] OTel Collector deployed with appropriate exporters for target environment
- [ ] Structured JSON logging with trace/span correlation fields
- [ ] Log aggregation deployed (Loki / EFK / cloud-native)
- [ ] Prometheus metrics exposed (`/metrics`) or push-gateway configured
- [ ] Distributed traces visible end-to-end in tracing UI
- [ ] SLOs defined and SLO dashboards created in Grafana
- [ ] Alerting rules configured with proper routing (PagerDuty/Slack/OpsGenie)
- [ ] Dashboards cover: golden signals, SLOs, resource saturation, business KPIs

### Traffic Engineering
- [ ] Health check endpoints (`/health`, `/ready`) on all services
- [ ] Load balancer configured with health checks and appropriate algorithm
- [ ] TLS certificates configured and auto-renewed
- [ ] Rate limiting configured at edge
- [ ] Circuit breaker configured for inter-service calls
- [ ] Retry policies defined with exponential backoff
- [ ] Traffic splitting configured for canary deployments
- [ ] Service mesh deployed (Tier 3+) with mTLS enabled

### Cost Engineering
- [ ] All resources tagged with mandatory tag set
- [ ] Cost allocation tags activated in cloud billing console
- [ ] Monthly budgets set with 50/80/100% alert thresholds
- [ ] Cost anomaly detection enabled
- [ ] Kubecost/OpenCost deployed (K8s environments)
- [ ] Unused resource detection automated
- [ ] FinOps review process established

### AI Agents (when enabled)
- [ ] LLM calls instrumented with token + cost metadata spans
- [ ] Agent workflow traces include all tool calls and handoffs
- [ ] Token budget monitoring and alerting configured
- [ ] Cost attribution per agent/workflow/tenant established
