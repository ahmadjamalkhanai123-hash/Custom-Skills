# AI Agent Security

## Threat Model for Autonomous AI Systems

### OWASP LLM Top 10 Threats (2025)

| Rank | Threat | Risk | Mitigation |
|------|--------|------|-----------|
| LLM01 | Prompt Injection | CRITICAL | Input sanitization + system prompt protection |
| LLM02 | Insecure Output Handling | HIGH | Output validation + encoding |
| LLM03 | Training Data Poisoning | HIGH | Dataset provenance + validation |
| LLM04 | Model Denial of Service | MEDIUM | Rate limiting + circuit breakers |
| LLM05 | Supply Chain Vulnerabilities | HIGH | SBOM + model signing |
| LLM06 | Sensitive Information Disclosure | HIGH | PII detection + output filtering |
| LLM07 | Insecure Plugin Design | HIGH | Plugin sandboxing + capability control |
| LLM08 | Excessive Agency | CRITICAL | Capability restrictions + human-in-loop |
| LLM09 | Overreliance | MEDIUM | Human validation for critical decisions |
| LLM10 | Model Theft | MEDIUM | API rate limiting + watermarking |

---

## Prompt Injection Defense

### Defense-in-Depth Pattern

```python
import re
import hashlib
from typing import Optional
from anthropic import Anthropic

SYSTEM_PROMPT_HASH = None  # Computed at startup

def init_system_prompt(system_prompt: str) -> str:
    """Initialize and hash the system prompt to detect tampering."""
    global SYSTEM_PROMPT_HASH
    SYSTEM_PROMPT_HASH = hashlib.sha256(system_prompt.encode()).hexdigest()
    return system_prompt

def detect_prompt_injection(user_input: str) -> tuple[bool, str]:
    """Multi-layer prompt injection detection."""
    # Layer 1: Pattern-based detection
    injection_patterns = [
        r"ignore\s+(previous|all|above)\s+instructions?",
        r"forget\s+(your|all)\s+(previous\s+)?instructions?",
        r"you\s+are\s+now\s+(a|an)\s+\w+",
        r"pretend\s+(you\s+are|to\s+be)",
        r"disregard\s+(your\s+)?(system\s+)?prompt",
        r"</?(system|human|assistant)>",   # XML/tag injection
        r"\[INST\]|\[\/INST\]",           # Llama token injection
        r"<\|im_start\|>|<\|im_end\|>",   # ChatML token injection
        r"jailbreak|DAN\s+mode|developer\s+mode",
    ]

    for pattern in injection_patterns:
        if re.search(pattern, user_input, re.IGNORECASE):
            return True, f"Pattern injection detected: {pattern}"

    # Layer 2: Length anomaly (very long inputs may hide injections)
    if len(user_input) > 10000:
        return True, "Input exceeds maximum allowed length"

    # Layer 3: Encoding attack detection
    suspicious_encodings = [
        "\u202e",  # Right-to-left override
        "\u200b",  # Zero-width space
        "\u00ad",  # Soft hyphen
    ]
    if any(char in user_input for char in suspicious_encodings):
        return True, "Suspicious Unicode encoding detected"

    return False, ""

def sanitize_input(user_input: str) -> str:
    """Sanitize user input before passing to LLM."""
    # Remove null bytes
    sanitized = user_input.replace("\x00", "")

    # Strip leading/trailing whitespace
    sanitized = sanitized.strip()

    # Escape special XML-like markers that might confuse the model
    sanitized = sanitized.replace("<|", "< |").replace("|>", "| >")

    return sanitized

class SecureAgentClient:
    """Production-grade secure LLM agent wrapper."""

    def __init__(
        self,
        system_prompt: str,
        allowed_tools: list[str],
        max_tokens: int = 4096,
        max_tool_calls: int = 10,
    ):
        self.client = Anthropic()
        self.system_prompt = init_system_prompt(system_prompt)
        self.allowed_tools = set(allowed_tools)
        self.max_tokens = max_tokens
        self.max_tool_calls = max_tool_calls
        self.tool_call_count = 0

    def run(self, user_message: str) -> str:
        # Step 1: Injection detection
        is_injection, reason = detect_prompt_injection(user_message)
        if is_injection:
            self._log_security_event("PROMPT_INJECTION", reason, user_message)
            return "I cannot process this request. Please try rephrasing."

        # Step 2: Input sanitization
        safe_input = sanitize_input(user_message)

        # Step 3: Execute with guardrails
        try:
            return self._execute_with_guardrails(safe_input)
        except Exception as e:
            self._log_security_event("EXECUTION_ERROR", str(e), user_message)
            return "An error occurred processing your request."

    def _validate_tool_call(self, tool_name: str, tool_input: dict) -> bool:
        """Validate tool call against allowlist before execution."""
        # Check tool is allowed
        if tool_name not in self.allowed_tools:
            self._log_security_event(
                "UNAUTHORIZED_TOOL",
                f"Agent requested disallowed tool: {tool_name}",
                str(tool_input)
            )
            return False

        # Check tool call budget
        self.tool_call_count += 1
        if self.tool_call_count > self.max_tool_calls:
            self._log_security_event(
                "TOOL_BUDGET_EXCEEDED",
                f"Tool calls exceeded limit of {self.max_tool_calls}",
                tool_name
            )
            return False

        return True

    def _log_security_event(self, event_type: str, reason: str, context: str):
        """Log security events to audit trail (send to SIEM in production)."""
        import json, time
        event = {
            "timestamp": time.time(),
            "event_type": event_type,
            "reason": reason,
            "context": context[:500],  # Truncate for log safety
            "system_prompt_hash": SYSTEM_PROMPT_HASH,
        }
        print(f"SECURITY_EVENT: {json.dumps(event)}")
```

---

## Excessive Agency Prevention

### Principle of Minimal Capability

```python
# WRONG: Give agent full filesystem access
tools = [
    {"name": "bash", "description": "Execute any bash command"},
    {"name": "read_file", "description": "Read any file on the system"},
    {"name": "write_file", "description": "Write any file on the system"},
]

# CORRECT: Scoped tools with explicit boundaries
tools = [
    {
        "name": "read_task_file",
        "description": "Read a task configuration file from /app/tasks/ directory only",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "pattern": "^[a-zA-Z0-9_-]+\\.json$",  # Strict filename validation
                    "description": "Task filename (no path traversal allowed)"
                }
            },
            "required": ["filename"]
        }
    },
    {
        "name": "submit_task_result",
        "description": "Submit task results to the results queue",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "maxLength": 64},
                "result": {"type": "string", "maxLength": 10000},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
            },
            "required": ["task_id", "result"]
        }
    }
]
```

### Human-in-the-Loop for Sensitive Operations

```python
SENSITIVE_OPERATIONS = [
    "delete", "drop", "truncate", "remove",
    "send_email", "transfer_money", "modify_user",
    "grant_permission", "deploy_to_production"
]

def requires_human_approval(tool_name: str, tool_input: dict) -> bool:
    """Check if operation requires human approval before execution."""
    # Check tool name
    if any(op in tool_name.lower() for op in SENSITIVE_OPERATIONS):
        return True

    # Check input for sensitive keywords
    input_str = str(tool_input).lower()
    if any(op in input_str for op in SENSITIVE_OPERATIONS):
        return True

    # High-value financial thresholds
    if "amount" in tool_input and tool_input.get("amount", 0) > 1000:
        return True

    return False

async def request_human_approval(tool_name: str, tool_input: dict) -> bool:
    """Send approval request to human operator."""
    # Integration with Slack/PagerDuty/Teams
    approval_request = {
        "tool": tool_name,
        "input": tool_input,
        "timeout_seconds": 300,  # 5-minute approval window
        "auto_deny_on_timeout": True,  # Default: deny if no response
    }
    # await send_to_approval_queue(approval_request)
    return False  # Default deny
```

---

## Agent RBAC in Kubernetes

```yaml
# AI Agent ServiceAccount with minimal permissions
apiVersion: v1
kind: ServiceAccount
metadata:
  name: task-agent
  namespace: agents
  labels:
    agent-type: task-processor
    security-tier: restricted
---
# Agent Role: only read tasks, write results
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: task-agent-role
  namespace: agents
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["task-queue", "task-config"]
    verbs: ["get", "watch"]
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["task-results"]
    verbs: ["get", "patch"]
  # No pods/exec, no secrets, no cluster resources
---
# Network isolation: agent can only reach LLM API and task queue
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: task-agent-network
  namespace: agents
spec:
  podSelector:
    matchLabels:
      app: task-agent
  policyTypes: [Ingress, Egress]
  egress:
    - to:   # LLM API endpoint (internal proxy)
        - podSelector:
            matchLabels:
              app: llm-proxy
          namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: llm-gateway
      ports:
        - port: 443
    - ports:        # DNS
        - port: 53
          protocol: UDP
  ingress: []       # No inbound traffic to agent
```

---

## PII Detection and Masking

```python
import re
from typing import Any

# PII patterns
PII_PATTERNS = {
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b(\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ip_address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    "api_key": r"\b[A-Za-z0-9]{32,64}\b",
}

def detect_and_mask_pii(text: str, mask_char: str = "*") -> tuple[str, list[str]]:
    """Detect PII in text and replace with masked values."""
    detected_types = []
    masked_text = text

    for pii_type, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            detected_types.append(pii_type)
            masked_text = re.sub(
                pattern,
                lambda m: mask_char * min(len(m.group()), 8),
                masked_text
            )

    return masked_text, detected_types

def safe_llm_call(user_input: str, system_context: str) -> str:
    """Sanitize input/output for PII before/after LLM call."""
    # Mask PII in input
    safe_input, input_pii_types = detect_and_mask_pii(user_input)
    if input_pii_types:
        log_pii_detection("INPUT", input_pii_types)

    # Make LLM call
    response = call_llm(safe_input, system_context)

    # Mask PII in output (LLM may echo or generate PII)
    safe_response, output_pii_types = detect_and_mask_pii(response)
    if output_pii_types:
        log_pii_detection("OUTPUT", output_pii_types)

    return safe_response
```

---

## Agent Security Checklist

```
BEFORE DEPLOYMENT:
  [ ] Threat model completed (attacker goals, attack vectors)
  [ ] Tool allowlist defined (no wildcard tools)
  [ ] Tool input schemas validated (strict types, maxLength)
  [ ] Prompt injection tests passed
  [ ] PII detection enabled in input and output
  [ ] Human-in-loop for sensitive operations
  [ ] Tool call budget set (max_tool_calls)
  [ ] Agent RBAC with dedicated ServiceAccount
  [ ] Network isolation (egress only to required endpoints)
  [ ] Rate limiting applied (tokens/min, requests/hour)
  [ ] Audit logging for all tool calls

IN PRODUCTION:
  [ ] Monitor tool call patterns for anomalies
  [ ] Alert on prompt injection patterns
  [ ] Rotate API keys for LLM providers
  [ ] Review agent action logs weekly
  [ ] Penetration test agent annually
```
