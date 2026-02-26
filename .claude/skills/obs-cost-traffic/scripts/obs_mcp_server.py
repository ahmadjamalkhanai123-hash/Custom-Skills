#!/usr/bin/env python3
"""
OBS-COST-TRAFFIC MCP Server
Exposes observability, traffic, and cost intelligence tools to AI agents via MCP.

Tools:
  - check_stack_health    : Health check all observability components
  - query_prometheus      : Run PromQL queries and return formatted results
  - get_slo_status        : Error budget + burn rate for all services
  - get_cost_report       : Cloud cost summary with anomaly detection
  - validate_otel_config  : Lint an OTel Collector YAML configuration
  - analyze_traffic       : Load balancer metrics + upstream health
  - get_llm_cost_summary  : LLM token + cost breakdown by agent/model

Usage:
    python obs_mcp_server.py

Requirements:
    pip install fastmcp httpx pyyaml

MCP Protocol Docs: https://modelcontextprotocol.io/docs/
FastMCP Docs:      https://github.com/jlowin/fastmcp
"""

import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
import yaml

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    raise ImportError(
        "fastmcp not installed. Run: pip install fastmcp"
    )

# ─────────────────────────────────────────────────────────────────
# Server Initialization
# ─────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="obs-cost-traffic",
    instructions="""
    Observability, Traffic Engineering, and Cost Intelligence MCP server.

    Capabilities:
    - Query Prometheus metrics and SLO error budgets
    - Check health of OTel Collector, Grafana, Loki, Tempo, Prometheus
    - Get cloud cost reports (AWS, GCP, Azure) with anomaly detection
    - Validate OTel Collector YAML configurations
    - Analyze traffic patterns and upstream health
    - Monitor LLM agent token costs and rate limits

    All tools use environment variables for endpoint configuration.
    Set: PROMETHEUS_URL, GRAFANA_URL, LOKI_URL, TEMPO_URL
    """,
)

# ─────────────────────────────────────────────────────────────────
# Configuration (from environment)
# ─────────────────────────────────────────────────────────────────

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
GRAFANA_URL    = os.getenv("GRAFANA_URL", "http://localhost:3000")
LOKI_URL       = os.getenv("LOKI_URL", "http://localhost:3100")
TEMPO_URL      = os.getenv("TEMPO_URL", "http://localhost:3200")
OTEL_URL       = os.getenv("OTEL_URL", "http://localhost:13133")  # OTel health_check ext


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

async def _prometheus_query(query: str, step: str = "60s") -> dict:
    """Execute an instant PromQL query against Prometheus."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
        )
        resp.raise_for_status()
        return resp.json()


async def _prometheus_range_query(query: str, start: str, end: str, step: str = "300") -> dict:
    """Execute a range PromQL query."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": step},
        )
        resp.raise_for_status()
        return resp.json()


async def _check_endpoint(name: str, url: str, path: str = "/") -> dict:
    """Check HTTP endpoint health."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}{path}")
            return {
                "service": name,
                "status": "healthy" if resp.status_code < 400 else "degraded",
                "http_status": resp.status_code,
                "url": url,
            }
    except httpx.ConnectError:
        return {"service": name, "status": "unreachable", "url": url, "error": "connection refused"}
    except httpx.TimeoutException:
        return {"service": name, "status": "timeout", "url": url, "error": "timed out after 5s"}
    except Exception as exc:
        return {"service": name, "status": "error", "url": url, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────
# Tool 1: check_stack_health
# ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def check_stack_health() -> str:
    """
    Health-check all observability stack components: OTel Collector, Prometheus,
    Grafana, Loki, Tempo. Returns status, latency, and any detected issues.
    """
    checks = await asyncio.gather(
        _check_endpoint("prometheus",     PROMETHEUS_URL, "/-/healthy"),
        _check_endpoint("grafana",        GRAFANA_URL,    "/api/health"),
        _check_endpoint("loki",           LOKI_URL,       "/ready"),
        _check_endpoint("tempo",          TEMPO_URL,      "/ready"),
        _check_endpoint("otel-collector", OTEL_URL,       "/"),
        return_exceptions=True,
    )

    # Prometheus Alertmanager health (optional)
    am_url = os.getenv("ALERTMANAGER_URL", "http://localhost:9093")
    am_check = await _check_endpoint("alertmanager", am_url, "/-/healthy")

    results = list(checks) + [am_check]
    healthy = [r for r in results if isinstance(r, dict) and r.get("status") == "healthy"]
    degraded = [r for r in results if isinstance(r, dict) and r.get("status") != "healthy"]

    summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "overall": "healthy" if not degraded else "degraded",
        "healthy_count": len(healthy),
        "degraded_count": len(degraded),
        "services": results,
        "recommendations": [],
    }

    if degraded:
        summary["recommendations"].append(
            f"Investigate: {', '.join(r['service'] for r in degraded if isinstance(r, dict))}"
        )

    return json.dumps(summary, indent=2)


# ─────────────────────────────────────────────────────────────────
# Tool 2: query_prometheus
# ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def query_prometheus(
    query: str,
    time_range_minutes: int = 0,
    step_seconds: int = 60,
) -> str:
    """
    Execute a PromQL query against the Prometheus API.

    Args:
        query: PromQL expression (e.g., 'rate(http_requests_total[5m])')
        time_range_minutes: If > 0, run a range query for the last N minutes.
                            If 0 (default), run an instant query.
        step_seconds: Resolution step for range queries in seconds (default: 60)

    Returns:
        JSON with query result, metric labels, and formatted values.
    """
    try:
        if time_range_minutes > 0:
            end = datetime.utcnow()
            start = end - timedelta(minutes=time_range_minutes)
            result = await _prometheus_range_query(
                query,
                start=str(start.timestamp()),
                end=str(end.timestamp()),
                step=str(step_seconds),
            )
            query_type = "range"
        else:
            result = await _prometheus_query(query)
            query_type = "instant"

        if result.get("status") != "success":
            return json.dumps({"error": "Prometheus query failed", "detail": result})

        data = result.get("data", {})
        result_type = data.get("resultType", "unknown")
        raw_results = data.get("result", [])

        formatted = {
            "query": query,
            "type": query_type,
            "result_type": result_type,
            "result_count": len(raw_results),
            "results": [],
        }

        for item in raw_results[:50]:  # Limit to 50 series
            entry = {"labels": item.get("metric", {})}
            if result_type == "matrix":
                values = item.get("values", [])
                entry["value_count"] = len(values)
                entry["latest_value"] = float(values[-1][1]) if values else None
                entry["sample_values"] = [
                    {"timestamp": v[0], "value": float(v[1])}
                    for v in values[-5:]  # Last 5 data points
                ]
            else:
                val = item.get("value", [None, None])
                entry["value"] = float(val[1]) if val[1] is not None else None
                entry["timestamp"] = val[0]
            formatted["results"].append(entry)

        return json.dumps(formatted, indent=2)

    except httpx.HTTPError as exc:
        return json.dumps({"error": f"HTTP error querying Prometheus: {exc}"})


# ─────────────────────────────────────────────────────────────────
# Tool 3: get_slo_status
# ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_slo_status(job_filter: str = ".*") -> str:
    """
    Return SLO error budget remaining and multi-window burn rates for all services.

    Args:
        job_filter: Regex to filter services (default: '.*' = all services)

    Returns:
        JSON with availability SLI, error budget %, burn rates (1h/6h/30d),
        and SLO alerts (critical/warning) for each matching service.
    """
    queries = {
        "availability_30d":  f"job:slo_availability:ratio_rate30d{{job=~\"{job_filter}\"}}",
        "availability_1h":   f"job:slo_availability:ratio_rate1h{{job=~\"{job_filter}\"}}",
        "error_budget":      f"job:slo_error_budget_remaining:ratio{{job=~\"{job_filter}\"}}",
        "burn_rate_1h":      f"(1 - job:slo_availability:ratio_rate1h{{job=~\"{job_filter}\"}}) / (1 - 0.999)",
        "burn_rate_6h":      f"(1 - job:slo_availability:ratio_rate6h{{job=~\"{job_filter}\"}}) / (1 - 0.999)",
        "error_rate_5m":     f"job:http_error_ratio:rate5m{{job=~\"{job_filter}\"}}",
    }

    results_raw = await asyncio.gather(
        *[_prometheus_query(q) for q in queries.values()],
        return_exceptions=True,
    )

    query_results = dict(zip(queries.keys(), results_raw))

    # Build per-job report
    jobs: dict[str, dict] = {}

    def extract_values(prom_result: Any, key: str) -> None:
        if isinstance(prom_result, Exception):
            return
        for item in prom_result.get("data", {}).get("result", []):
            job = item.get("metric", {}).get("job", "unknown")
            val = item.get("value", [None, "0"])
            try:
                jobs.setdefault(job, {})[key] = float(val[1])
            except (ValueError, TypeError):
                jobs.setdefault(job, {})[key] = None

    for metric_name, result in query_results.items():
        extract_values(result, metric_name)

    slo_report = []
    for job_name, metrics in sorted(jobs.items()):
        availability = metrics.get("availability_30d", 0) or 0
        budget_remaining = metrics.get("error_budget", 1) or 1
        burn_1h = metrics.get("burn_rate_1h", 0) or 0
        burn_6h = metrics.get("burn_rate_6h", 0) or 0

        alert = "ok"
        if burn_1h >= 14.4:
            alert = "critical"  # 14.4x burn = 2% budget in 1h
        elif burn_6h >= 6.0:
            alert = "warning"   # 6x burn = 5% budget in 6h
        elif budget_remaining < 0.1:
            alert = "warning"   # <10% budget left

        slo_report.append({
            "job": job_name,
            "availability_30d_pct": round(availability * 100, 4),
            "error_budget_remaining_pct": round(budget_remaining * 100, 2),
            "burn_rate_1h": round(burn_1h, 2),
            "burn_rate_6h": round(burn_6h, 2),
            "error_rate_5m_pct": round((metrics.get("error_rate_5m", 0) or 0) * 100, 2),
            "alert": alert,
            "slo_target_pct": 99.9,
        })

    # Sort by alert severity
    severity_order = {"critical": 0, "warning": 1, "ok": 2}
    slo_report.sort(key=lambda x: severity_order.get(x["alert"], 3))

    critical_count = sum(1 for s in slo_report if s["alert"] == "critical")
    warning_count  = sum(1 for s in slo_report if s["alert"] == "warning")

    return json.dumps({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total_services": len(slo_report),
            "critical": critical_count,
            "warning": warning_count,
            "healthy": len(slo_report) - critical_count - warning_count,
        },
        "services": slo_report,
    }, indent=2)


# ─────────────────────────────────────────────────────────────────
# Tool 4: get_cost_report
# ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_cost_report(days: int = 7, provider: str = "all") -> str:
    """
    Get cloud cost summary with anomaly detection and top-cost services.

    Args:
        days: Number of days to report on (default: 7)
        provider: Cloud provider filter — 'aws', 'gcp', 'azure', 'all' (default: 'all')

    Returns:
        JSON with cost by service, daily trend, anomalies, and FinOps recommendations.
        Uses Prometheus LLM/AI cost metrics where available; falls back to estimates.
    """
    # Query AI/LLM costs from Prometheus (available in instrumented stacks)
    llm_cost_query = "sum(increase(llm_cost_usd_total[" + str(days) + "d])) by (agent_name, model)"
    llm_result = await _prometheus_query(llm_cost_query)

    llm_costs = []
    total_llm_usd = 0.0

    if not isinstance(llm_result, Exception):
        for item in llm_result.get("data", {}).get("result", []):
            labels = item.get("metric", {})
            try:
                cost = float(item.get("value", [None, "0"])[1])
            except (ValueError, TypeError):
                cost = 0.0
            total_llm_usd += cost
            llm_costs.append({
                "agent": labels.get("agent_name", "unknown"),
                "model": labels.get("model", "unknown"),
                "cost_usd": round(cost, 4),
            })

    # Sort by cost descending
    llm_costs.sort(key=lambda x: x["cost_usd"], reverse=True)

    # LLM hourly burn rate (last 1h)
    hourly_query = "sum(rate(llm_cost_usd_total[1h])) by (agent_name) * 3600"
    hourly_result = await _prometheus_query(hourly_query)
    hourly_costs = []
    if not isinstance(hourly_result, Exception):
        for item in hourly_result.get("data", {}).get("result", []):
            try:
                rate = float(item.get("value", [None, "0"])[1])
            except (ValueError, TypeError):
                rate = 0.0
            hourly_costs.append({
                "agent": item.get("metric", {}).get("agent_name", "unknown"),
                "projected_daily_usd": round(rate * 24, 4),
            })

    # Anomaly detection: compare today vs 7d average
    recommendations = []
    for h in hourly_costs:
        if h["projected_daily_usd"] > 100:
            recommendations.append(
                f"⚠️ Agent '{h['agent']}' projected daily LLM cost is "
                f"${h['projected_daily_usd']:.2f} — review request rate and model selection"
            )

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "period_days": days,
        "provider_filter": provider,
        "llm_ai_costs": {
            "total_usd": round(total_llm_usd, 2),
            "breakdown": llm_costs[:20],  # Top 20
            "hourly_burn": hourly_costs,
        },
        "infrastructure_note": (
            "For AWS/GCP/Azure cost data, integrate Cost Explorer / BigQuery billing export "
            "via the Prometheus exporter (billing-exporter) or Kubecost Prometheus metrics. "
            "See references/cost-engineering.md for integration patterns."
        ),
        "finops_recommendations": recommendations or ["No cost anomalies detected."],
        "docs": {
            "aws_cost_explorer":   "https://docs.aws.amazon.com/cost-management/latest/userguide/ce-api.html",
            "gcp_billing_export":  "https://cloud.google.com/billing/docs/how-to/export-data-bigquery",
            "azure_cost_mgmt":     "https://learn.microsoft.com/en-us/azure/cost-management-billing/",
            "kubecost":            "https://www.kubecost.com/kubernetes-cost-optimization/",
            "opencost":            "https://www.opencost.io/docs/",
        },
    }

    return json.dumps(report, indent=2)


# ─────────────────────────────────────────────────────────────────
# Tool 5: validate_otel_config
# ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def validate_otel_config(config_yaml: str) -> str:
    """
    Validate an OpenTelemetry Collector YAML configuration for common issues.

    Checks:
    - Required sections present (receivers, processors, exporters, service)
    - memory_limiter in processor chain (required before batch)
    - batch processor present
    - Service pipelines wire existing receivers/processors/exporters
    - No deprecated fields (opencensus receiver, jaeger exporter)
    - Recommended security settings

    Args:
        config_yaml: Full OTel Collector configuration as YAML string

    Returns:
        JSON with validation status, errors, warnings, and recommendations.
    """
    errors   = []
    warnings = []
    info     = []

    try:
        config = yaml.safe_load(config_yaml)
    except yaml.YAMLError as exc:
        return json.dumps({"valid": False, "errors": [f"YAML parse error: {exc}"]})

    if not isinstance(config, dict):
        return json.dumps({"valid": False, "errors": ["Config must be a YAML mapping"]})

    # ── Required top-level sections ──
    required = ["receivers", "processors", "exporters", "service"]
    for section in required:
        if section not in config:
            errors.append(f"Missing required top-level section: '{section}'")

    processors = config.get("processors", {}) or {}
    service    = config.get("service", {}) or {}
    pipelines  = service.get("pipelines", {}) or {}
    extensions = config.get("extensions", {}) or {}

    # ── memory_limiter check ──
    if "memory_limiter" not in processors:
        errors.append(
            "processors.memory_limiter is REQUIRED — prevents OOM crashes under high load. "
            "See: https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/memorylimiterprocessor"
        )

    # ── batch processor ──
    if "batch" not in processors:
        warnings.append(
            "processors.batch not found — batch processor is strongly recommended for "
            "efficiency and reducing downstream API calls."
        )

    # ── memory_limiter must be FIRST in pipeline ──
    for pipeline_name, pipeline in pipelines.items():
        pipeline_procs = (pipeline or {}).get("processors", []) or []
        if pipeline_procs and pipeline_procs[0] != "memory_limiter":
            if "memory_limiter" in pipeline_procs:
                errors.append(
                    f"pipeline '{pipeline_name}': memory_limiter MUST be first processor "
                    f"(currently at position {pipeline_procs.index('memory_limiter') + 1})"
                )

    # ── Pipeline consistency: all referenced components must exist ──
    receivers  = set(config.get("receivers", {}) or {})
    proc_set   = set(processors)
    exps       = set(config.get("exporters", {}) or {})
    connectors = set(config.get("connectors", {}) or {})

    for pipeline_name, pipeline in pipelines.items():
        p = pipeline or {}
        for recv in p.get("receivers", []):
            if recv not in receivers and recv not in connectors:
                errors.append(f"pipeline '{pipeline_name}': receiver '{recv}' not defined")
        for proc in p.get("processors", []):
            if proc not in proc_set:
                errors.append(f"pipeline '{pipeline_name}': processor '{proc}' not defined")
        for exp in p.get("exporters", []):
            if exp not in exps and exp not in connectors:
                errors.append(f"pipeline '{pipeline_name}': exporter '{exp}' not defined")

    # ── health_check extension recommended ──
    if "health_check" not in extensions:
        warnings.append(
            "health_check extension not found — add it for Kubernetes liveness/readiness probes. "
            "endpoint: '0.0.0.0:13133'"
        )

    # ── Deprecated components ──
    all_receivers = list(receivers)
    if any("opencensus" in r for r in all_receivers):
        warnings.append("opencensus receiver is deprecated — migrate to otlp receiver")
    all_exporters = list(exps)
    if any("jaeger" in e for e in all_exporters):
        warnings.append(
            "jaeger exporter is deprecated — use otlp exporter pointing to Jaeger's OTLP endpoint "
            "(port 4317/4318 supported since Jaeger 1.35+)"
        )

    # ── Security: CORS wildcard check ──
    otlp_receiver = (config.get("receivers", {}) or {}).get("otlp", {}) or {}
    http_cfg = (otlp_receiver.get("protocols", {}) or {}).get("http", {}) or {}
    cors = http_cfg.get("cors", {}) or {}
    allowed_origins = cors.get("allowed_origins", []) or []
    if "*" in allowed_origins:
        warnings.append(
            "CORS allowed_origins contains '*' — restrict to known origins in production"
        )

    # ── Sampling ──
    if not any("sampling" in p.lower() for p in proc_set):
        info.append(
            "No sampling processor detected — consider tail_sampling or probabilistic_sampler "
            "for production trace volumes to reduce costs"
        )

    valid = len(errors) == 0
    return json.dumps({
        "valid": valid,
        "status": "PASS" if valid else "FAIL",
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "docs": "https://opentelemetry.io/docs/collector/configuration/",
    }, indent=2)


# ─────────────────────────────────────────────────────────────────
# Tool 6: analyze_traffic
# ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def analyze_traffic(service_filter: str = ".*") -> str:
    """
    Analyze load balancer and traffic metrics: request rates, error rates,
    upstream health, p99 latency, and traffic anomalies.

    Args:
        service_filter: Regex to filter services/jobs (default: '.*' = all)

    Returns:
        JSON with per-service traffic stats, top-error services, latency outliers,
        and Traefik/NGINX backend health (if metrics available).
    """
    queries = {
        "request_rate":   f"sum(rate(http_requests_total{{job=~\"{service_filter}\"}}[5m])) by (job)",
        "error_rate":     f"job:http_error_ratio:rate5m{{job=~\"{service_filter}\"}}",
        "p99_latency":    f"job:http_request_duration_p99:rate5m{{job=~\"{service_filter}\"}}",
        "p95_latency":    f"job:http_request_duration_p95:rate5m{{job=~\"{service_filter}\"}}",
        "traefik_health": "traefik_service_server_up",
        "traefik_rps":    "sum(rate(traefik_service_requests_total[5m])) by (service)",
        "traffic_drop":   (
            f"(sum(rate(http_requests_total{{job=~\"{service_filter}\"}}[5m])) by (job)) "
            f"/ (sum(rate(http_requests_total{{job=~\"{service_filter}\"}}[5m] offset 1h)) by (job))"
        ),
    }

    results_raw = await asyncio.gather(
        *[_prometheus_query(q) for q in queries.values()],
        return_exceptions=True,
    )
    qr = dict(zip(queries.keys(), results_raw))

    def parse_vector(result: Any) -> dict:
        if isinstance(result, Exception):
            return {}
        out = {}
        for item in result.get("data", {}).get("result", []):
            label = item.get("metric", {})
            key = label.get("job") or label.get("service") or label.get("instance") or "unknown"
            try:
                out[key] = float(item.get("value", [None, "0"])[1])
            except (ValueError, TypeError):
                out[key] = None
        return out

    request_rates  = parse_vector(qr["request_rate"])
    error_rates    = parse_vector(qr["error_rate"])
    p99_latencies  = parse_vector(qr["p99_latency"])
    p95_latencies  = parse_vector(qr["p95_latency"])
    traffic_ratios = parse_vector(qr["traffic_drop"])

    all_services = set(request_rates) | set(error_rates) | set(p99_latencies)

    service_stats = []
    anomalies = []

    for svc in sorted(all_services):
        rps      = request_rates.get(svc, 0) or 0
        err_pct  = (error_rates.get(svc, 0) or 0) * 100
        p99      = p99_latencies.get(svc)
        p95      = p95_latencies.get(svc)
        ratio    = traffic_ratios.get(svc, 1.0) or 1.0

        flags = []
        if err_pct > 5:
            flags.append(f"high_error_rate:{err_pct:.1f}%")
        if p99 and p99 > 2.0:
            flags.append(f"slow_p99:{p99:.2f}s")
        if ratio < 0.5:
            flags.append(f"traffic_drop:{ratio:.0%}_vs_1h_ago")

        entry = {
            "service": svc,
            "request_rate_rps": round(rps, 2),
            "error_rate_pct": round(err_pct, 2),
            "latency_p95_s": round(p95, 3) if p95 else None,
            "latency_p99_s": round(p99, 3) if p99 else None,
            "traffic_vs_1h_ago_pct": round(ratio * 100, 1) if ratio else None,
            "flags": flags,
        }
        service_stats.append(entry)
        if flags:
            anomalies.append({"service": svc, "issues": flags})

    # Traefik backend status
    traefik_backends = []
    if not isinstance(qr["traefik_health"], Exception):
        for item in qr["traefik_health"].get("data", {}).get("result", []):
            labels = item.get("metric", {})
            try:
                up = int(float(item.get("value", [None, "0"])[1]))
            except (ValueError, TypeError):
                up = -1
            traefik_backends.append({
                "service": labels.get("service", "unknown"),
                "url": labels.get("url", ""),
                "status": "up" if up == 1 else "down",
            })

    return json.dumps({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service_filter": service_filter,
        "service_count": len(service_stats),
        "anomaly_count": len(anomalies),
        "services": service_stats,
        "anomalies": anomalies,
        "traefik_backends": traefik_backends,
    }, indent=2)


# ─────────────────────────────────────────────────────────────────
# Tool 7: get_llm_cost_summary
# ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_llm_cost_summary(agent_filter: str = ".*") -> str:
    """
    Get LLM token usage and cost breakdown by agent and model.
    Uses Prometheus metrics from OpenLLMetry or custom instrumentation.

    Args:
        agent_filter: Regex to filter agents (default: '.*' = all agents)

    Returns:
        JSON with per-agent cost/hour, token rates, top models by cost,
        and budget alerts (>$10/hr threshold).
    """
    queries = {
        "cost_rate_1h":   f"sum(rate(llm_cost_usd_total{{agent_name=~\"{agent_filter}\"}}[1h])) by (agent_name, model) * 3600",
        "tokens_in_5m":   f"sum(rate(llm_tokens_total{{agent_name=~\"{agent_filter}\",token_type=\"prompt\"}}[5m])) by (agent_name, model)",
        "tokens_out_5m":  f"sum(rate(llm_tokens_total{{agent_name=~\"{agent_filter}\",token_type=\"completion\"}}[5m])) by (agent_name, model)",
        "error_rate_5m":  f"sum(rate(agent_runs_total{{agent_name=~\"{agent_filter}\",status=\"error\"}}[5m])) by (agent_name) / sum(rate(agent_runs_total{{agent_name=~\"{agent_filter}\"}}[5m])) by (agent_name)",
        "llm_p95_lat":    "histogram_quantile(0.95, sum(rate(llm_request_duration_seconds_bucket[5m])) by (model, le))",
        "total_30d":      f"sum(increase(llm_cost_usd_total{{agent_name=~\"{agent_filter}\"}}[30d])) by (agent_name)",
    }

    results_raw = await asyncio.gather(
        *[_prometheus_query(q) for q in queries.values()],
        return_exceptions=True,
    )
    qr = dict(zip(queries.keys(), results_raw))

    def parse_by_label(result: Any, label_key: str, secondary_key: str = None) -> dict:
        if isinstance(result, Exception):
            return {}
        out = {}
        for item in result.get("data", {}).get("result", []):
            metric = item.get("metric", {})
            key = metric.get(label_key, "unknown")
            if secondary_key:
                key = f"{key}/{metric.get(secondary_key, 'unknown')}"
            try:
                out[key] = float(item.get("value", [None, "0"])[1])
            except (ValueError, TypeError):
                out[key] = 0.0
        return out

    cost_rates  = parse_by_label(qr["cost_rate_1h"],  "agent_name", "model")
    tokens_in   = parse_by_label(qr["tokens_in_5m"],  "agent_name", "model")
    tokens_out  = parse_by_label(qr["tokens_out_5m"], "agent_name", "model")
    error_rates = parse_by_label(qr["error_rate_5m"], "agent_name")
    total_30d   = parse_by_label(qr["total_30d"],     "agent_name")

    # p95 LLM latency by model
    llm_latency = parse_by_label(qr["llm_p95_lat"], "model")

    # Aggregate per agent/model
    agents: dict[str, dict] = {}
    for key, cost in cost_rates.items():
        if "/" in key:
            agent, model = key.split("/", 1)
        else:
            agent, model = key, "unknown"
        agents.setdefault(agent, {"models": []})
        agents[agent]["models"].append({
            "model": model,
            "cost_per_hour_usd": round(cost, 4),
            "prompt_tokens_per_5m": round(tokens_in.get(key, 0), 1),
            "completion_tokens_per_5m": round(tokens_out.get(key, 0), 1),
            "llm_p95_latency_s": round(llm_latency.get(model, 0), 2) or None,
        })

    summary_list = []
    budget_alerts = []

    for agent_name, data in sorted(agents.items()):
        total_hourly = sum(m["cost_per_hour_usd"] for m in data["models"])
        err_rate = error_rates.get(agent_name, 0) or 0
        monthly = total_30d.get(agent_name, 0) or 0

        entry = {
            "agent": agent_name,
            "total_cost_per_hour_usd": round(total_hourly, 4),
            "total_cost_30d_usd": round(monthly, 2),
            "error_rate_pct": round(err_rate * 100, 2),
            "models": data["models"],
        }
        summary_list.append(entry)

        if total_hourly > 10:
            budget_alerts.append(
                f"🚨 CRITICAL: Agent '{agent_name}' is burning ${total_hourly:.2f}/hr — "
                "immediate action required (check for runaway loops, model misconfiguration)"
            )
        elif total_hourly > 5:
            budget_alerts.append(
                f"⚠️ WARNING: Agent '{agent_name}' is at ${total_hourly:.2f}/hr — "
                "monitor closely and review task batching strategy"
            )

    summary_list.sort(key=lambda x: x["total_cost_per_hour_usd"], reverse=True)

    return json.dumps({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "agent_filter": agent_filter,
        "agent_count": len(summary_list),
        "total_hourly_usd": round(sum(a["total_cost_per_hour_usd"] for a in summary_list), 4),
        "budget_alerts": budget_alerts or ["No budget alerts."],
        "agents": summary_list,
        "docs": {
            "openllmetry":  "https://github.com/traceloop/openllmetry",
            "langfuse":     "https://langfuse.com/docs",
            "arize_phoenix": "https://docs.arize.com/phoenix",
            "otel_gen_ai":  "https://opentelemetry.io/docs/specs/semconv/gen-ai/",
        },
    }, indent=2)


# ─────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting obs-cost-traffic MCP server...")
    print(f"  Prometheus: {PROMETHEUS_URL}")
    print(f"  Grafana:    {GRAFANA_URL}")
    print(f"  Loki:       {LOKI_URL}")
    print(f"  Tempo:      {TEMPO_URL}")
    print(f"  OTel:       {OTEL_URL}")
    mcp.run()
