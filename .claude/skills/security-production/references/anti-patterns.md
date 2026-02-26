# Security Anti-Patterns

## Container Security Anti-Patterns

| Anti-Pattern | Risk | Fix |
|-------------|------|-----|
| Running as root (UID 0) | Container escape = host root | Set `runAsUser: 65534`, `runAsNonRoot: true` |
| `privileged: true` | Full host access | Remove; use specific capabilities only |
| `hostNetwork: true` | Bypass NetworkPolicy | Only for CNI/system components |
| `hostPID: true` | See all host processes | Never in application containers |
| `capabilities: add: [SYS_ADMIN]` | Escalation to root | Use specific caps or eBPF alternative |
| Writable root filesystem | Malware persistence | `readOnlyRootFilesystem: true` + tmpfs |
| `image: myapp:latest` | Unpredictable image | Pin to `@sha256:digest` |
| No resource limits | DoS via resource exhaustion | Always set CPU/memory limits |
| Mounting `/var/run/docker.sock` | Container escape | Use dedicated build tool (kaniko) |
| Mounting host filesystem | Host access | Use PVCs, not hostPath |

---

## Kubernetes RBAC Anti-Patterns

```yaml
# BAD: Wildcard everything (never do this for workloads)
rules:
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["*"]

# BAD: Grant cluster-admin to application ServiceAccount
roleRef:
  kind: ClusterRole
  name: cluster-admin    # Only for actual cluster administrators

# BAD: Allow pods/exec across all namespaces
rules:
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]
  # pods/exec = interactive shell = privilege escalation vector

# BAD: Automount default SA token
# default ServiceAccount token automounted in every pod by default
# (allows API server access from any pod)
spec:
  automountServiceAccountToken: true  # Default — dangerous!

# GOOD: Disable automount at SA level, use projected token
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-service
automountServiceAccountToken: false
```

---

## Secrets Management Anti-Patterns

```yaml
# CRITICAL FAIL: Secret in Dockerfile
RUN pip install app && \
    export DB_PASSWORD=supersecret   # NEVER — stored in image layer

# CRITICAL FAIL: Secret in environment variable (visible in kubectl describe)
env:
  - name: DB_PASSWORD
    value: "supersecret"            # Visible in pod spec, logs

# CRITICAL FAIL: Secret in ConfigMap
apiVersion: v1
kind: ConfigMap
data:
  db-password: "supersecret"       # ConfigMap is NOT encrypted by default

# CRITICAL FAIL: Secret committed to Git (even base64)
echo "c3VwZXJzZWNyZXQ=" # base64 is NOT encryption

# CRITICAL FAIL: Shared database credentials across services
# One service compromised = all services compromised

# BAD: Long-lived static credentials
# Use Vault dynamic credentials with 1h TTL instead

# BAD: Secrets Manager but same secret for dev/staging/prod
# Each environment must have isolated secrets

# CORRECT pattern:
# Use External Secrets Operator → Vault/cloud KMS
# Each service gets its own secret path
# TTL ≤ 24h for sensitive credentials
```

---

## Network Security Anti-Patterns

```yaml
# BAD: No NetworkPolicy (flat cluster networking)
# All pods can reach all other pods — huge blast radius

# BAD: Allow-all ingress
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
spec:
  podSelector: {}
  ingress:
    - {}   # Empty from = allow all ingress (defeats the purpose)

# BAD: NetworkPolicy without egress restriction
# Only ingress restriction still allows exfiltration

# BAD: Service with type=LoadBalancer for internal services
# Creates public cloud load balancer unnecessarily
# Use ClusterIP + internal ingress

# BAD: Skip TLS on internal services ("it's all internal anyway")
# Internal attackers, container escapes, lateral movement all use internal paths

# BAD: Using NodePort to bypass NetworkPolicy
# NodePort bypasses most NetworkPolicy implementations

# CORRECT: Default-deny-all first, then selective allow
```

---

## Admission Control Anti-Patterns

```yaml
# BAD: No admission webhook validation
# Developers can deploy anything without security review

# BAD: Kyverno/OPA in audit-only forever
# Policies that never enforce are security theater
# → Set timeline: audit 1 week → warn 1 week → enforce

# BAD: Admission webhook failure-open
webhooks:
  - name: my-webhook.example.com
    failurePolicy: Ignore    # If webhook fails, admit anyway (security bypass)
# CORRECT: failurePolicy: Fail (reject admission if webhook unavailable)

# BAD: Webhook without timeout
webhooks:
  - name: my-webhook.example.com
    timeoutSeconds: 30       # Too long — use 10s max
# Long webhook timeout can block all pod creation

# BAD: ValidatingWebhook matching all resources with no scope
# Watch your performance — use namespaceSelector to limit scope
```

---

## Supply Chain Anti-Patterns

```
BAD: Base image without digest pinning
  FROM python:3.12-slim    ← may change tomorrow
  CORRECT: FROM python:3.12-slim@sha256:abc123...

BAD: Running pip/npm install during container startup
  ENTRYPOINT ["pip", "install", "-r", "requirements.txt", "&&", "python", "main.py"]
  # Pulls untrusted packages at runtime
  CORRECT: Install during build, copy to production image

BAD: No SBOM — can't audit what's in production images

BAD: Unsigned images from public registry used in production
  image: nginx:latest  # Unverified, could be tampered

BAD: Dependency pinning only in requirements.txt, not Dockerfile FROM
  FROM node:latest    # Even if you pin app deps, base is uncontrolled

BAD: Skip dependency audit because "we're just a startup"
  Security debt compounds — a 0-day in lodash cost Uber $148M

BAD: CI runs as root / has excessive cloud permissions
  If CI is compromised, it can exfiltrate secrets, push malicious images
  CORRECT: Use OIDC (no long-lived keys), minimal IAM scope, no * permissions
```

---

## Compliance Anti-Patterns

```
BAD: Compliance-as-checkbox
  "We have RBAC" doesn't mean "we pass SOC 2"
  Evidence matters: automated collection, continuous monitoring

BAD: Audit logs only for compliance audit period
  K8s audit logs should be continuous, not just when auditor visits

BAD: Single person with access to production secrets
  Key escrow, dual-person control for Tier 4 operations

BAD: No secret rotation plan
  Static credentials are indefinitely valuable to attackers

BAD: Compliance without threat modeling
  Controls without knowing what you're defending against = random effort

BAD: Manual compliance evidence collection
  Automate with scripts (see compliance-frameworks.md)
  Tool: kube-bench for CIS, Falco for runtime, Trivy for CVEs

BAD: Shared accounts / no individual accountability
  Everyone logs in as admin = no audit trail = fails CC6, AU requirements

BAD: PCI scope creep
  Systems touching cardholder data must be in-scope
  Segment CDE in dedicated namespace/cluster with strict NetworkPolicy
```

---

## Runtime Security Anti-Patterns

```
BAD: Falco deployed but alerts never reviewed
  "Alert fatigue" → tune rules, don't disable monitoring

BAD: Falco alerting on too many things (high false positive rate)
  Start with default ruleset, tune before adding custom rules

BAD: No runtime security (Falco disabled "to save resources")
  Container escape detection requires runtime monitoring
  Falco on eBPF driver: <1% CPU overhead

BAD: seccomp:RuntimeDefault disabled for "compatibility"
  RuntimeDefault blocks <30 syscalls, rarely causes issues
  Profile first with seccomp logging if unsure

BAD: AppArmor profile too permissive (only a comment)
  Verify AppArmor is actually loaded: aa-status | grep container-default

BAD: Trust container image signatures but not verify at admission
  Sign images in CI but skip Kyverno verifyImages = no enforcement

BAD: Forensics capability added after incident
  Have forensics tooling ready BEFORE incident (this runbook, tools installed)
```

---

## Top 10 Critical Security Mistakes (Summary)

1. Running containers as root with `privileged: true`
2. Storing secrets in environment variables or ConfigMaps
3. No NetworkPolicy (flat cluster = lateral movement paradise)
4. Cluster-admin RBAC for application ServiceAccounts
5. `latest` image tags with no signature verification
6. No admission webhooks — developers can deploy anything
7. Sharing secrets across environments (dev = prod secret = breach)
8. No runtime security (Falco/eBPF) — blind to container escapes
9. Compliance checkbox without continuous evidence collection
10. AI agent with excessive tool access (wildcard tool lists = excessive agency)
