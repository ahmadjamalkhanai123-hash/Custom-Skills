# MCP Project Structure

Optimized folder layouts and packaging configuration for MCP servers.

---

## Standard Project Layout

### Full Server (5+ tools)

```
my-server/
├── src/
│   └── my_server/
│       ├── __init__.py          ← Package init, version
│       ├── server.py            ← FastMCP instance + decorator registration
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── queries.py       ← Query-related tools
│       │   └── mutations.py     ← Write-operation tools
│       ├── resources/
│       │   ├── __init__.py
│       │   └── data.py          ← Resource handlers
│       ├── prompts/
│       │   ├── __init__.py
│       │   └── templates.py     ← Prompt templates
│       └── utils/
│           ├── __init__.py
│           └── helpers.py       ← Shared utilities
├── scripts/
│   ├── run_stdio.py             ← `python scripts/run_stdio.py`
│   └── run_http.py              ← `python scripts/run_http.py`
├── tests/
│   ├── __init__.py
│   ├── test_tools.py
│   └── test_resources.py
├── pyproject.toml               ← Package config
├── .env.example                 ← Environment variable template
└── README.md                    ← Usage + client configuration
```

### Simple Server (1-3 tools)

```
my-server/
├── src/
│   └── my_server/
│       ├── __init__.py
│       └── server.py            ← Everything in one file
├── pyproject.toml
├── .env.example
└── README.md
```

### Decision Guide

| Tools Count | Structure |
|-------------|-----------|
| 1-3 | Single `server.py` |
| 4-7 | `server.py` + `tools/` directory |
| 8+ | Full structure with tools/, resources/, prompts/ subdirs |

---

## pyproject.toml Configuration

### Complete Template

```toml
[project]
name = "my-mcp-server"
version = "0.1.0"
description = "MCP server for [domain description]"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "Your Name", email = "you@example.com"}
]
dependencies = [
    "mcp[cli]>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.scripts]
my-mcp-server = "my_server.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_server"]
```

### Common Dependencies by Server Type

| Server Type | Additional Dependencies |
|-------------|------------------------|
| Database (PostgreSQL) | `asyncpg>=0.29` |
| Database (MongoDB) | `motor>=3.3` |
| Database (Redis) | `redis>=5.0` |
| REST API wrapper | `httpx>=0.27` |
| Filesystem | (none — stdlib only) |
| Web scraping | `httpx>=0.27`, `beautifulsoup4>=4.12` |
| Data processing | `pandas>=2.1`, `polars>=0.20` |
| AI/ML | `openai>=1.0`, `anthropic>=0.30` |

---

## Entry Points

### Standard Entry Point

```python
# src/my_server/server.py

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

# ... tool/resource/prompt decorators ...

def main():
    """Entry point for pyproject.toml script."""
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

### Dual Transport Entry Point

```python
# src/my_server/server.py

import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

# ... decorators ...

def main():
    """Entry point supporting both stdio and HTTP transport."""
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if transport == "http":
        mcp.run(transport="sse", host="0.0.0.0", port=8080)
    else:
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

---

## Environment Configuration

### .env.example Template

```bash
# Required
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
API_TOKEN=your-api-token-here

# Optional
LOG_LEVEL=info
MAX_RESULTS=50
CACHE_TTL=300
```

### Loading Environment Variables

```python
import os
from dotenv import load_dotenv

load_dotenv()  # Load .env file

DATABASE_URL = os.environ["DATABASE_URL"]  # Required — crashes if missing
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info")  # Optional with default
```

---

## Client Configuration

### Claude Desktop

```json
{
  "mcpServers": {
    "my-server": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/my-server", "my-mcp-server"],
      "env": {
        "DATABASE_URL": "postgresql://..."
      }
    }
  }
}
```

### Claude Code

```json
{
  "mcpServers": {
    "my-server": {
      "command": "uv",
      "args": ["run", "my-mcp-server"],
      "cwd": "/path/to/my-server"
    }
  }
}
```

### Cursor IDE

```json
{
  "mcpServers": {
    "my-server": {
      "command": "uv",
      "args": ["run", "my-mcp-server"],
      "env": {}
    }
  }
}
```

---

## Testing Setup

### Test File Structure

```python
# tests/test_tools.py

import pytest
import pytest_asyncio
from my_server.server import mcp

@pytest.mark.asyncio
async def test_tool_basic():
    """Test tool returns expected structure."""
    # Direct function call (bypasses MCP protocol)
    result = await your_tool_function("test_input")
    assert "error" not in result
    assert "data" in result

@pytest.mark.asyncio
async def test_tool_error_handling():
    """Test tool handles invalid input gracefully."""
    result = await your_tool_function("")
    assert "error" in result
```

### MCP Inspector Testing

```bash
# Install MCP Inspector
npx @modelcontextprotocol/inspector

# Test stdio server
npx @modelcontextprotocol/inspector uv run my-mcp-server

# Test HTTP server
npx @modelcontextprotocol/inspector http://localhost:8080
```

### Testing Checklist

- [ ] Each tool tested with valid input
- [ ] Each tool tested with invalid/edge input
- [ ] Error responses verified (structured, not crashes)
- [ ] MCP Inspector shows all tools discovered
- [ ] Resources accessible via MCP Inspector
- [ ] Prompts render correctly with arguments

---

## Context Optimization Tips

### Why Structure Matters for Context

When Claude loads an MCP server's tools, it sees ALL tool descriptions in its context window. Optimization reduces token usage:

### Tip 1: Concise Tool Descriptions

```python
# BAD: 80+ tokens
@mcp.tool()
async def search(query: str) -> dict:
    """This tool allows you to search through all available documents
    in the database. It supports full-text search with various filters
    and returns a list of matching documents sorted by relevance score."""

# GOOD: 20 tokens
@mcp.tool()
async def search(query: str, limit: int = 10) -> dict:
    """Search documents by keyword. Returns matches sorted by relevance."""
```

### Tip 2: Split Large Servers

If server has 15+ tools, consider splitting into focused servers:

```
# Instead of one mega-server:
mega-server (15 tools = ~1500 context tokens)

# Split into focused servers:
query-server (5 tools = ~500 tokens)
mutation-server (5 tools = ~500 tokens)
admin-server (5 tools = ~500 tokens)

# User only connects servers they need
```

### Tip 3: Parameter Names as Documentation

```python
# Self-documenting parameters reduce description length
@mcp.tool()
async def create_issue(
    repo_owner_slash_name: str,  # "org/repo"
    issue_title: str,
    issue_body_markdown: str = "",
    priority_level: str = "medium"  # low, medium, high, critical
) -> dict:
    """Create a GitHub issue."""
```
