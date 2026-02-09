# MCP Server Examples

Complete, production-ready examples for common server types.

---

## Example 1: Database MCP Server

Full server for PostgreSQL database access.

```python
"""PostgreSQL MCP Server — query and manage database tables."""

import os
import asyncpg
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP, Context

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Manage database connection pool."""
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    try:
        yield {"pool": pool}
    finally:
        await pool.close()

mcp = FastMCP("postgres-server", lifespan=lifespan)

# --- Tools ---

@mcp.tool()
async def query(sql: str, params: list | None = None, *, ctx: Context) -> dict:
    """Execute a read-only SQL query. Returns rows as list of dicts."""
    if not sql.strip().upper().startswith("SELECT"):
        return {"error": "Only SELECT queries allowed", "code": "WRITE_DENIED"}

    pool = ctx.request_context.lifespan_context["pool"]
    try:
        ctx.info(f"Executing query: {sql[:100]}...")
        rows = await pool.fetch(sql, *(params or []))
        result = [dict(row) for row in rows]
        ctx.info(f"Returned {len(result)} rows")
        return {"rows": result, "count": len(result)}
    except asyncpg.PostgresSyntaxError as e:
        return {"error": f"SQL syntax error: {e}", "code": "SYNTAX_ERROR"}
    except Exception as e:
        ctx.error(f"Query failed: {e}")
        return {"error": "Query execution failed", "code": "QUERY_ERROR"}

@mcp.tool()
async def list_tables(schema: str = "public", *, ctx: Context) -> dict:
    """List all tables in the specified schema."""
    pool = ctx.request_context.lifespan_context["pool"]
    rows = await pool.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = $1",
        schema
    )
    tables = [row["table_name"] for row in rows]
    ctx.info(f"Found {len(tables)} tables in schema '{schema}'")
    return {"tables": tables, "schema": schema}

@mcp.tool()
async def describe_table(table: str, schema: str = "public", *, ctx: Context) -> dict:
    """Get column information for a table."""
    pool = ctx.request_context.lifespan_context["pool"]
    rows = await pool.fetch("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
    """, schema, table)
    columns = [dict(row) for row in rows]
    return {"table": table, "schema": schema, "columns": columns}

# --- Resources ---

@mcp.resource("db://schemas")
async def list_schemas() -> str:
    """Available database schemas."""
    return "Available schemas: public, analytics, staging"

# --- Prompts ---

@mcp.prompt()
async def sql_expert(table_name: str) -> str:
    """SQL query writing assistant for a specific table."""
    return f"""You are a PostgreSQL expert. Help write queries for the '{table_name}' table.
Rules:
- Use parameterized queries (never string concatenation)
- Prefer CTEs over subqueries for readability
- Always include WHERE clauses on large tables
- Use EXPLAIN ANALYZE for performance-critical queries
"""

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## Example 2: REST API Wrapper Server

Wrapping an external REST API with MCP tools.

```python
"""REST API Wrapper MCP Server — example wrapping a project management API."""

import os
import httpx
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP, Context

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Manage HTTP client lifecycle."""
    client = httpx.AsyncClient(
        base_url=os.environ["API_BASE_URL"],
        headers={"Authorization": f"Bearer {os.environ['API_TOKEN']}"},
        timeout=30.0
    )
    try:
        yield {"client": client}
    finally:
        await client.aclose()

mcp = FastMCP("api-wrapper")

# --- Tools ---

@mcp.tool()
async def list_projects(status: str = "active", *, ctx: Context) -> dict:
    """List projects filtered by status (active, archived, all)."""
    client = ctx.request_context.lifespan_context["client"]
    try:
        resp = await client.get("/projects", params={"status": status})
        resp.raise_for_status()
        data = resp.json()
        ctx.info(f"Found {len(data['projects'])} projects")
        return data
    except httpx.HTTPStatusError as e:
        ctx.error(f"API error: {e.response.status_code}")
        return {"error": f"API returned {e.response.status_code}", "retryable": e.response.status_code >= 500}
    except httpx.TimeoutException:
        ctx.warning("API request timed out")
        return {"error": "Request timed out", "retryable": True}

@mcp.tool()
async def create_task(
    project_id: str,
    title: str,
    description: str = "",
    priority: str = "medium",
    *,
    ctx: Context
) -> dict:
    """Create a new task in a project."""
    if priority not in ("low", "medium", "high", "critical"):
        return {"error": f"Invalid priority: {priority}. Use: low, medium, high, critical"}

    client = ctx.request_context.lifespan_context["client"]
    try:
        resp = await client.post(
            f"/projects/{project_id}/tasks",
            json={"title": title, "description": description, "priority": priority}
        )
        resp.raise_for_status()
        task = resp.json()
        ctx.info(f"Created task: {task['id']}")
        return task
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"Project not found: {project_id}"}
        return {"error": f"Failed to create task: {e.response.status_code}"}

@mcp.tool()
async def search_tasks(
    query: str,
    project_id: str | None = None,
    limit: int = 20,
    *,
    ctx: Context
) -> dict:
    """Search tasks by keyword across projects."""
    client = ctx.request_context.lifespan_context["client"]
    params = {"q": query, "limit": min(limit, 100)}
    if project_id:
        params["project_id"] = project_id

    resp = await client.get("/tasks/search", params=params)
    resp.raise_for_status()
    return resp.json()

# --- Resources ---

@mcp.resource("api://status")
async def api_status() -> str:
    """Current API health and rate limit info."""
    return "API Status: healthy | Rate limit: 1000 req/min | Version: v2"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## Example 3: Filesystem Server

File operations with security boundaries.

```python
"""Filesystem MCP Server — read and search files with path security."""

import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("filesystem-server")

BASE_DIR = os.environ.get("FS_BASE_DIR", os.getcwd())

def safe_resolve(user_path: str) -> Path:
    """Resolve path safely, preventing directory traversal."""
    base = Path(BASE_DIR).resolve()
    target = (base / user_path).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"Path traversal blocked: {user_path}")
    return target

@mcp.tool()
async def read_file(path: str, ctx: Context) -> dict:
    """Read file contents. Path is relative to base directory."""
    try:
        target = safe_resolve(path)
        if not target.exists():
            return {"error": f"File not found: {path}"}
        if not target.is_file():
            return {"error": f"Not a file: {path}"}
        if target.stat().st_size > 10 * 1024 * 1024:  # 10MB limit
            return {"error": "File too large (>10MB)"}

        content = target.read_text(encoding="utf-8")
        ctx.info(f"Read {len(content)} chars from {path}")
        return {"content": content, "path": str(path), "size": len(content)}
    except ValueError as e:
        ctx.error(str(e))
        return {"error": str(e)}
    except UnicodeDecodeError:
        return {"error": f"Binary file, cannot read as text: {path}"}

@mcp.tool()
async def list_directory(path: str = ".", *, ctx: Context) -> dict:
    """List files and directories at the given path."""
    try:
        target = safe_resolve(path)
        if not target.is_dir():
            return {"error": f"Not a directory: {path}"}

        entries = []
        for entry in sorted(target.iterdir()):
            entries.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None
            })

        ctx.info(f"Listed {len(entries)} entries in {path}")
        return {"entries": entries, "path": path}
    except ValueError as e:
        return {"error": str(e)}

@mcp.tool()
async def search_files(
    pattern: str,
    path: str = ".",
    *,
    ctx: Context
) -> dict:
    """Search for files matching a glob pattern."""
    try:
        target = safe_resolve(path)
        matches = [
            str(p.relative_to(Path(BASE_DIR).resolve()))
            for p in target.rglob(pattern)
            if p.is_file()
        ][:100]  # Limit results

        ctx.info(f"Found {len(matches)} files matching '{pattern}'")
        return {"matches": matches, "count": len(matches), "pattern": pattern}
    except ValueError as e:
        return {"error": str(e)}

# --- Resources ---

@mcp.resource("fs://info")
async def fs_info() -> str:
    """File system server information."""
    return f"Base directory: {BASE_DIR}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## Example 4: Full-Featured Server (All Primitives + Advanced)

Server combining tools, resources, prompts with context, progress, and lifespan.

```python
"""Full-featured MCP Server demonstrating all primitives and advanced patterns."""

import os
import json
from pathlib import Path
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP, Context

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialize shared resources."""
    cache = {}
    yield {"cache": cache}

mcp = FastMCP("full-server", lifespan=lifespan)

# --- Tools (with Context, Progress, Error Handling) ---

@mcp.tool()
async def analyze_files(directory: str, extensions: list[str], ctx: Context) -> dict:
    """Analyze files in a directory by extension with progress reporting."""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return {"error": f"Directory not found: {directory}"}

    files = [f for f in dir_path.rglob("*") if f.suffix in extensions and f.is_file()]
    total = len(files)
    ctx.info(f"Found {total} files to analyze")

    stats = {"total_files": total, "total_lines": 0, "by_extension": {}}

    for i, file in enumerate(files):
        if i % max(1, total // 20) == 0:
            await ctx.report_progress(i, total)

        try:
            lines = len(file.read_text().splitlines())
            stats["total_lines"] += lines
            ext = file.suffix
            stats["by_extension"].setdefault(ext, {"files": 0, "lines": 0})
            stats["by_extension"][ext]["files"] += 1
            stats["by_extension"][ext]["lines"] += lines
        except Exception:
            ctx.warning(f"Could not read: {file}")

    await ctx.report_progress(total, total)
    ctx.info(f"Analysis complete: {stats['total_lines']} total lines")
    return stats

@mcp.tool()
async def cached_lookup(key: str, ctx: Context) -> dict:
    """Look up a value from the server cache (lifespan demo)."""
    cache = ctx.request_context.lifespan_context["cache"]
    if key in cache:
        ctx.info(f"Cache hit: {key}")
        return {"key": key, "value": cache[key], "cached": True}
    ctx.info(f"Cache miss: {key}")
    return {"key": key, "value": None, "cached": False}

@mcp.tool()
async def cache_store(key: str, value: str, ctx: Context) -> dict:
    """Store a value in the server cache."""
    cache = ctx.request_context.lifespan_context["cache"]
    cache[key] = value
    ctx.info(f"Cached: {key}")
    return {"key": key, "stored": True}

# --- Resources ---

@mcp.resource("server://info")
async def server_info() -> str:
    """Server metadata and capabilities."""
    return json.dumps({
        "name": "full-server",
        "version": "1.0.0",
        "capabilities": ["tools", "resources", "prompts", "progress", "caching"]
    })

@mcp.resource("server://health")
async def health_check() -> str:
    """Server health status."""
    return json.dumps({"status": "healthy", "uptime": "running"})

# --- Prompts ---

@mcp.prompt()
async def code_review(language: str, focus: str = "general") -> str:
    """Code review template for specified language and focus area."""
    focus_areas = {
        "general": "code quality, readability, and maintainability",
        "security": "security vulnerabilities, injection points, and auth issues",
        "performance": "performance bottlenecks, memory leaks, and optimization",
        "testing": "test coverage, edge cases, and test quality"
    }
    area = focus_areas.get(focus, focus_areas["general"])

    return f"""Review the following {language} code focusing on {area}.

Provide:
1. Issues found (severity: critical/warning/info)
2. Specific line references
3. Suggested fixes with code examples
4. Overall assessment (pass/needs-work/fail)
"""

@mcp.prompt()
async def documentation(component: str) -> str:
    """Documentation template for a code component."""
    return f"""Write documentation for: {component}

Include:
- Purpose and overview
- Parameters/arguments with types
- Return values
- Usage examples (basic + advanced)
- Error handling notes
- Related components
"""

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## Minimal Server (Quick Start)

Smallest possible production server for simple use cases.

```python
"""Minimal MCP Server — single tool, production-ready."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hello-server")

@mcp.tool()
async def greet(name: str) -> str:
    """Greet a user by name."""
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**pyproject.toml**:
```toml
[project]
name = "hello-server"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["mcp[cli]>=1.0.0"]

[project.scripts]
hello-server = "hello_server:mcp.run"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```
