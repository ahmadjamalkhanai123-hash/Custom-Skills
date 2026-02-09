"""
{{SERVER_NAME}} MCP Server

{{DESCRIPTION}}
"""

import os
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("{{SERVER_NAME}}")


# --- Tools ---

@mcp.tool()
async def {{TOOL_NAME}}(ctx: Context, {{PARAMS}}) -> dict:
    """{{TOOL_DESCRIPTION}}"""
    ctx.info(f"{{TOOL_NAME}} called")
    try:
        # TODO: Implement tool logic
        result = {}
        return {"data": result, "status": "success"}
    except Exception as e:
        ctx.error(f"{{TOOL_NAME}} failed: {e}")
        return {"error": "Operation failed", "status": "failed"}


# --- Resources ---

@mcp.resource("server://info")
async def server_info() -> str:
    """Server metadata and capabilities."""
    return "{{SERVER_NAME}} v0.1.0"


# --- Entry Point ---

def main():
    """Entry point for pyproject.toml script."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
