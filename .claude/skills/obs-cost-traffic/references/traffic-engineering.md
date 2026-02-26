# Traffic Engineering
## Load Balancers, Service Mesh, Global Traffic Management, Resilience Patterns

---

## Load Balancing Algorithms

| Algorithm | Best For | Description |
|-----------|----------|-------------|
| Round Robin | Stateless, uniform services | Distributes requests sequentially |
| Weighted Round Robin | Mixed server capacity | More requests to higher-weight backends |
| Least Connections | Long-lived connections | Routes to backend with fewest active connections |
| Least Response Time | API gateways | Routes to fastest-responding backend |
| IP Hash | Session affinity required | Same client always hits same backend |
| Random | Simple, stateless | Randomly picks healthy backend |
| EWMA | Production (Netflix Ribbon) | Exponentially weighted moving avg of latency |

---

## NGINX — Production Configuration

```nginx
# /etc/nginx/nginx.conf — Production L7 Load Balancer

worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 65535;
    use epoll;
    multi_accept on;
}

http {
    # Connection optimization
    keepalive_timeout 65;
    keepalive_requests 1000;
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;

    # Logging
    log_format json_combined escape=json
        '{"timestamp":"$time_iso8601",'
        '"remote_addr":"$remote_addr",'
        '"method":"$request_method",'
        '"uri":"$request_uri",'
        '"status":$status,'
        '"body_bytes_sent":$body_bytes_sent,'
        '"request_time":$request_time,'
        '"upstream_addr":"$upstream_addr",'
        '"upstream_response_time":"$upstream_response_time",'
        '"trace_id":"$http_x_trace_id"}';

    access_log /var/log/nginx/access.log json_combined;

    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=per_ip:10m rate=100r/m;
    limit_req_zone $http_x_api_key zone=per_token:10m rate=1000r/m;
    limit_conn_zone $binary_remote_addr zone=conn_per_ip:10m;

    # Upstream — order service cluster
    upstream order_service {
        least_conn;
        keepalive 32;

        server order-svc-1:8080 weight=5 max_fails=3 fail_timeout=30s;
        server order-svc-2:8080 weight=5 max_fails=3 fail_timeout=30s;
        server order-svc-3:8080 weight=3 max_fails=3 fail_timeout=30s;

        # Health check (nginx plus only; use passive for OSS)
    }

    server {
        listen 443 ssl http2;
        server_name api.example.com;

        ssl_certificate /etc/ssl/certs/api.crt;
        ssl_certificate_key /etc/ssl/private/api.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';

        # Security headers
        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";

        location /api/ {
            limit_req zone=per_ip burst=20 nodelay;
            limit_conn conn_per_ip 20;

            proxy_pass http://order_service;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Trace-Id $request_id;

            # Timeouts
            proxy_connect_timeout 5s;
            proxy_send_timeout 30s;
            proxy_read_timeout 30s;

            # Health check
            proxy_next_upstream error timeout http_500 http_502 http_503;
            proxy_next_upstream_tries 2;
        }

        location /health {
            access_log off;
            return 200 '{"status":"ok"}';
            add_header Content-Type application/json;
        }

        location /metrics {
            stub_status;
            allow 10.0.0.0/8;
            deny all;
        }
    }

    # HTTP → HTTPS redirect
    server {
        listen 80;
        return 301 https://$host$request_uri;
    }
}
```

---

## HAProxy — High-Performance L4/L7

```haproxy
# /etc/haproxy/haproxy.cfg

global
    maxconn 100000
    log /dev/log local0
    log /dev/log local1 notice
    stats socket /run/haproxy/admin.sock mode 660 level admin
    tune.ssl.default-dh-param 2048
    ssl-default-bind-ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256
    ssl-default-bind-options ssl-min-ver TLSv1.2 no-tls-tickets

defaults
    log global
    mode http
    option httplog
    option dontlognull
    option http-server-close
    option forwardfor
    option redispatch
    timeout connect 5s
    timeout client 30s
    timeout server 30s
    maxconn 50000

# Stats dashboard
frontend stats
    bind *:8404
    mode http
    stats enable
    stats uri /stats
    stats refresh 10s
    stats admin if LOCALHOST

# HTTPS frontend
frontend https_frontend
    bind *:443 ssl crt /etc/haproxy/certs/
    mode http
    option http-server-close
    http-request set-header X-Forwarded-Proto https
    http-request set-header X-Request-ID %[uuid]

    # Rate limiting (by source IP)
    stick-table type ip size 100k expire 30s store http_req_rate(10s)
    http-request track-sc0 src
    http-request deny deny_status 429 if { sc_http_req_rate(0) gt 100 }

    # Routing ACLs
    acl is_api path_beg /api/
    acl is_ws hdr(Upgrade) -i WebSocket

    use_backend order_backend if is_api { path_beg /api/orders }
    use_backend ws_backend if is_ws
    default_backend api_gateway_backend

# Backend — order service
backend order_backend
    mode http
    balance leastconn
    option httpchk GET /health
    http-check expect status 200

    server order1 10.0.1.10:8080 check weight 10 inter 5s rise 2 fall 3
    server order2 10.0.1.11:8080 check weight 10 inter 5s rise 2 fall 3
    server order3 10.0.1.12:8080 check weight 5  inter 5s rise 2 fall 3

    # Retries
    retries 2
    option redispatch

    # Circuit breaker — mark server down after 3 consecutive failures
    default-server inter 5s fastinter 1s downinter 30s rise 2 fall 3 maxconn 1000
```

---

## Traefik — Cloud-Native Reverse Proxy

```yaml
# traefik.yaml (static config)
api:
  dashboard: true
  insecure: false

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entrypoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"

certificatesResolvers:
  letsencrypt:
    acme:
      tlsChallenge: {}
      email: ops@example.com
      storage: /letsencrypt/acme.json

providers:
  docker:
    exposedByDefault: false
    watch: true
  file:
    directory: /etc/traefik/dynamic
    watch: true

metrics:
  prometheus:
    addEntryPointsLabels: true
    addServicesLabels: true
    buckets:
      - 0.1
      - 0.3
      - 1.2
      - 5.0

tracing:
  otlp:
    grpc:
      endpoint: otel-collector:4317
      insecure: true
```

```yaml
# dynamic/middlewares.yaml
http:
  middlewares:
    rate-limit:
      rateLimit:
        average: 100
        burst: 50
        period: 1s

    circuit-breaker:
      circuitBreaker:
        expression: "NetworkErrorRatio() > 0.30 || ResponseCodeRatio(500, 600, 0, 600) > 0.25"
        checkPeriod: 10s
        fallbackDuration: 10s
        recoverDuration: 10s

    retry:
      retry:
        attempts: 3
        initialInterval: 100ms

    auth-forward:
      forwardAuth:
        address: http://auth-service:8080/validate
        authResponseHeaders:
          - X-User-ID
          - X-Tenant-ID

  routers:
    order-api:
      rule: "Host(`api.example.com`) && PathPrefix(`/api/orders`)"
      entryPoints: [websecure]
      service: order-service
      middlewares:
        - rate-limit
        - circuit-breaker
        - retry
      tls:
        certResolver: letsencrypt

  services:
    order-service:
      loadBalancer:
        healthCheck:
          path: /health
          interval: 10s
          timeout: 3s
        servers:
          - url: "http://order-svc-1:8080"
          - url: "http://order-svc-2:8080"
          - url: "http://order-svc-3:8080"
        sticky:
          cookie:
            name: lb_session
            secure: true
            httpOnly: true
```

---

## Istio Service Mesh (Kubernetes)

```yaml
# VirtualService — traffic routing + canary
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: order-service
spec:
  hosts:
    - order-service
  http:
    # Canary: 10% to new version
    - match:
        - headers:
            x-canary:
              exact: "true"
      route:
        - destination:
            host: order-service
            subset: v2
    - route:
        - destination:
            host: order-service
            subset: v1
          weight: 90
        - destination:
            host: order-service
            subset: v2
          weight: 10
      timeout: 10s
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: "gateway-error,connect-failure,retriable-4xx"
---
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: order-service
spec:
  host: order-service
  trafficPolicy:
    connectionPool:
      http:
        h2UpgradePolicy: UPGRADE
        http1MaxPendingRequests: 100
        http2MaxRequests: 1000
    outlierDetection:
      # Circuit breaker
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
  subsets:
    - name: v1
      labels:
        version: v1
    - name: v2
      labels:
        version: v2
```

---

## Cloud Load Balancers

### AWS ALB (Application Load Balancer)
```yaml
# Terraform resource (reference)
resource "aws_lb" "main" {
  name               = "prod-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = true
  drop_invalid_header_fields = true

  access_logs {
    bucket  = aws_s3_bucket.alb_logs.id
    enabled = true
  }
}

# Listener with WAF
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
```

**ALB Routing rules** (path/header/weight-based):
- Use **ALB weighted target groups** for blue/green and canary (no Istio needed)
- **AWS Global Accelerator** for cross-region failover with static anycast IPs
- **AWS WAF v2** with managed rule groups (OWASP Core, Bot Control)

### GCP Cloud Load Balancing
- **Global external HTTP(S)**: Multi-region, Anycast, Cloud CDN integration
- **Regional internal**: For internal microservice traffic (replaces Istio for simple cases)
- **Traffic Director**: Managed service mesh control plane
- URL map for path-based routing + weighted backends for canary

### Azure Application Gateway + Front Door
```
Azure Front Door (Global) → Application Gateway (Regional WAF + L7) → AKS / App Service
```
- Front Door: Global load balancing, CDN, DDoS protection, URL-based routing
- Application Gateway: WAF v2 with OWASP 3.2 rules, SSL termination, cookie affinity

---

## Global Traffic Management

### Cloudflare Load Balancing
```yaml
# Cloudflare Load Balancer (via API / Terraform)
resource "cloudflare_load_balancer" "main" {
  zone_id          = var.zone_id
  name             = "api.example.com"
  fallback_pool_id = cloudflare_load_balancer_pool.fallback.id
  default_pool_ids = [cloudflare_load_balancer_pool.primary.id]
  session_affinity = "cookie"

  rules {
    name      = "us-traffic"
    condition = "ip.src.country == \"US\""
    fixed_response {
      status_code = 200
    }
    overrides {
      session_affinity = "none"
      default_pools    = [cloudflare_load_balancer_pool.us.id]
    }
  }
}

resource "cloudflare_load_balancer_pool" "primary" {
  account_id         = var.account_id
  name               = "primary-pool"
  minimum_origins    = 1

  origins {
    name    = "us-east"
    address = "api-us.example.com"
    weight  = 0.5
  }
  origins {
    name    = "eu-west"
    address = "api-eu.example.com"
    weight  = 0.5
  }

  monitor = cloudflare_load_balancer_monitor.http.id

  load_shedding {
    default_policy    = "random"
    default_percent   = 0
    session_policy    = "hash"
    session_percent   = 0
  }
}
```

---

## Resilience Patterns

### Circuit Breaker States
```
CLOSED → (failure threshold exceeded) → OPEN → (timeout) → HALF-OPEN → (success) → CLOSED
                                                                        ↓ (failure)
                                                                       OPEN
```

### Retry with Exponential Backoff
```python
import asyncio
import random

async def call_with_retry(func, max_retries=3, base_delay=0.1):
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except (TimeoutError, ConnectionError) as e:
            if attempt == max_retries:
                raise
            # Exponential backoff with jitter
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
            await asyncio.sleep(delay)
```

### Health Check Endpoint Pattern
```python
# FastAPI health endpoint
@app.get("/health")
async def liveness():
    return {"status": "ok"}

@app.get("/ready")
async def readiness():
    checks = {}
    # Check DB connection
    try:
        await db.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Check downstream dependencies
    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
        status_code=200 if all_ok else 503
    )
```
