"""{{AGENT_NAME}} — Built with CrewAI.

{{AGENT_DESCRIPTION}}
"""

import os
from crewai import Agent, Task, Crew, LLM
from crewai.tools import tool

# Ensure API key is set
assert os.environ.get("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY environment variable"


# --- Tools ---

@tool("{{TOOL_DISPLAY_NAME}}")
def {{TOOL_NAME}}({{TOOL_PARAMS}}) -> str:
    """{{TOOL_DESCRIPTION}}"""
    try:
        # Implementation here
        return "Result"
    except Exception as e:
        return f"Error: {e}"


# --- Agents ---

{{AGENT_VAR_1}} = Agent(
    role="{{AGENT_ROLE_1}}",
    goal="{{AGENT_GOAL_1}}",
    backstory="{{AGENT_BACKSTORY_1}}",
    tools=[{{AGENT_TOOLS_1}}],
    llm=LLM(model="anthropic/claude-sonnet-4-5-20250929"),
    verbose=True,
    allow_delegation={{ALLOW_DELEGATION}},
    max_iter=15
)

{{AGENT_VAR_2}} = Agent(
    role="{{AGENT_ROLE_2}}",
    goal="{{AGENT_GOAL_2}}",
    backstory="{{AGENT_BACKSTORY_2}}",
    tools=[],
    llm=LLM(model="anthropic/claude-sonnet-4-5-20250929"),
    verbose=True
)


# --- Tasks ---

{{TASK_VAR_1}} = Task(
    description="{{TASK_DESCRIPTION_1}}",
    expected_output="{{TASK_EXPECTED_OUTPUT_1}}",
    agent={{AGENT_VAR_1}},
    output_file="{{TASK_OUTPUT_FILE_1}}"
)

{{TASK_VAR_2}} = Task(
    description="{{TASK_DESCRIPTION_2}}",
    expected_output="{{TASK_EXPECTED_OUTPUT_2}}",
    agent={{AGENT_VAR_2}},
    context=[{{TASK_VAR_1}}]  # Depends on first task output
)


# --- Crew ---

crew = Crew(
    agents=[{{AGENT_VAR_1}}, {{AGENT_VAR_2}}],
    tasks=[{{TASK_VAR_1}}, {{TASK_VAR_2}}],
    process="{{PROCESS_TYPE}}",  # "sequential" or "hierarchical"
    verbose=True,
    memory=True,
    max_rpm=10
)


def run_crew(inputs: dict | None = None) -> str:
    """Execute the crew with optional inputs."""
    result = crew.kickoff(inputs=inputs or {})
    return str(result)


if __name__ == "__main__":
    result = run_crew({"topic": "{{DEFAULT_TOPIC}}"})
    print(f"Result: {result}")
