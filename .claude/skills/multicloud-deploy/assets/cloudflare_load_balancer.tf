# Cloudflare Global Load Balancer — Production Template
# Provides: anycast routing, health checks, geo-steering, WAF, DDoS protection

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

variable "cloudflare_api_token"  { sensitive = true }
variable "cloudflare_account_id" {}
variable "cloudflare_zone_id"    {}
variable "domain"                { default = "example.com" }
variable "subdomain"             { default = "api" }

# Cloud origins — replace with real ALB/NEG/Front Door endpoints
variable "aws_origin_address"    { default = "prod-alb.us-east-1.elb.amazonaws.com" }
variable "gcp_origin_address"    { default = "34.102.x.x" }    # GCP GLB Anycast IP
variable "azure_origin_address"  { default = "prod.azurefd.net" }

# ─── Health Monitors ─────────────────────────────────────────────────────────
resource "cloudflare_load_balancer_monitor" "https_health" {
  account_id     = var.cloudflare_account_id
  type           = "https"
  description    = "HTTPS health check for all cloud origins"
  path           = "/healthz"
  expected_codes = "200"
  method         = "GET"
  interval       = 30       # check every 30s
  timeout        = 5
  retries        = 2
  consecutive_up   = 2      # mark healthy after 2 consecutive successes
  consecutive_down = 2      # mark unhealthy after 2 consecutive failures
  follow_redirects = false
  allow_insecure   = false

  header {
    header = "Host"
    values = ["${var.subdomain}.${var.domain}"]
  }
  header {
    header = "X-Health-Check"
    values = ["cloudflare"]
  }
}

# ─── Origin Pools ─────────────────────────────────────────────────────────────

# AWS Pool (primary — highest weight)
resource "cloudflare_load_balancer_pool" "aws" {
  account_id         = var.cloudflare_account_id
  name               = "aws-us-east-1"
  description        = "AWS EKS production cluster — primary"
  minimum_origins    = 1
  enabled            = true
  notification_email = "ops@${var.domain}"
  monitor            = cloudflare_load_balancer_monitor.https_health.id

  origins {
    name    = "aws-alb-us-east-1"
    address = var.aws_origin_address
    enabled = true
    weight  = 1.0
    header {
      header = "Host"
      values = [var.aws_origin_address]
    }
  }

  load_shedding {
    default_percent = 0
    default_policy  = "random"
    session_percent = 0
    session_policy  = "hash"
  }

  origin_steering {
    policy = "random"
  }
}

# GCP Pool
resource "cloudflare_load_balancer_pool" "gcp" {
  account_id         = var.cloudflare_account_id
  name               = "gcp-us-central1"
  description        = "GCP GKE production cluster — secondary"
  minimum_origins    = 1
  enabled            = true
  notification_email = "ops@${var.domain}"
  monitor            = cloudflare_load_balancer_monitor.https_health.id

  origins {
    name    = "gcp-glb-us-central1"
    address = var.gcp_origin_address
    enabled = true
    weight  = 1.0
  }

  origin_steering {
    policy = "random"
  }
}

# Azure Pool
resource "cloudflare_load_balancer_pool" "azure" {
  account_id         = var.cloudflare_account_id
  name               = "azure-eastus"
  description        = "Azure AKS production cluster — tertiary"
  minimum_origins    = 1
  enabled            = true
  notification_email = "ops@${var.domain}"
  monitor            = cloudflare_load_balancer_monitor.https_health.id

  origins {
    name    = "azure-frontdoor-eastus"
    address = var.azure_origin_address
    enabled = true
    weight  = 1.0
  }

  origin_steering {
    policy = "random"
  }
}

# ─── Global Load Balancer ─────────────────────────────────────────────────────
resource "cloudflare_load_balancer" "api" {
  zone_id          = var.cloudflare_zone_id
  name             = "${var.subdomain}.${var.domain}"
  description      = "Multi-cloud API load balancer — Tier 2 active-active"
  proxied          = true          # traffic flows through Cloudflare (enables WAF, DDoS)
  ttl              = 1             # Cloudflare proxy ignores TTL; set to 1 for proxied
  steering_policy  = "geo"         # geo-based routing

  # Default pool order (failover chain if no geo rule matches)
  default_pool_ids = [
    cloudflare_load_balancer_pool.aws.id,    # primary
    cloudflare_load_balancer_pool.gcp.id,    # first failover
    cloudflare_load_balancer_pool.azure.id,  # second failover
  ]
  fallback_pool_id = cloudflare_load_balancer_pool.gcp.id

  # Session affinity — stick clients to same cloud for 30 min
  session_affinity          = "cookie"
  session_affinity_ttl      = 1800    # 30 minutes
  session_affinity_attributes {
    samesite     = "Strict"
    secure       = "Always"
    drain_duration = 300
    headers      = []
    require_zero_downtime_failover = false
  }

  # ── Geo Routing Rules ────────────────────────────────────────────────────
  # Route US/CA/MX → AWS (lowest latency)
  rules {
    name      = "us-traffic-to-aws"
    condition = "ip.geoip.continent eq \"NA\""
    overrides {
      default_pool_ids = [
        cloudflare_load_balancer_pool.aws.id,
        cloudflare_load_balancer_pool.gcp.id,
        cloudflare_load_balancer_pool.azure.id,
      ]
      steering_policy = "geo"
    }
  }

  # Route EU → GCP (or Azure, depending on latency)
  rules {
    name      = "eu-traffic-to-gcp"
    condition = "ip.geoip.continent eq \"EU\""
    overrides {
      default_pool_ids = [
        cloudflare_load_balancer_pool.gcp.id,
        cloudflare_load_balancer_pool.azure.id,
        cloudflare_load_balancer_pool.aws.id,
      ]
      steering_policy = "geo"
    }
  }

  # Route APAC → GCP (us-central1 is still closer than AWS us-east-1 for most APAC)
  rules {
    name      = "apac-traffic-to-gcp"
    condition = "ip.geoip.continent eq \"AS\" or ip.geoip.continent eq \"OC\""
    overrides {
      default_pool_ids = [
        cloudflare_load_balancer_pool.gcp.id,
        cloudflare_load_balancer_pool.aws.id,
        cloudflare_load_balancer_pool.azure.id,
      ]
      steering_policy = "geo"
    }
  }

  # Canary: route X-Canary header to canary pool (when canary is configured)
  rules {
    name      = "canary-header-routing"
    condition = "http.request.headers[\"x-canary\"][0] == \"true\""
    overrides {
      # When canary is active, this rule overrides to canary pool
      # Uncomment and set canary pool when needed:
      # default_pool_ids = [cloudflare_load_balancer_pool.canary.id]
      steering_policy = "off"    # no steering, use first pool only
    }
    disabled = true    # enable when canary is live
  }
}

# ─── WAF (Cloudflare Managed Rules) ──────────────────────────────────────────
resource "cloudflare_ruleset" "waf" {
  zone_id     = var.cloudflare_zone_id
  name        = "prod-waf"
  description = "Production WAF ruleset"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  # Cloudflare Managed Ruleset
  rules {
    action      = "execute"
    description = "Cloudflare Managed Rules"
    expression  = "true"
    enabled     = true
    action_parameters {
      id      = "efb7b8c949ac4650a09736fc376e9aee"
      version = "latest"
      overrides {
        action  = "log"      # change to "block" for enforcement after tuning
        enabled = true
        sensitivity_level = "default"
      }
    }
  }

  # OWASP Core Rule Set
  rules {
    action      = "execute"
    description = "OWASP Core Rule Set"
    expression  = "true"
    enabled     = true
    action_parameters {
      id      = "4814384a9e5d4991b9815dcfc25d2f1f"
      version = "latest"
    }
  }
}

# ─── Rate Limiting ───────────────────────────────────────────────────────────
resource "cloudflare_ruleset" "rate_limit" {
  zone_id     = var.cloudflare_zone_id
  name        = "api-rate-limits"
  description = "Rate limiting for API endpoints"
  kind        = "zone"
  phase       = "http_ratelimit"

  rules {
    action      = "block"
    description = "Block > 1000 req/min per IP to /api/*"
    expression  = "http.request.uri.path matches \"/api/.*\""
    enabled     = true
    ratelimit {
      characteristics       = ["ip.src"]
      period                = 60       # 1 minute window
      requests_per_period   = 1000
      mitigation_timeout    = 600      # block for 10 minutes after threshold
      counting_expression   = ""
    }
  }

  rules {
    action      = "block"
    description = "Block > 5 auth failures per IP per minute"
    expression  = "http.request.uri.path eq \"/api/v1/auth/login\""
    enabled     = true
    ratelimit {
      characteristics     = ["ip.src"]
      period              = 60
      requests_per_period = 5
      mitigation_timeout  = 3600    # 1-hour block for brute force
    }
  }
}

# ─── DNS Record ──────────────────────────────────────────────────────────────
resource "cloudflare_record" "api" {
  zone_id = var.cloudflare_zone_id
  name    = var.subdomain
  type    = "CNAME"
  value   = cloudflare_load_balancer.api.name
  proxied = true
  ttl     = 1    # TTL is ignored for proxied records
}

# ─── Outputs ──────────────────────────────────────────────────────────────────
output "load_balancer_hostname" { value = cloudflare_load_balancer.api.name }
output "api_endpoint"           { value = "https://${var.subdomain}.${var.domain}" }
output "aws_pool_id"            { value = cloudflare_load_balancer_pool.aws.id }
output "gcp_pool_id"            { value = cloudflare_load_balancer_pool.gcp.id }
output "azure_pool_id"          { value = cloudflare_load_balancer_pool.azure.id }
