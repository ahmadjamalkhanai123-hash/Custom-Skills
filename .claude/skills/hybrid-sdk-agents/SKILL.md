---
name: hybrid-sdk-agents
description: |
  Creates production-ready AI agents using any combination of hybrid SDKs including
  Anthropic Agent SDK, OpenAI Agents SDK, LangGraph, CrewAI, AutoGen/AG2, and Vercel AI SDK.
  This skill should be used when users want to build custom agents, create multi-agent
  systems, scaffold agent projects, select the right SDK for their use case, or develop
  global-scale production agent architectures from zero to deployment.
---

# Hybrid SDK Agents

Build production-ready AI agents using any SDK — from single agents to global-scale multi-agent systems.

## What This Skill Does

- Selects optimal SDK(s) based on use case, scale, and constraints
- Creates complete agent projects with proper architecture and structure
- Builds single-agent, multi-agent, orchestrator, supervisor, and swarm patterns
- Implements tool integration including MCP servers, function calling, and custom tools
- Configures memory systems, guardrails, observability, and deployment
- Generates hybrid architectures combining multiple SDKs for complex systems
- Handles any agent domain: coding, research, customer support, data processing, DevOps, etc.

## What This Skill Does NOT Do

- Deploy agents to production infrastructure (scaffolds deployment configs only)
- Manage cloud credentials or secrets provisioning
- Train or fine-tune LLM models
- Build MCP servers (use `mcp-skills` skill for that)
- Handle billing or API key management for LLM providers

---

## Before Implementation

Gather context to ensure successful implementation:

| Source | Gather |
|--------|--------|
| **Codebase** | Existing project structure, language (Python/TypeScript/both), package manager, frameworks |
| **Conversation** | User's agent requirements, scale targets, SDK preferences, deployment target |
| **Skill References** | SDK patterns from `references/` (API examples, architecture, anti-patterns) |
| **User Guidelines** | Team conventions, security requirements, compliance constraints |

Ensure all required context is gathered before implementing.
Only ask user for THEIR specific requirements (SDK expertise is in this skill).

---

## Required Clarifications

Before building, ask:

1. **Agent Purpose**: "What will your agent(s) do?"
   - Code generation / review / debugging
   - Research / data analysis / RAG
   - Customer support / task automation
   - Multi-step workflow orchestration
   - Custom domain (describe)

2. **Scale & Complexity**: "Single agent or multi-agent system?"
   - Single agent with tools (simplest)
   - Multi-agent with handoffs (moderate)
   - Orchestrator/supervisor pattern (complex)
   - Swarm / autonomous fleet (advanced)

3. **Language**: "Python, TypeScript, or both?"
   - Python (Recommended — widest SDK support)
   - TypeScript (Vercel AI SDK, Anthropic Agent SDK, OpenAI Agents SDK)
   - Both (hybrid architecture)

## Optional Clarifications

4. **SDK Preference**: "Any preferred SDK?"
   - Let skill recommend based on use case (default)
   - Specific SDK requested
   - Hybrid (multiple SDKs)

5. **Deployment Target**: "Where will this run?"
   - Local development (default)
   - Cloud (AWS/GCP/Azure)
   - Edge / Serverless
   - Containerized (Docker/K8s)

6. **Integration Needs**: "External systems to connect?"
   - MCP servers
   - REST/GraphQL APIs
   - Databases
   - Custom tools

Note: Start with questions 1-2. Follow up with 3-6 based on context.

### Defaults (If Not Specified)

| Clarification | Default |
|---------------|---------|
| Agent Purpose | Infer from conversation |
| Scale | Single agent |
| Language | Python |
| SDK | Recommend based on use case |
| Deployment | Local development |
| Integration | None (add tools as needed) |

### Before Asking

1. Check conversation history for prior answers
2. Infer from existing project files (pyproject.toml, package.json, existing agents)
3. Only ask what cannot be determined from context

---

## SDK Selection Decision Tree

```
What's the primary need?

Autonomous code/file agent with built-in tools?
  → Anthropic Agent SDK (references/sdk-anthropic.md)

Lightweight multi-agent with handoffs + guardrails?
  → OpenAI Agents SDK (references/sdk-openai.md)

Complex stateful workflows with conditional routing?
  → LangGraph (references/sdk-langgraph.md)

Role-based team of specialized agents?
  → CrewAI (references/sdk-crewai.md)

Full-stack web app with streaming AI?
  → Vercel AI SDK (references/sdk-vercel.md)

Enterprise .NET/Java + Azure integration?
  → Microsoft Agent Framework / AG2 (references/sdk-autogen.md)

Multiple needs → Hybrid architecture:
  - LangGraph orchestrator + Anthropic Agent SDK subagents
  - CrewAI crews + OpenAI Agents SDK tools
  - Vercel AI SDK frontend + LangGraph backend
```

### SDK Comparison Matrix

| Factor | Anthropic | OpenAI | LangGraph | CrewAI | Vercel | AG2 |
|--------|-----------|--------|-----------|--------|--------|-----|
| Language | Py/TS | Py/TS | Python | Python | TS/JS | Py/C# |
| Multi-agent | Subagents | Handoffs | Graph nodes | Crews | Loop | GroupChat |
| Tool system | Built-in | Functions | Functions | Tools | Zod schema | Functions |
| MCP support | Native | Built-in | Via tools | Plugin | Via tools | Plugin |
| Memory | Sessions | Context | Checkpoints | Memory | Context | Memory |
| Guardrails | Hooks | Guardrails | Interrupts | Guardrails | stopWhen | Guards |
| Observability | Hooks | Tracing | LangSmith | Logging | OpenTelemetry | Logging |
| Best for | Code agents | Chat agents | Workflows | Teams | Web apps | Enterprise |

---

## Workflow

```
Select SDK → Architecture → Structure → Implement → Integrate → Test → Deploy
```

### Step 1: Select SDK(s)

Use decision tree above. Read relevant `references/sdk-*.md` for chosen SDK(s).

### Step 2: Choose Architecture Pattern

Read `references/architecture-patterns.md` for detailed patterns:

| Pattern | When to Use | SDKs |
|---------|-------------|------|
| **Single Agent** | One purpose, simple tools | All SDKs |
| **Router/Triage** | Classify then delegate | OpenAI, Anthropic |
| **Pipeline** | Sequential processing stages | LangGraph, CrewAI |
| **Orchestrator** | Central coordinator + workers | LangGraph, CrewAI |
| **Supervisor** | Manager reviews worker output | LangGraph, CrewAI |
| **Swarm** | Autonomous peer agents | OpenAI, AG2 |
| **Hybrid** | Different SDKs for different layers | Multi-SDK |

### Step 3: Generate Project Structure

**Python agent project:**
```
{agent-name}/
├── src/{package}/
│   ├── __init__.py
│   ├── agent.py            ← Main agent definition
│   ├── tools/              ← Custom tool definitions
│   │   ├── __init__.py
│   │   └── {tool_name}.py
│   ├── prompts/            ← System prompts / templates
│   │   └── {agent_name}.md
│   └── config.py           ← Settings, env vars, constants
├── tests/
│   ├── test_agent.py
│   └── test_tools.py
├── pyproject.toml
├── .env.example
└── README.md
```

**TypeScript agent project:**
```
{agent-name}/
├── src/
│   ├── agent.ts            ← Main agent definition
│   ├── tools/              ← Custom tool definitions
│   │   └── {tool_name}.ts
│   ├── prompts/            ← System prompts
│   │   └── {agent_name}.md
│   └── config.ts           ← Settings, env vars
├── tests/
│   └── agent.test.ts
├── package.json
├── tsconfig.json
├── .env.example
└── README.md
```

For simple agents (1-2 tools), flatten to single `agent.py`/`agent.ts`.

### Step 4: Implement Agent Code

Read the specific SDK reference for implementation patterns:
- `references/sdk-anthropic.md` → query() API, built-in tools, subagents, hooks
- `references/sdk-openai.md` → Agent/Runner, handoffs, guardrails, tracing
- `references/sdk-langgraph.md` → StateGraph, nodes, edges, checkpointing
- `references/sdk-crewai.md` → Crew, Agent, Task, Flow
- `references/sdk-vercel.md` → generateText, streamText, tool schemas
- `references/sdk-autogen.md` → ConversableAgent, GroupChat, nested chats

### Step 5: Add Integrations

From `references/production-patterns.md`:
- **MCP Servers**: Connect external tools via MCP protocol
- **Memory**: Short-term (context), long-term (vector stores), episodic (checkpoints)
- **Guardrails**: Input validation, output filtering, human-in-the-loop
- **Observability**: Tracing, logging, metrics

### Step 6: Test Agent

- Unit test individual tools
- Integration test agent loops with mock LLM responses
- Eval test with benchmark prompts
- Safety test with adversarial inputs

### Step 7: Deploy

Match deployment to scale requirements:

| Scale | Deployment |
|-------|-----------|
| Development | Local process |
| Team | Docker container |
| Production | K8s / Cloud Run / ECS |
| Global | Multi-region + CDN + load balancer |
| Edge | Vercel Edge / Cloudflare Workers |

---

## Output Specification

Every generated agent project includes:

### Required Components
- [ ] Agent definition with system prompt and tool configuration
- [ ] Typed tool definitions with input validation
- [ ] Error handling for LLM failures, tool errors, and timeouts
- [ ] Environment variable configuration (no hardcoded secrets)
- [ ] Package configuration (pyproject.toml or package.json)

### Required Patterns
- [ ] Async-first implementation (all SDKs are async)
- [ ] Structured output from tools (dict/object, not raw strings)
- [ ] Graceful degradation on tool failure
- [ ] Token-aware context management
- [ ] Clean separation: agent logic / tools / prompts / config

---

## Domain Standards

### Must Follow

- [ ] Use official SDK imports (not deprecated APIs)
- [ ] Type all tool parameters and return values
- [ ] Use async/await for all agent and tool handlers
- [ ] Store secrets in environment variables
- [ ] Implement retry with backoff for LLM API calls
- [ ] Set appropriate max_tokens and temperature per use case
- [ ] Use structured tool results (not raw strings)
- [ ] Log agent actions for debugging (SDK-native tracing)

### Must Avoid

- Hardcoded API keys or secrets in source code
- Synchronous blocking calls in async handlers
- Unbounded agent loops (always set max_steps/max_turns)
- Tools with >7 parameters (use Pydantic/Zod models)
- Catching all exceptions silently (log and return structured errors)
- print() for logging (use SDK-native tracing/logging)
- Mutable global state (breaks concurrent execution)
- Sending full conversation history when not needed (token waste)

---

## Error Handling

| Scenario | Detection | Action |
|----------|-----------|--------|
| LLM API rate limit | 429 response | Retry with exponential backoff |
| LLM API timeout | Timeout exception | Retry once, then fail gracefully |
| Tool execution error | Exception in tool | Return structured error, let agent retry |
| Invalid tool params | Validation error | Return clear error message to agent |
| Agent stuck in loop | max_steps reached | Terminate with partial results |
| Memory overflow | Context too large | Summarize/truncate conversation history |

---

## Output Checklist

Before delivering any agent project, verify ALL items:

### Architecture
- [ ] SDK choice justified for use case
- [ ] Architecture pattern appropriate for complexity
- [ ] Agent boundaries clearly defined (single vs multi)

### Code Quality
- [ ] All tools typed with proper schemas
- [ ] All handlers are async
- [ ] No hardcoded secrets
- [ ] Error handling in every tool
- [ ] Max steps/turns configured (no infinite loops)
- [ ] Structured logging via SDK-native tracing

### Integration
- [ ] MCP servers configured if needed
- [ ] Memory system appropriate for use case
- [ ] Guardrails implemented for production

### Packaging
- [ ] Package config with correct dependencies
- [ ] .env.example with all required variables
- [ ] Entry point configured for execution

### Testing
- [ ] Test scaffold for tools and agent flows
- [ ] Eval prompts for agent behavior testing

### Security
- [ ] Environment variables for all secrets
- [ ] Input validation on all tool parameters
- [ ] Output sanitization where needed
- [ ] No sensitive data in logs or error messages

---

## Reference Files

| File | When to Read |
|------|--------------|
| `references/sdk-anthropic.md` | Building with Claude Agent SDK: query(), tools, subagents, hooks, MCP |
| `references/sdk-openai.md` | Building with OpenAI Agents SDK: Agent, Runner, handoffs, guardrails, tracing |
| `references/sdk-langgraph.md` | Building with LangGraph: StateGraph, nodes, edges, checkpointing, LangSmith |
| `references/sdk-crewai.md` | Building with CrewAI: Crews, Flows, role-based agents, sequential/hierarchical |
| `references/sdk-vercel.md` | Building with Vercel AI SDK: generateText, streamText, Zod tools, edge deploy |
| `references/sdk-autogen.md` | Building with AutoGen/AG2/Microsoft Agent Framework |
| `references/architecture-patterns.md` | Cross-SDK patterns: single, multi, orchestrator, supervisor, swarm, hybrid |
| `references/production-patterns.md` | Deployment, observability, guardrails, testing, memory, scaling |
| `references/anti-patterns.md` | Common mistakes across all SDKs with fixes |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scaffold_agent.py` | Generate full agent project structure for any SDK. Usage: `python scaffold_agent.py <name> --sdk <sdk> --path <dir> [--lang python\|typescript]` |

## Asset Templates

### Python Templates

| Template | Purpose |
|----------|---------|
| `assets/templates/agent_anthropic.py` | Claude Agent SDK starter agent |
| `assets/templates/agent_openai.py` | OpenAI Agents SDK starter agent (Python) |
| `assets/templates/agent_langgraph.py` | LangGraph starter agent |
| `assets/templates/agent_crewai.py` | CrewAI starter crew |
| `assets/templates/agent_autogen.py` | AG2/AutoGen starter with GroupChat |
| `assets/templates/hybrid_langgraph_anthropic.py` | Hybrid: LangGraph orchestrator + Anthropic subagents |

### TypeScript Templates

| Template | Purpose |
|----------|---------|
| `assets/templates/agent_vercel.ts` | Vercel AI SDK starter agent with Zod tools + streaming |
| `assets/templates/agent_openai.ts` | OpenAI Agents SDK starter agent (TypeScript) |

## Official Documentation

| Resource | URL | Use For |
|----------|-----|---------|
| Anthropic Agent SDK | https://platform.claude.com/docs/en/agent-sdk/overview | Claude Agent SDK reference |
| OpenAI Agents SDK | https://openai.github.io/openai-agents-python/ | OpenAI Agents reference |
| LangGraph Docs | https://docs.langchain.com/oss/python/langgraph/overview | LangGraph reference |
| CrewAI Docs | https://docs.crewai.com | CrewAI reference |
| Vercel AI SDK | https://ai-sdk.dev/docs/introduction | Vercel AI SDK reference |
| AG2 / AutoGen | https://github.com/ag2ai/ag2 | AG2 reference |
| MCP Specification | https://spec.modelcontextprotocol.io | MCP protocol details |

Last verified: February 2026.

For patterns not covered in references, fetch from official SDK documentation.
