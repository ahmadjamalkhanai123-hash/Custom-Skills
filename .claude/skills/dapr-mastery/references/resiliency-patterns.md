# Dapr Resiliency Patterns Reference

Dapr resiliency policies define fault tolerance for service invocation, pub/sub, and component
operations. Applied via `Resiliency` CRD in Kubernetes or local YAML in self-hosted.

## Resiliency Resource Structure

```yaml
apiVersion: dapr.io/v1alpha1
kind: Resiliency
metadata:
  name: production-resiliency
  namespace: production
spec:
  policies:
    retries: { ... }        # Named retry policies
    timeouts: { ... }       # Named timeout policies
    circuitBreakers: { ... } # Named circuit breaker policies

  targets:
    apps: { ... }           # Apply to service invocation targets
    components: { ... }     # Apply to state/pubsub/binding components
    actors: { ... }         # Apply to actor calls
```

---

## Retry Policies

### Constant Retry
```yaml
spec:
  policies:
    retries:
      constant-retry:
        policy: constant
        duration: 2s          # Wait 2s between retries
        maxRetries: 3         # Max 3 attempts (total 4)

      # With maximum interval cap
      constant-with-jitter:
        policy: constant
        duration: 1s
        maxRetries: 5
```

### Exponential Backoff (Recommended for Production)
```yaml
spec:
  policies:
    retries:
      exponential-backoff:
        policy: exponential
        initialInterval: 500ms     # Start with 500ms
        randomizationFactor: 0.5   # ±50% jitter (prevents thundering herd)
        multiplier: 1.5            # Each retry: interval × 1.5
        maxInterval: 30s           # Cap at 30s
        maxRetries: 5

      # Database operations — more patient
      db-retry:
        policy: exponential
        initialInterval: 1s
        randomizationFactor: 0.3
        multiplier: 2.0
        maxInterval: 60s
        maxRetries: 10
```

### Retry on Specific Status Codes
```yaml
retries:
  http-retry:
    policy: exponential
    initialInterval: 200ms
    maxRetries: 3
    # Retry only on transient errors (5xx, 429)
    # Dapr automatically skips retry on 4xx client errors
```

---

## Timeout Policies

```yaml
spec:
  policies:
    timeouts:
      # Fast operations
      api-timeout:
        duration: 5s

      # Database queries
      db-timeout:
        duration: 10s

      # External payment processing
      payment-timeout:
        duration: 30s

      # Long-running batch operations
      batch-timeout:
        duration: 5m
```

---

## Circuit Breaker Policies

```yaml
spec:
  policies:
    circuitBreakers:
      # Standard circuit breaker
      standard-cb:
        maxRequests: 1          # Requests allowed in half-open state
        interval: 10s           # Cyclic period for counting failures
        timeout: 60s            # Time in open state before half-open
        trip: consecutiveFailures > 5  # Trip condition

      # More sensitive — trip faster
      sensitive-cb:
        maxRequests: 2
        interval: 5s
        timeout: 30s
        trip: consecutiveFailures > 3

      # Less sensitive — tolerate bursts
      tolerant-cb:
        maxRequests: 5
        interval: 60s
        timeout: 120s
        trip: consecutiveFailures > 10
```

### Circuit Breaker States
```
CLOSED (normal) → failures > threshold → OPEN (blocking) → timeout → HALF-OPEN (testing)
     ↑                                                                        │
     └──────────────────── success ──────────────────────────────────────────┘
```

---

## Complete Production Resiliency Policy

```yaml
apiVersion: dapr.io/v1alpha1
kind: Resiliency
metadata:
  name: production-resiliency
  namespace: production
spec:
  policies:
    retries:
      default-retry:
        policy: exponential
        initialInterval: 500ms
        randomizationFactor: 0.5
        multiplier: 1.5
        maxInterval: 30s
        maxRetries: 3

      critical-retry:
        policy: exponential
        initialInterval: 200ms
        randomizationFactor: 0.3
        multiplier: 2.0
        maxInterval: 60s
        maxRetries: 7

      no-retry:
        policy: constant
        maxRetries: 0          # Idempotency concern — no retry

    timeouts:
      fast-timeout: { duration: 3s }
      standard-timeout: { duration: 10s }
      slow-timeout: { duration: 30s }
      batch-timeout: { duration: 5m }

    circuitBreakers:
      standard-cb:
        maxRequests: 1
        interval: 10s
        timeout: 60s
        trip: consecutiveFailures > 5

      aggressive-cb:
        maxRequests: 1
        interval: 5s
        timeout: 30s
        trip: consecutiveFailures > 3

  targets:
    apps:
      # Payment service — critical, aggressive protection
      payment-service:
        timeout: slow-timeout
        retry: critical-retry
        circuitBreaker: aggressive-cb

      # Order service — standard
      order-service:
        timeout: standard-timeout
        retry: default-retry
        circuitBreaker: standard-cb

      # Notification service — fire-and-forget, no retry
      notification-service:
        timeout: fast-timeout
        retry: no-retry

    components:
      # State store — retry with CB
      statestore:
        outbound:
          timeout: standard-timeout
          retry: default-retry
          circuitBreaker: standard-cb

      # Pub/Sub — retry on send failures
      kafka-pubsub:
        outbound:
          timeout: slow-timeout
          retry: default-retry
          circuitBreaker: standard-cb
        inbound:
          timeout: slow-timeout
          retry: default-retry

    actors:
      myActors:
        timeout: standard-timeout
        retry: default-retry
        circuitBreaker: standard-cb
        circuitBreakerScope: id    # Per-actor CB instance
        circuitBreakerCacheSize: 5000  # Track 5000 actor CBs
```

---

## Resiliency for Actors

```yaml
targets:
  actors:
    OrderActor:
      timeout: standard-timeout
      retry:
        policy: exponential
        initialInterval: 1s
        maxRetries: 5
        maxInterval: 30s
      circuitBreaker: standard-cb
      circuitBreakerScope: type     # One CB per actor TYPE (not per ID)

    PaymentActor:
      timeout: slow-timeout
      retry: critical-retry
      circuitBreaker: aggressive-cb
      circuitBreakerScope: id       # One CB per actor INSTANCE
      circuitBreakerCacheSize: 10000
```

---

## Per-Namespace Scoping

```yaml
# Apply resiliency policy only to specific app IDs
metadata:
  name: payment-resiliency
  namespace: production
spec:
  # ... policies ...
  # scopes field applies the ENTIRE policy to specific apps
  # (no explicit scopes = applies to all apps in namespace)
```

---

## Self-Hosted Resiliency (local file)

```yaml
# resiliency.yaml in component path
apiVersion: dapr.io/v1alpha1
kind: Resiliency
metadata:
  name: local-resiliency
spec:
  policies:
    retries:
      default-retry:
        policy: exponential
        initialInterval: 200ms
        maxRetries: 3
  targets:
    apps:
      backend-service:
        retry: default-retry
        timeout: { duration: 10s }
```

---

## Resiliency Verification

```bash
# Check resiliency policies applied
dapr components -k -n production

# Verify via metrics
# Counter: dapr_http_client_retry_count
# Gauge:   dapr_circuit_breaker_state (0=closed, 1=open, 2=half-open)
```

---

## Resiliency Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Retry non-idempotent ops | Duplicate charges, double-inserts | Use `no-retry` or idempotency keys |
| No jitter on retry | Thundering herd on recovery | Set `randomizationFactor: 0.5` |
| No circuit breaker | Cascading failures | Add CB to every service target |
| Timeout too high | Resources held too long | Tune per operation type |
| Global CB for actors | One bad actor trips all | Set `circuitBreakerScope: id` |
| Missing inbound pubsub retry | Message loss on consumer crash | Add inbound retry policy |
| Retry on 4xx | Retrying client errors | Dapr handles this automatically |
