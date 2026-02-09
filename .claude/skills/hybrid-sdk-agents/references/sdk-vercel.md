# Vercel AI SDK

Complete patterns for building agents with the Vercel AI SDK.

---

## Overview

Full-stack TypeScript SDK for building AI applications. Provides `generateText` and `streamText` for LLM interaction, Zod-validated tool schemas, multi-step agent loops, and edge deployment. Best for web applications with AI-powered features.

**Install:**
```bash
npm install ai @ai-sdk/anthropic  # or @ai-sdk/openai
```

---

## Core API: generateText / streamText

### Basic Agent

```typescript
import { generateText } from "ai";
import { anthropic } from "@ai-sdk/anthropic";

const { text } = await generateText({
  model: anthropic("claude-sonnet-4-5-20250929"),
  prompt: "Explain quantum computing in simple terms",
});
```

### Streaming Agent

```typescript
import { streamText } from "ai";
import { anthropic } from "@ai-sdk/anthropic";

const result = streamText({
  model: anthropic("claude-sonnet-4-5-20250929"),
  prompt: "Write a story about AI agents",
});

for await (const chunk of result.textStream) {
  process.stdout.write(chunk);
}
```

---

## Tool Calling with Zod Schemas

```typescript
import { generateText, tool } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { z } from "zod";

const weatherTool = tool({
  description: "Get weather for a location",
  parameters: z.object({
    city: z.string().describe("City name"),
    unit: z.enum(["celsius", "fahrenheit"]).default("celsius"),
  }),
  execute: async ({ city, unit }) => {
    // Implementation
    return { temperature: 22, unit, city, condition: "sunny" };
  },
});

const createTicketTool = tool({
  description: "Create a support ticket",
  parameters: z.object({
    title: z.string().min(1).max(200),
    priority: z.enum(["low", "medium", "high", "critical"]),
    description: z.string(),
  }),
  execute: async ({ title, priority, description }) => {
    return { id: "TICKET-456", title, priority, status: "created" };
  },
});

const { text, steps } = await generateText({
  model: anthropic("claude-sonnet-4-5-20250929"),
  tools: { weather: weatherTool, createTicket: createTicketTool },
  maxSteps: 10,  // Enable multi-step agent loop
  prompt: "What's the weather in London? If it's rainy, create a ticket.",
});
```

---

## Multi-Step Agent Loop

The agent loop runs automatically when `maxSteps > 1`:

```typescript
const { text, steps, finishReason } = await generateText({
  model: anthropic("claude-sonnet-4-5-20250929"),
  tools: { search, analyze, report },
  maxSteps: 20,  // Max iterations before stopping
  prompt: "Research AI frameworks and write a comparison report",
});

// Inspect each step
for (const step of steps) {
  console.log(`Step: ${step.toolCalls?.map(t => t.toolName).join(", ")}`);
}
```

### Loop Control (AI SDK 5+)

```typescript
const result = await generateText({
  model: anthropic("claude-sonnet-4-5-20250929"),
  tools: { search, analyze },
  maxSteps: 20,
  stopWhen: (options) => {
    // Custom stop condition
    return options.steps.length >= 5 && options.finishReason === "stop";
  },
  prepareStep: (options) => {
    // Modify tools/settings per step
    if (options.steps.length > 10) {
      return { toolChoice: "none" }; // Force final answer
    }
    return {};
  },
  prompt: "Analyze this codebase",
});
```

---

## Human-in-the-Loop (Tool Approval)

```typescript
const dangerousTool = tool({
  description: "Delete a database record",
  parameters: z.object({ id: z.string() }),
  needsApproval: true,  // Requires human review
  execute: async ({ id }) => {
    return await deleteRecord(id);
  },
});
```

---

## Streaming with React (Next.js)

### Server Route

```typescript
// app/api/chat/route.ts
import { streamText } from "ai";
import { anthropic } from "@ai-sdk/anthropic";

export async function POST(req: Request) {
  const { messages } = await req.json();

  const result = streamText({
    model: anthropic("claude-sonnet-4-5-20250929"),
    messages,
    tools: { search: searchTool, calculate: calcTool },
    maxSteps: 10,
  });

  return result.toDataStreamResponse();
}
```

### Client Component

```typescript
// app/page.tsx
"use client";
import { useChat } from "@ai-sdk/react";

export default function Chat() {
  const { messages, input, handleInputChange, handleSubmit } = useChat({
    api: "/api/chat",
  });

  return (
    <div>
      {messages.map((m) => (
        <div key={m.id}>{m.role}: {m.content}</div>
      ))}
      <form onSubmit={handleSubmit}>
        <input value={input} onChange={handleInputChange} />
      </form>
    </div>
  );
}
```

---

## Multi-Agent via Tool Delegation

```typescript
import { generateText, tool } from "ai";
import { z } from "zod";

// Agent as a tool — delegate to specialized agent
const researchAgent = tool({
  description: "Delegate research tasks to the research specialist",
  parameters: z.object({ query: z.string() }),
  execute: async ({ query }) => {
    const { text } = await generateText({
      model: anthropic("claude-sonnet-4-5-20250929"),
      system: "You are a research specialist. Be thorough and factual.",
      tools: { search: searchTool },
      maxSteps: 5,
      prompt: query,
    });
    return text;
  },
});

// Orchestrator uses sub-agents as tools
const { text } = await generateText({
  model: anthropic("claude-sonnet-4-5-20250929"),
  tools: { research: researchAgent, write: writerAgent },
  maxSteps: 10,
  prompt: "Research AI agents and write a summary",
});
```

---

## Provider Support

```typescript
import { anthropic } from "@ai-sdk/anthropic";
import { openai } from "@ai-sdk/openai";
import { google } from "@ai-sdk/google";

// Switch models per agent
const researcher = anthropic("claude-sonnet-4-5-20250929");
const writer = openai("gpt-4o");
const summarizer = google("gemini-2.0-flash");
```

---

## Best Practices

- Use Zod schemas for all tool parameters (validated at runtime)
- Set `maxSteps` to prevent infinite loops (default 1 = no loop)
- Use `streamText` for real-time user-facing responses
- Use `generateText` for background processing
- Use `stopWhen` and `prepareStep` for fine-grained loop control
- Use `needsApproval: true` for destructive operations
- Use `@ai-sdk/react` hooks for Next.js integration
- Deploy to Vercel Edge for low-latency global distribution
- Use `toDataStreamResponse()` for server-to-client streaming
- Keep tools focused — one tool per action, not mega-tools
