# AI Agent & LLM Observability
## Token Tracking, Agent Telemetry, LLM Cost Attribution, Multi-Agent Tracing

---

## Why AI Agent Observability is Different

Traditional services process deterministic requests. AI agents:
- Make **non-deterministic decisions** (tool selection, response generation)
- **Chain multiple LLM calls** across steps, handoffs, and retries
- Have **variable cost per invocation** (token usage varies wildly)
- Can **fail silently** (wrong output, hallucination, safety violation)
- Involve **multi-step workflows** spanning multiple services and agents

Standard APM tools cannot capture these semantics. Dedicated AI observability is required.

---

## OpenTelemetry GenAI Semantic Conventions

The OTel Semantic Conventions for GenAI (stable in 2025):

```python
# Standard attributes for LLM spans
from opentelemetry import trace

tracer = trace.get_tracer("my-agent")

with tracer.start_as_current_span("llm.chat") as span:
    span.set_attributes({
        # Model identification
        "gen_ai.system": "anthropic",           # anthropic | openai | google_vertex_ai
        "gen_ai.request.model": "claude-sonnet-4-6",
        "gen_ai.request.max_tokens": 2048,
        "gen_ai.request.temperature": 0.7,

        # Usage (set after response)
        "gen_ai.usage.input_tokens": 1024,
        "gen_ai.usage.output_tokens": 512,
        "gen_ai.usage.total_tokens": 1536,

        # Cost (custom — not in spec yet)
        "gen_ai.usage.cost_usd": 0.00461,       # calculated from token pricing

        # Response metadata
        "gen_ai.response.finish_reasons": ["stop"],
        "gen_ai.response.id": "msg_01XFDUDYJgAACzvnptvVoYEL",

        # Operation
        "gen_ai.operation.name": "chat",        # chat | text_completion | embeddings
    })
```

---

## OpenLLMetry — OpenTelemetry for LLMs

```python
# pip install opentelemetry-sdk traceloop-sdk
from traceloop.sdk import Traceloop
from traceloop.sdk.decorators import workflow, task, agent, tool

Traceloop.init(
    app_name="order-ai-agent",
    api_endpoint="http://otel-collector:4318",  # OTLP HTTP
)

@workflow(name="process_order_request")
def process_order_workflow(user_request: str):
    intent = classify_intent(user_request)
    if intent == "order":
        return place_order_agent(user_request)
    return general_response_agent(user_request)

@agent(name="order_placement_agent")
def place_order_agent(request: str):
    items = extract_items(request)
    for item in items:
        validate_item(item)
    return confirm_order(items)

@task(name="extract_order_items")
def extract_items(request: str) -> list:
    # LLM call automatically traced
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": request}],
    )
    return response.content[0].text

@tool(name="validate_inventory")
def validate_item(item: dict) -> bool:
    return inventory_service.check(item["sku"])
```

---

## Langfuse — LLM Observability Platform

```python
# pip install langfuse
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context

langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)

@observe(name="agent_workflow")
def run_agent(user_id: str, query: str):
    # Automatically creates trace with user_id context
    langfuse_context.update_current_trace(
        user_id=user_id,
        session_id=f"session_{uuid4()}",
        tags=["production", "order-agent"],
        metadata={"query_type": "order", "tenant": get_tenant(user_id)}
    )

    # Each nested @observe call creates a span
    intent = classify_query(query)
    result = execute_intent(intent, query)

    # Track cost
    langfuse_context.update_current_observation(
        usage={
            "input": total_input_tokens,
            "output": total_output_tokens,
            "unit": "TOKENS",
        }
    )
    return result

@observe(name="llm_classify")
def classify_query(query: str) -> str:
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": f"Classify: {query}"}],
    )
    # Langfuse captures token usage automatically for Anthropic client
    return response.content[0].text
```

### Langfuse Scoring (Quality Tracking)
```python
# Score LLM outputs for quality/safety
langfuse.score(
    trace_id=trace_id,
    name="user_satisfaction",
    value=4.5,          # 0-5 scale
    comment="User rated helpful"
)

langfuse.score(
    trace_id=trace_id,
    name="safety_check",
    value=1,            # 0 = safe, 1 = violation
    data_type="BOOLEAN",
    comment="PII detected in response"
)
```

---

## Arize Phoenix — LLM Tracing + Evaluation

```python
# pip install arize-phoenix openinference-instrumentation-anthropic
import phoenix as px
from openinference.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Start Phoenix (local) or point to cloud
endpoint = "http://phoenix.monitoring:6006/v1/traces"

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
)
trace_api.set_tracer_provider(tracer_provider)

# Auto-instrument Anthropic SDK
AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)

# All anthropic.messages.create() calls now traced automatically
```

---

## Token Cost Tracking (Custom)

```python
# Token pricing as of February 2026 (verify at vendor pricing pages)
LLM_PRICING = {
    "claude-opus-4-6": {
        "input_per_1m": 15.00,
        "output_per_1m": 75.00,
    },
    "claude-sonnet-4-6": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
    },
    "claude-haiku-4-5-20251001": {
        "input_per_1m": 0.25,
        "output_per_1m": 1.25,
    },
    "gpt-4o": {
        "input_per_1m": 2.50,
        "output_per_1m": 10.00,
    },
    "gpt-4o-mini": {
        "input_per_1m": 0.15,
        "output_per_1m": 0.60,
    },
}

def calculate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = LLM_PRICING.get(model)
    if not pricing:
        return 0.0
    return (
        (input_tokens / 1_000_000) * pricing["input_per_1m"] +
        (output_tokens / 1_000_000) * pricing["output_per_1m"]
    )

# Prometheus metrics for LLM cost tracking
from prometheus_client import Counter, Histogram

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens consumed by LLM calls",
    ["model", "agent_name", "operation", "token_type"]
)

llm_cost_usd_total = Counter(
    "llm_cost_usd_total",
    "Total USD cost of LLM calls",
    ["model", "agent_name", "operation"]
)

llm_request_duration = Histogram(
    "llm_request_duration_seconds",
    "LLM API call latency",
    ["model", "agent_name"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60]
)

def instrumented_llm_call(
    client, model: str, agent_name: str, **kwargs
):
    with llm_request_duration.labels(model=model, agent_name=agent_name).time():
        response = client.messages.create(model=model, **kwargs)

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = calculate_llm_cost(model, input_tokens, output_tokens)

    llm_tokens_total.labels(
        model=model, agent_name=agent_name,
        operation="chat", token_type="input"
    ).inc(input_tokens)

    llm_tokens_total.labels(
        model=model, agent_name=agent_name,
        operation="chat", token_type="output"
    ).inc(output_tokens)

    llm_cost_usd_total.labels(
        model=model, agent_name=agent_name, operation="chat"
    ).inc(cost)

    return response
```

---

## Multi-Agent Tracing Patterns

```python
# Parent agent creates root span; child agents link via trace context
from opentelemetry import trace
from opentelemetry.propagate import inject, extract

tracer = trace.get_tracer("orchestrator")

class OrchestratorAgent:
    async def run(self, task: str):
        with tracer.start_as_current_span("orchestrator.run",
            attributes={"agent.type": "orchestrator", "task": task}
        ) as span:
            # Inject context for passing to sub-agents
            carrier = {}
            inject(carrier)

            # Spawn sub-agents with trace context
            results = await asyncio.gather(
                self.research_agent.run(task, trace_context=carrier),
                self.validator_agent.run(task, trace_context=carrier),
            )
            return self.synthesize(results)

class ResearchAgent:
    async def run(self, task: str, trace_context: dict):
        # Extract context from parent agent
        ctx = extract(trace_context)

        with tracer.start_as_current_span("research.run",
            context=ctx,
            kind=trace.SpanKind.INTERNAL,
            attributes={
                "agent.type": "research",
                "agent.parent": "orchestrator",
            }
        ) as span:
            tool_result = await self.search_tool(task)
            llm_result = await self.summarize(tool_result)
            span.set_attribute("agent.steps", 2)
            return llm_result
```

---

## AI-Specific SLOs and Alerts

```yaml
# Prometheus alerting rules for AI agents
groups:
  - name: ai-agent-slos
    rules:
      # Token budget exceeded
      - alert: AgentTokenBudgetExceeded
        expr: |
          sum(rate(llm_tokens_total[1h])) by (agent_name) > 1000000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Agent {{ $labels.agent_name }} consuming >1M tokens/hour"

      # LLM cost spike
      - alert: LLMCostSpike
        expr: |
          sum(rate(llm_cost_usd_total[10m])) by (agent_name) * 3600 > 10
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "{{ $labels.agent_name }} projected hourly LLM cost >$10"

      # High LLM latency (p99 > 30s)
      - alert: LLMHighLatency
        expr: |
          histogram_quantile(0.99,
            sum(rate(llm_request_duration_seconds_bucket[5m])) by (model, le)
          ) > 30
        for: 10m
        labels:
          severity: warning

      # Agent error rate
      - alert: AgentHighErrorRate
        expr: |
          sum(rate(agent_runs_total{status="error"}[5m])) by (agent_name)
          / sum(rate(agent_runs_total[5m])) by (agent_name) > 0.1
        for: 5m
        labels:
          severity: critical
```

---

## Grafana Dashboard — AI Agent Cost & Performance

Key panels for an AI agent dashboard:
1. **Token Usage Rate** — tokens/minute by model and agent
2. **LLM Cost Rate** — $/hour by agent (area chart with threshold line)
3. **LLM Latency** — p50/p95/p99 by model
4. **Agent Success Rate** — gauge with SLO threshold
5. **Cost Per Agent Run** — histogram
6. **Model Distribution** — pie chart of token usage by model (cheaper vs expensive)
7. **Tool Call Volume** — tool calls per agent per minute
8. **Daily Cost Forecast** — current spend + linear projection vs budget

```json
{
  "title": "LLM Cost Rate ($/hr)",
  "type": "timeseries",
  "targets": [{
    "expr": "sum(rate(llm_cost_usd_total[5m])) by (agent_name) * 3600",
    "legendFormat": "{{ agent_name }}"
  }],
  "thresholds": {
    "steps": [
      {"value": null, "color": "green"},
      {"value": 5, "color": "yellow"},
      {"value": 20, "color": "red"}
    ]
  }
}
```
