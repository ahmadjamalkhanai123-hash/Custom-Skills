"""{{AGENT_NAME}} — Built with Anthropic SDK.

{{AGENT_DESCRIPTION}}
"""

import asyncio
import os
from anthropic import Anthropic

# Ensure API key is set
assert os.environ.get("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY environment variable"

client = Anthropic()


async def run_agent(prompt: str) -> str:
    """Run the agent with the given prompt."""
    messages = [{"role": "user", "content": prompt}]

    response = client.messages.create(
        model="{{MODEL}}",
        max_tokens=8096,
        system="{{SYSTEM_PROMPT}}",
        messages=messages,
        # tools={{TOOLS}},  # Uncomment and define tools for agentic behavior
    )

    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text += block.text
            print(block.text, end="", flush=True)

    return result_text


async def main():
    result = await run_agent("{{DEFAULT_PROMPT}}")
    print(f"\nResult: {result}")


if __name__ == "__main__":
    asyncio.run(main())
