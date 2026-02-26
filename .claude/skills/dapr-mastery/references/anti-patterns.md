# Dapr Anti-Patterns & Common Mistakes

---

## Workflow Anti-Patterns

### 1. I/O in Orchestrator (Critical)
```python
# ❌ WRONG — breaks deterministic replay
def my_workflow(ctx, input):
    response = requests.get("https://api.example.com/data")  # I/O!
    db.insert(response.json())  # Side effect!
    return response.json()

# ✅ CORRECT — I/O only in activities
def my_workflow(ctx, input):
    result = yield ctx.call_activity(fetch_data, input=input)
    return result

def fetch_data(ctx, input):
    response = requests.get("https://api.example.com/data")  # Safe here
    db.insert(response.json())
    return response.json()
```

### 2. Non-Deterministic Time
```python
# ❌ WRONG — different value on replay
def my_workflow(ctx, input):
    expiry = datetime.now() + timedelta(hours=1)  # Non-deterministic!

# ✅ CORRECT — use workflow-provided time
def my_workflow(ctx, input):
    expiry = ctx.current_utc_datetime + timedelta(hours=1)
```

### 3. Infinite Loop (History Explosion)
```python
# ❌ WRONG — history grows unboundedly
def monitor_workflow(ctx, order_id):
    while True:  # Never ends, history = infinite
        status = yield ctx.call_activity(check_status, input=order_id)
        if status == "done":
            break
        yield ctx.create_timer(timedelta(minutes=5))

# ✅ CORRECT — continue_as_new resets history
def monitor_workflow(ctx, order_id):
    status = yield ctx.call_activity(check_status, input=order_id)
    if status != "done":
        yield ctx.create_timer(timedelta(minutes=5))
        ctx.continue_as_new(order_id)  # Fresh history
```

### 4. Random/UUID in Orchestrator
```python
# ❌ WRONG — generates different value on each replay
def my_workflow(ctx, input):
    correlation_id = str(uuid.uuid4())  # Different each replay!
    yield ctx.call_activity(process, input={"id": correlation_id, **input})

# ✅ CORRECT — generate IDs in activities
def my_workflow(ctx, input):
    correlation_id = yield ctx.call_activity(generate_id, input=None)
    yield ctx.call_activity(process, input={"id": correlation_id, **input})
```

### 5. No Compensation (Partial Failures)
```python
# ❌ WRONG — leaves system in inconsistent state on failure
def checkout_workflow(ctx, order):
    yield ctx.call_activity(reserve_inventory, input=order)
    yield ctx.call_activity(charge_payment, input=order)  # Fails here!
    # inventory reserved but payment failed — stuck state!

# ✅ CORRECT — implement saga compensation
def checkout_workflow(ctx, order):
    compensations = []
    try:
        reservation = yield ctx.call_activity(reserve_inventory, input=order)
        compensations.append((release_inventory, reservation["id"]))
        payment = yield ctx.call_activity(charge_payment, input=order)
        compensations.append((refund_payment, payment["id"]))
    except Exception:
        for activity, args in reversed(compensations):
            yield ctx.call_activity(activity, input=args)
        raise
```

---

## Actor Anti-Patterns

### 6. Timer Instead of Reminder for Durable Work
```python
# ❌ WRONG — timer lost if actor deactivates before firing
async def schedule_payment(self):
    await self.register_timer("pay", "charge_card", timedelta(minutes=30), timedelta(0))

# ✅ CORRECT — reminder survives deactivation
async def schedule_payment(self):
    await self.register_reminder("pay", b"", timedelta(minutes=30), timedelta(0))
```

### 7. Missing remindersStoragePartitions at Scale
```yaml
# ❌ WRONG — all reminders in one key = hot spot
entities: ["ProductActor"]
# remindersStoragePartitions: 0  (default)

# ✅ CORRECT — partition for >100K actors
entities: ["ProductActor"]
remindersStoragePartitions: 7
```

### 8. Large State per Actor
```python
# ❌ WRONG — 10MB state per actor = slow serialization + memory pressure
async def update_actor(self, full_dataset: dict):
    await self._state_manager.set_state("data", full_dataset)  # 10MB!

# ✅ CORRECT — store references, load on demand
async def update_actor(self, chunk: dict):
    await self._state_manager.set_state(f"chunk:{chunk['index']}", chunk["data"])
    await self._state_manager.set_state("meta", {"chunks": chunk["total"]})
```

### 9. Missing drainRebalancedActors
```yaml
# ❌ WRONG — in-flight calls dropped during pod reschedule
drainRebalancedActors: false

# ✅ CORRECT
drainRebalancedActors: true
drainOngoingCallTimeout: 60s
```

### 10. Actor per Request (Fan-Out Abuse)
```python
# ❌ WRONG — creating millions of actors per HTTP request
for item in 100_000_items:
    actor = ActorProxy("ItemActor", ActorId(item.id))
    await actor.process(item)    # 100K actors created per request!

# ✅ CORRECT — batch within actor or use pub/sub
await publish_batch(pubsub, "items-topic", items)
# Worker pool consumes and creates bounded actor set
```

---

## State Management Anti-Patterns

### 11. No ETag for Concurrent Updates
```python
# ❌ WRONG — last-write-wins, silent data loss
client.save_state("statestore", "counter", new_value)

# ✅ CORRECT — optimistic concurrency with ETag
resp = client.get_state("statestore", "counter")
etag = resp.etag
client.save_state("statestore", "counter", new_value,
                  state_options=StateOptions(concurrency=StateConcurrency.first_write),
                  etag=etag)
# Raises error if another writer changed it first
```

### 12. Plaintext Secrets in Component YAML
```yaml
# ❌ WRONG — secrets in plain text (never in production!)
metadata:
  - name: redisPassword
    value: "mysupersecretpassword"

# ✅ CORRECT — always secretKeyRef
metadata:
  - name: redisPassword
    secretKeyRef:
      name: redis-credentials
      key: password
```

### 13. Missing Component Scopes
```yaml
# ❌ WRONG — all services can access production DB
kind: Component
metadata:
  name: prod-statestore
spec:
  type: state.redis
# No scopes — any app can access!

# ✅ CORRECT
scopes:
  - order-service
  - payment-service
```

---

## Pub/Sub Anti-Patterns

### 14. Missing Dead Letter Topic
```yaml
# ❌ WRONG — failed messages lost silently
kind: Subscription
spec:
  pubsubname: kafka-pubsub
  topic: orders
  route: /orders/handler

# ✅ CORRECT
spec:
  pubsubname: kafka-pubsub
  topic: orders
  route: /orders/handler
  deadLetterTopic: orders-dlq   # Failed messages → DLQ
```

### 15. Returning 200 on Processing Failure
```python
# ❌ WRONG — tells Dapr success, message lost forever
@app.post("/orders/handler")
def handle_order(event: dict):
    try:
        process_order(event)
    except Exception:
        pass    # Swallowed! Returns 200 → message ACK'd and dropped
    return {}

# ✅ CORRECT
@app.post("/orders/handler")
def handle_order(event: dict):
    try:
        process_order(event)
        return {"status": "SUCCESS"}
    except RetryableError:
        return {"status": "RETRY"}      # Dapr will retry
    except PoisonPill:
        return {"status": "DROP"}       # Intentional discard → to DLQ
```

---

## Resiliency Anti-Patterns

### 16. No Resiliency Policy (Default Behavior)
```yaml
# ❌ WRONG — no resilience = first failure = user error

# ✅ CORRECT — define for every service and component
kind: Resiliency
spec:
  targets:
    apps:
      my-service:
        retry: exponential-backoff
        circuitBreaker: standard-cb
        timeout: standard-timeout
```

### 17. Retrying Non-Idempotent Operations
```python
# ❌ WRONG — charging twice!
# Resiliency retries charge-payment on timeout
# If charge succeeded but response timed out → double charge

# ✅ CORRECT — idempotency key prevents duplicates
def charge_payment(ctx, data):
    idempotency_key = data["orderId"]   # Use business key
    return payment_gateway.charge(
        amount=data["amount"],
        idempotency_key=idempotency_key  # Provider deduplicates
    )
```

---

## Security Anti-Patterns

### 18. defaultAction: allow in ACL
```yaml
# ❌ WRONG — all services can call all other services
accessControl:
  defaultAction: allow   # Zero-trust violation!

# ✅ CORRECT
accessControl:
  defaultAction: deny    # Allowlist only
  policies:
    - appId: order-service
      defaultAction: allow
      operations:
        - name: /orders/**
          action: allow
```

### 19. Disabled mTLS
```yaml
# ❌ NEVER disable mTLS in production
global:
  mtls:
    enabled: false   # DO NOT DO THIS

# mTLS is on by default — don't touch it
```

---

## Performance Anti-Patterns

### 20. Sidecar Without Resource Limits
```yaml
# ❌ WRONG — sidecar starves production pods
annotations:
  dapr.io/enabled: "true"
  # No resource limits → unbounded

# ✅ CORRECT
annotations:
  dapr.io/sidecar-cpu-request: "100m"
  dapr.io/sidecar-cpu-limit: "300m"
  dapr.io/sidecar-memory-request: "128Mi"
  dapr.io/sidecar-memory-limit: "256Mi"
  dapr.io/env: "GOMEMLIMIT=230MiB"
```

### 21. samplingRate: "1" on High-Traffic Services
```yaml
# ❌ WRONG — 100% trace sampling at 10K RPS = huge storage cost
tracing:
  samplingRate: "1"

# ✅ CORRECT — sample 1% in production
tracing:
  samplingRate: "0.01"
  # Or use head-based sampling at load balancer level
```

### 22. Single Replica for Actor Placement
```yaml
# ❌ WRONG — placement service is SPOF, all actors unavailable on restart
dapr_placement:
  replicaCount: 1

# ✅ CORRECT — HA requires odd number for Raft consensus
dapr_placement:
  replicaCount: 3    # Or 5 for highest availability
```
