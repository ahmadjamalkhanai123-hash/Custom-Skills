/**
 * {{AGENT_NAME}} — Built with OpenAI Agents SDK (TypeScript).
 *
 * {{AGENT_DESCRIPTION}}
 */

import { Agent, Runner } from "@openai/agents";
import { z } from "zod";

// Ensure API key is set
if (!process.env.OPENAI_API_KEY) {
  throw new Error("Set OPENAI_API_KEY environment variable");
}

// --- Tools ---

const {{TOOL_NAME}} = {
  name: "{{TOOL_NAME}}",
  description: "{{TOOL_DESCRIPTION}}",
  parameters: z.object({
    {{TOOL_PARAM}}: z.string().describe("{{TOOL_PARAM_DESCRIPTION}}"),
  }),
  execute: async ({ {{TOOL_PARAM}} }: { {{TOOL_PARAM}}: string }) => {
    try {
      // Implementation here
      return JSON.stringify({ result: "success", data: {{TOOL_PARAM}} });
    } catch (error) {
      return JSON.stringify({ error: String(error), retryable: false });
    }
  },
};

// --- Agents ---

const {{SPECIALIST_AGENT}} = new Agent({
  name: "{{SPECIALIST_NAME}}",
  instructions: "{{SPECIALIST_INSTRUCTIONS}}",
  tools: [{{SPECIALIST_TOOLS}}],
  model: "gpt-4o",
});

const mainAgent = new Agent({
  name: "{{AGENT_NAME}}",
  instructions: "{{AGENT_INSTRUCTIONS}}",
  model: "gpt-4o",
  tools: [{{TOOL_NAME}}],
  handoffs: [{{SPECIALIST_AGENT}}],
});

// --- Runner ---

export async function runAgent(prompt: string): Promise<string> {
  const result = await Runner.run(mainAgent, prompt, {
    maxTurns: {{MAX_TURNS}},
  });
  return result.finalOutput;
}

// --- Entry Point ---

async function main() {
  const result = await runAgent("{{DEFAULT_PROMPT}}");
  console.log(`Result: ${result}`);
}

main().catch(console.error);
