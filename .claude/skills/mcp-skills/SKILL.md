---
name: mcp-skills
description: |
  Creates production-ready MCP Servers and optimized MCP-wrapping Skills with
  industry-grade architecture, JSON-RPC 2.0 compliance, and optimized project structure.
  This skill should be used when users want to build MCP servers, create skills that
  wrap MCP servers, scaffold MCP projects, or generate server code for any domain
  (database, API, filesystem, DevOps, healthcare, finance, etc.).
---

# MCP Skills

Build production-ready MCP Servers and optimized MCP-wrapping Skills for any domain.

## What This Skill Does

- Creates complete MCP Servers with `@mcp.tool`, `@mcp.resource`, `@mcp.prompt` decorators
- Generates optimized project structures (`src/`, `scripts/`, `tests/`)
- Builds MCP-wrapping Skills (SKILL.md files that add intelligence over MCP servers)
- Scaffolds `pyproject.toml` with entry points for installable packages
- Implements advanced patterns: Context injection, sampling, progress notifications, roots
- Configures transport: stdio (local) and StreamableHTTP (production)
- Handles any domain: provide your domain, get a production MCP server

## What This Skill Does NOT Do

- Deploy servers to production infrastructure
- Manage cloud credentials or secrets provisioning
- Create MCP Clients or Hosts (only Servers and Skills)
- Test against live external APIs (scaffolds test structure only)
- Handle MCP Registry publishing

---

## Before Implementation

Gather context to ensure successful implementation:

| Source | Gather |
|--------|--------|
| **Codebase** | Existing project structure, Python version, package manager (uv/pip) |
| **Conversation** | User's domain, tools needed, transport requirements |
| **Skill References** | MCP patterns from `references/` (architecture, examples, anti-patterns) |
| **User Guidelines** | Team conventions, naming standards, deployment target |

Ensure all required context is gathered before implementing.
Only ask user for THEIR specific requirements (MCP domain expertise is in this skill).

---

## Required Clarifications

Before building, ask:

1. **Domain**: "What domain is this MCP Server for?"
   - Database (Postgres, MongoDB, Redis, etc.)
   - API wrapper (REST, GraphQL, proprietary)
   - Filesystem / document processing
   - DevOps / infrastructure
   - Custom domain (describe)

2. **Primitives needed**: "Which MCP primitives do you need?"
   - Tools only (most common)
   - Tools + Resources
   - Tools + Resources + Prompts (full server)

3. **Transport**: "Local development or production deployment?"
   - stdio (local, Claude Desktop/Code) (Recommended)
   - StreamableHTTP (production, remote clients)
   - Both (dual transport)

## Optional Clarifications

4. **Advanced features**: "Need any advanced patterns?"
   - Context injection + logging
   - Sampling (server calling LLMs through client)
   - Progress notifications (long operations)
   - Roots (file system permission boundaries)

5. **Output type**: "MCP Server, MCP-wrapping Skill, or both?"
   - MCP Server only (default)
   - MCP-wrapping Skill only
   - Both (server + skill that wraps it)

Note: Avoid asking all questions at once. Start with 1-2, follow up as needed.

### Defaults (If Not Specified)

| Clarification | Default |
|---------------|---------|
| Domain | Infer from conversation context |
| Primitives | Tools only |
| Transport | stdio |
| Advanced features | None (basic server) |
| Output type | MCP Server only |

### Before Asking

1. Check conversation history for prior answers
2. Infer from existing project files (pyproject.toml, existing servers)
3. Only ask what cannot be determined from context

---

## Workflow

```
Domain → Primitives → Structure → Implement → Configure → Validate
```

### Step 1: Determine Server Scope

From user's domain, identify:
- What **tools** the server exposes (actions with inputs/outputs)
- What **resources** it provides (read-only data URIs)
- What **prompts** encode domain expertise (template instructions)

### Step 2: Generate Project Structure

Use optimized layout from `references/project-structure.md`:

```
{server-name}/
├── src/{package_name}/
│   ├── __init__.py
│   ├── server.py          ← Main server with decorators
│   ├── tools/             ← Tool handlers (one per module)
│   │   ├── __init__.py
│   │   └── {tool_name}.py
│   ├── resources/         ← Resource handlers
│   │   ├── __init__.py
│   │   └── {resource_name}.py
│   └── prompts/           ← Prompt templates
│       ├── __init__.py
│       └── {prompt_name}.py
├── scripts/
│   ├── run_stdio.py       ← Local development launch
│   └── run_http.py        ← Production launch (if needed)
├── tests/
│   └── test_server.py     ← Server test scaffold
├── pyproject.toml         ← Package config with entry points
└── README.md              ← Usage + client configuration
```

For simple servers (1-3 tools), flatten to single `server.py` without subdirectories.

### Step 3: Implement Server Code

Read `references/mcp-server-examples.md` for complete patterns. Core structure:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("{server-name}")

@mcp.tool()
async def tool_name(param: str) -> str:
    """Tool description for LLM discovery."""
    # Implementation
    return result

@mcp.resource("resource://{uri}")
async def resource_name() -> str:
    """Resource description."""
    return data

@mcp.prompt()
async def prompt_name(context: str) -> str:
    """Prompt description."""
    return template
```

### Step 4: Configure Transport & Packaging

**stdio** (development):
```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**StreamableHTTP** (production):
```python
if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8080)
```

**pyproject.toml entry point**:
```toml
[project.scripts]
{server-name} = "{package}:main"
```

### Step 5: Generate Client Configuration

For Claude Desktop/Code (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "{server-name}": {
      "command": "uv",
      "args": ["run", "{server-name}"],
      "env": {}
    }
  }
}
```

### Step 6: Validate Output

Apply output checklist below before delivering.

---

## Output Specification

Every generated MCP Server includes:

### Required Components
- [ ] `server.py` with FastMCP initialization and all decorators
- [ ] Typed parameters with Pydantic or type hints on all tools
- [ ] `inputSchema` auto-generated from type annotations (JSON Schema compliant)
- [ ] Docstrings on every tool/resource/prompt (used for LLM discovery)
- [ ] Error handling returning structured JSON-RPC errors
- [ ] `pyproject.toml` with dependencies and entry points

### Required Patterns
- [ ] JSON-RPC 2.0 compliance (method, params, result/error, id)
- [ ] Tool descriptions ≤200 chars (concise for LLM context)
- [ ] Resource URIs follow `scheme://authority/path` pattern
- [ ] Prompt templates use argument interpolation

### Context Optimization
- [ ] Tools split into modules when >5 tools (context-efficient loading)
- [ ] Heavy logic in separate modules, not inline in decorators
- [ ] Constants and configs in dedicated files, not hardcoded

---

## Domain Standards

### Must Follow

- [ ] Use `FastMCP` from `mcp.server.fastmcp` (not raw protocol)
- [ ] Type all tool parameters (str, int, float, bool, list, dict, Pydantic models)
- [ ] Return structured data (dict/str), not raw objects
- [ ] Use `async def` for all handlers (MCP is async-first)
- [ ] Handle exceptions inside tools — return error dict, never crash server
- [ ] Use `ctx: Context` parameter for logging/progress (not print())
- [ ] Validate inputs at tool boundary before processing
- [ ] Keep server stateless where possible (horizontal scaling)

### Must Avoid

- Raw JSON-RPC message construction (use FastMCP abstractions)
- Hardcoded credentials in server code (use environment variables)
- Blocking synchronous calls inside async handlers (use asyncio)
- Tools with >10 parameters (split into multiple tools)
- Resource URIs without scheme prefix
- Mutable global state (breaks stateless deployment)
- `print()` for logging (use `ctx.info()`, `ctx.warning()`, `ctx.error()`)
- Catching all exceptions silently (log context, return structured error)

---

## Advanced Features Decision Tree

```
Need logging/progress?
  → Yes: Add Context injection (references/mcp-advanced-patterns.md)
  → No: Skip

Server needs to call an LLM?
  → Yes: Add Sampling (references/mcp-advanced-patterns.md)
  → No: Skip

Long-running operations (>5s)?
  → Yes: Add Progress notifications
  → No: Skip

File system access needed?
  → Yes: Add Roots for permission boundaries
  → No: Skip

Production deployment?
  → Yes: Configure StreamableHTTP (references/mcp-advanced-patterns.md)
  → No: Use stdio
```

---

## MCP-Wrapping Skill Generation

When generating a SKILL.md that wraps an MCP server:

### Intelligence Layer Pattern

The skill adds value OVER raw MCP by:
1. **Deciding WHEN** to call the MCP server (trigger logic)
2. **Filtering WHAT** results to show (token optimization)
3. **Handling HOW** errors are recovered (retry, fallback)
4. **Encoding WHY** certain patterns matter (domain expertise)

See `references/skill-wrapping-patterns.md` for complete pattern.

### Wrapping Skill Structure
```markdown
---
name: {skill-name}
description: |
  [What it does] with [MCP server name].
  This skill should be used when users [triggers].
---

# Skill Name

## What This Skill Does / Does NOT Do
## Before Implementation (context gathering)
## Required Clarifications (user-specific)
## Workflow (when/how to call MCP tools)
## Token Optimization (filter strategies)
## Error Recovery (MCP-specific failures)
## Output Checklist
```

---

## Error Handling

| Scenario | Detection | Action |
|----------|-----------|--------|
| Invalid tool parameters | Pydantic validation error | Return `{"error": "Invalid input: {details}"}` |
| External service down | ConnectionError / Timeout | Return error with `retryable: true`, suggest retry |
| Authentication failure | 401/403 from external API | Return clear message, prompt for credential check |
| Resource not found | 404 or missing data | Return `{"error": "Resource not found: {uri}"}` |
| Server crash | Unhandled exception | Log via `ctx.error()`, return safe JSON-RPC error |

---

## Output Checklist

Before delivering any MCP Server or Skill, verify ALL items:

### Architecture
- [ ] Host-Client-Server boundaries respected
- [ ] Server is standalone process (not embedded in host)
- [ ] Transport configured correctly (stdio or StreamableHTTP)

### Code Quality
- [ ] All tools have typed parameters and docstrings
- [ ] All handlers are `async def`
- [ ] No hardcoded secrets or credentials
- [ ] Error handling in every tool (try/except with structured return)
- [ ] Input validation at tool boundaries

### Packaging
- [ ] `pyproject.toml` has correct dependencies
- [ ] Entry point configured for `uv run` or `pip install`
- [ ] Client configuration example provided

### Testing
- [ ] Test file scaffold with at least one test per tool
- [ ] MCP Inspector command documented for manual testing

### Security
- [ ] Environment variables for all secrets
- [ ] Path validation if filesystem access (no traversal)
- [ ] Input sanitization on all tool parameters
- [ ] No sensitive data in error messages or logs

---

## Reference Files

| File | When to Read |
|------|--------------|
| `references/mcp-server-architecture.md` | Core MCP concepts: Host/Client/Server, JSON-RPC, primitives |
| `references/mcp-advanced-patterns.md` | Context, sampling, progress, roots, StreamableHTTP |
| `references/mcp-server-examples.md` | Complete code examples for database, API, filesystem servers |
| `references/skill-wrapping-patterns.md` | Creating SKILL.md files that wrap MCP servers |
| `references/project-structure.md` | Optimized folder layouts, pyproject.toml, entry points |
| `references/anti-patterns-and-security.md` | Common MCP mistakes, security checklist |

## Asset Templates

| Template | Purpose |
|----------|---------|
| `assets/templates/server_basic.py` | Basic MCP server with tools only |
| `assets/templates/server_advanced.py` | Advanced server with context, sampling, progress |
| `assets/templates/pyproject_template.toml` | Package configuration with MCP dependencies |
| `assets/templates/mcp_config_template.json` | Claude Desktop/Code client configuration |

## Official Documentation

| Resource | URL | Use For |
|----------|-----|---------|
| MCP Specification | https://spec.modelcontextprotocol.io | Protocol details |
| MCP Python SDK | https://github.com/modelcontextprotocol/python-sdk | Python implementation |
| MCP TypeScript SDK | https://github.com/modelcontextprotocol/typescript-sdk | TypeScript implementation |
| FastMCP Docs | https://gofastmcp.com | FastMCP framework |
| MCP Inspector | https://inspector.modelcontextprotocol.io | Testing servers |
| MCP Servers Registry | https://github.com/modelcontextprotocol/servers | Community servers |

Last verified: February 2026 (MCP Python SDK 1.x, MCP spec 2025-06-18).

When MCP SDK updates:
1. Check `references/mcp-server-architecture.md` for protocol changes
2. Update `references/mcp-server-examples.md` for API changes
3. Verify `assets/templates/` still match current SDK patterns

For patterns not covered in references, fetch from official MCP docs.
