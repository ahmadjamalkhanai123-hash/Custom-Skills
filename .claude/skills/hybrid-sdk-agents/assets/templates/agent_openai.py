"""{{AGENT_NAME}} — Built with OpenAI Agents SDK.

{{AGENT_DESCRIPTION}}
"""

import asyncio
import os
from agents import Agent, Runner, function_tool, handoff, trace
from agents import InputGuardrail, GuardrailFunctionOutput

# Ensure API key is set
assert os.environ.get("OPENAI_API_KEY"), "Set OPENAI_API_KEY environment variable"


# --- Tools ---

@function_tool
def {{TOOL_NAME}}({{TOOL_PARAMS}}) -> dict:
    """{{TOOL_DESCRIPTION}}"""
    try:
        # Implementation here
        return {"result": "success", "data": {}}
    except Exception as e:
        return {"error": str(e), "retryable": False}


# --- Guardrails ---

class ContentFilter(InputGuardrail):
    async def run(self, input, context) -> GuardrailFunctionOutput:
        # Validate input before agent processes it
        return GuardrailFunctionOutput(output_info={"status": "clean"})


# --- Agents ---

{{SPECIALIST_AGENT}} = Agent(
    name="{{SPECIALIST_NAME}}",
    instructions="{{SPECIALIST_INSTRUCTIONS}}",
    tools=[{{SPECIALIST_TOOLS}}],
)

main_agent = Agent(
    name="{{AGENT_NAME}}",
    instructions="{{AGENT_INSTRUCTIONS}}",
    model="gpt-4o",
    tools=[{{TOOL_NAME}}],
    handoffs=[{{SPECIALIST_AGENT}}],
    guardrails=[ContentFilter()],
)


async def run_agent(prompt: str) -> str:
    """Run the agent with tracing."""
    with trace("{{AGENT_NAME_LOWER}}-execution"):
        result = await Runner.run(main_agent, prompt, max_turns=15)
        return result.final_output


async def main():
    result = await run_agent("{{DEFAULT_PROMPT}}")
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
