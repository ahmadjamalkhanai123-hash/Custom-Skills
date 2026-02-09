#!/usr/bin/env python3
"""
MCP Server Scaffolder — Generate production-ready MCP server project structure.

Usage:
    python scaffold_mcp_server.py <server-name> --path <output-dir> [--tools N] [--transport stdio|http|both]

Examples:
    python scaffold_mcp_server.py my-db-server --path ./projects --tools 5
    python scaffold_mcp_server.py api-wrapper --path ./projects --transport both
    python scaffold_mcp_server.py simple-server --path ./projects --tools 2
"""

import sys
import os
from pathlib import Path
from textwrap import dedent


def to_package_name(server_name: str) -> str:
    """Convert kebab-case server name to snake_case package name."""
    return server_name.replace("-", "_")


def generate_server_py(server_name: str, package_name: str, tool_count: int) -> str:
    """Generate main server.py content."""
    tools_section = ""
    for i in range(1, min(tool_count + 1, 4)):
        tools_section += f'''
@mcp.tool()
async def tool_{i}(input: str, ctx: Context) -> dict:
    """TODO: Describe what tool_{i} does."""
    ctx.info(f"tool_{i} called with: {{input}}")
    try:
        # TODO: Implement tool logic
        return {{"result": f"Processed: {{input}}", "status": "success"}}
    except Exception as e:
        ctx.error(f"tool_{i} failed: {{e}}")
        return {{"error": "Operation failed", "status": "failed"}}

'''

    return dedent(f'''
"""
{server_name} MCP Server

TODO: Add server description.
"""

import os
from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("{server_name}")

# --- Tools ---
{tools_section}
# --- Resources ---

@mcp.resource("server://info")
async def server_info() -> str:
    """Server metadata and capabilities."""
    return "{server_name} v0.1.0"


# --- Entry Point ---

def main():
    """Entry point for pyproject.toml script."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
''').lstrip()


def generate_pyproject(server_name: str, package_name: str) -> str:
    """Generate pyproject.toml content."""
    return dedent(f'''
[project]
name = "{server_name}"
version = "0.1.0"
description = "MCP server for TODO: add description"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.scripts]
{server_name} = "{package_name}.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{package_name}"]
''').lstrip()


def generate_test(package_name: str) -> str:
    """Generate test file content."""
    return dedent(f'''
"""Tests for {package_name} MCP server."""

import pytest


@pytest.mark.asyncio
async def test_placeholder():
    """TODO: Replace with actual tool tests."""
    # Example: test a tool function directly
    # from {package_name}.server import tool_1
    # result = await tool_1("test_input")
    # assert "error" not in result
    assert True
''').lstrip()


def generate_env_example() -> str:
    """Generate .env.example content."""
    return dedent('''
# Required environment variables
# DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
# API_TOKEN=your-token-here

# Optional
LOG_LEVEL=info
''').lstrip()


def generate_readme(server_name: str) -> str:
    """Generate README.md content."""
    return dedent(f'''
# {server_name}

MCP server for TODO: add description.

## Setup

```bash
# Install dependencies
uv sync

# Run the server (stdio)
uv run {server_name}
```

## Client Configuration

### Claude Desktop / Claude Code

Add to your MCP configuration:

```json
{{
  "mcpServers": {{
    "{server_name}": {{
      "command": "uv",
      "args": ["run", "--directory", "/path/to/{server_name}", "{server_name}"],
      "env": {{}}
    }}
  }}
}}
```

## Testing

```bash
# Run tests
uv run pytest

# Test with MCP Inspector
npx @modelcontextprotocol/inspector uv run {server_name}
```

## Tools

| Tool | Description |
|------|-------------|
| TODO | Add tool descriptions |
''').lstrip()


def scaffold(server_name: str, output_dir: str, tool_count: int = 3, transport: str = "stdio"):
    """Create the full MCP server project structure."""
    package_name = to_package_name(server_name)
    project_dir = Path(output_dir).resolve() / server_name

    if project_dir.exists():
        print(f"Error: Directory already exists: {project_dir}")
        return None

    # Determine structure based on tool count
    use_subdirs = tool_count > 3

    # Create directories
    src_dir = project_dir / "src" / package_name
    src_dir.mkdir(parents=True)
    (project_dir / "tests").mkdir()
    (project_dir / "scripts").mkdir()

    if use_subdirs:
        (src_dir / "tools").mkdir()
        (src_dir / "tools" / "__init__.py").write_text("")
        (src_dir / "resources").mkdir()
        (src_dir / "resources" / "__init__.py").write_text("")

    # Write files
    (src_dir / "__init__.py").write_text(f'"""MCP server: {server_name}."""\n')
    (src_dir / "server.py").write_text(generate_server_py(server_name, package_name, tool_count))
    (project_dir / "pyproject.toml").write_text(generate_pyproject(server_name, package_name))
    (project_dir / "tests" / "__init__.py").write_text("")
    (project_dir / "tests" / "test_server.py").write_text(generate_test(package_name))
    (project_dir / ".env.example").write_text(generate_env_example())
    (project_dir / "README.md").write_text(generate_readme(server_name))

    print(f"Created MCP server project: {project_dir}")
    print(f"  Package: {package_name}")
    print(f"  Tools: {tool_count}")
    print(f"  Structure: {'full (subdirectories)' if use_subdirs else 'simple (single file)'}")
    print(f"\nNext steps:")
    print(f"  cd {project_dir}")
    print(f"  uv sync")
    print(f"  # Edit src/{package_name}/server.py to implement your tools")
    print(f"  uv run {server_name}")

    return project_dir


def main():
    if len(sys.argv) < 4 or "--path" not in sys.argv:
        print(__doc__)
        sys.exit(1)

    server_name = sys.argv[1]
    path_idx = sys.argv.index("--path") + 1
    output_dir = sys.argv[path_idx]

    tool_count = 3
    transport = "stdio"

    if "--tools" in sys.argv:
        tool_count = int(sys.argv[sys.argv.index("--tools") + 1])
    if "--transport" in sys.argv:
        transport = sys.argv[sys.argv.index("--transport") + 1]

    scaffold(server_name, output_dir, tool_count, transport)


if __name__ == "__main__":
    main()
