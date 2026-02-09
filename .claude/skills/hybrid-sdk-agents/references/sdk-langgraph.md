# LangGraph

Complete patterns for building agents with LangGraph.

---

## Overview

LangGraph is a low-level orchestration framework for building stateful, multi-agent systems as graphs. Nodes are functions/agents, edges control flow, and state persists across steps. Production-ready with checkpointing, human-in-the-loop, and time-travel debugging.

**Install:**
```bash
pip install langgraph langchain-anthropic  # or langchain-openai
```

---

## Core Architecture: StateGraph

### State Definition

```python
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    current_step: str
    results: dict
```

### Basic Agent Graph

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

# Define tools
@tool
def search_docs(query: str) -> str:
    """Search documentation for information."""
    return f"Results for: {query}"

@tool
def create_ticket(title: str, body: str) -> dict:
    """Create a support ticket."""
    return {"id": "TICKET-123", "title": title}

# Create model with tools
model = ChatAnthropic(model="claude-sonnet-4-5-20250929")
tools = [search_docs, create_ticket]
model_with_tools = model.bind_tools(tools)

# Define nodes
def agent_node(state: AgentState):
    response = model_with_tools.invoke(state["messages"])
    return {"messages": [response]}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

# Build graph
graph = StateGraph(AgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(tools))

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")

app = graph.compile()

# Run
result = app.invoke({"messages": [("user", "Search for auth docs")]})
```

---

## Multi-Agent Patterns

### Supervisor Pattern

```python
from langgraph.graph import StateGraph, START, END

class TeamState(TypedDict):
    messages: Annotated[list, add_messages]
    next_agent: str

def supervisor_node(state: TeamState):
    """Supervisor decides which agent works next."""
    response = supervisor_model.invoke(
        state["messages"] + [("system", "Choose: researcher, writer, or FINISH")]
    )
    return {"next_agent": response.content}

def researcher_node(state: TeamState):
    response = research_model.invoke(state["messages"])
    return {"messages": [("assistant", f"[Researcher]: {response.content}")]}

def writer_node(state: TeamState):
    response = writer_model.invoke(state["messages"])
    return {"messages": [("assistant", f"[Writer]: {response.content}")]}

def route_supervisor(state: TeamState):
    if state["next_agent"] == "FINISH":
        return END
    return state["next_agent"]

graph = StateGraph(TeamState)
graph.add_node("supervisor", supervisor_node)
graph.add_node("researcher", researcher_node)
graph.add_node("writer", writer_node)

graph.add_edge(START, "supervisor")
graph.add_conditional_edges("supervisor", route_supervisor)
graph.add_edge("researcher", "supervisor")
graph.add_edge("writer", "supervisor")

team = graph.compile()
```

### Pipeline (Sequential) Pattern

```python
graph = StateGraph(PipelineState)
graph.add_node("extract", extract_node)
graph.add_node("transform", transform_node)
graph.add_node("validate", validate_node)
graph.add_node("load", load_node)

graph.add_edge(START, "extract")
graph.add_edge("extract", "transform")
graph.add_edge("transform", "validate")
graph.add_conditional_edges("validate", check_valid, {"valid": "load", "invalid": "extract"})
graph.add_edge("load", END)
```

---

## Checkpointing (Memory & State Persistence)

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)

# Run with thread ID for persistence
config = {"configurable": {"thread_id": "user-123"}}
result = app.invoke({"messages": [("user", "Hello")]}, config=config)

# Resume later — full state restored
result = app.invoke({"messages": [("user", "Continue")]}, config=config)
```

For production: use `SqliteSaver`, `PostgresSaver`, or custom checkpointer.

---

## Human-in-the-Loop (Interrupts)

```python
from langgraph.graph import StateGraph

# Compile with interrupt points
app = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["dangerous_action_node"]
)

# Run until interrupt
result = app.invoke(input, config)
# → Pauses before "dangerous_action_node"

# User reviews, then continue
app.invoke(None, config)  # Resume from checkpoint
```

---

## LangSmith Observability

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=ls-...
```

Traces all LLM calls, tool invocations, graph transitions automatically. Includes:
- Run traces with latency and token counts
- Feedback collection for evaluation
- Dataset creation for testing
- Time-travel debugging for graph states

---

## MCP Integration

```python
from langchain_core.tools import tool
import subprocess, json

# Wrap MCP tool calls as LangChain tools
@tool
def mcp_query(sql: str) -> str:
    """Query the database via MCP server."""
    # Call MCP server tool
    result = call_mcp_tool("query", {"sql": sql})
    return json.dumps(result)
```

Or use LangChain's MCP adapter when available.

---

## Best Practices

- Define state types explicitly with TypedDict
- Use conditional edges for dynamic routing (not hardcoded flows)
- Add checkpointing for any agent that needs persistence or human-in-the-loop
- Use `interrupt_before` for dangerous/irreversible actions
- Keep node functions pure — side effects only through tools
- Use subgraphs for complex multi-agent hierarchies
- Set recursion limits: `app.invoke(input, {"recursion_limit": 25})`
- Enable LangSmith tracing in production for debugging
- Use `MemorySaver` for dev, `PostgresSaver` for production
