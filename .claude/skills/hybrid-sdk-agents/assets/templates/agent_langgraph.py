"""{{AGENT_NAME}} — Built with LangGraph.

{{AGENT_DESCRIPTION}}
"""

import os
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

# Ensure API key is set
assert os.environ.get("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY environment variable"


# --- State ---

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    # Add custom state fields here
    # results: dict
    # current_step: str


# --- Tools ---

@tool
def {{TOOL_NAME}}({{TOOL_PARAMS}}) -> str:
    """{{TOOL_DESCRIPTION}}"""
    try:
        # Implementation here
        return "Result"
    except Exception as e:
        return f"Error: {e}"


# --- Model ---

model = ChatAnthropic(model="claude-sonnet-4-5-20250929")
tools = [{{TOOL_NAME}}]
model_with_tools = model.bind_tools(tools)


# --- Nodes ---

def agent_node(state: AgentState) -> dict:
    """Main agent reasoning node."""
    response = model_with_tools.invoke(state["messages"])
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """Route: continue with tools or finish."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


# --- Graph ---

graph = StateGraph(AgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(tools))

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")

# Compile with checkpointing
checkpointer = MemorySaver()  # Use PostgresSaver for production
app = graph.compile(checkpointer=checkpointer)


async def run_agent(prompt: str, thread_id: str = "default") -> str:
    """Run the agent with state persistence."""
    config = {"configurable": {"thread_id": thread_id}}
    result = await app.ainvoke(
        {"messages": [("user", prompt)]},
        config=config
    )
    return result["messages"][-1].content


async def main():
    import asyncio
    result = await run_agent("{{DEFAULT_PROMPT}}")
    print(f"Result: {result}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
