"""
{{SERVER_NAME}} MCP Server (Advanced)

{{DESCRIPTION}}

Features: Context injection, lifespan management, progress reporting, error handling.
"""

import os
import sys
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP, Context


# --- Lifespan: Manage shared resources ---

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialize and cleanup server resources."""
    # Startup: create connections, load models, etc.
    resources = {
        # "db": await create_db_pool(os.environ["DATABASE_URL"]),
        # "client": httpx.AsyncClient(base_url=os.environ["API_URL"]),
    }
    try:
        yield resources
    finally:
        # Shutdown: cleanup
        # await resources["db"].close()
        # await resources["client"].aclose()
        pass


mcp = FastMCP("{{SERVER_NAME}}", lifespan=lifespan)


# --- Tools ---

@mcp.tool()
async def {{TOOL_NAME}}(ctx: Context, {{PARAMS}}) -> dict:
    """{{TOOL_DESCRIPTION}}"""
    ctx.info(f"Starting {{TOOL_NAME}}")

    # Access lifespan resources
    # db = ctx.request_context.lifespan_context["db"]

    try:
        # TODO: Implement tool logic
        result = {}
        ctx.info("{{TOOL_NAME}} completed successfully")
        return {"data": result, "status": "success"}
    except Exception as e:
        ctx.error(f"{{TOOL_NAME}} failed: {e}")
        return {"error": "Operation failed", "status": "failed"}


@mcp.tool()
async def {{BATCH_TOOL_NAME}}(items: list[str], ctx: Context) -> dict:
    """{{BATCH_TOOL_DESCRIPTION}} with progress reporting."""
    total = len(items)
    ctx.info(f"Processing {total} items")
    results = []

    for i, item in enumerate(items):
        if i % max(1, total // 20) == 0:
            await ctx.report_progress(i, total)

        try:
            # TODO: Process each item
            results.append({"item": item, "status": "processed"})
        except Exception as e:
            ctx.warning(f"Failed to process '{item}': {e}")
            results.append({"item": item, "status": "failed", "error": str(e)})

    await ctx.report_progress(total, total)
    ctx.info(f"Batch complete: {len(results)}/{total} processed")
    return {"results": results, "total": total}


# --- Resources ---

@mcp.resource("server://info")
async def server_info() -> str:
    """Server metadata and capabilities."""
    return '{"name": "{{SERVER_NAME}}", "version": "0.1.0"}'


@mcp.resource("server://health")
async def health_check() -> str:
    """Server health status."""
    return '{"status": "healthy"}'


# --- Prompts ---

@mcp.prompt()
async def {{PROMPT_NAME}}(context: str) -> str:
    """{{PROMPT_DESCRIPTION}}"""
    return f"""{{PROMPT_TEMPLATE}}

Context:
{context}
"""


# --- Entry Point ---

def main():
    """Entry point supporting stdio and HTTP transport."""
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if transport == "http":
        mcp.run(transport="sse", host="0.0.0.0", port=8080)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
