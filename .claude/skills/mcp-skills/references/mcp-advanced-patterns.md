# MCP Advanced Patterns

Advanced server features for production-grade implementations.

---

## Context Object Injection

The `Context` object provides logging, progress reporting, and session access inside tools.

### Basic Context Usage

```python
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("my-server")

@mcp.tool()
async def process_data(file_path: str, ctx: Context) -> dict:
    """Process a data file with progress reporting."""
    ctx.info(f"Starting processing: {file_path}")

    try:
        data = await load_file(file_path)
        ctx.info(f"Loaded {len(data)} records")

        result = await transform(data)
        ctx.info("Processing complete")

        return {"records_processed": len(result), "status": "success"}

    except FileNotFoundError:
        ctx.error(f"File not found: {file_path}")
        return {"error": f"File not found: {file_path}", "status": "failed"}
    except Exception as e:
        ctx.error(f"Processing failed: {str(e)}")
        return {"error": "Internal processing error", "status": "failed"}
```

### Context Methods

| Method | Purpose | Client Receives |
|--------|---------|-----------------|
| `ctx.info(msg)` | Informational log | `notifications/message` (level: info) |
| `ctx.warning(msg)` | Warning log | `notifications/message` (level: warning) |
| `ctx.error(msg)` | Error log | `notifications/message` (level: error) |
| `ctx.debug(msg)` | Debug log | `notifications/message` (level: debug) |
| `ctx.report_progress(current, total)` | Progress update | `notifications/progress` |
| `ctx.read_resource(uri)` | Read another resource | Internal resource fetch |
| `ctx.session` | Access session object | N/A (internal) |

### When to Use Context

| Scenario | Method |
|----------|--------|
| Start of long operation | `ctx.info("Starting...")` |
| Each major step | `ctx.info("Step N complete")` |
| Recoverable issue | `ctx.warning("Retrying...")` |
| Fatal error | `ctx.error("Failed: reason")` |
| Batch processing | `ctx.report_progress(i, total)` |

---

## Server Lifespan Management

Manage async resources (database connections, HTTP clients) that persist across tool calls.

```python
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Manage server lifecycle resources."""
    # Startup: initialize resources
    db = await create_db_pool(os.environ["DATABASE_URL"])
    http_client = httpx.AsyncClient()

    try:
        yield {"db": db, "http_client": http_client}
    finally:
        # Shutdown: cleanup resources
        await db.close()
        await http_client.aclose()

mcp = FastMCP("my-server", lifespan=lifespan)

@mcp.tool()
async def query_data(sql: str, ctx: Context) -> list[dict]:
    """Execute a database query."""
    db = ctx.request_context.lifespan_context["db"]
    return await db.fetch(sql)
```

### Lifespan Pattern

```
Server Start → lifespan.__aenter__() → yield resources
                                          ↓
                              Tools access resources via ctx
                                          ↓
Server Stop  → lifespan.__aexit__()  → cleanup resources
```

**Use lifespan for**: Database pools, HTTP clients, file handles, cache connections, ML models.

**Do NOT use for**: Per-request state (use tool parameters instead).

---

## Sampling: Server Calling LLMs

Sampling allows your MCP server to request LLM completions through the connected client.

### When to Use Sampling
- Server needs AI analysis of data before returning results
- Server wants to summarize large datasets for the user
- Server needs classification/categorization of inputs

### Implementation

```python
from mcp.types import TextContent

@mcp.tool()
async def analyze_code(file_path: str, ctx: Context) -> dict:
    """Analyze code quality using LLM through client."""
    code = Path(file_path).read_text()

    # Request LLM completion through client
    response = await ctx.session.create_message(
        messages=[
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"Analyze this code for quality issues:\n\n{code}"
                }
            }
        ],
        max_tokens=1000
    )

    # Extract text from response
    analysis = ""
    for block in response.content:
        if isinstance(block, TextContent):
            analysis += block.text

    return {"analysis": analysis, "file": file_path}
```

### Sampling Considerations

| Consideration | Guidance |
|---------------|----------|
| **Cost** | Each sampling call costs tokens — minimize unnecessary calls |
| **Latency** | Adds round-trip to client + LLM — use for high-value operations |
| **Client support** | Not all clients support sampling — handle `NotImplementedError` |
| **Token limits** | Set reasonable `max_tokens` — don't request more than needed |
| **Fallback** | Always have non-sampling fallback for unsupported clients |

### Handling Unsupported Clients

```python
@mcp.tool()
async def smart_analyze(data: str, ctx: Context) -> dict:
    """Analyze with LLM if available, rule-based otherwise."""
    try:
        response = await ctx.session.create_message(
            messages=[{"role": "user", "content": {"type": "text", "text": f"Analyze: {data}"}}],
            max_tokens=500
        )
        return {"analysis": response.content[0].text, "method": "llm"}
    except (NotImplementedError, AttributeError):
        # Fallback to rule-based analysis
        return {"analysis": rule_based_analyze(data), "method": "rule-based"}
```

---

## Progress Notifications

Report progress for long-running operations.

```python
@mcp.tool()
async def batch_process(items: list[str], ctx: Context) -> dict:
    """Process a batch of items with progress reporting."""
    results = []
    total = len(items)

    for i, item in enumerate(items):
        await ctx.report_progress(i, total)
        ctx.info(f"Processing item {i+1}/{total}: {item}")

        result = await process_single(item)
        results.append(result)

    await ctx.report_progress(total, total)
    ctx.info("Batch processing complete")

    return {
        "processed": len(results),
        "total": total,
        "results": results
    }
```

### Progress Best Practices

- Report at meaningful intervals (not every iteration for 10k items)
- Use `total` parameter for determinate progress
- Combine with `ctx.info()` for descriptive status
- Final progress report should show completion (current == total)

```python
# For large batches, report every N items
REPORT_INTERVAL = max(1, total // 20)  # ~5% increments
for i, item in enumerate(items):
    if i % REPORT_INTERVAL == 0:
        await ctx.report_progress(i, total)
```

---

## Roots: File System Permissions

Roots define which directories the server can access.

### Requesting Roots

```python
mcp = FastMCP("file-server")

@mcp.tool()
async def read_project_file(path: str, ctx: Context) -> str:
    """Read a file, respecting root boundaries."""
    roots = await ctx.session.list_roots()

    # Validate path is within allowed roots
    resolved = Path(path).resolve()
    allowed = False
    for root in roots:
        root_path = Path(root.uri.replace("file://", ""))
        if str(resolved).startswith(str(root_path)):
            allowed = True
            break

    if not allowed:
        return f"Access denied: {path} is outside allowed roots"

    return resolved.read_text()
```

### Path Validation Helper

```python
import os
from pathlib import Path

def is_path_allowed(path: str, roots: list) -> bool:
    """Check if path is within any allowed root directory."""
    resolved = os.path.realpath(path)
    for root in roots:
        root_path = os.path.realpath(root.uri.replace("file://", ""))
        if resolved.startswith(root_path + os.sep) or resolved == root_path:
            return True
    return False

def safe_resolve(base_dir: str, user_path: str) -> str:
    """Resolve path safely, preventing traversal attacks."""
    full = os.path.normpath(os.path.join(base_dir, user_path))
    if not full.startswith(os.path.normpath(base_dir)):
        raise ValueError(f"Path traversal detected: {user_path}")
    return full
```

---

## StreamableHTTP Transport (Production)

### Stateful Server (Session Persistence)

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("production-server")

# Register tools, resources, prompts...

if __name__ == "__main__":
    mcp.run(
        transport="sse",
        host="0.0.0.0",
        port=8080
    )
```

### Stateless Server (Horizontal Scaling)

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("scalable-server", stateless_http=True)

if __name__ == "__main__":
    mcp.run(
        transport="sse",
        host="0.0.0.0",
        port=8080
    )
```

### Stateful vs Stateless Decision

| Factor | Stateful | Stateless |
|--------|----------|-----------|
| Session data | Preserved between calls | Lost between calls |
| Horizontal scaling | Sticky sessions required | Any instance handles request |
| Memory usage | Higher (session state) | Lower (no state) |
| Complexity | Simpler code | Need external state store |
| Use case | Single-instance, dev | Multi-instance, production |

**Default to stateful** for simplicity. Switch to stateless when you need horizontal scaling behind a load balancer.

---

## Error Handling Patterns

### Tool-Level Error Handling

```python
@mcp.tool()
async def safe_operation(input: str, ctx: Context) -> dict:
    """Operation with comprehensive error handling."""
    # Input validation
    if not input.strip():
        return {"error": "Input cannot be empty", "code": "INVALID_INPUT"}

    try:
        result = await perform_operation(input)
        return {"data": result, "status": "success"}

    except ConnectionError as e:
        ctx.warning(f"Connection failed: {e}")
        return {
            "error": "Service temporarily unavailable",
            "code": "CONNECTION_ERROR",
            "retryable": True
        }
    except PermissionError:
        ctx.error("Permission denied for operation")
        return {
            "error": "Insufficient permissions",
            "code": "PERMISSION_DENIED",
            "retryable": False
        }
    except Exception as e:
        ctx.error(f"Unexpected error: {type(e).__name__}: {e}")
        return {
            "error": "Internal server error",
            "code": "INTERNAL_ERROR",
            "retryable": False
        }
```

### Never Do This

```python
# BAD: Unhandled exception crashes the server
@mcp.tool()
async def unsafe_operation(path: str) -> str:
    return Path(path).read_text()  # FileNotFoundError crashes server!

# BAD: Silent failure
@mcp.tool()
async def silent_operation(data: str) -> str:
    try:
        return process(data)
    except:
        pass  # Error is hidden, returns None
```
