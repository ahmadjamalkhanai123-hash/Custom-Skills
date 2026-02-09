# Agent Anti-Patterns

Common mistakes across all SDKs with fixes.

---

## Architecture Anti-Patterns

### 1. God Agent

```
BAD: One agent handles everything
Agent(tools=[search, write, deploy, email, db_query, file_ops, ...])
→ Overwhelmed context, poor tool selection, confused behavior

GOOD: Specialized agents with clear boundaries
router → [search_agent, writing_agent, deploy_agent, db_agent]
→ Each agent focused, better tool selection, predictable behavior
```

### 2. Wrong SDK for the Job

| Mistake | Problem | Fix |
|---------|---------|-----|
| LangGraph for simple Q&A | Over-engineered graph for one node | Use OpenAI/Anthropic directly |
| CrewAI for single agent | Role-based framework with no team | Use single SDK agent |
| AG2 GroupChat for 2 agents | Complex orchestration for simple delegation | Use OpenAI handoffs |
| Vercel AI SDK for backend-only | Full-stack SDK without frontend | Use Python SDK |

### 3. Premature Multi-Agent

```
BAD: Starting with 5 agents for a simple task
→ Complex, hard to debug, higher cost, more latency

GOOD: Start with one agent, split ONLY when needed
→ Simple, debuggable, cheaper, faster
→ Split when: one agent's context window overflows,
   or distinct responsibilities emerge
```

---

## Implementation Anti-Patterns

### 4. Unbounded Loops

```python
# BAD: No loop limit — can run forever
result = await Runner.run(agent, prompt)  # No max_steps!

# GOOD: Always set limits
# OpenAI
result = await Runner.run(agent, prompt, max_turns=15)
# Vercel
generateText({ tools, maxSteps: 20 })
# LangGraph
app.invoke(input, {"recursion_limit": 25})
# CrewAI
Agent(max_iter=15)
# AG2
GroupChat(max_round=12)
```

### 5. Hardcoded Secrets

```python
# BAD: API key in source code
agent = Agent(api_key="sk-abc123...")

# GOOD: Environment variables
import os
api_key = os.environ["OPENAI_API_KEY"]
```

### 6. Synchronous Blocking in Async

```python
# BAD: Blocks event loop
@tool
async def slow_tool(query: str) -> str:
    import time
    time.sleep(5)  # Blocks ALL other agents!
    result = requests.get(url)  # Synchronous HTTP!
    return result.text

# GOOD: Async I/O
@tool
async def fast_tool(query: str) -> str:
    import asyncio
    await asyncio.sleep(5)  # Non-blocking
    async with httpx.AsyncClient() as client:
        result = await client.get(url)
    return result.text
```

### 7. No Error Handling in Tools

```python
# BAD: Exception crashes agent
@function_tool
def query_db(sql: str) -> str:
    return db.execute(sql)  # Any error kills the agent

# GOOD: Structured error handling
@function_tool
def query_db(sql: str) -> dict:
    try:
        result = db.execute(sql)
        return {"data": result, "status": "success"}
    except SyntaxError as e:
        return {"error": f"SQL syntax error: {e}", "status": "failed"}
    except ConnectionError:
        return {"error": "Database connection failed", "status": "failed", "retryable": True}
    except Exception as e:
        logger.error(f"Unexpected DB error: {e}")
        return {"error": "Query failed", "status": "failed"}
```

### 8. Mega-Tools (Too Many Parameters)

```python
# BAD: Tool with 12 parameters — LLM gets confused
@function_tool
def create_report(title, subtitle, author, date, format, template,
                  sections, charts, footer, header, watermark, style) -> dict:
    ...

# GOOD: Focused tools or Pydantic model
from pydantic import BaseModel

class ReportConfig(BaseModel):
    title: str
    author: str
    format: str = "pdf"

@function_tool
def create_report(config: ReportConfig) -> dict:
    ...
```

---

## Context & Token Anti-Patterns

### 9. Sending Full History Always

```python
# BAD: Every agent call includes entire conversation
# → Costs grow linearly, eventually hits context limit

# GOOD: Summarize or truncate history
def prepare_context(messages, max_tokens=4000):
    """Keep recent messages, summarize old ones."""
    if total_tokens(messages) > max_tokens:
        summary = summarize(messages[:-5])
        return [{"role": "system", "content": summary}] + messages[-5:]
    return messages
```

### 10. Verbose Tool Descriptions

```python
# BAD: 200+ token tool description
@function_tool
def search(query: str) -> str:
    """This tool allows you to search through all available documents
    in the database. It supports full-text search with various filters
    including date ranges, categories, and relevance scoring. Results
    are returned sorted by relevance with metadata including title,
    author, date, and a snippet of the matching content..."""

# GOOD: Concise description (<50 tokens)
@function_tool
def search(query: str, limit: int = 10) -> str:
    """Search documents by keyword. Returns matches sorted by relevance."""
```

---

## Production Anti-Patterns

### 11. No Rate Limiting

```python
# BAD: Unlimited API calls
async def handle_request(prompt):
    return await agent.run(prompt)  # No throttling!

# GOOD: Rate limit per user
from agent_utils import rate_limiter

@rate_limiter(max_per_minute=10)
async def handle_request(prompt):
    return await agent.run(prompt)
```

### 12. No Guardrails

```python
# BAD: Agent runs unsanitized user input
result = await agent.run(user_input)

# GOOD: Validate input, validate output
validated_input = validate_and_sanitize(user_input)
result = await agent.run(validated_input)
validated_output = validate_output(result)
```

### 13. print() for Logging

```python
# BAD: print() — not structured, lost in production
print(f"Agent called tool: {tool_name}")

# GOOD: Structured logging
import logging
logger = logging.getLogger("agent")
logger.info("Tool called", extra={"tool": tool_name, "agent": agent_name})
```

### 14. No Graceful Degradation

```python
# BAD: Agent fails completely on any error
result = await primary_agent.run(prompt)  # If LLM is down → crash

# GOOD: Fallback chain
try:
    result = await primary_agent.run(prompt)  # Claude
except Exception:
    try:
        result = await fallback_agent.run(prompt)  # GPT-4o
    except Exception:
        result = "I'm temporarily unable to help. Please try again."
```

---

## Security Anti-Patterns

### 15. Unrestricted Tool Access

```python
# BAD: Agent can execute any command
Agent(tools=["Bash"])  # Can rm -rf /, access secrets, etc.

# GOOD: Restricted, sandboxed tools
Agent(
    allowed_tools=["Read", "Glob", "Grep"],  # Read-only
    permission_mode="bypassPermissions"
)
```

### 16. Leaking Internal Data

```python
# BAD: Error exposes internals
except Exception as e:
    return str(e)  # May contain DB credentials, file paths, etc.

# GOOD: Sanitized errors
except Exception as e:
    logger.error(f"Internal error: {e}")
    return {"error": "Operation failed. Please try again."}
```
