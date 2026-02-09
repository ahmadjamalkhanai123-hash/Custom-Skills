# Skill Wrapping Patterns

How to create SKILL.md files that add intelligence on top of MCP servers.

---

## What is an MCP-Wrapping Skill?

A SKILL.md that guides Claude to use an MCP server intelligently — deciding WHEN to call, HOW to filter results, and WHAT to do with errors.

**Raw MCP server**: Exposes tools. LLM calls them directly.
**Wrapping skill**: Adds domain intelligence OVER the MCP server.

```
Without skill:  User → LLM → MCP tool → raw result
With skill:     User → LLM + Skill intelligence → MCP tool → filtered, optimized result
```

---

## The Intelligence Layer

A wrapping skill adds 4 types of intelligence:

### 1. WHEN to Call (Trigger Logic)

```markdown
## When to Use This MCP Server

Trigger when user:
- Asks to [domain action 1]
- Mentions [domain keyword]
- Needs [domain capability]

Do NOT trigger for:
- [Similar but different domain]
- [Tasks the server can't handle]
```

### 2. WHAT to Filter (Token Optimization)

MCP servers often return more data than needed. The skill filters:

```markdown
## Token Optimization

When calling `search_documents`:
- Set `max_results` to 5 (not default 50)
- Filter by `file_type` matching user's context
- Extract only `title` and `summary` from results (ignore metadata)

When calling `query`:
- Add LIMIT clause (max 20 rows for display)
- SELECT only columns relevant to user's question
- Summarize large result sets instead of showing all rows
```

**Target**: 30%+ token reduction over raw MCP calls.

### 3. HOW to Handle Errors (Recovery)

```markdown
## Error Recovery

| MCP Error | Skill Action |
|-----------|-------------|
| Tool timeout | Retry once with simpler query, then report |
| Auth failure | Tell user to check credentials, provide setup steps |
| Rate limited | Wait and retry, inform user of delay |
| Invalid params | Auto-correct common mistakes (e.g., trailing slash) |
| Server down | Use cached results if available, inform user |
```

### 4. WHY Patterns Matter (Domain Expertise)

```markdown
## Domain Best Practices

When creating database queries:
- Always use parameterized queries (MCP server handles this)
- Prefer `list_tables` before `query` to discover schema
- Use `describe_table` to get column types before writing SQL

When creating tasks:
- Check existing tasks first to avoid duplicates
- Set priority based on context (bug = high, feature = medium)
- Include reproduction steps for bug reports
```

---

## Complete Wrapping Skill Template

```markdown
---
name: {mcp-server}-helper
description: |
  Intelligent assistant for [{MCP server name}] operations.
  This skill should be used when users need to [domain actions],
  [domain queries], or [domain operations].
---

# {Server Name} Helper

Adds intelligence layer over the [{server-name} MCP server].

## What This Skill Does
- Optimizes calls to {server-name} MCP tools
- Filters results for token efficiency
- Handles errors with domain-aware recovery
- Encodes {domain} best practices

## What This Skill Does NOT Do
- Replace the MCP server (server must be configured)
- Handle server deployment or configuration
- Work without the MCP server connected

---

## Before Implementation

| Source | Gather |
|--------|--------|
| **MCP Server** | Verify {server-name} is connected and responding |
| **Conversation** | User's specific {domain} requirements |
| **Skill References** | Domain patterns from `references/` |
| **User Guidelines** | Team conventions |

---

## When to Trigger

| Trigger | MCP Tool to Call |
|---------|-----------------|
| User asks to [action 1] | `tool_name_1` |
| User asks to [action 2] | `tool_name_2` |
| User asks about [data] | `resource_uri` |

## Token Optimization

[Filtering strategies per tool]

## Error Recovery

[Error → Recovery mapping]

## Domain Best Practices

[Encoded expertise for this domain]

## Output Checklist
- [ ] MCP server connection verified
- [ ] Results filtered for relevance
- [ ] Token usage optimized
- [ ] Errors handled gracefully
```

---

## Real Example: Library Docs Wrapping Skill

Based on the `fetch-library-docs` skill pattern that wraps Context7:

### What it wraps
Context7 MCP server (fetches library documentation)

### Intelligence it adds
1. **WHEN**: Triggers during coding work with external libraries
2. **WHAT**: Filters by content type (60-90% token savings)
3. **HOW**: Falls back to WebFetch if MCP fails
4. **WHY**: "Fetch docs before writing code, not after guessing wrong"

### Key patterns
- Content-type filtering reduces tokens dramatically
- Specific library name resolution (not vague queries)
- Version-aware fetching (latest docs, not outdated)
- Graceful degradation to web search

---

## Token Optimization Strategies

### Strategy 1: Result Limiting
```python
# Instead of: search(query)  → 50 results
# Call: search(query, max_results=5)  → 5 results
```

### Strategy 2: Field Selection
```python
# Instead of: get_full_record(id)  → all 30 fields
# Call: get_record(id, fields=["name", "status", "summary"])
```

### Strategy 3: Summarization
```markdown
When query returns >20 rows:
- Show first 5 rows as examples
- Provide aggregate summary (counts, averages)
- Offer to show more if user needs detail
```

### Strategy 4: Caching Awareness
```markdown
For frequently accessed data:
- Note when data was last fetched
- Skip re-fetching if recent (<5 minutes)
- Inform user if using cached results
```

---

## Anti-Patterns in Wrapping Skills

### Too Thin (No Value Added)
```markdown
# BAD: Just repeats MCP tool descriptions
## Tools
- `search`: Searches things
- `create`: Creates things
```

### Too Thick (Bypasses MCP)
```markdown
# BAD: Reimplements what the server does
## Custom Search
1. Read all files manually
2. Parse content with regex
3. Return matches
```

### No Error Handling
```markdown
# BAD: Assumes MCP always works
## Workflow
1. Call search tool
2. Show results
# What if the server is down? Auth fails? Rate limited?
```

### Right Balance
```markdown
# GOOD: Intelligence layer
## Search Workflow
1. Determine optimal search parameters from user context
2. Call `search` with filtered params (limit=10, type=relevant)
3. If error: retry once, then suggest manual alternative
4. Filter results to show top 3 most relevant
5. Provide actionable summary, not raw data
```
