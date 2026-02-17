# Global Agent Production Challenges

**Scope**: Universal — SDK-agnostic, domain-agnostic, scale-agnostic
**Root Cause**: LLMs are probabilistic text predictors being used as decision engines.

---

## 1. Grounding Failure

**Problem**: Agents fabricate information — fake tool outputs, invented APIs, confident wrong answers, plausible but broken code — and present it as fact. There is no error code for "I made this up." Every other agent problem is recoverable. This one is not, because the system doesn't know it failed.

**Solution**:
- Never deliver unverified agent output. Every response passes through deterministic verification before reaching users or downstream agents.
- Validate every tool call result against the actual tool response — reject mismatches.
- Trace every factual claim to a source document. No source = not delivered.
- Use constrained decoding and structured output to limit generation to valid values.

---

## 2. Planning Horizon Collapse

**Problem**: Agent plans degrade after 5 steps. By step 8-12, the agent contradicts earlier decisions. By step 20+, behavior is effectively random. The agent doesn't know its plan is degrading — it continues with full confidence, silently skipping or reinventing steps.

**Solution**:
- Decompose every task into max 5-step sub-plans. Each sub-plan runs in a fresh agent invocation.
- Pass only completed outputs between invocations, not full conversation history.
- Use an external state store (not the LLM's memory) to track plan progress.
- The orchestrator holds the plan. The agent executes one phase.

---

## 3. Tool Use Unreliability

**Problem**: Agents call tools incorrectly 10-30% of the time — wrong parameters, wrong tool selection, hallucinated tool names, missing required fields, wrong data types, ignoring error responses. Schema validation catches type errors but not semantic errors.

**Solution**:
- Strict input validation (Pydantic/JSON Schema) on every tool call.
- Fewer tools is better — 5 focused tools outperform 20 overlapping tools.
- Tool descriptions must be precise and unambiguous.
- Validate tool output before passing to agent. Return clear structured errors, not stack traces.
- Implement idempotency — redundant calls must not cause side effects.

---

## 4. Context Window Saturation

**Problem**: As context fills, agent quality degrades gradually — not at the limit, but starting around 25% capacity. Information at positions 50K-150K gets measurably less attention ("lost in the middle"). At 90%+, system prompts may be pushed out entirely.

**Solution**:
- Compress conversation history aggressively — summaries, not full transcripts.
- Place critical information at the start and end of context (attention anchoring).
- Use external memory (Redis, vector DB) instead of stuffing the context window.
- Implement sliding window with summarization for long conversations.
- Monitor context usage — alert at 60% capacity.

---

## 5. Instruction Following Decay

**Problem**: Agents follow 90% of a 10-line prompt, 60% of a 50-line prompt, 30% of a 100-line prompt. Selective compliance, negation failure ("Do NOT include X" — includes X), conditional failure ("if X then Y, else Z" — always does Y), and format drift after 3-4 responses.

**Solution**:
- Keep instructions under 30 lines. Split longer instructions into phases.
- Use checklists, not paragraphs — models parse lists better than prose.
- Put critical rules first and last (attention anchoring).
- Verify compliance programmatically — never trust the agent's self-report.
- Use structured output (JSON mode) to enforce format compliance.

---

## 6. Multi-Agent State Corruption

**Problem**: Multiple agents sharing state corrupt each other's data through race conditions, lost updates, phantom reads, and stale context propagation. Classic concurrency problems, made worse because agents don't understand concurrency.

**Solution**:
- Each agent gets its own isolated state namespace.
- Shared state requires explicit locking (optimistic or pessimistic).
- Use event sourcing — log state changes, don't overwrite state.
- Implement version vectors — every state read includes a version. Write only if version matches.
- Never let agents directly modify shared databases — route through an API layer.

---

## 7. Evaluation Bankruptcy

**Problem**: No reliable automated way to measure if an agent is production-ready. Output varies per run (same input, different output). LLM-as-judge is inconsistent. Golden datasets fail on non-deterministic output. Manual testing doesn't scale. "Vibe checks" are not engineering.

**Solution**:
- Define deterministic PASS/FAIL criteria: correct tool called, required fields present, response within token limit.
- Separate "did it work" (deterministic checks) from "was it good" (LLM-as-judge with specific rubric).
- Run evals on every prompt change in CI/CD. Minimum 50 test cases. Track pass rate over time.
- Alert on >5% regression. Accept that 100% pass rate is impossible — 90% with known failure modes beats 99% on cherry-picked tests.

---

## 8. Cost-Quality Tradeoff

**Problem**: Every quality improvement increases cost — better models, bigger context, more tool calls, verification layers, retries. But users expect both quality and low cost. These goals directly oppose each other.

**Solution**:
- Route by complexity: simple requests → small model ($0.01), medium → medium model ($0.15), complex → large model ($2.00).
- Cache aggressively — semantic cache (embed query, match similar) reduces costs 40-70%.
- Progressive enhancement: start small, escalate on low confidence.
- Set per-request budget caps ($0.50 catches 99% of runaway loops). Kill requests that exceed budget.

---

## 9. Security Surface Explosion

**Problem**: Every tool is an attack surface. Every prompt is an injection vector. Every output is a potential data leak. Agents create a dynamic attack surface — the LLM decides the code path, and attackers can manipulate that decision through prompt injection, indirect injection via fetched content, and privilege escalation through the agent's permissions.

**Solution**:
- Least privilege by default — read-only unless explicitly needed. Destructive operations require human approval.
- Treat all user input as untrusted. Sanitize before passing to agent.
- Isolate agent execution — sandbox tools in containers, enforce network and filesystem isolation.
- Audit every tool call: who triggered, what tool, what parameters, what result. Alert on anomalies.
- Scan agent responses for PII, secrets, internal URLs before delivery. Never echo raw tool errors.

---

## 10. Alignment Tax

**Problem**: Making agents safe reduces capability. Every safety layer adds latency, reduces flexibility, and blocks legitimate use cases. Basic content filtering blocks 2% of valid requests. Full guardrails block 15%. Human-in-the-loop works perfectly but defeats the purpose of automation.

**Solution**:
- Tiered safety based on risk: read operations → minimal guardrails, write → confirmation, destructive → human approval.
- Domain-specific guardrails, not generic ones. Blocking "rm -rf" in a coding agent = good. Blocking "delete" in all contexts = over-broad.
- Measure false refusal rate alongside safety rate. Track "user had to rephrase because agent refused valid request."
- Use structural permissions (tool-level access control), not prompt-based safety. Deterministic > probabilistic.

---

## Production Roadmap

| Phase | What | Solved By | Blocked By |
|---|---|---|---|
| 1. Architecture | SDK choice, project structure | Skills + scaffold scripts | Nothing |
| 2. Scaffolding | Working code, endpoints, tools | Skills + templates | Nothing |
| 3. Reliability | Validation, guardrails, error handling | Engineering | #1 Grounding, #2 Planning, #3 Tools, #5 Instructions |
| 4. Production | Monitoring, cost control, recovery | Infrastructure | #6 State, #7 Evaluation, #8 Cost, #9 Security |
| 5. Scale | Load testing, optimization, multi-region | Operations | #4 Context, #7 Evaluation, #8 Cost, #10 Alignment |

**Key Insight**: Skills solve Phases 1-2 in hours. The 10 challenges above are what stand between Phase 2 and Phase 5. Without addressing them: demo. With addressing them: product.

---

## Priority by Team Size

**Solo / Small Team** — Fix #1 (Grounding), #3 (Tools), #8 (Cost) first.
**Mid-Size (5-20 engineers)** — Fix #7 (Evaluation), #6 (State), #9 (Security) first.
**Enterprise** — Fix #9 (Security), #7 (Evaluation), #10 (Alignment) first.
