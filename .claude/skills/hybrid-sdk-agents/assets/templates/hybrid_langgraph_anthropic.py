"""{{AGENT_NAME}} — Hybrid: LangGraph Orchestrator + Anthropic Agent SDK Subagents.

{{AGENT_DESCRIPTION}}

Architecture:
  LangGraph manages state, routing, and workflow control.
  Anthropic Agent SDK handles autonomous tool-use subagents.
  Best of both: stateful orchestration + powerful autonomous agents.
"""

import asyncio
import os
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from anthropic import Anthropic

# Ensure API keys are set
assert os.environ.get("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY environment variable"

subagent_client = Anthropic()


# --- State ---

class OrchestratorState(TypedDict):
    messages: Annotated[list, add_messages]
    task: str
    subtask_results: dict
    current_phase: str


# --- Anthropic Agent SDK Subagents ---

async def run_subagent(prompt: str) -> str:
    """Delegate a task to an Anthropic subagent."""
    response = subagent_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text += block.text

    return result_text


# --- LangGraph Nodes ---

model = ChatAnthropic(model="claude-sonnet-4-5-20250929")


async def plan_node(state: OrchestratorState) -> dict:
    """Plan: Break task into subtasks using LLM."""
    response = await model.ainvoke([
        ("system", "You are a task planner. Break the task into 2-3 concrete subtasks. "
                   "Return JSON: {\"subtasks\": [\"task1\", \"task2\"]}"),
        ("user", state["task"]),
    ])
    return {"messages": [response], "current_phase": "execute"}


async def execute_node(state: OrchestratorState) -> dict:
    """Execute: Delegate subtasks to Anthropic Agent SDK subagents."""
    # Extract subtasks from planner output
    plan_output = state["messages"][-1].content

    # Run subagents in parallel for each subtask
    results = {}
    tasks = []
    subtask_names = []

    # Parse subtasks (simplified — production would use structured output)
    import json
    try:
        parsed = json.loads(plan_output)
        subtasks = parsed.get("subtasks", [plan_output])
    except json.JSONDecodeError:
        subtasks = [plan_output]

    for i, subtask in enumerate(subtasks):
        subtask_name = f"subtask_{i}"
        subtask_names.append(subtask_name)
        tasks.append(run_subagent(prompt=subtask))

    # Execute all subagents concurrently
    subagent_results = await asyncio.gather(*tasks, return_exceptions=True)

    for name, result in zip(subtask_names, subagent_results):
        if isinstance(result, Exception):
            results[name] = f"Error: {result}"
        else:
            results[name] = result

    return {"subtask_results": results, "current_phase": "synthesize"}


async def synthesize_node(state: OrchestratorState) -> dict:
    """Synthesize: Combine subagent results into final output."""
    results_summary = "\n\n".join(
        f"### {k}\n{v}" for k, v in state["subtask_results"].items()
    )
    response = await model.ainvoke([
        ("system", "Synthesize these subtask results into a coherent final response."),
        ("user", f"Original task: {state['task']}\n\nSubtask results:\n{results_summary}"),
    ])
    return {"messages": [response], "current_phase": "done"}


def route_phase(state: OrchestratorState) -> str:
    """Route based on current workflow phase."""
    phase = state.get("current_phase", "plan")
    if phase == "execute":
        return "execute"
    if phase == "synthesize":
        return "synthesize"
    return END


# --- Graph ---

graph = StateGraph(OrchestratorState)
graph.add_node("plan", plan_node)
graph.add_node("execute", execute_node)
graph.add_node("synthesize", synthesize_node)

graph.add_edge(START, "plan")
graph.add_conditional_edges("plan", route_phase, {
    "execute": "execute",
    END: END,
})
graph.add_conditional_edges("execute", route_phase, {
    "synthesize": "synthesize",
    END: END,
})
graph.add_edge("synthesize", END)

checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)


# --- Runner ---

async def run_hybrid_agent(task: str, thread_id: str = "default") -> str:
    """Run the hybrid orchestrator."""
    config = {"configurable": {"thread_id": thread_id}}
    result = await app.ainvoke(
        {"task": task, "messages": [], "subtask_results": {}, "current_phase": "plan"},
        config=config,
    )
    return result["messages"][-1].content


async def main():
    result = await run_hybrid_agent("{{DEFAULT_PROMPT}}")
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
