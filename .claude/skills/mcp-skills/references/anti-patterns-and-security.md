# MCP Anti-Patterns and Security

Common mistakes and security considerations for MCP servers.

---

## Server Anti-Patterns

### 1. Unhandled Exceptions (Server Crash)

```python
# BAD: Exception crashes the entire server process
@mcp.tool()
async def read_file(path: str) -> str:
    return Path(path).read_text()  # FileNotFoundError = crash

# GOOD: Exception caught, structured error returned
@mcp.tool()
async def read_file(path: str, ctx: Context) -> dict:
    try:
        return {"content": Path(path).read_text(), "path": path}
    except FileNotFoundError:
        return {"error": f"File not found: {path}"}
    except PermissionError:
        return {"error": f"Permission denied: {path}"}
    except Exception as e:
        ctx.error(f"Unexpected: {e}")
        return {"error": "Failed to read file"}
```

### 2. Blocking Synchronous Code in Async Handlers

```python
# BAD: Blocks the event loop
@mcp.tool()
async def process(path: str) -> str:
    import time
    time.sleep(5)  # Blocks ALL other requests
    return Path(path).read_text()  # Synchronous I/O in async handler

# GOOD: Use async I/O
@mcp.tool()
async def process(path: str) -> str:
    import asyncio
    import aiofiles
    await asyncio.sleep(5)  # Non-blocking
    async with aiofiles.open(path) as f:
        return await f.read()
```

### 3. Hardcoded Credentials

```python
# BAD: Credentials in source code
@mcp.tool()
async def connect() -> dict:
    db = await connect_db("postgresql://admin:password123@prod-db:5432/app")
    return {"status": "connected"}

# GOOD: Environment variables
@mcp.tool()
async def connect(ctx: Context) -> dict:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return {"error": "DATABASE_URL not configured"}
    db = await connect_db(db_url)
    return {"status": "connected"}
```

### 4. Mutable Global State

```python
# BAD: Global state breaks stateless deployment
results_cache = {}

@mcp.tool()
async def search(query: str) -> dict:
    if query in results_cache:
        return results_cache[query]
    result = await do_search(query)
    results_cache[query] = result  # Grows forever, inconsistent across instances
    return result

# GOOD: Use lifespan-managed state or external cache
@asynccontextmanager
async def lifespan(server):
    cache = {}  # Scoped to server lifetime
    yield {"cache": cache}

mcp = FastMCP("server", lifespan=lifespan)

@mcp.tool()
async def search(query: str, ctx: Context) -> dict:
    cache = ctx.request_context.lifespan_context["cache"]
    # Managed, scoped, cleared on restart
```

### 5. Tool With Too Many Parameters

```python
# BAD: 12 parameters — confusing for LLM
@mcp.tool()
async def create_report(
    title, subtitle, author, date, format, template,
    sections, include_charts, chart_style, footer,
    page_numbers, watermark
) -> dict:
    ...

# GOOD: Use Pydantic model for complex inputs
from pydantic import BaseModel

class ReportConfig(BaseModel):
    title: str
    author: str
    format: str = "pdf"
    include_charts: bool = True

@mcp.tool()
async def create_report(config: ReportConfig, ctx: Context) -> dict:
    """Create a report from configuration."""
    ...
```

### 6. Using print() Instead of Context

```python
# BAD: print goes to stdout, conflicts with stdio transport
@mcp.tool()
async def process(data: str) -> str:
    print(f"Processing: {data}")  # BREAKS stdio transport!
    return "done"

# GOOD: Use Context logging
@mcp.tool()
async def process(data: str, ctx: Context) -> str:
    ctx.info(f"Processing: {data}")  # Proper MCP notification
    return "done"
```

### 7. Raw JSON-RPC Construction

```python
# BAD: Manual JSON-RPC messages
import json
response = json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "result": {"data": "value"}
})

# GOOD: Use FastMCP abstractions
@mcp.tool()
async def my_tool(input: str) -> dict:
    return {"data": "value"}  # FastMCP handles JSON-RPC wrapping
```

### 8. Resource URIs Without Scheme

```python
# BAD: No scheme prefix
@mcp.resource("settings")
async def get_settings() -> str: ...

# GOOD: Proper URI with scheme
@mcp.resource("config://app/settings")
async def get_settings() -> str: ...
```

---

## Security Checklist

### Input Validation

| Attack | Prevention |
|--------|-----------|
| **Path traversal** | Resolve paths, verify within base directory |
| **SQL injection** | Parameterized queries only (never string concat) |
| **Command injection** | Never pass user input to shell commands |
| **XSS** | Escape HTML in any web-rendered output |
| **SSRF** | Validate URLs, block internal network access |

### Path Traversal Prevention

```python
import os
from pathlib import Path

def validate_path(user_path: str, base_dir: str) -> Path:
    """Validate path is within allowed base directory."""
    base = Path(base_dir).resolve()
    target = (base / user_path).resolve()

    # Check target is within base (Python 3.9+)
    if not target.is_relative_to(base):
        raise ValueError(f"Access denied: path outside base directory")

    # Block hidden files
    for part in target.relative_to(base).parts:
        if part.startswith('.'):
            raise ValueError(f"Access denied: hidden files blocked")

    return target
```

### SQL Injection Prevention

```python
# NEVER: String formatting
query = f"SELECT * FROM users WHERE name = '{user_input}'"  # INJECTABLE!

# ALWAYS: Parameterized queries
await pool.fetch("SELECT * FROM users WHERE name = $1", user_input)
```

### Environment Variable Security

```python
# Required variables — fail fast if missing
def require_env(key: str) -> str:
    """Get required environment variable or fail with clear message."""
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Required environment variable '{key}' is not set")
    return value

DATABASE_URL = require_env("DATABASE_URL")
API_TOKEN = require_env("API_TOKEN")
```

### Sensitive Data in Responses

```python
# BAD: Leaking internal details
@mcp.tool()
async def query(sql: str, ctx: Context) -> dict:
    try:
        return await db.fetch(sql)
    except Exception as e:
        return {"error": str(e)}  # May contain DB credentials, schema details!

# GOOD: Sanitized error messages
@mcp.tool()
async def query(sql: str, ctx: Context) -> dict:
    try:
        return await db.fetch(sql)
    except Exception as e:
        ctx.error(f"Query failed: {e}")  # Full error in logs (server-side)
        return {"error": "Query execution failed"}  # Safe message to client
```

---

## Production Deployment Checklist

### Before Deploying

- [ ] All tools handle exceptions (no unhandled crashes)
- [ ] No hardcoded credentials (all in environment variables)
- [ ] `.env.example` provided (without real values)
- [ ] Input validation on all tool parameters
- [ ] Path traversal protection (if filesystem access)
- [ ] SQL injection protection (if database access)
- [ ] Rate limiting considered (for API wrappers)
- [ ] Logging via Context (not print())
- [ ] Resource URIs have proper schemes
- [ ] Tool descriptions are concise (<200 chars)

### Transport Security

| Transport | Security Consideration |
|-----------|----------------------|
| stdio | Local only — no network exposure |
| StreamableHTTP | Add authentication layer (reverse proxy, API gateway) |
| SSE | CORS configuration for browser clients |

### Authentication for HTTP Transport

MCP itself doesn't handle authentication. For production HTTP servers:

```python
# Use a reverse proxy (nginx, caddy) for auth
# Or implement middleware:

from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware

# Configure in your ASGI app setup
```

**Recommended**: Use reverse proxy (nginx/caddy) with API key or OAuth, keeping the MCP server focused on business logic.
