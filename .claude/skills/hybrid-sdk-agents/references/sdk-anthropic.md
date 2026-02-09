# Anthropic Agent SDK

Complete patterns for building agents with the Claude Agent SDK.

---

## Overview

The Claude Agent SDK gives you the same tools, agent loop, and context management that power Claude Code — programmable in Python and TypeScript. It provides built-in tools (Read, Edit, Bash, Glob, Grep, WebSearch, WebFetch) so agents work immediately without implementing tool execution.

**Install:**
```bash
pip install claude-agent-sdk        # Python
npm install @anthropic-ai/claude-agent-sdk  # TypeScript
```

**Auth:** Set `ANTHROPIC_API_KEY` env var. Also supports Bedrock (`CLAUDE_CODE_USE_BEDROCK=1`), Vertex AI (`CLAUDE_CODE_USE_VERTEX=1`), and Azure (`CLAUDE_CODE_USE_FOUNDRY=1`).

---

## Core API: query()

The `query()` function is the primary interface — streams messages as the agent works.

### Basic Agent (Python)

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    async for message in query(
        prompt="Find and fix the bug in auth.py",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep"]
        )
    ):
        if hasattr(message, "result"):
            print(message.result)

asyncio.run(main())
```

### Basic Agent (TypeScript)

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Find and fix the bug in auth.py",
  options: { allowedTools: ["Read", "Edit", "Bash", "Glob", "Grep"] }
})) {
  if ("result" in message) console.log(message.result);
}
```

---

## Built-in Tools

| Tool | Purpose | When to Allow |
|------|---------|---------------|
| **Read** | Read any file | Analysis, review tasks |
| **Write** | Create new files | Scaffolding, generation |
| **Edit** | Precise file edits | Bug fixes, refactoring |
| **Bash** | Run terminal commands | Testing, git, builds |
| **Glob** | Find files by pattern | Codebase exploration |
| **Grep** | Search file contents | Pattern finding |
| **WebSearch** | Search the web | Research tasks |
| **WebFetch** | Fetch web pages | Documentation lookup |
| **Task** | Spawn subagents | Complex multi-step work |
| **AskUserQuestion** | Get user clarification | Ambiguous requirements |

---

## Subagents (Multi-Agent)

Define specialized agents for delegation:

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

async def main():
    async for message in query(
        prompt="Review this codebase for security issues",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep", "Task"],
            agents={
                "security-reviewer": AgentDefinition(
                    description="Expert security code reviewer.",
                    prompt="Analyze code for OWASP top 10 vulnerabilities.",
                    tools=["Read", "Glob", "Grep"]
                ),
                "dependency-checker": AgentDefinition(
                    description="Checks dependencies for known CVEs.",
                    prompt="Scan package files for vulnerable dependencies.",
                    tools=["Read", "Bash"]
                )
            }
        )
    ):
        if hasattr(message, "result"):
            print(message.result)
```

Subagent messages include `parent_tool_use_id` for tracking.

---

## Hooks (Lifecycle Callbacks)

Run custom code at key points in agent execution:

```python
from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher

async def audit_file_changes(input_data, tool_use_id, context):
    file_path = input_data.get('tool_input', {}).get('file_path', 'unknown')
    with open('./audit.log', 'a') as f:
        f.write(f"Modified: {file_path}\n")
    return {}

async def block_dangerous_commands(input_data, tool_use_id, context):
    command = input_data.get('tool_input', {}).get('command', '')
    if any(danger in command for danger in ['rm -rf', 'drop table', 'format']):
        return {"decision": "block", "reason": "Dangerous command blocked"}
    return {}

options = ClaudeAgentOptions(
    permission_mode="acceptEdits",
    hooks={
        "PostToolUse": [HookMatcher(matcher="Edit|Write", hooks=[audit_file_changes])],
        "PreToolUse": [HookMatcher(matcher="Bash", hooks=[block_dangerous_commands])]
    }
)
```

**Available hooks:** `PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`.

---

## MCP Integration

Connect any MCP server to give agents external capabilities:

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "postgres": {
            "command": "uv",
            "args": ["run", "postgres-mcp-server"],
            "env": {"DATABASE_URL": "postgresql://..."}
        },
        "playwright": {
            "command": "npx",
            "args": ["@playwright/mcp@latest"]
        }
    }
)
```

---

## Sessions (Stateful Agents)

Maintain context across multiple interactions:

```python
session_id = None

# First interaction
async for message in query(
    prompt="Read the authentication module",
    options=ClaudeAgentOptions(allowed_tools=["Read", "Glob"])
):
    if hasattr(message, 'subtype') and message.subtype == 'init':
        session_id = message.session_id

# Resume with full context
async for message in query(
    prompt="Now find all callers",
    options=ClaudeAgentOptions(resume=session_id)
):
    if hasattr(message, "result"):
        print(message.result)
```

---

## Permission Modes

| Mode | Behavior |
|------|----------|
| `bypassPermissions` | All allowed tools run without prompting |
| `acceptEdits` | Read-only tools auto-approved, edits need approval |
| `default` | All tool uses require approval |

---

## Skills & Memory

Enable Claude Code's filesystem-based config:

```python
options = ClaudeAgentOptions(
    setting_sources=["project"],  # Loads CLAUDE.md, skills, commands
    allowed_tools=["Read", "Edit", "Bash"]
)
```

Loads: `.claude/skills/SKILL.md`, `.claude/commands/*.md`, `CLAUDE.md`.

---

## Best Practices

- Start with minimal `allowed_tools`, expand as needed
- Use `permission_mode="acceptEdits"` for safety with file modifications
- Use subagents for parallel independent tasks
- Use hooks for audit logging and guardrails
- Set `max_turns` to prevent infinite loops
- Use sessions for multi-turn conversations with context
- Connect MCP servers for external integrations instead of custom Bash scripts
