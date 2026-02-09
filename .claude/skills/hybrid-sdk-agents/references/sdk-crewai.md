# CrewAI

Complete patterns for building agents with CrewAI.

---

## Overview

CrewAI is a role-based multi-agent orchestration framework. Agents are assigned roles, goals, and backstories. They collaborate through Crews (autonomous collaboration) and Flows (deterministic orchestration). 30K+ GitHub stars, 1M+ monthly downloads.

**Install:**
```bash
pip install crewai crewai-tools
```

---

## Core Architecture: Crews

### Agent Definition

```python
from crewai import Agent, Task, Crew, LLM

llm = LLM(model="anthropic/claude-sonnet-4-5-20250929")

researcher = Agent(
    role="Senior Research Analyst",
    goal="Discover cutting-edge developments in AI",
    backstory="You're a seasoned researcher at a leading tech think tank.",
    tools=[search_tool, web_scrape_tool],
    llm=llm,
    verbose=True,
    allow_delegation=True,
    max_iter=15
)

writer = Agent(
    role="Tech Content Writer",
    goal="Write engaging articles about AI developments",
    backstory="You're a renowned content writer specializing in tech.",
    tools=[],
    llm=llm,
)
```

### Task Definition

```python
research_task = Task(
    description="Research the latest AI agent frameworks released in 2026.",
    expected_output="A detailed report with key findings and comparisons.",
    agent=researcher,
    output_file="research_report.md"
)

writing_task = Task(
    description="Write a blog post based on the research report.",
    expected_output="A 1500-word engaging blog post.",
    agent=writer,
    context=[research_task]  # This task depends on research_task output
)
```

### Crew Assembly

```python
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, writing_task],
    process="sequential",  # or "hierarchical"
    verbose=True,
    memory=True,
    max_rpm=10  # Rate limiting
)

result = crew.kickoff()
print(result)
```

---

## Process Types

### Sequential (Default)

Tasks execute in order. Each task can use output from previous tasks via `context`.

```python
crew = Crew(
    agents=[agent1, agent2, agent3],
    tasks=[task1, task2, task3],
    process="sequential"
)
```

### Hierarchical

A manager agent coordinates. Workers report to the manager.

```python
crew = Crew(
    agents=[researcher, writer, editor],
    tasks=[research_task, writing_task, edit_task],
    process="hierarchical",
    manager_llm=LLM(model="anthropic/claude-sonnet-4-5-20250929")
)
```

---

## Flows (Deterministic Orchestration)

For complex workflows with branching, state management, and event-driven execution:

```python
from crewai.flow.flow import Flow, start, listen, router

class ContentPipeline(Flow):
    @start()
    def gather_requirements(self):
        """First step — gather input."""
        self.state["topic"] = self.inputs.get("topic", "AI Agents")
        return self.state["topic"]

    @listen(gather_requirements)
    def research(self, topic):
        """Research the topic using a crew."""
        crew = Crew(agents=[researcher], tasks=[research_task])
        result = crew.kickoff(inputs={"topic": topic})
        self.state["research"] = result.raw
        return result.raw

    @router(research)
    def quality_check(self, research_output):
        """Route based on research quality."""
        if len(research_output) > 1000:
            return "write"
        return "research_more"

    @listen("write")
    def write_article(self):
        crew = Crew(agents=[writer], tasks=[writing_task])
        return crew.kickoff(inputs={"research": self.state["research"]})

    @listen("research_more")
    def deeper_research(self):
        # Re-run research with more specific prompts
        return self.research(self.state["topic"] + " detailed analysis")

# Execute
pipeline = ContentPipeline()
result = pipeline.kickoff(inputs={"topic": "Multi-Agent Systems"})
```

---

## Tools

### Built-in Tools

```python
from crewai_tools import (
    SerperDevTool,       # Web search
    ScrapeWebsiteTool,   # Web scraping
    FileReadTool,        # Read files
    DirectoryReadTool,   # List directory
    CodeInterpreterTool  # Execute code
)

agent = Agent(
    role="Researcher",
    tools=[SerperDevTool(), ScrapeWebsiteTool()]
)
```

### Custom Tools

```python
from crewai.tools import tool

@tool("Database Query")
def query_database(sql: str) -> str:
    """Execute a SQL query against the analytics database."""
    # Implementation
    return json.dumps(results)
```

---

## Memory

```python
crew = Crew(
    agents=[...],
    tasks=[...],
    memory=True,  # Enables all memory types
    # Memory types:
    # - Short-term: Current conversation context
    # - Long-term: Persistent across sessions (vector store)
    # - Entity: Remembers entities mentioned in conversations
)
```

---

## Best Practices

- Give agents specific roles and clear goals (role-based prompting)
- Use `backstory` to establish expertise and personality
- Set `max_iter` to prevent infinite loops (default 15)
- Use `context` on tasks to chain outputs
- Use `sequential` for simple pipelines, `hierarchical` for complex coordination
- Use Flows for enterprise workflows with branching and state
- Set `max_rpm` for API rate limiting
- Enable `memory=True` for multi-session agents
- Use `output_file` on tasks for persistent outputs
- `allow_delegation=True` lets agents delegate to team members
