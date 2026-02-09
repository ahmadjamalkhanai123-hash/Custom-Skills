# AutoGen / AG2 / Microsoft Agent Framework

Complete patterns for building agents with AutoGen ecosystem.

---

## Landscape (2026)

The AutoGen ecosystem has split into two paths:

| Path | Description | Best For |
|------|-------------|----------|
| **AG2** | Community-driven fork of AutoGen 0.2, maintained by original creators | Stable, backward-compatible multi-agent systems |
| **Microsoft Agent Framework** | Merger of AutoGen 0.4 + Semantic Kernel, actor-model based | Enterprise Azure integration, .NET/Python/Java |

---

## AG2 (Community AutoGen)

**Install:**
```bash
pip install ag2  # or: pip install pyautogen (legacy)
```

### Basic Conversable Agent

```python
from autogen import ConversableAgent

assistant = ConversableAgent(
    name="Assistant",
    system_message="You are a helpful AI assistant.",
    llm_config={
        "config_list": [
            {"model": "claude-sonnet-4-5-20250929", "api_type": "anthropic", "api_key": "..."},
            {"model": "gpt-4o", "api_key": "..."}  # Fallback
        ],
        "temperature": 0.7
    }
)

user_proxy = ConversableAgent(
    name="User",
    human_input_mode="NEVER",  # "ALWAYS", "TERMINATE", "NEVER"
    code_execution_config={"work_dir": "workspace", "use_docker": True}
)

# Two-agent conversation
user_proxy.initiate_chat(
    assistant,
    message="Write a Python function to calculate fibonacci numbers"
)
```

### Group Chat (Multi-Agent)

```python
from autogen import GroupChat, GroupChatManager

researcher = ConversableAgent(name="Researcher", system_message="Research topics deeply.")
writer = ConversableAgent(name="Writer", system_message="Write clear, engaging content.")
critic = ConversableAgent(name="Critic", system_message="Review and improve content quality.")

group_chat = GroupChat(
    agents=[researcher, writer, critic],
    messages=[],
    max_round=12,
    speaker_selection_method="auto"  # or "round_robin", "random", custom function
)

manager = GroupChatManager(
    groupchat=group_chat,
    llm_config=llm_config
)

user_proxy.initiate_chat(
    manager,
    message="Create a comprehensive guide to AI agents"
)
```

### Custom Speaker Selection

```python
def custom_speaker(last_speaker, group_chat):
    """Route based on conversation state."""
    messages = group_chat.messages
    if len(messages) < 3:
        return researcher
    if "RESEARCH COMPLETE" in messages[-1]["content"]:
        return writer
    if "DRAFT COMPLETE" in messages[-1]["content"]:
        return critic
    return None  # Let LLM decide

group_chat = GroupChat(
    agents=[researcher, writer, critic],
    speaker_selection_method=custom_speaker
)
```

### Tool Registration

```python
from autogen import register_function

def search_database(query: str) -> str:
    """Search the database for relevant records."""
    return json.dumps({"results": [...]})

# Register tool for an agent
register_function(
    search_database,
    caller=assistant,
    executor=user_proxy,
    description="Search the database for records matching a query."
)
```

### Nested Conversations

```python
# Agent can spawn sub-conversations
assistant.register_nested_chats(
    [
        {
            "recipient": specialist_agent,
            "message": "Analyze this data in detail",
            "max_turns": 5
        }
    ],
    trigger=lambda sender, message, *args, **kwargs:
        "need specialist" in message.get("content", "").lower()
)
```

---

## Microsoft Agent Framework (AutoGen 0.4 + Semantic Kernel)

**Architecture**: Layered design based on actor model for distributed, event-driven systems.

### Layers

| Layer | Purpose |
|-------|---------|
| **Core** | Actor model, message passing, event-driven runtime |
| **AgentChat** | High-level multi-agent conversation APIs |
| **Extensions** | Azure integration, Semantic Kernel skills, connectors |

### Key Concepts

```python
# AutoGen 0.4 style (Microsoft Agent Framework)
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

model = OpenAIChatCompletionClient(model="gpt-4o")

agent1 = AssistantAgent("analyzer", model_client=model)
agent2 = AssistantAgent("writer", model_client=model)

team = RoundRobinGroupChat(
    participants=[agent1, agent2],
    max_turns=6
)

result = await team.run(task="Analyze and summarize this data")
```

### Semantic Kernel Integration

```csharp
// C# — Semantic Kernel + AutoGen
var kernel = Kernel.CreateBuilder()
    .AddAzureOpenAIChatCompletion("gpt-4o", endpoint, apiKey)
    .Build();

var agent = new ChatCompletionAgent
{
    Name = "Analyst",
    Instructions = "Analyze data and provide insights.",
    Kernel = kernel
};
```

---

## Code Execution

AG2 agents can write and execute code:

```python
user_proxy = ConversableAgent(
    name="Executor",
    code_execution_config={
        "work_dir": "workspace",
        "use_docker": True,      # Sandboxed execution
        "timeout": 60,
        "last_n_messages": 3     # Only execute recent code blocks
    }
)
```

---

## Best Practices

- Use `human_input_mode="TERMINATE"` for production (auto-stops at termination keywords)
- Use Docker for code execution (`use_docker=True`) in production
- Set `max_round` on GroupChat to prevent infinite conversations
- Use config lists with fallback models for reliability
- Use nested chats for complex sub-tasks instead of one large group
- Register tools with specific caller/executor pairs
- Use `speaker_selection_method` function for deterministic routing
- For enterprise: evaluate Microsoft Agent Framework for Azure/C# integration
- For community/stability: use AG2 for proven AutoGen 0.2 patterns
