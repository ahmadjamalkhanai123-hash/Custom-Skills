# Anti-Patterns
## Common Observability, Traffic, and Cost Engineering Mistakes

---

## Observability Anti-Patterns

### AP-O1: High Cardinality Labels (Metric Explosion)
```yaml
# WRONG — user_id creates millions of time series
http_requests_total{method="GET", user_id="user_12345", path="/api/orders"}

# RIGHT — aggregate at a meaningful level
http_requests_total{method="GET", user_tier="premium", path="/api/orders"}
```
**Impact**: Prometheus OOM crash, $10K+/month in Grafana Cloud costs, query timeouts
**Rule**: Max 50 unique values per label dimension

---

### AP-O2: Logging Everything at DEBUG in Production
```python
# WRONG — generates terabytes of noise
logging.setLevel(logging.DEBUG)
log.debug(f"Processing item {item}")  # Called 10K times/second

# RIGHT — INFO for normal flow, DEBUG only in development
if os.getenv("ENV") == "development":
    logging.setLevel(logging.DEBUG)
else:
    logging.setLevel(logging.INFO)
```
**Impact**: 100x log volume, massive storage cost, signal buried in noise
**Rule**: Production default is INFO; disable DEBUG via feature flag only for specific sessions

---

### AP-O3: 100% Trace Sampling Rate in Production
```python
# WRONG — 100% sampling at 10K req/s = 100% bandwidth on traces
sampler = ALWAYS_ON

# RIGHT — Probabilistic + tail-based for errors
sampler = ParentBased(root=TraceIdRatioBased(0.1))  # 10% + keep all errors
```
**Impact**: 10x storage cost, Jaeger/Tempo OOM, DataDog APM bill shock
**Rule**: 1-10% head-based sampling; tail-based 100% for errors and slow requests

---

### AP-O4: Missing Trace Correlation in Logs
```python
# WRONG — logs have no trace context
log.error(f"Payment failed: {error}")

# RIGHT — inject trace_id and span_id into every log
span = trace.get_current_span()
ctx = span.get_span_context()
log.error("payment_failed",
    error=str(error),
    trace_id=format(ctx.trace_id, '032x'),
    span_id=format(ctx.span_id, '016x'),
)
```
**Impact**: Cannot correlate logs to traces during incident, debugging takes 10x longer

---

### AP-O5: Alert on Causes, Not Symptoms
```yaml
# WRONG — alerts on internal metrics that may not affect users
- alert: HighCPU
  expr: cpu_usage_percent > 80  # CPU at 80% might be fine

# RIGHT — alert on user-facing symptoms (SLO breach)
- alert: SLOBurnRateCritical
  expr: |
    job:slo_availability:ratio_rate1h < (1 - 14.4 * (1 - 0.999))
```
**Impact**: Alert fatigue, on-call burnout, real issues missed in noise
**Rule**: Alert on SLO burn rate and golden signals; never alert on CPU/memory alone

---

### AP-O6: No Retention Policy (Infinite Storage Growth)
```yaml
# WRONG — no retention = infinite disk growth
storage.tsdb:
  path: /var/lib/prometheus

# RIGHT — explicit retention policy
storage.tsdb:
  retention.time: 15d
  retention.size: 50GB  # Whichever comes first
```
**Impact**: Disk full → service outage, runaway storage costs

---

### AP-O7: Structured Logging Ignored (printf-style logs)
```python
# WRONG — unstructured, impossible to parse/filter
logger.error(f"Order {order_id} failed for user {user_id}: {error}")

# RIGHT — structured key-value pairs
logger.error("order_failed",
    order_id=order_id, user_id=user_id, error_type=type(error).__name__
)
```
**Impact**: Log queries require regex, no faceted filtering, Loki/ES queries 100x slower

---

### AP-O8: No SLO Definition ("Just Alert on Everything")
```yaml
# WRONG — no SLOs, teams alert on whatever seems important
- alert: SlowQuery
  expr: db_query_duration_seconds > 0.1  # 100ms seems slow?

# RIGHT — define SLOs first, alerts follow
# SLO: 99.9% of requests complete in < 500ms
# → Alert when burning error budget at 14.4x rate
```
**Impact**: No shared understanding of reliability targets, constant toil, no prioritization

---

### AP-O9: Observability as Afterthought (Add-On at Deploy Time)
```
Wrong approach: Build app → Deploy → "Add monitoring later" → Incident → Panic

Right approach: Define SLOs → Design metrics/traces → Code with instrumentation → Deploy monitored
```
**Impact**: Blind spots during incidents, expensive retro-instrumentation

---

## Traffic Engineering Anti-Patterns

### AP-T1: No Health Checks on Backends
```nginx
# WRONG — no health check = traffic sent to dead backends
upstream order_service {
    server order1:8080;
    server order2:8080;
}

# RIGHT — passive health checks (OSS NGINX)
upstream order_service {
    server order1:8080 max_fails=3 fail_timeout=30s;
    server order2:8080 max_fails=3 fail_timeout=30s;
}
```
**Impact**: Requests routed to crashed backends, 50x error rate spikes

---

### AP-T2: No Circuit Breaker Between Services
```python
# WRONG — one failing service cascades to all callers
async def call_inventory(sku: str):
    return await httpx.get(f"http://inventory-svc/sku/{sku}")  # No timeout, no circuit breaker

# RIGHT — circuit breaker with timeout
async def call_inventory(sku: str):
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            return await circuit_breaker.call(
                client.get, f"http://inventory-svc/sku/{sku}"
            )
        except CircuitBreakerOpen:
            return {"available": True}  # Degrade gracefully
```
**Impact**: Cascading failures bring down entire microservice graph

---

### AP-T3: Retrying Non-Idempotent Operations
```python
# WRONG — retrying POST /payment can double-charge customers
@retry(max_attempts=3)
async def charge_card(amount: float):
    return await payment_gateway.post("/charge", {"amount": amount})

# RIGHT — check idempotency; use idempotency keys
async def charge_card(amount: float, idempotency_key: str):
    return await payment_gateway.post(
        "/charge",
        {"amount": amount},
        headers={"Idempotency-Key": idempotency_key}
    )
# Only retry on connection errors, not on business errors
```
**Impact**: Double charges, duplicate orders, data corruption

---

### AP-T4: Thundering Herd on Recovery
```
Scenario: Service goes down for 60s → queue builds up → service recovers →
          all 60s of queued requests hit simultaneously → service crashes again

Fix:
- Exponential backoff with jitter in clients
- Request queue with rate limiting
- Gradual traffic ramp-up via load balancer health check thresholds
```

---

### AP-T5: Missing TLS Between Internal Services (mTLS Required in Production)
```
# WRONG — plaintext internal traffic
http://payment-svc:8080/charge  # Unencrypted in shared network

# RIGHT — mTLS via service mesh
Istio/Linkerd PeerAuthentication: STRICT mode
All east-west traffic encrypted and mutually authenticated
```
**Impact**: Man-in-the-middle attacks on internal network, compliance violations

---

### AP-T6: Static Load Balancer Config (No Dynamic Discovery)
```
# WRONG — hardcoded IP list requires manual update on scale
upstream order_service {
    server 10.0.1.10:8080;   # What when this pod is replaced?
    server 10.0.1.11:8080;
}

# RIGHT — service discovery
# Kubernetes: Use ClusterIP Service (kube-proxy handles load balancing)
# Consul: consul-template updates NGINX upstream automatically
# Traefik/Envoy: Dynamic discovery via Docker/K8s provider
```

---

## Cost Engineering Anti-Patterns

### AP-C1: Untagged Resources
```
# WRONG — deploying without tags
aws ec2 run-instances --instance-type m5.xlarge --image-id ami-xxx

# RIGHT — enforce tags at deployment
aws ec2 run-instances \
  --instance-type m5.xlarge \
  --image-id ami-xxx \
  --tag-specifications 'ResourceType=instance,Tags=[
    {Key=env,Value=production},
    {Key=team,Value=platform},
    {Key=service,Value=order-api}
  ]'
```
**Impact**: Cannot attribute costs, FinOps reviews impossible, no accountability

---

### AP-C2: Running Dev Resources 24/7
```
# WRONG — dev/staging VMs run nights and weekends ($1000s/month wasted)

# RIGHT — schedule-based auto-stop
# AWS: Instance Scheduler
# GCP: Cloud Scheduler + Cloud Functions to stop/start
# Azure: DevTest Labs auto-shutdown
# K8s: kube-downscaler (scales to 0 outside business hours)
```
**Impact**: 40-60% of dev spend wasted on idle resources

---

### AP-C3: No Budget Alerts Until Bill Arrives
```
# WRONG — monthly surprise: "Why is our AWS bill $50K this month?"

# RIGHT — proactive budget alerts at 50/80/100% with forecasted overage alerts
aws budgets create-budget ... with alert thresholds
```
**Impact**: Budget overruns discovered too late to respond

---

### AP-C4: Over-Provisioned Kubernetes Resources
```yaml
# WRONG — requesting too much, low actual usage
resources:
  requests:
    memory: "4Gi"   # Actual usage: 256Mi
    cpu: "2000m"    # Actual usage: 100m
  limits:
    memory: "8Gi"
    cpu: "4000m"

# RIGHT — use Goldilocks/VPA recommendations
# Install Goldilocks, label namespace, check UI for recommendations
```
**Impact**: Node count 5-10x higher than needed, wasted $10Ks/month

---

### AP-C5: Storing All Observability Data at Hot Tier Forever
```
# WRONG — 1 year of metrics in Prometheus local storage
# $500/month in SSD vs $5/month in S3

# RIGHT — tiered retention
Prometheus local: 15 days (fast queries for recent incidents)
Thanos S3: 90 days (slower queries for trend analysis)
Glacier: 1 year (compliance only, rarely queried)
```

---

### AP-C6: Ignoring Data Egress Costs
```
# WRONG — microservices calling each other across AZs constantly
Order Service (us-east-1a) → Inventory Service (us-east-1b): $0.01/GB

# RIGHT — deploy dependent services in the same AZ
# Or use service mesh to route intra-AZ first
# Cross-AZ: $0.01/GB × 1TB/day = $10/day = $300/month per pair
```
**Impact**: Egress costs can exceed compute costs for data-heavy services

---

### AP-C7: Not Using Spot/Preemptible for Batch Workloads
```yaml
# WRONG — running ML training on on-demand instances
instanceType: ml.m5.4xlarge  # $0.768/hour

# RIGHT — Spot instances for fault-tolerant batch
# AWS Spot: up to 90% discount = $0.077/hour
# Implement checkpointing for preemption handling
```
**Impact**: 5-10x higher compute cost for jobs that can tolerate interruption

---

## AI Agent Cost Anti-Patterns

### AP-A1: Using Largest Model for Every Task
```python
# WRONG — always using most expensive model
response = anthropic.messages.create(
    model="claude-opus-4-6",  # $15/M input, $75/M output
    messages=[{"role": "user", "content": "Summarize this in one line."}]
)

# RIGHT — match model to task complexity
MODELS = {
    "classification": "claude-haiku-4-5-20251001",  # $0.25/M — simple tasks
    "reasoning": "claude-sonnet-4-6",               # $3/M — balanced
    "complex_analysis": "claude-opus-4-6",          # $15/M — hardest tasks only
}
```
**Impact**: 10-60x higher LLM costs than necessary

---

### AP-A2: No Token Budget Enforcement
```python
# WRONG — unlimited context accumulation
messages = conversation_history + [new_message]  # Can grow to 200K tokens

# RIGHT — sliding window + summarization
if count_tokens(messages) > 50000:
    summary = summarize_history(messages[:-10])
    messages = [{"role": "system", "content": summary}] + messages[-10:]
```
**Impact**: Runaway costs; single agent run can cost $50+ undetected
