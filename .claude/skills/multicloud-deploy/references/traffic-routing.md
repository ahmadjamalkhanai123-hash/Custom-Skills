# Global Traffic Routing Reference

## Cloudflare (Recommended for Global LB)

Cloudflare sits in front of all cloud origins, providing:
- Global anycast (300+ PoPs) — routes users to nearest healthy origin
- DDoS protection (unlimited, always-on)
- WAF with managed rulesets
- Load Balancing with health checks + geo-steering

### Load Balancer Configuration

```
Cloudflare DNS (api.example.com)
       │
  Load Balancer (active-active)
       │
  ┌────┴────┐
Origin Pool A      Origin Pool B
(AWS EKS ALB)     (GCP GKE NEG)
  10.0.0.1         172.16.0.1
  (weight: 50)     (weight: 50)
```

### Terraform Configuration
```hcl
resource "cloudflare_load_balancer" "api" {
  zone_id          = var.cloudflare_zone_id
  name             = "api.example.com"
  fallback_pool_id = cloudflare_load_balancer_pool.azure.id
  default_pool_ids = [
    cloudflare_load_balancer_pool.aws.id,
    cloudflare_load_balancer_pool.gcp.id,
  ]
  description      = "Multi-cloud API load balancer"
  proxied          = true
  steering_policy  = "geo"

  rules {
    name      = "us-traffic-to-aws"
    condition = "http.request.headers[\"cf-ipcountry\"][0] in {\"US\" \"CA\"}"
    overrides {
      default_pool_ids = [cloudflare_load_balancer_pool.aws.id]
    }
  }

  rules {
    name      = "eu-traffic-to-gcp"
    condition = "http.request.headers[\"cf-ipcountry\"][0] in {\"DE\" \"FR\" \"GB\" \"NL\"}"
    overrides {
      default_pool_ids = [cloudflare_load_balancer_pool.gcp.id]
    }
  }
}

resource "cloudflare_load_balancer_pool" "aws" {
  account_id         = var.cloudflare_account_id
  name               = "aws-us-east-1"
  minimum_origins    = 1
  notification_email = "ops@example.com"

  origins {
    name    = "aws-alb-us-east-1"
    address = "alb-prod.us-east-1.elb.amazonaws.com"
    enabled = true
    weight  = 1.0
  }

  health_check {
    enabled            = true
    interval           = 30
    path               = "/healthz"
    expected_codes     = "200"
    type               = "https"
    timeout            = 5
    retries            = 3
    consecutive_up     = 2
    consecutive_down   = 2
  }
}
```

### Argo Smart Routing (Enterprise)
Routes traffic on Cloudflare's backbone instead of public internet:
- Typically 30% faster inter-cloud latency
- Enable: `argo` block in zone settings

---

## AWS Global Accelerator

Use when Cloudflare is not available or for UDP/TCP (non-HTTP) acceleration.

### How It Works
- Provides 2 static Anycast IP addresses (globally routable)
- Routes traffic on AWS's backbone to the nearest AWS PoP
- Configurable traffic dials per endpoint group

```hcl
resource "aws_globalaccelerator_accelerator" "main" {
  name            = "prod-accelerator"
  ip_address_type = "IPV4"
  enabled         = true

  attributes {
    flow_logs_enabled   = true
    flow_logs_s3_bucket = aws_s3_bucket.ga_logs.bucket
    flow_logs_s3_prefix = "ga-logs/"
  }
}

resource "aws_globalaccelerator_listener" "https" {
  accelerator_arn = aws_globalaccelerator_accelerator.main.id
  protocol        = "TCP"
  port_range {
    from_port = 443
    to_port   = 443
  }
}

resource "aws_globalaccelerator_endpoint_group" "aws_primary" {
  listener_arn                  = aws_globalaccelerator_listener.https.id
  endpoint_group_region         = "us-east-1"
  traffic_dial_percentage       = 80
  health_check_path             = "/healthz"
  health_check_protocol         = "HTTPS"
  health_check_interval_seconds = 10
  threshold_count               = 3

  endpoint_configuration {
    endpoint_id                    = aws_lb.prod.arn
    weight                         = 128
    client_ip_preservation_enabled = true
  }
}

resource "aws_globalaccelerator_endpoint_group" "gcp_secondary" {
  listener_arn            = aws_globalaccelerator_listener.https.id
  endpoint_group_region   = "us-east-1"  # dummy region for non-AWS endpoints
  traffic_dial_percentage = 20

  endpoint_configuration {
    endpoint_id = "IP:35.192.x.x"  # GCP LB IP
    weight      = 128
  }
}
```

---

## GCP Premium Tier + Cloud Load Balancing

### Global HTTP(S) Load Balancer
Single global Anycast IP across 80+ PoPs. Always use Premium Tier for global LB.

```hcl
# Backend service pointing to GKE NEGs
resource "google_compute_backend_service" "api" {
  name                  = "api-backend"
  protocol              = "HTTPS"
  port_name             = "https"
  timeout_sec           = 30
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group           = google_compute_network_endpoint_group.gke.id
    balancing_mode  = "RATE"
    max_rate_per_endpoint = 100
  }

  health_checks = [google_compute_health_check.api.id]

  security_policy = google_compute_security_policy.cloud_armor.id

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}
```

---

## Azure Front Door (Premium)

```hcl
resource "azurerm_cdn_frontdoor_profile" "main" {
  name                = "prod-frontdoor"
  resource_group_name = var.rg
  sku_name            = "Premium_AzureFrontDoor"
}

resource "azurerm_cdn_frontdoor_origin_group" "api" {
  name                     = "api-origin-group"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id

  load_balancing {
    sample_size                 = 4
    successful_samples_required = 3
  }

  health_probe {
    interval_in_seconds = 30
    path                = "/healthz"
    protocol            = "Https"
    request_type        = "HEAD"
  }
}
```

---

## DNS Failover Patterns

### Sub-30s Failover (Required for Class A RTO)

```
Active Health Check interval: 10s
Consecutive failures to mark down: 2  → marks down in 20s
DNS TTL: 30s maximum
Total failover window: 20s (detect) + 30s (DNS propagation) = ~50s
```

For sub-30s total: use Anycast (Cloudflare/Global Accelerator) which bypasses DNS propagation.

### Route 53 Health Check + Failover

```hcl
resource "aws_route53_health_check" "primary" {
  fqdn              = "api-aws.example.com"
  port              = 443
  type              = "HTTPS"
  resource_path     = "/healthz"
  failure_threshold = "2"
  request_interval  = "10"
}

resource "aws_route53_record" "api_primary" {
  zone_id         = aws_route53_zone.main.zone_id
  name            = "api.example.com"
  type            = "A"
  set_identifier  = "primary"
  health_check_id = aws_route53_health_check.primary.id
  failover_routing_policy { type = "PRIMARY" }
  alias {
    name                   = aws_lb.primary.dns_name
    zone_id                = aws_lb.primary.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "api_secondary" {
  zone_id        = aws_route53_zone.main.zone_id
  name           = "api.example.com"
  type           = "A"
  set_identifier = "secondary"
  failover_routing_policy { type = "SECONDARY" }
  alias {
    name                   = aws_lb.secondary.dns_name
    zone_id                = aws_lb.secondary.zone_id
    evaluate_target_health = true
  }
}
```

---

## Active-Active vs Active-Passive Decision Matrix

| Factor | Active-Active | Active-Passive |
|--------|--------------|----------------|
| RTO Target | < 30s | 1–60 min |
| Cost | 2–3x higher | ~1.2x (standby costs) |
| Complexity | High | Medium |
| Data consistency | Requires multi-master DB | Simpler (single-master) |
| Traffic distribution | Load-balanced globally | All to primary |
| Best for | Global users, Tier A RTO | Regional apps, Tier B/C RTO |

### Active-Active Requirements
1. Stateless services OR globally-consistent data store (CockroachDB, Spanner)
2. Global LB with health checks (Cloudflare or Global Accelerator)
3. Service mesh mTLS across clusters
4. Same container image deployed to all clusters (via GitOps)
5. Chaos test: verify no data loss on simultaneous zone failures

### Active-Passive Checklist
1. Health check triggers automatic failover (no manual intervention)
2. DR cluster is warm (pods running, 0 replicas scaled to 1 in <60s)
3. Data replication lag monitored and alerted (target < 5min RPO)
4. DNS TTL set to ≤60s before planned failover test
5. Failover tested monthly (not just in theory)

---

## Traffic Shifting for Deployments

### Canary Across Clouds (Argo Rollouts + Karmada)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: checkout-api
spec:
  replicas: 10
  strategy:
    canary:
      steps:
        - setWeight: 5    # 5% to canary
        - pause: {duration: 5m}
        - setWeight: 20
        - pause: {duration: 10m}
        - setWeight: 50
        - pause: {duration: 10m}
        - setWeight: 100
      trafficRouting:
        istio:
          virtualService:
            name: checkout-api-vs
          destinationRule:
            name: checkout-api-dr
            stableSubsetName: stable
            canarySubsetName: canary
  analysis:
    successfulRunHistoryLimit: 3
    unsuccessfulRunHistoryLimit: 3
```

### Blue-Green Across Clouds

1. Deploy "green" to all clusters via Karmada (inactive)
2. Shift 10% traffic via Cloudflare LB traffic dial
3. Validate metrics (error rate, latency, saturation)
4. Shift to 100% green
5. Keep blue for 24h as fallback, then decommission
