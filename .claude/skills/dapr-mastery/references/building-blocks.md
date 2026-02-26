# Dapr Building Blocks Reference

All 11 Dapr building blocks with API specs, component configs, and production guidance.
Dapr version: **v1.15+ / v1.16** (latest stable).

---

## 1. Service Invocation

**Purpose**: Synchronous service-to-service calls with built-in mTLS, retries, tracing.

```
App A → Dapr Sidecar A →[mTLS]→ Dapr Sidecar B → App B
```

### API
```
GET|POST|PUT|DELETE http://localhost:3500/v1.0/invoke/{appId}/method/{method-name}
```

### SDK (Python)
```python
from dapr.clients import DaprClient
with DaprClient() as d:
    resp = d.invoke_method("order-service", "getOrder", data=b'{"id":"123"}',
                           content_type="application/json")
```

### Production Notes
- App ID must match `dapr.io/app-id` annotation exactly
- Use name resolution: Kubernetes (default), Consul, mDNS (self-hosted)
- Enable `allowedOperations` in Dapr config for least-privilege invocation
- Resiliency policies applied automatically to invocation calls

---

## 2. State Management

**Purpose**: Key/value state with pluggable backends; supports ACID transactions.

### API
```
POST   /v1.0/state/{storeName}             # save state (bulk)
GET    /v1.0/state/{storeName}/{key}        # get state
DELETE /v1.0/state/{storeName}/{key}        # delete state
POST   /v1.0/state/{storeName}/transaction  # transactional (ACID)
POST   /v1.0/state/{storeName}/bulk         # bulk get
```

### State Options
```json
{
  "key": "order-42",
  "value": {...},
  "options": {
    "concurrency": "first-write",   // or "last-write"
    "consistency": "strong"          // or "eventual"
  },
  "etag": "abc123"                   // optimistic concurrency
}
```

### Component: Redis (Dev/Production)
```yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: statestore
  namespace: production
spec:
  type: state.redis
  version: v1
  metadata:
    - name: redisHost
      secretKeyRef: { name: redis-secret, key: host }
    - name: redisPassword
      secretKeyRef: { name: redis-secret, key: password }
    - name: enableTLS
      value: "true"
    - name: failover
      value: "true"          # Redis Sentinel
    - name: replicaCount
      value: "3"
    - name: ttlInSeconds
      value: "3600"
scopes: [order-service]
```

### Component: PostgreSQL (Production)
```yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: statestore-pg
spec:
  type: state.postgresql/v2
  version: v1
  metadata:
    - name: connectionString
      secretKeyRef: { name: pg-secret, key: connStr }
    - name: cleanupIntervalInSeconds
      value: "300"
    - name: tablePrefix
      value: "dapr_"
```

### Component: Azure Cosmos DB
```yaml
spec:
  type: state.azure.cosmosdb
  version: v1
  metadata:
    - name: url
      secretKeyRef: { name: cosmos-secret, key: url }
    - name: masterKey
      secretKeyRef: { name: cosmos-secret, key: key }
    - name: database
      value: "daprDB"
    - name: collection
      value: "daprState"
    - name: partitionKey
      value: "partitionKey"
```

---

## 3. Publish & Subscribe

**Purpose**: Async event messaging with at-least-once delivery guarantees.

### API
```
POST /v1.0/publish/{pubsubName}/{topic}     # publish
# Subscribe: app registers endpoint /dapr/subscribe or component scoping
```

### Subscription (Programmatic)
```python
# FastAPI + Dapr
from dapr.ext.fastapi import DaprApp
dapr_app = DaprApp(app)

@dapr_app.subscribe(pubsub="kafka-pubsub", topic="orders")
def order_handler(event: CloudEvent):
    # Return {"status": "SUCCESS"} | "RETRY" | "DROP"
    return {"status": "SUCCESS"}
```

### Subscription (Declarative YAML)
```yaml
apiVersion: dapr.io/v1alpha1
kind: Subscription
metadata:
  name: order-subscription
spec:
  pubsubname: kafka-pubsub
  topic: orders
  route: /orders/handler
  deadLetterTopic: orders-dlq    # Dead letter queue
  bulkSubscribe:
    enabled: true
    maxMessagesCount: 100
    maxAwaitDurationMs: 1000
scopes: [order-processor]
```

### Component: Kafka (Production)
```yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: kafka-pubsub
spec:
  type: pubsub.kafka
  version: v1
  metadata:
    - name: brokers
      value: "kafka-broker:9092"
    - name: consumerGroup
      value: "dapr-consumer-group"
    - name: authType
      value: "certificate"
    - name: caCert
      secretKeyRef: { name: kafka-secret, key: caCert }
    - name: clientCert
      secretKeyRef: { name: kafka-secret, key: cert }
    - name: clientKey
      secretKeyRef: { name: kafka-secret, key: key }
    - name: initialOffset
      value: "newest"
    - name: maxMessageBytes
      value: "1048576"
```

### Component: RabbitMQ (Production)
```yaml
spec:
  type: pubsub.rabbitmq
  version: v1
  metadata:
    - name: host
      secretKeyRef: { name: rabbitmq-secret, key: uri }
    - name: durable
      value: "true"
    - name: deletedWhenUnused
      value: "false"
    - name: autoAck
      value: "false"
    - name: deliveryMode
      value: "2"        # persistent
    - name: prefetchCount
      value: "10"
```

### CloudEvent Envelope
Dapr wraps messages in CloudEvent v1.0:
```json
{
  "id": "uuid",
  "specversion": "1.0",
  "type": "com.example.orders.created",
  "source": "order-service",
  "time": "2025-01-01T00:00:00Z",
  "datacontenttype": "application/json",
  "data": { "orderId": "42" }
}
```

---

## 4. Input/Output Bindings

**Purpose**: Connect to external systems (queues, storage, HTTP, cron) without SDK.

### Output Binding (Invoke)
```
POST /v1.0/bindings/{name}
Body: { "data": {...}, "metadata": {...}, "operation": "create" }
```

### Input Binding (Receive)
```
App exposes: POST /{binding-name}   # Dapr calls this
```

### Component: Cron (Scheduler alternative pre-v1.14)
```yaml
spec:
  type: bindings.cron
  version: v1
  metadata:
    - name: schedule
      value: "@every 10m"
```

### Component: HTTP Output
```yaml
spec:
  type: bindings.http
  version: v1
  metadata:
    - name: url
      value: "https://api.external.com/webhook"
    - name: MTLSRootCA
      secretKeyRef: { name: tls-secret, key: ca }
```

---

## 5. Secrets Management

**Purpose**: Retrieve secrets from external stores without code changes.

### API
```
GET /v1.0/secrets/{storeName}/{secretName}
GET /v1.0/secrets/{storeName}/bulk
```

### SDK
```python
with DaprClient() as d:
    secret = d.get_secret("vault-store", "db-password")
    print(secret.secret["db-password"])
```

### Component: Kubernetes (Default in K8s)
```yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: kubernetes-secrets
spec:
  type: secretstores.kubernetes
  version: v1
```

### Component: HashiCorp Vault
```yaml
spec:
  type: secretstores.hashicorp.vault
  version: v1
  metadata:
    - name: vaultAddr
      value: "https://vault.internal:8200"
    - name: tlsCACert
      secretKeyRef: { name: vault-tls, key: ca }
    - name: vaultTokenMountPath
      value: "/var/run/secrets/vault/token"
    - name: enginePath
      value: "secret"
    - name: vaultKVVersion
      value: "v2"
```

### Component: AWS Secrets Manager
```yaml
spec:
  type: secretstores.aws.secretmanager
  version: v1
  metadata:
    - name: region
      value: "us-east-1"
    - name: accessKey
      secretKeyRef: { name: aws-secret, key: accessKey }
    - name: secretKey
      secretKeyRef: { name: aws-secret, key: secretKey }
```

---

## 6. Configuration API

**Purpose**: Dynamic configuration subscription with live update support.

### API
```
GET       /v1.0/configuration/{store}?key=k1&key=k2
SUBSCRIBE /v1.0-alpha1/configuration/{store}/subscribe?key=k1
```

### Component: Redis Configuration
```yaml
spec:
  type: configuration.redis
  version: v1
  metadata:
    - name: redisHost
      secretKeyRef: { name: redis-secret, key: host }
    - name: enableTLS
      value: "true"
```

---

## 7. Distributed Lock

**Purpose**: Mutual exclusion across distributed instances.

### API
```
POST   /v1.0-alpha1/lock/{storeName}
POST   /v1.0-alpha1/unlock/{storeName}
```

### SDK (Go)
```go
resp, err := client.TryLockAlpha1(ctx, "lockstore", &dapr.LockRequest{
    LockOwner:         "instance-1",
    ResourceID:        "my-resource",
    ExpiryInSeconds:   30,
})
```

### Component: Redis Lock
```yaml
spec:
  type: lock.redis
  version: v1
  metadata:
    - name: redisHost
      secretKeyRef: { name: redis-secret, key: host }
    - name: redisPassword
      secretKeyRef: { name: redis-secret, key: password }
```

---

## 8. Jobs API (Scheduler) — Alpha, Stable in v1.15

**Purpose**: Schedule jobs at a specific time or recurring interval.

### API
```
POST   /v1.0-alpha1/jobs/{name}    # schedule job
GET    /v1.0-alpha1/jobs/{name}    # get job
DELETE /v1.0-alpha1/jobs/{name}    # delete job
```

### SDK (Python)
```python
with DaprClient() as d:
    d.schedule_job_alpha1("daily-report",
        schedule="0 8 * * *",       # cron expression
        repeats=0,                   # 0 = infinite
        data=b'{"reportType":"daily"}')
```

### Job Handler
```python
@app.post("/job/daily-report")
async def handle_job(req: Request):
    payload = await req.json()
    # process job
    return {"status": "ok"}
```

---

## 9. Conversation API (Alpha — v1.15+)

**Purpose**: Standardized interface for LLM providers with prompt caching and PII obfuscation.

### API
```
POST /v1.0-alpha1/conversation/{LLM-component}/converse
```

### Component: OpenAI
```yaml
spec:
  type: conversation.openai
  version: v1
  metadata:
    - name: key
      secretKeyRef: { name: openai-secret, key: apiKey }
    - name: model
      value: "gpt-4o"
    - name: cachingEnabled
      value: "true"
```

### SDK (Python)
```python
with DaprClient() as d:
    resp = d.converse_alpha1("openai-llm",
        inputs=[ConversationInput(content="Summarize this...", role="user")],
        parameters={"temperature": 0.7},
        scrubPII=True)             # Built-in PII obfuscation
```

### Tool Calling (v1.16)
```python
tools = [ConversationTool(name="getWeather", description="...")]
resp = d.converse_alpha1("openai-llm", inputs=inputs, tools=tools)
```

---

## 10. Cryptography API (Alpha)

**Purpose**: Encrypt/decrypt data using keys from external vaults.

### API
```
POST /v1.0-alpha1/crypto/{vault}/encrypt
POST /v1.0-alpha1/crypto/{vault}/decrypt
```

### Component: Azure Key Vault
```yaml
spec:
  type: crypto.azure.keyvault
  version: v1
  metadata:
    - name: vaultUri
      value: "https://myvault.vault.azure.net"
```

---

## 11. Dapr Configuration Resource

Configure sidecar behavior per-app:
```yaml
apiVersion: dapr.io/v1alpha1
kind: Configuration
metadata:
  name: app-config
spec:
  tracing:
    samplingRate: "1"
    otel:
      endpointAddress: "otel-collector:4317"
      isSecure: false
      protocol: grpc
  metric:
    enabled: true
    rules: []
  httpPipeline:
    handlers:
      - name: oauth2
        type: middleware.http.oauth2
  api:
    allowed:
      - name: invoke
        version: v1
        protocol: http
  accessControl:
    defaultAction: deny
    trustDomain: "cluster.local"
    policies:
      - appId: order-service
        defaultAction: allow
        namespace: production
        operations:
          - name: /orders/**
            httpVerb: [POST, GET]
            action: allow
  features:
    - name: SchedulerReminders
      enabled: true             # Use Scheduler for actor reminders (v1.15+)
```
