#!/usr/bin/env python3
"""
Agent Project Scaffolder — Generate production-ready agent project structure.

Usage:
    python scaffold_agent.py <agent-name> --sdk <sdk> --path <output-dir> [options]

SDKs:
    anthropic, openai, langgraph, crewai, vercel, autogen, hybrid

Examples:
    python scaffold_agent.py my-agent --sdk anthropic --path ./projects
    python scaffold_agent.py research-crew --sdk crewai --path ./projects --lang python
    python scaffold_agent.py web-assistant --sdk vercel --path ./projects --lang typescript
    python scaffold_agent.py orchestrator --sdk hybrid --path ./projects
"""

import sys
import os
from pathlib import Path
from textwrap import dedent


SDK_CHOICES = ["anthropic", "openai", "langgraph", "crewai", "vercel", "autogen", "hybrid"]
LANG_MAP = {
    "anthropic": "python",
    "openai": "python",
    "langgraph": "python",
    "crewai": "python",
    "vercel": "typescript",
    "autogen": "python",
    "hybrid": "python",
}

DEPENDENCIES = {
    "anthropic": '"anthropic>=0.40.0"',
    "openai": '"openai-agents>=0.1.0"',
    "langgraph": '"langgraph>=0.2.0",\n    "langchain-anthropic>=0.3.0"',
    "crewai": '"crewai>=0.80.0"',
    "autogen": '"ag2>=0.4.0"',
    "hybrid": '"langgraph>=0.2.0",\n    "langchain-anthropic>=0.3.0",\n    "anthropic>=0.40.0"',
}

TS_DEPENDENCIES = {
    "vercel": {
        "ai": "^4.0.0",
        "@ai-sdk/anthropic": "^1.0.0",
        "zod": "^3.23.0",
    },
    "openai": {
        "@openai/agents": "^0.1.0",
        "zod": "^3.23.0",
    },
}


def to_package_name(agent_name: str) -> str:
    """Convert kebab-case to snake_case."""
    return agent_name.replace("-", "_")


# --- Python generators ---

def gen_pyproject(agent_name: str, package_name: str, sdk: str) -> str:
    deps = DEPENDENCIES.get(sdk, '"claude-agent-sdk>=0.1.0"')
    return dedent(f'''\
[project]
name = "{agent_name}"
version = "0.1.0"
description = "AI agent built with {sdk}"
requires-python = ">=3.11"
dependencies = [
    {deps},
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.scripts]
{agent_name} = "{package_name}.agent:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{package_name}"]
''')


def gen_agent_py(agent_name: str, sdk: str) -> str:
    if sdk == "anthropic":
        return dedent(f'''\
"""Agent: {agent_name} — Built with Anthropic SDK."""

import asyncio
import os
from anthropic import Anthropic

assert os.environ.get("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY"

client = Anthropic()


async def run_agent(prompt: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8096,
        messages=[{{"role": "user", "content": prompt}}],
    )
    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text += block.text
            print(block.text, end="", flush=True)
    return result_text


async def main():
    result = await run_agent("Hello! What can you help with?")
    print(f"\\nResult: {{result}}")


if __name__ == "__main__":
    asyncio.run(main())
''')
    elif sdk == "openai":
        return dedent(f'''\
"""Agent: {agent_name} — Built with OpenAI Agents SDK."""

import asyncio
import os
from agents import Agent, Runner, function_tool, trace

assert os.environ.get("OPENAI_API_KEY"), "Set OPENAI_API_KEY"


@function_tool
def example_tool(query: str) -> dict:
    """Example tool — replace with your implementation."""
    return {{"result": "success", "data": query}}


agent = Agent(
    name="{agent_name}",
    instructions="You are a helpful assistant.",
    model="gpt-4o",
    tools=[example_tool],
)


async def run_agent(prompt: str) -> str:
    with trace("{agent_name}-execution"):
        result = await Runner.run(agent, prompt, max_turns=15)
        return result.final_output


async def main():
    result = await run_agent("Hello! What can you help with?")
    print(f"Result: {{result}}")


if __name__ == "__main__":
    asyncio.run(main())
''')
    elif sdk == "langgraph":
        return dedent(f'''\
"""Agent: {agent_name} — Built with LangGraph."""

import asyncio
import os
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

assert os.environ.get("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY"


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


@tool
def example_tool(query: str) -> str:
    """Example tool — replace with your implementation."""
    return f"Result for: {{query}}"


model = ChatAnthropic(model="claude-sonnet-4-5-20250929")
tools = [example_tool]
model_with_tools = model.bind_tools(tools)


def agent_node(state: AgentState) -> dict:
    response = model_with_tools.invoke(state["messages"])
    return {{"messages": [response]}}


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


graph = StateGraph(AgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(tools))
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, {{"tools": "tools", END: END}})
graph.add_edge("tools", "agent")

checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)


async def run_agent(prompt: str, thread_id: str = "default") -> str:
    config = {{"configurable": {{"thread_id": thread_id}}}}
    result = await app.ainvoke({{"messages": [("user", prompt)]}}, config=config)
    return result["messages"][-1].content


async def main():
    result = await run_agent("Hello! What can you help with?")
    print(f"Result: {{result}}")


if __name__ == "__main__":
    asyncio.run(main())
''')
    elif sdk == "crewai":
        return dedent(f'''\
"""Agent: {agent_name} — Built with CrewAI."""

import os
from crewai import Agent, Task, Crew, LLM
from crewai.tools import tool

assert os.environ.get("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY"

llm = LLM(model="anthropic/claude-sonnet-4-5-20250929")


@tool("ExampleTool")
def example_tool(query: str) -> str:
    """Example tool — replace with your implementation."""
    return f"Result for: {{query}}"


worker = Agent(
    role="Worker",
    goal="Complete assigned tasks effectively.",
    backstory="You are a skilled specialist.",
    tools=[example_tool],
    llm=llm,
    verbose=True,
    max_iter=15,
)

reviewer = Agent(
    role="Reviewer",
    goal="Review and improve work quality.",
    backstory="You are an expert reviewer.",
    tools=[],
    llm=llm,
    verbose=True,
)

task_work = Task(
    description="Complete the user's request.",
    expected_output="Detailed result.",
    agent=worker,
)

task_review = Task(
    description="Review the work for quality.",
    expected_output="Reviewed and improved result.",
    agent=reviewer,
    context=[task_work],
)

crew = Crew(
    agents=[worker, reviewer],
    tasks=[task_work, task_review],
    process="sequential",
    verbose=True,
    memory=True,
    max_rpm=10,
)


def run_crew(inputs: dict | None = None) -> str:
    result = crew.kickoff(inputs=inputs or {{}})
    return str(result)


if __name__ == "__main__":
    result = run_crew({{"topic": "AI agents"}})
    print(f"Result: {{result}}")
''')
    elif sdk == "autogen":
        return dedent(f'''\
"""Agent: {agent_name} — Built with AG2 (AutoGen)."""

import json
import os
from ag2 import ConversableAgent, GroupChat, GroupChatManager, register_function

assert os.environ.get("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY"

llm_config = {{
    "config_list": [{{
        "model": "claude-sonnet-4-5-20250929",
        "api_type": "anthropic",
        "api_key": os.environ["ANTHROPIC_API_KEY"],
    }}],
    "temperature": 0.7,
}}


def example_tool(query: str) -> str:
    """Example tool — replace with your implementation."""
    return json.dumps({{"result": "success", "data": query}})


user_proxy = ConversableAgent(
    name="User",
    human_input_mode="NEVER",
    code_execution_config={{"work_dir": "workspace", "use_docker": False, "timeout": 60}},
)

assistant = ConversableAgent(
    name="Assistant",
    system_message="You are a helpful assistant.",
    llm_config=llm_config,
)

register_function(example_tool, caller=assistant, executor=user_proxy, description="Example tool")

group_chat = GroupChat(agents=[assistant], messages=[], max_round=12, speaker_selection_method="auto")
manager = GroupChatManager(groupchat=group_chat, llm_config=llm_config)


def run_agents(prompt: str) -> str:
    result = user_proxy.initiate_chat(manager, message=prompt)
    return result.summary


if __name__ == "__main__":
    result = run_agents("Hello! What can you help with?")
    print(f"Result: {{result}}")
''')
    else:  # hybrid
        return dedent(f'''\
"""Agent: {agent_name} — Hybrid: LangGraph + Anthropic Agent SDK."""

import asyncio
import os
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from anthropic import Anthropic

assert os.environ.get("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY"

subagent_client = Anthropic()


class State(TypedDict):
    messages: Annotated[list, add_messages]
    task: str
    subtask_results: dict
    current_phase: str


async def run_subagent(prompt: str) -> str:
    response = subagent_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[{{"role": "user", "content": prompt}}],
    )
    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text += block.text
    return result_text


model = ChatAnthropic(model="claude-sonnet-4-5-20250929")


def plan_node(state: State) -> dict:
    response = model.invoke([
        ("system", "Break this task into 2-3 subtasks. Return JSON: {{\\"subtasks\\": [...]}}"),
        ("user", state["task"]),
    ])
    return {{"messages": [response], "current_phase": "execute"}}


async def execute_node(state: State) -> dict:
    import json
    try:
        parsed = json.loads(state["messages"][-1].content)
        subtasks = parsed.get("subtasks", [state["messages"][-1].content])
    except json.JSONDecodeError:
        subtasks = [state["messages"][-1].content]

    results = await asyncio.gather(
        *[run_subagent(st) for st in subtasks], return_exceptions=True
    )
    subtask_results = {{
        f"subtask_{{i}}": str(r) for i, r in enumerate(results)
    }}
    return {{"subtask_results": subtask_results, "current_phase": "synthesize"}}


def synthesize_node(state: State) -> dict:
    summary = "\\n".join(f"{{k}}: {{v}}" for k, v in state["subtask_results"].items())
    response = model.invoke([
        ("system", "Synthesize subtask results into a final response."),
        ("user", f"Task: {{state['task']}}\\n\\nResults:\\n{{summary}}"),
    ])
    return {{"messages": [response], "current_phase": "done"}}


def route(state: State) -> str:
    phase = state.get("current_phase", "plan")
    return {{"execute": "execute", "synthesize": "synthesize"}}.get(phase, END)


graph = StateGraph(State)
graph.add_node("plan", plan_node)
graph.add_node("execute", execute_node)
graph.add_node("synthesize", synthesize_node)
graph.add_edge(START, "plan")
graph.add_conditional_edges("plan", route, {{"execute": "execute", END: END}})
graph.add_conditional_edges("execute", route, {{"synthesize": "synthesize", END: END}})
graph.add_edge("synthesize", END)

app = graph.compile(checkpointer=MemorySaver())


async def run_agent(task: str, thread_id: str = "default") -> str:
    config = {{"configurable": {{"thread_id": thread_id}}}}
    result = await app.ainvoke(
        {{"task": task, "messages": [], "subtask_results": {{}}, "current_phase": "plan"}},
        config=config,
    )
    return result["messages"][-1].content


async def main():
    result = await run_agent("Hello! What can you help with?")
    print(f"Result: {{result}}")


if __name__ == "__main__":
    asyncio.run(main())
''')


# --- TypeScript generators ---

def gen_package_json(agent_name: str, sdk: str) -> str:
    deps = TS_DEPENDENCIES.get(sdk, TS_DEPENDENCIES["vercel"])
    deps_str = ",\n    ".join(f'"{k}": "{v}"' for k, v in deps.items())
    return dedent(f'''\
{{
  "name": "{agent_name}",
  "version": "0.1.0",
  "description": "AI agent built with {sdk}",
  "type": "module",
  "main": "dist/agent.js",
  "scripts": {{
    "build": "tsc",
    "start": "tsx src/agent.ts",
    "dev": "tsx watch src/agent.ts",
    "test": "vitest run"
  }},
  "dependencies": {{
    {deps_str}
  }},
  "devDependencies": {{
    "typescript": "^5.6.0",
    "tsx": "^4.19.0",
    "vitest": "^2.1.0",
    "@types/node": "^22.0.0"
  }}
}}
''')


def gen_tsconfig() -> str:
    return dedent('''\
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "outDir": "dist",
    "rootDir": "src",
    "declaration": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*"]
}
''')


def gen_agent_ts(agent_name: str, sdk: str) -> str:
    if sdk == "vercel":
        return dedent(f'''\
/**
 * Agent: {agent_name} — Built with Vercel AI SDK.
 */

import {{ generateText, tool }} from "ai";
import {{ anthropic }} from "@ai-sdk/anthropic";
import {{ z }} from "zod";

if (!process.env.ANTHROPIC_API_KEY) {{
  throw new Error("Set ANTHROPIC_API_KEY environment variable");
}}

const exampleTool = tool({{
  description: "Example tool — replace with your implementation",
  parameters: z.object({{
    query: z.string().describe("The input query"),
  }}),
  execute: async ({{ query }}) => {{
    return {{ result: "success", data: query }};
  }},
}});

export async function runAgent(prompt: string): Promise<string> {{
  const {{ text, steps }} = await generateText({{
    model: anthropic("claude-sonnet-4-5-20250929"),
    system: "You are a helpful assistant.",
    tools: {{ example: exampleTool }},
    maxSteps: 10,
    prompt,
  }});
  return text;
}}

async function main() {{
  const result = await runAgent("Hello! What can you help with?");
  console.log(`Result: ${{result}}`);
}}

main().catch(console.error);
''')
    else:  # openai ts
        return dedent(f'''\
/**
 * Agent: {agent_name} — Built with OpenAI Agents SDK (TypeScript).
 */

import {{ Agent, Runner }} from "@openai/agents";
import {{ z }} from "zod";

if (!process.env.OPENAI_API_KEY) {{
  throw new Error("Set OPENAI_API_KEY environment variable");
}}

const exampleTool = {{
  name: "example_tool",
  description: "Example tool — replace with your implementation",
  parameters: z.object({{
    query: z.string().describe("The input query"),
  }}),
  execute: async ({{ query }}: {{ query: string }}) => {{
    return JSON.stringify({{ result: "success", data: query }});
  }},
}};

const agent = new Agent({{
  name: "{agent_name}",
  instructions: "You are a helpful assistant.",
  model: "gpt-4o",
  tools: [exampleTool],
}});

export async function runAgent(prompt: string): Promise<string> {{
  const result = await Runner.run(agent, prompt, {{ maxTurns: 15 }});
  return result.finalOutput;
}}

async function main() {{
  const result = await runAgent("Hello! What can you help with?");
  console.log(`Result: ${{result}}`);
}}

main().catch(console.error);
''')


def gen_gitignore(lang: str) -> str:
    lines = [
        "# Environment",
        ".env",
        ".env.*",
        "!.env.example",
        "",
        "# Python",
        "__pycache__/",
        "*.pyc",
        ".venv/",
        "venv/",
        "dist/",
        "*.egg-info/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        "",
    ]
    if lang == "typescript":
        lines.extend([
            "# Node",
            "node_modules/",
            "dist/",
            "*.js",
            "*.d.ts",
            "*.js.map",
            "!vitest.config.ts",
            "",
        ])
    lines.extend([
        "# IDE",
        ".vscode/",
        ".idea/",
        "*.swp",
        ".DS_Store",
    ])
    return "\n".join(lines) + "\n"


def gen_env_example(sdk: str) -> str:
    lines = ["# Required environment variables"]
    if sdk in ("anthropic", "langgraph", "crewai", "hybrid"):
        lines.append("ANTHROPIC_API_KEY=your-api-key-here")
    if sdk in ("openai",):
        lines.append("OPENAI_API_KEY=your-api-key-here")
    if sdk == "autogen":
        lines.append("ANTHROPIC_API_KEY=your-api-key-here")
        lines.append("# OPENAI_API_KEY=your-api-key-here  # optional fallback")
    if sdk == "vercel":
        lines.append("ANTHROPIC_API_KEY=your-api-key-here")
    lines.append("")
    lines.append("# Optional")
    lines.append("LOG_LEVEL=info")
    return "\n".join(lines) + "\n"


def gen_test_py(package_name: str) -> str:
    return dedent(f'''\
"""Tests for {package_name} agent."""

import pytest


@pytest.mark.asyncio
async def test_placeholder():
    """Replace with actual agent tests."""
    # from {package_name}.agent import run_agent
    # result = await run_agent("test prompt")
    # assert result is not None
    assert True
''')


def gen_test_ts(agent_name: str) -> str:
    return dedent(f'''\
/**
 * Tests for {agent_name} agent.
 */

import {{ describe, it, expect }} from "vitest";

describe("{agent_name}", () => {{
  it("placeholder test", () => {{
    // import {{ runAgent }} from "../src/agent";
    // const result = await runAgent("test prompt");
    // expect(result).toBeDefined();
    expect(true).toBe(true);
  }});
}});
''')


# --- Scaffolder ---

def scaffold(agent_name: str, sdk: str, output_dir: str, lang: str | None = None):
    """Create the full agent project structure."""
    resolved_lang = lang or LANG_MAP.get(sdk, "python")
    package_name = to_package_name(agent_name)
    output_path = Path(output_dir).resolve()

    if not output_path.exists():
        print(f"Error: Parent directory does not exist: {output_path}")
        return None

    project_dir = output_path / agent_name

    if project_dir.exists():
        print(f"Error: Directory already exists: {project_dir}")
        return None

    if resolved_lang == "typescript":
        # TypeScript project
        src_dir = project_dir / "src"
        src_dir.mkdir(parents=True)
        (project_dir / "src" / "tools").mkdir()
        (project_dir / "src" / "prompts").mkdir()
        (project_dir / "tests").mkdir()

        (src_dir / "agent.ts").write_text(gen_agent_ts(agent_name, sdk))
        (src_dir / "config.ts").write_text(
            f'// Configuration for {agent_name}\n'
            f'export const MAX_STEPS = 10;\n'
        )
        (project_dir / "package.json").write_text(gen_package_json(agent_name, sdk))
        (project_dir / "tsconfig.json").write_text(gen_tsconfig())
        (project_dir / "tests" / "agent.test.ts").write_text(gen_test_ts(agent_name))
    else:
        # Python project
        src_dir = project_dir / "src" / package_name
        src_dir.mkdir(parents=True)
        (src_dir / "tools").mkdir()
        (src_dir / "tools" / "__init__.py").write_text("")
        (src_dir / "prompts").mkdir()
        (project_dir / "tests").mkdir()

        (src_dir / "__init__.py").write_text(f'"""Agent: {agent_name}."""\n')
        (src_dir / "agent.py").write_text(gen_agent_py(agent_name, sdk))
        (src_dir / "config.py").write_text(
            f'"""Configuration for {agent_name}."""\n\nimport os\n\n'
            f'MAX_TURNS = int(os.environ.get("MAX_TURNS", "15"))\n'
        )
        (project_dir / "pyproject.toml").write_text(gen_pyproject(agent_name, package_name, sdk))
        (project_dir / "tests" / "__init__.py").write_text("")
        (project_dir / "tests" / "test_agent.py").write_text(gen_test_py(package_name))

    # Common files
    (project_dir / ".env.example").write_text(gen_env_example(sdk))
    (project_dir / ".gitignore").write_text(gen_gitignore(resolved_lang))

    print(f"Created agent project: {project_dir}")
    print(f"  SDK: {sdk}")
    print(f"  Language: {resolved_lang}")
    print(f"  Package: {package_name}")
    print(f"\nNext steps:")
    if resolved_lang == "typescript":
        print(f"  cd {project_dir}")
        print(f"  npm install")
        print(f"  cp .env.example .env  # add your API key")
        print(f"  npm run start")
    else:
        print(f"  cd {project_dir}")
        print(f"  uv sync")
        print(f"  cp .env.example .env  # add your API key")
        print(f"  uv run {agent_name}")

    return project_dir


def main():
    if len(sys.argv) < 5 or "--sdk" not in sys.argv or "--path" not in sys.argv:
        print(__doc__)
        sys.exit(1)

    agent_name = sys.argv[1]
    sdk_idx = sys.argv.index("--sdk") + 1
    sdk = sys.argv[sdk_idx]
    path_idx = sys.argv.index("--path") + 1
    output_dir = sys.argv[path_idx]

    if sdk not in SDK_CHOICES:
        print(f"Error: SDK must be one of: {', '.join(SDK_CHOICES)}")
        sys.exit(1)

    lang = None
    if "--lang" in sys.argv:
        lang = sys.argv[sys.argv.index("--lang") + 1]

    scaffold(agent_name, sdk, output_dir, lang)


if __name__ == "__main__":
    main()
