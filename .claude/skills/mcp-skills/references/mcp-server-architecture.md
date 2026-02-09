# MCP Server Architecture

Core architectural patterns for building MCP servers.

---

## Host-Client-Server Model

```
┌─────────────────────────────────────┐
│           MCP Host                  │
│  (Claude Desktop, Cursor, VS Code) │
│                                     │
│  ┌──────────────────────────────┐  │
│  │       MCP Client             │  │
│  │  (connection manager)        │  │
│  └──────────┬───────────────────┘  │
└─────────────┼───────────────────────┘
              │ JSON-RPC 2.0
              │ (stdio or HTTP/SSE)
      ┌───────▼────────┐
      │   MCP Server   │
      │ (your code)    │
      └────────────────┘
```

- **Host**: Application where humans work (IDE, chat app, API service)
- **Client**: Component inside Host managing server connections (one Client per Server)
- **Server**: Standalone process exposing tools, resources, prompts

**Key**: Your code is the Server. You never build Clients or Hosts.

---

## JSON-RPC 2.0 Protocol

All MCP messages use JSON-RPC 2.0:

### Request (Client → Server)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "create_issue",
    "arguments": {
      "repo": "org/repo",
      "title": "Bug report"
    }
  }
}
```

### Response (Server → Client)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Issue #42 created successfully"
      }
    ]
  }
}
```

### Error Response
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": {"field": "repo", "issue": "Repository not found"}
  }
}
```

### Standard Error Codes
| Code | Meaning | When to Use |
|------|---------|-------------|
| -32700 | Parse error | Malformed JSON |
| -32600 | Invalid request | Missing required fields |
| -32601 | Method not found | Unknown tool/resource |
| -32602 | Invalid params | Wrong parameter types |
| -32603 | Internal error | Server-side failure |

---

## Three Primitives

### 1. Tools (Model-Controlled Actions)

Functions the LLM decides to call. Server registers, Client discovers, LLM invokes.

```python
@mcp.tool()
async def create_issue(repo: str, title: str, body: str = "") -> dict:
    """Create a GitHub issue in the specified repository."""
    # Implementation here
    return {"issue_number": 42, "url": "https://..."}
```

**Schema auto-generation**: Python type hints → JSON Schema `inputSchema`:
```json
{
  "name": "create_issue",
  "description": "Create a GitHub issue in the specified repository.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "repo": {"type": "string"},
      "title": {"type": "string"},
      "body": {"type": "string", "default": ""}
    },
    "required": ["repo", "title"]
  }
}
```

### 2. Resources (App-Controlled Data)

Read-only data the Client can list and fetch. URIs with MIME types.

```python
@mcp.resource("config://app/settings")
async def get_settings() -> str:
    """Application configuration settings."""
    return json.dumps({"theme": "dark", "language": "en"})

@mcp.resource("file:///{path}")
async def read_file(path: str) -> str:
    """Read a file from the project directory."""
    return Path(path).read_text()
```

**URI patterns**:
- `file:///path/to/file` — filesystem resources
- `db://database/table` — database resources
- `config://app/settings` — configuration resources
- `template://name` — template resources

### 3. Prompts (User-Controlled Templates)

Pre-written instruction templates encoding domain expertise.

```python
@mcp.prompt()
async def security_review(code: str) -> str:
    """Security-focused code review template."""
    return f"""Review this code for security vulnerabilities:

{code}

Check for:
- SQL injection points
- Authentication bypasses
- Data exposure risks
- Input validation gaps
"""
```

---

## Transport Options

### stdio (Local Development)

Server communicates via stdin/stdout. Used by Claude Desktop, Claude Code, Cursor.

```python
mcp = FastMCP("my-server")

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**Client config** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "my-server": {
      "command": "uv",
      "args": ["run", "my-server"]
    }
  }
}
```

**When**: Local development, single-user, desktop applications.

### StreamableHTTP (Production)

Server listens on HTTP with Server-Sent Events for streaming. Used for remote deployment.

```python
mcp = FastMCP("my-server")

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8080)
```

**When**: Production deployment, multi-user, cloud hosting, load balancing.

### Choosing Transport

| Factor | stdio | StreamableHTTP |
|--------|-------|----------------|
| Setup complexity | Low | Medium |
| Multi-user | No | Yes |
| Load balancing | No | Yes |
| Firewall traversal | N/A | HTTP-friendly |
| Debugging | Harder (binary pipes) | Easier (HTTP tools) |
| Use case | Local dev, desktop apps | Production, cloud |

---

## Tool Schema Design Principles

### Good Tool Design
```python
# Clear name, focused purpose, typed params
@mcp.tool()
async def search_documents(
    query: str,
    max_results: int = 10,
    file_type: str = "all"
) -> list[dict]:
    """Search documents by keyword. Returns title, path, and relevance score."""
```

### Bad Tool Design
```python
# Vague name, too many params, no types
@mcp.tool()
async def do_stuff(data, options=None, flag1=False, flag2=False,
                    mode="default", extra=None, config=None,
                    timeout=30, retries=3, verbose=False, dry_run=False):
    """Does stuff with data."""
```

### Tool Naming Conventions
| Pattern | Example | Use For |
|---------|---------|---------|
| `verb_noun` | `create_issue`, `search_docs` | Standard actions |
| `get_noun` | `get_user`, `get_config` | Data retrieval |
| `list_nouns` | `list_issues`, `list_files` | Collection listing |
| `update_noun` | `update_issue`, `update_settings` | Modifications |
| `delete_noun` | `delete_issue`, `delete_file` | Removal operations |

### Parameter Guidelines
- **Max 7 parameters** per tool (cognitive limit)
- Use **Pydantic models** for complex inputs (>4 params)
- **Default values** for optional params
- **Descriptive names** (not `x`, `d`, `opts`)
- **Enum types** for constrained choices
