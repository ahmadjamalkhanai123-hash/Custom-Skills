/**
 * {{AGENT_NAME}} — Built with Vercel AI SDK.
 *
 * {{AGENT_DESCRIPTION}}
 */

import { generateText, streamText, tool } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { z } from "zod";

// Ensure API key is set
if (!process.env.ANTHROPIC_API_KEY) {
  throw new Error("Set ANTHROPIC_API_KEY environment variable");
}

// --- Tools ---

const {{TOOL_NAME}} = tool({
  description: "{{TOOL_DESCRIPTION}}",
  parameters: z.object({
    {{TOOL_PARAM}}: z.string().describe("{{TOOL_PARAM_DESCRIPTION}}"),
  }),
  execute: async ({ {{TOOL_PARAM}} }) => {
    try {
      // Implementation here
      return { result: "success", data: {{TOOL_PARAM}} };
    } catch (error) {
      return { error: String(error), retryable: false };
    }
  },
});

// --- Agent (Non-Streaming) ---

export async function runAgent(prompt: string): Promise<string> {
  const { text, steps } = await generateText({
    model: anthropic("claude-sonnet-4-5-20250929"),
    system: "{{SYSTEM_PROMPT}}",
    tools: { {{TOOL_NAME}}: {{TOOL_NAME}} },
    maxSteps: {{MAX_STEPS}},
    prompt,
  });

  // Log tool usage per step
  for (const step of steps) {
    const toolNames = step.toolCalls?.map((t) => t.toolName).join(", ");
    if (toolNames) console.log(`Step tools: ${toolNames}`);
  }

  return text;
}

// --- Agent (Streaming) ---

export async function runAgentStream(prompt: string): Promise<void> {
  const result = streamText({
    model: anthropic("claude-sonnet-4-5-20250929"),
    system: "{{SYSTEM_PROMPT}}",
    tools: { {{TOOL_NAME}}: {{TOOL_NAME}} },
    maxSteps: {{MAX_STEPS}},
    prompt,
  });

  for await (const chunk of result.textStream) {
    process.stdout.write(chunk);
  }
  console.log();
}

// --- Next.js API Route (uncomment for web apps) ---
//
// export async function POST(req: Request) {
//   const { messages } = await req.json();
//   const result = streamText({
//     model: anthropic("claude-sonnet-4-5-20250929"),
//     system: "{{SYSTEM_PROMPT}}",
//     tools: { {{TOOL_NAME}}: {{TOOL_NAME}} },
//     maxSteps: {{MAX_STEPS}},
//     messages,
//   });
//   return result.toDataStreamResponse();
// }

// --- Entry Point ---

async function main() {
  const result = await runAgent("{{DEFAULT_PROMPT}}");
  console.log(`Result: ${result}`);
}

main().catch(console.error);
