# Agent Architecture Patterns

Cross-SDK patterns for designing agent systems at any scale.

---

## Pattern Selection Guide

```
How many agents?

ONE agent:
  Simple tools? → Single Agent
  Complex routing? → Router Agent

MULTIPLE agents:
  Sequential stages? → Pipeline
  Central coordinator? → Orchestrator / Supervisor
  Peer collaboration? → Swarm / Group Chat
  Different SDKs? → Hybrid Architecture
```

---

## 1. Single Agent

One agent with tools. Simplest pattern — use when one agent can handle all tasks.

```
User → Agent → [Tool A, Tool B, Tool C] → Response
```

| SDK | Implementation |
|-----|----------------|
| Anthropic | `query(prompt, options={allowed_tools: [...]})` |
| OpenAI | `Agent(tools=[...])` → `Runner.run(agent, input)` |
| LangGraph | Single node with tool binding |
| CrewAI | One Agent + one Task in a Crew |
| Vercel | `generateText({tools: {...}, maxSteps: N})` |
| AG2 | `ConversableAgent` with registered functions |

**When to use:** Simple tasks, single domain, <5 tools.

---

## 2. Router / Triage

Classify input, then delegate to the right specialist.

```
User → Router Agent → [Agent A (billing), Agent B (tech), Agent C (general)]
```

| SDK | Implementation |
|-----|----------------|
| OpenAI | `Agent(handoffs=[billing, tech, general])` |
| Anthropic | Main agent with subagents via Task tool |
| LangGraph | Conditional edges from router node |
| CrewAI | Hierarchical process with manager |

**When to use:** Customer support, help desks, multi-domain queries.

---

## 3. Pipeline (Sequential)

Each agent processes a stage, passing output to the next.

```
User → [Extract] → [Transform] → [Validate] → [Load] → Result
```

| SDK | Implementation |
|-----|----------------|
| LangGraph | `add_edge(A, B)` chaining nodes sequentially |
| CrewAI | Sequential process with `context=[prev_task]` |
| OpenAI | Chain `Runner.run()` calls, passing output forward |
| Vercel | Nested `generateText` calls |

**When to use:** ETL, content pipelines, review workflows.

---

## 4. Orchestrator (Central Coordinator)

One coordinator agent decides what to do next and delegates.

```
              ┌→ Worker A → ┐
User → Orchestrator → Worker B → Orchestrator → Response
              └→ Worker C → ┘
```

| SDK | Implementation |
|-----|----------------|
| LangGraph | Supervisor node with conditional edges to workers |
| CrewAI | Hierarchical process with `manager_llm` |
| Anthropic | Main agent spawning subagents via Task tool |
| AG2 | GroupChatManager with custom speaker selection |

**When to use:** Complex multi-step tasks, research, report generation.

---

## 5. Supervisor (Manager Reviews)

Like orchestrator, but manager reviews and may reject worker output.

```
User → Supervisor ←→ Worker A (iterate until approved)
         ↓
       Worker B (iterate until approved)
         ↓
       Final Response
```

| SDK | Implementation |
|-----|----------------|
| LangGraph | Loop: worker → supervisor → (approve or retry) |
| CrewAI | Hierarchical with quality gates |

**When to use:** Quality-critical workflows, content creation, code review.

---

## 6. Swarm / Group Chat

Agents communicate as peers without central coordinator.

```
Agent A ↔ Agent B ↔ Agent C
(self-organizing)
```

| SDK | Implementation |
|-----|----------------|
| OpenAI | Agents with mutual `handoffs=[]` |
| AG2 | `GroupChat` with `speaker_selection_method="auto"` |
| LangGraph | Fully connected graph with conditional edges |

**When to use:** Brainstorming, debate, consensus-driven decisions.

---

## 7. Hybrid Architecture

Different SDKs for different layers. Best for global-scale systems.

### Example: LangGraph Orchestrator + Anthropic Workers

```python
# LangGraph manages workflow state and routing
# Anthropic Agent SDK handles autonomous code tasks

from langgraph.graph import StateGraph
from claude_agent_sdk import query, ClaudeAgentOptions

async def code_worker(state):
    """Anthropic Agent SDK for autonomous coding."""
    result_text = ""
    async for msg in query(
        prompt=state["task"],
        options=ClaudeAgentOptions(allowed_tools=["Read", "Edit", "Bash"])
    ):
        if hasattr(msg, "result"):
            result_text = msg.result
    return {"results": {**state["results"], "code": result_text}}

async def research_worker(state):
    """OpenAI agent for research tasks."""
    result = await Runner.run(research_agent, state["task"])
    return {"results": {**state["results"], "research": result.final_output}}

graph = StateGraph(WorkflowState)
graph.add_node("orchestrate", orchestrator_node)
graph.add_node("code", code_worker)
graph.add_node("research", research_worker)
# ... routing logic
```

### Example: CrewAI Backend + Vercel Frontend

```
Browser → Vercel AI SDK (streaming UI) → API → CrewAI Crew (backend processing)
```

### Common Hybrid Combos

| Frontend | Orchestration | Workers | Use Case |
|----------|---------------|---------|----------|
| Vercel AI SDK | LangGraph | Anthropic Agent SDK | Full-stack code agent |
| Vercel AI SDK | - | OpenAI Agents SDK | Chat with handoffs |
| - | LangGraph | CrewAI Crews | Complex research pipeline |
| - | CrewAI Flows | Multiple LLM providers | Enterprise workflows |

---

## Scaling Patterns

### Vertical Scaling (Single Agent)

- Increase `max_steps` / `max_turns`
- Add more tools
- Use better models for complex reasoning

### Horizontal Scaling (Multi-Agent)

- Split responsibilities across specialized agents
- Use message queues between agents (Redis, RabbitMQ)
- Deploy agents as separate services

### Global Scaling

- Deploy to multiple regions
- Use CDN for static agent responses
- Implement caching for common queries
- Use streaming for real-time responses (Vercel Edge, CloudFlare Workers)
- Load balance across agent instances

---

## Pattern Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| God agent | One agent does everything | Split into specialists |
| Chatty agents | Agents pass too many messages | Define clear interfaces |
| No termination | Agents loop forever | Set max_steps, max_rounds |
| Wrong SDK | Using complex SDK for simple task | Match SDK to complexity |
| Over-engineering | Multi-agent for single-purpose task | Start simple, scale up |
