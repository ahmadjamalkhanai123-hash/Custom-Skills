# Observability Stack

## Structured Logging with structlog

```python
import structlog
import logging
import sys


def configure_logging(log_level: str = "INFO", json_output: bool = True):
    """Call once at application startup."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
```

## Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import FastAPI, Response

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

AGENT_EXECUTIONS = Counter(
    "agent_executions_total",
    "Total agent executions",
    ["agent_id", "status"],
)

AGENT_DURATION = Histogram(
    "agent_execution_duration_seconds",
    "Agent execution duration in seconds",
    ["agent_id"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

ACTIVE_AGENTS = Gauge(
    "active_agents",
    "Currently running agent executions",
)

TOKEN_USAGE = Counter(
    "agent_token_usage_total",
    "Total tokens consumed by agent calls",
    ["agent_id", "token_type"],
)


def setup_metrics(app: FastAPI):
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(
            content=generate_latest(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )
```

## OpenTelemetry Instrumentation

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
import os


def configure_tracing(app):
    resource = Resource.create({
        "service.name": os.getenv("SERVICE_NAME", "fastapi-agent-service"),
        "service.version": os.getenv("SERVICE_VERSION", "0.1.0"),
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
    })

    exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanExporter(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
```

## Key Metrics and Alerting Thresholds

| Metric | Warning | Critical | Notes |
|--------|---------|----------|-------|
| Request latency (p99) | > 10s | > 30s | Agent calls are inherently slow |
| Token usage per request | > 20K | > 50K | May indicate runaway loops |
| Error rate (5xx) | > 2% | > 5% | Exclude expected 4xx |
| Active agents | > 50 | > 100 | Depends on infra capacity |
| Circuit breaker opens | any | > 3/min | Downstream service degraded |
| Memory usage | > 70% | > 85% | LLM responses can be large |
| Queue depth | > 100 | > 500 | For async task architectures |

## LLM Observability Platforms

| Platform | Strengths | Integration |
|----------|-----------|-------------|
| **LangSmith** | Trace chains, prompt versioning, LangChain native | `LANGCHAIN_TRACING_V2=true` env var |
| **Braintrust** | Evals, scoring, dataset management | SDK wrapper around LLM calls |
| **Phoenix (Arize)** | Open source, span visualization, embeddings | OpenInference + OTEL exporter |
| **Opik (Comet)** | Trace logging, prompt experiments | `opik.track()` decorator |
| **Helicone** | Proxy-based, zero-code, cost tracking | Set base_url to Helicone proxy |

## Agent-Specific Trace Example

```python
import structlog
from opentelemetry import trace

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


async def run_agent_with_observability(agent_id: str, input_text: str):
    with tracer.start_as_current_span(
        "agent_execution",
        attributes={"agent.id": agent_id, "input.length": len(input_text)},
    ) as span:
        ACTIVE_AGENTS.inc()
        logger.info("agent_started", agent_id=agent_id)

        try:
            result = await execute_agent(agent_id, input_text)

            span.set_attribute("output.length", len(result.output))
            span.set_attribute("tokens.used", result.token_usage)
            AGENT_EXECUTIONS.labels(agent_id=agent_id, status="success").inc()
            AGENT_DURATION.labels(agent_id=agent_id).observe(result.duration)
            TOKEN_USAGE.labels(agent_id=agent_id, token_type="total").inc(result.token_usage)

            logger.info(
                "agent_completed",
                agent_id=agent_id,
                tokens=result.token_usage,
                duration_s=result.duration,
            )
            return result

        except Exception as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(exc))
            AGENT_EXECUTIONS.labels(agent_id=agent_id, status="error").inc()
            logger.error("agent_failed", agent_id=agent_id, error=str(exc))
            raise

        finally:
            ACTIVE_AGENTS.dec()
```
