"""{{AGENT_NAME}} — Built with AG2 (AutoGen).

{{AGENT_DESCRIPTION}}
"""

import json
import os
from ag2 import ConversableAgent, GroupChat, GroupChatManager, register_function

# Ensure API key is set
assert os.environ.get("ANTHROPIC_API_KEY"), "Set ANTHROPIC_API_KEY environment variable"

# --- LLM Config ---

llm_config = {
    "config_list": [
        {
            "model": "claude-sonnet-4-5-20250929",
            "api_type": "anthropic",
            "api_key": os.environ["ANTHROPIC_API_KEY"],
        }
    ],
    "temperature": 0.7,
}


# --- Tools ---

def {{TOOL_NAME}}({{TOOL_PARAMS}}) -> str:
    """{{TOOL_DESCRIPTION}}"""
    try:
        # Implementation here
        return json.dumps({"result": "success", "data": {{TOOL_PARAMS}}})
    except Exception as e:
        return json.dumps({"error": str(e), "status": "failed"})


# --- Agents ---

user_proxy = ConversableAgent(
    name="User",
    human_input_mode="NEVER",
    code_execution_config={
        "work_dir": "workspace",
        "use_docker": {{USE_DOCKER}},
        "timeout": 60,
    },
)

{{AGENT_VAR_1}} = ConversableAgent(
    name="{{AGENT_NAME_1}}",
    system_message="{{AGENT_SYSTEM_1}}",
    llm_config=llm_config,
)

{{AGENT_VAR_2}} = ConversableAgent(
    name="{{AGENT_NAME_2}}",
    system_message="{{AGENT_SYSTEM_2}}",
    llm_config=llm_config,
)


# --- Register Tools ---

register_function(
    {{TOOL_NAME}},
    caller={{AGENT_VAR_1}},
    executor=user_proxy,
    description="{{TOOL_DESCRIPTION}}",
)


# --- Group Chat ---

group_chat = GroupChat(
    agents=[{{AGENT_VAR_1}}, {{AGENT_VAR_2}}],
    messages=[],
    max_round={{MAX_ROUNDS}},
    speaker_selection_method="auto",
)

manager = GroupChatManager(groupchat=group_chat, llm_config=llm_config)


def run_agents(prompt: str) -> str:
    """Run the multi-agent group chat."""
    result = user_proxy.initiate_chat(manager, message=prompt)
    return result.summary


if __name__ == "__main__":
    result = run_agents("{{DEFAULT_PROMPT}}")
    print(f"Result: {result}")
