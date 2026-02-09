# OpenAI Agents SDK

Complete patterns for building agents with the OpenAI Agents SDK.

---

## Overview

A lightweight, Python-first framework for multi-agent workflows. Built around four primitives: **Agent**, **Handoff**, **Guardrail**, **Tracing**. Minimal abstractions — uses Python language features for orchestration.

**Install:**
```bash
pip install openai-agents
export OPENAI_API_KEY=sk-...
```

---

## Core Primitives

### 1. Agent

```python
from agents import Agent, Runner

agent = Agent(
    name="Research Assistant",
    instructions="You are a helpful research assistant. Be concise and factual.",
    model="gpt-4o",
    tools=[search_tool, summarize_tool],
    handoffs=[specialist_agent],
    guardrails=[content_filter]
)

# Run synchronously
result = Runner.run_sync(agent, "Summarize the latest AI research")
print(result.final_output)

# Run asynchronously
result = await Runner.run(agent, "Summarize the latest AI research")
```

### 2. Tools (Function Calling)

```python
from agents import function_tool

@function_tool
def search_documents(query: str, max_results: int = 5) -> list[dict]:
    """Search the document database by keyword."""
    # Implementation
    return [{"title": "...", "content": "..."}]

@function_tool
def create_report(title: str, sections: list[str]) -> dict:
    """Generate a structured report from sections."""
    return {"title": title, "sections": sections, "status": "created"}

agent = Agent(
    name="Report Writer",
    instructions="Write reports based on research.",
    tools=[search_documents, create_report]
)
```

Automatic schema generation from type hints via Pydantic validation.

### 3. Handoffs (Multi-Agent Delegation)

```python
from agents import Agent, handoff
from pydantic import BaseModel

# Define specialized agents
billing_agent = Agent(
    name="Billing Agent",
    instructions="Handle billing questions and payment issues."
)

refund_agent = Agent(
    name="Refund Agent",
    instructions="Process refund requests. Verify purchase first."
)

# Triage agent delegates to specialists
triage_agent = Agent(
    name="Triage Agent",
    instructions="Route customer requests to the right specialist.",
    handoffs=[billing_agent, handoff(refund_agent)]
)

# Handoff with input data
class EscalationData(BaseModel):
    reason: str
    priority: str

async def on_escalate(ctx, input_data: EscalationData):
    print(f"Escalation: {input_data.reason} (priority: {input_data.priority})")

escalation_handoff = handoff(
    agent=supervisor_agent,
    on_handoff=on_escalate,
    input_type=EscalationData
)
```

When handoff occurs, new agent receives the **full conversation history**.

### 4. Guardrails (Input/Output Validation)

```python
from agents import Agent, InputGuardrail, OutputGuardrail, GuardrailFunctionOutput

# Input guardrail — runs PARALLEL with agent
class ContentFilter(InputGuardrail):
    async def run(self, input, context) -> GuardrailFunctionOutput:
        # Check for prohibited content
        if contains_prohibited(input):
            return GuardrailFunctionOutput(
                output_info={"reason": "prohibited content"},
                tripwire_triggered=True  # Stops agent immediately
            )
        return GuardrailFunctionOutput(output_info={"status": "clean"})

# Output guardrail — validates agent response
class FactChecker(OutputGuardrail):
    async def run(self, output, context) -> GuardrailFunctionOutput:
        if contains_unverified_claims(output):
            return GuardrailFunctionOutput(
                output_info={"reason": "unverified claims"},
                tripwire_triggered=True
            )
        return GuardrailFunctionOutput(output_info={"status": "verified"})

agent = Agent(
    name="Safe Assistant",
    guardrails=[ContentFilter(), FactChecker()]
)
```

### 5. Tracing (Built-in Observability)

```python
from agents import trace, Runner

# Automatic tracing — every run is traced
result = await Runner.run(agent, "Process this request")

# Custom trace spans
with trace("custom-workflow"):
    result1 = await Runner.run(agent1, "Step 1")
    result2 = await Runner.run(agent2, f"Step 2: {result1.final_output}")
```

Traces capture: LLM generations, tool calls, handoffs, guardrails, custom events. Compatible with OpenAI's evaluation/fine-tuning tools.

---

## MCP Integration

MCP servers work as tools:

```python
from agents.mcp import MCPServerStdio

async with MCPServerStdio(
    command="uv",
    args=["run", "postgres-mcp-server"],
    env={"DATABASE_URL": "postgresql://..."}
) as mcp_server:
    agent = Agent(
        name="DB Assistant",
        instructions="Query databases to answer questions.",
        mcp_servers=[mcp_server]
    )
    result = await Runner.run(agent, "What tables exist?")
```

---

## Multi-Agent Patterns

### Triage/Router Pattern

```python
triage = Agent(
    name="Router",
    instructions="Route to: billing for payment issues, tech for technical issues.",
    handoffs=[billing_agent, tech_agent, general_agent]
)
result = await Runner.run(triage, user_message)
```

### Pipeline Pattern

```python
researcher = Agent(name="Researcher", instructions="Research the topic.", tools=[search])
writer = Agent(name="Writer", instructions="Write article from research.", handoffs=[])

with trace("research-pipeline"):
    research = await Runner.run(researcher, topic)
    article = await Runner.run(writer, f"Write about: {research.final_output}")
```

### Orchestrator with Context

```python
from agents import RunContextWrapper

class OrchestratorContext:
    results: dict = {}

orchestrator = Agent(
    name="Orchestrator",
    instructions="Coordinate research agents and compile results.",
    handoffs=[researcher_1, researcher_2, compiler_agent]
)
```

---

## Best Practices

- Use handoffs for clear responsibility boundaries between agents
- Guardrails run in parallel — use for safety without latency cost
- Use `function_tool` decorator for simple tools, Pydantic models for complex inputs
- Set `model_settings` for temperature, max_tokens per agent
- Enable tracing in production for debugging and evaluation
- Use `input_filter` on handoffs to control what context transfers
- Keep agent instructions concise and specific (<500 tokens)
