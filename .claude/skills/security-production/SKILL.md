---
name: security-production
description: |
  Creates production-ready security configurations and compliance frameworks for
  microservices, autonomous AI systems, and cloud-native platforms — from basic
  workload hardening to enterprise zero-trust architectures with SOC 2 Type II,
  HIPAA, PCI-DSS v4, and FedRAMP compliance.
  This skill should be used when teams need to harden Kubernetes workloads,
  implement zero-trust networking, secure container supply chains, manage secrets,
  enforce policy-as-code, achieve regulatory compliance, secure AI/LLM agent
  workloads, or respond to security incidents across any cloud provider.
---

# Security Production

Build production-ready security posture for microservices and autonomous systems at any compliance tier.

## What This Skill Does

- Implements the 4C's security model: Cloud → Cluster → Container → Code
- Hardens Kubernetes: RBAC, NetworkPolicies, Pod Security Standards, API server
- Secures containers: multi-stage distroless builds, Trivy scanning, seccomp/AppArmor
- Manages secrets: HashiCorp Vault, External Secrets Operator, Sealed Secrets, cloud KMS
- Enforces zero-trust networking: SPIFFE/SPIRE, Istio mTLS, Cilium eBPF policies
- Secures supply chain: Cosign keyless signing, SBOM (Syft), SLSA L3 provenance
- Provides runtime protection: Falco threat detection, eBPF syscall filtering
- Enforces policy-as-code: OPA/Gatekeeper ConstraintTemplates, Kyverno ClusterPolicies
- Achieves compliance: SOC 2 Type II, HIPAA, PCI-DSS v4, FedRAMP/NIST 800-53, CIS L2
- Secures AI/LLM agent workloads: prompt injection defense, agent RBAC, data isolation
- Integrates SIEM and audit: Wazuh, Elastic SIEM, CloudTrail, audit logging pipelines

## What This Skill Does NOT Do

- Perform live penetration testing or active exploitation
- Manage cloud billing or account provisioning
- Deploy to production environments (generates configs, not deployments)
- Conduct real-time incident response (generates runbooks and tooling configs)
- Replace a dedicated security team or compliance auditor

---

## Before Implementation

| Source | Gather |
|--------|--------|
| **Codebase** | Existing K8s manifests, Dockerfiles, CI configs, cloud provider, language |
| **Conversation** | Compliance requirements, threat model, existing security tools |
| **Skill References** | Domain patterns from `references/` (12 specialized security domains) |
| **User Guidelines** | Team conventions, cloud provider, existing secrets backend, audit requirements |

Only ask user for THEIR specific context. Security expertise is embedded in this skill.

---

## Required Clarifications

### Before Asking

1. Check conversation history for prior answers
2. Infer from existing files (Dockerfile, values.yaml, terraform, CI/CD configs)
3. Only ask what cannot be determined from context

### Ask First (single message — batch together)

1. **Tier + Compliance target**: "What security tier and compliance framework do you need?"

| Tier | Scope | Compliance Targets |
|------|-------|--------------------|
| **1 — Hardened Dev** | Non-root containers, basic RBAC, NetworkPolicies, image scanning | Internal/startup, no formal compliance |
| **2 — Production** | PSS Restricted, mTLS, Vault secrets, supply chain signing, Falco | SOC 2 Type I, ISO 27001 readiness |
| **3 — Enterprise** | Zero-trust (SPIFFE/SPIRE), OPA/Kyverno, SIEM, full audit trail | SOC 2 Type II, HIPAA, PCI-DSS v4 |
| **4 — Regulated** | FIPS 140-2, HSM key management, FedRAMP controls, cryptographic audit | FedRAMP Moderate/High, PCI-DSS v4, HIPAA+HITECH |

2. **Target environment**: "Where does this run?"
   - AWS EKS / GCP GKE / Azure AKS / On-premises / Multi-cloud

### Ask If Needed

3. **Secrets backend**: Vault (self-hosted/HCP) / AWS Secrets Manager / GCP SM / Azure Key Vault / Sealed Secrets
4. **AI/Autonomous agents**: Yes/No (enables LLM-specific threat mitigations)
5. **Existing security tools**: Any existing scanning, policy engines, or SIEM in place

### Defaults (If Not Specified)

| Clarification | Default |
|---------------|---------|
| Tier | Infer from project type and context |
| Cloud | Multi-cloud (cloud-agnostic configs generated) |
| Secrets | HashiCorp Vault (self-hosted) |
| Policy engine | Kyverno (simpler) for Tier 2, OPA+Kyverno for Tier 3-4 |
| Service mesh | Istio (Tier 3-4), none (Tier 1-2) |
| Image scanning | Trivy (all tiers) |
| Runtime protection | Falco (Tier 2+) |

---

## Workflow

```
Clarify → Threat Model → 4C's Hardening → Compliance Mapping → Policy-as-Code → Validate
```

### Step 1: Threat Modeling

Apply STRIDE to user's system. Read `references/cloud-security.md`:

```
Spoofing      → Identity: mTLS, SPIFFE/SPIRE, OIDC workload identity
Tampering     → Integrity: Cosign signing, admission webhooks, immutable FS
Repudiation   → Audit: CloudTrail, K8s audit logs, Falco events → SIEM
Info Disclosure → Secrets: Vault/ESO, TLS everywhere, network segmentation
DoS           → Availability: ResourceQuota, LimitRange, PodDisruptionBudget
Elevation     → Privilege: PSS Restricted, non-root, no privilege escalation
```

### Step 2: Cloud Layer (4C Layer 1)

Read `references/cloud-security.md` for cloud-specific controls:

```
AWS:   IAM roles (IRSA) + SCP guardrails + CloudTrail + AWS Config + Security Hub
GCP:   Workload Identity + Org Policy + Security Command Center + VPC SC
Azure: Workload Identity + Azure Policy + Defender for Cloud + Private Endpoints
All:   VPC/VNet with private subnets, no public API server, cloud KMS for encryption
```

### Step 3: Cluster Layer (4C Layer 2)

Read `references/k8s-security.md`:

```
API Server:    Audit logging, anonymous-auth=false, encryption-at-rest
RBAC:          Least-privilege, no cluster-admin for workloads, ServiceAccount per pod
NetworkPolicy: Default-deny-all ingress+egress, allow only required paths
PSS:           Enforce Restricted profile in production namespaces
Admission:     Kyverno/OPA + ValidatingWebhooks for policy enforcement
```

### Step 4: Container Layer (4C Layer 3)

Read `references/container-security.md`:

```
Images:     Multi-stage → distroless/scratch final, no latest tags
User:       USER 65534 (nonroot), runAsNonRoot: true
Filesystem: readOnlyRootFilesystem: true, tmpfs for /tmp
Scanning:   Trivy in CI (block on CRITICAL/HIGH), Grype for SBOM
Caps:       drop: [ALL], add only NET_BIND_SERVICE if needed
Seccomp:    RuntimeDefault or custom profile
AppArmor:   runtime/default or custom profile
```

### Step 5: Code Layer (4C Layer 4)

```
Dependencies: Dependabot/Renovate auto-PRs, SCA (Snyk/OSV Scanner)
SAST:         Semgrep, CodeQL, Bandit (Python), gosec (Go)
Secrets:      Detect-secrets pre-commit hook, GitLeaks in CI
Input:        Input validation, parameterized queries, output encoding
AI/LLM:       Read references/ai-agent-security.md for prompt injection + agent RBAC
```

### Step 6: Secrets Management

Read `references/secrets-management.md`:

```
Tier 1-2: Sealed Secrets or SOPS + age encryption
Tier 2-3: External Secrets Operator (ESO) → cloud KMS / Vault
Tier 3-4: HashiCorp Vault (HA) + Vault Agent Injector / CSI driver
Tier 4:   Vault + HSM (PKCS#11) + FIPS 140-2 TLS, cloud HSM (AWS CloudHSM / GCP HSM)
```

### Step 7: Supply Chain Security

Read `references/supply-chain-security.md`:

```
1. Build:   Hermetic builds in CI, pinned base images (digest not tag)
2. Sign:    Cosign keyless signing (Sigstore) — sign image + attestation
3. SBOM:    Syft generates SBOM, Grype checks vulnerabilities
4. Provenance: SLSA L3 via slsa-github-generator
5. Verify:  Kyverno/OPA verifies signature before admission
6. Audit:   SBOM stored in registry (ORAS), attestation in Rekor log
```

### Step 8: Runtime Security

Read `references/runtime-security.md`:

```
Falco:    Custom rules for container escape, privilege escalation, suspicious execs
Seccomp:  RuntimeDefault (Tier 2), custom profiles blocking ptrace/mount (Tier 3-4)
AppArmor: runtime/default profile, deny raw socket access
eBPF:     Tetragon or Cilium for kernel-level enforcement (no kernel module needed)
```

### Step 9: Policy-as-Code

Read `references/policy-as-code.md`:

```
Kyverno ClusterPolicies (Tier 2+):
  - require-image-signature (Cosign verified)
  - require-non-root (runAsNonRoot=true)
  - require-resource-limits (CPU+memory mandatory)
  - restrict-privileged (no privileged containers)
  - require-network-policy (every namespace has deny-all)

OPA Gatekeeper ConstraintTemplates (Tier 3-4):
  - ConstraintTemplate + Constraint pattern
  - Custom Rego policies for organization-specific rules
  - Audit mode before enforcement mode
```

### Step 10: Compliance Mapping

Read `references/compliance-frameworks.md`:

```
SOC 2 Type II:  CC6 (logical access), CC7 (system ops), CC8 (change mgmt)
HIPAA:          164.312 (technical safeguards): access control, audit, encryption
PCI-DSS v4:     Req 1 (network), 2 (configs), 3 (stored data), 7 (access), 10 (logging)
FedRAMP:        NIST 800-53 rev5 control families: AC, AU, CM, IA, SC, SI, RA
CIS K8s L2:     All 200+ CIS Benchmark controls with automated kube-bench verification
```

### Step 11: Validate

Apply Output Checklist. Run `scripts/scaffold_security.py --audit` to generate compliance gap report.

---

## Tier Quick Reference

| | Tier 1 — Hardened Dev | Tier 2 — Production | Tier 3 — Enterprise | Tier 4 — Regulated |
|---|---|---|---|---|
| Container | Non-root, read-only FS | + distroless, seccomp | + AppArmor, Trivy gate | + FIPS base images |
| RBAC | Basic SA per workload | + least-privilege audit | + OPA/Kyverno enforce | + privileged access workstation |
| Network | NetworkPolicy deny-all | + Cilium/Calico L7 | + Istio mTLS mesh | + SPIFFE/SPIRE |
| Secrets | K8s Secrets (base64) | + Sealed Secrets/ESO | + Vault HA + agent | + Vault + HSM |
| Supply Chain | Trivy scan in CI | + Cosign sign | + SBOM + SLSA L3 | + full provenance |
| Runtime | - | Falco default rules | + custom Falco rules | + Tetragon eBPF |
| Policy | Manual review | Kyverno audit | Kyverno enforce + OPA | + custom Rego |
| Compliance | - | SOC 2 readiness | SOC 2 Type II, HIPAA | FedRAMP, PCI-DSS v4 |
| Audit | K8s events | + K8s audit log | + SIEM (Elastic/Wazuh) | + immutable audit |
| Encryption | TLS in transit | + secrets encrypted | + KMS CMK | + FIPS 140-2 HSM |

---

## MCP Server Tools

Security MCP server in `scripts/security_mcp_server.py`:

| Tool | Purpose |
|------|---------|
| `scan_image` | Run Trivy scan on image, return vulnerabilities by severity |
| `audit_rbac` | Check RBAC configurations for over-privileged roles/bindings |
| `check_policies` | Validate Kyverno/OPA policies against cluster state |
| `validate_secrets` | Check for hardcoded secrets, verify ESO/Vault connectivity |
| `compliance_check` | Map controls to SOC2/HIPAA/PCI-DSS/FedRAMP frameworks |

Start: `python scripts/security_mcp_server.py` (stdio transport, FastMCP)

---

## Output Specification

### Tier 1 — Hardened Dev
- [ ] Hardened Deployment manifest (non-root, read-only FS, resource limits)
- [ ] Default-deny NetworkPolicies (ingress + egress)
- [ ] ServiceAccount per workload (no default SA)
- [ ] Trivy scan in CI (block on CRITICAL)
- [ ] RBAC: Role + RoleBinding (least-privilege)

### Tier 2 — Production
- [ ] All Tier 1 outputs
- [ ] Kyverno ClusterPolicies (audit → enforce)
- [ ] Sealed Secrets or ESO configuration
- [ ] Cosign image signing workflow
- [ ] Falco DaemonSet with default rules
- [ ] seccomp RuntimeDefault profile
- [ ] Audit logging configuration (K8s audit policy)
- [ ] SOC 2 readiness control mapping

### Tier 3 — Enterprise
- [ ] All Tier 2 outputs
- [ ] OPA Gatekeeper ConstraintTemplates
- [ ] HashiCorp Vault HA + Vault Agent Injector
- [ ] SPIFFE/SPIRE deployment for workload identity
- [ ] Istio PeerAuthentication (STRICT mTLS) + AuthorizationPolicy
- [ ] SBOM generation (Syft) + vulnerability attestation (Grype)
- [ ] SLSA L3 provenance via GitHub Actions
- [ ] SIEM integration (Wazuh or Elastic)
- [ ] SOC 2 Type II + HIPAA control matrix
- [ ] CIS Kubernetes Benchmark L2 (kube-bench report)

### Tier 4 — Regulated
- [ ] All Tier 3 outputs
- [ ] FIPS 140-2 compliant base images and TLS configuration
- [ ] HSM-backed key management (Vault + PKCS#11)
- [ ] FedRAMP control implementation guide (800-53 rev5)
- [ ] PCI-DSS v4 network segmentation and logging evidence
- [ ] Immutable audit trail (WORM storage or blockchain-anchored)
- [ ] Privileged Access Workstation (PAW) configuration
- [ ] Incident response runbooks with RTO/RPO objectives
- [ ] Third-party penetration test readiness checklist

---

## Domain Standards

### Must Follow

- [ ] Run all containers as non-root (UID ≥ 1000, explicitly set)
- [ ] Set `readOnlyRootFilesystem: true` and use emptyDir for writable paths
- [ ] Drop ALL Linux capabilities; add only what is explicitly required
- [ ] Pin container images to digest (not tag) in production
- [ ] Never store secrets in environment variables; use mounted secrets or CSI
- [ ] Enforce NetworkPolicy default-deny before allowing any traffic
- [ ] Rotate all secrets regularly; vault leases ≤ 24h for dynamic credentials
- [ ] Sign all container images; verify signatures at admission
- [ ] Apply PSS Restricted profile to all production workloads
- [ ] Enable Kubernetes audit logging at RequestResponse level
- [ ] Scan all images in CI; block promotion on CRITICAL vulnerabilities
- [ ] Use dedicated ServiceAccounts per workload (never default SA)
- [ ] Implement defense-in-depth: no single security control is sufficient

### Must Avoid

- Running containers as root or with `privileged: true`
- Storing credentials in ConfigMaps, environment variables, or image layers
- Using `hostNetwork: true`, `hostPID: true`, or `hostIPC: true` without justification
- Wildcard RBAC (`*` verbs or resources) except cluster-admin bootstrapping
- Mounting `/var/run/docker.sock` or host filesystem paths
- Using `latest` or mutable image tags in production
- Disabling admission webhooks (`--disable-admission-plugins`)
- Granting cluster-admin to workload ServiceAccounts
- Sharing namespaces between environments or tenants
- Disabling TLS verification or using self-signed certs in production
- Exposing Kubernetes API server to public internet
- Storing secrets in Git (even encrypted — use sealed secrets or GitOps + ESO)

---

## Output Checklist

Before delivering, verify:

- [ ] All containers: non-root UID, readOnlyRootFilesystem, resource limits/requests
- [ ] All capabilities dropped; no privileged flag
- [ ] Image pinned to digest or verified tag in prod
- [ ] NetworkPolicy default-deny applied to every namespace
- [ ] RBAC: least-privilege SA per workload, no cluster-admin for apps
- [ ] Secrets: not in env vars or ConfigMaps; using Vault/ESO/Sealed Secrets
- [ ] Image scanning configured in CI with severity threshold
- [ ] PSS/PSA profile explicitly set per namespace
- [ ] Audit logging enabled with appropriate verbosity
- [ ] Compliance controls mapped and documented
- [ ] Anti-patterns from `references/anti-patterns.md` avoided
- [ ] MCP tools operational for ongoing security validation

---

## Reference Files

| File | When to Read | Grep For |
|------|--------------|----------|
| `references/cloud-security.md` | Cloud IAM, VPC, KMS, audit trail, cloud-native controls | `IRSA`, `Workload Identity`, `VPC`, `KMS`, `SCP` |
| `references/k8s-security.md` | RBAC, NetworkPolicy, PSS, API server hardening | `RBAC`, `NetworkPolicy`, `PSS`, `audit`, `admission` |
| `references/container-security.md` | Image hardening, scanning, seccomp, AppArmor | `distroless`, `Trivy`, `seccomp`, `AppArmor`, `non-root` |
| `references/secrets-management.md` | Vault, ESO, Sealed Secrets, SOPS, cloud KMS | `Vault`, `ESO`, `SealedSecret`, `SOPS`, `KMS` |
| `references/supply-chain-security.md` | Cosign, SBOM, SLSA, Sigstore, provenance | `Cosign`, `SBOM`, `SLSA`, `Syft`, `Rekor` |
| `references/zero-trust-networking.md` | SPIFFE/SPIRE, Istio, Cilium, mTLS | `SPIFFE`, `SPIRE`, `mTLS`, `Istio`, `Cilium` |
| `references/runtime-security.md` | Falco, eBPF, Tetragon, seccomp profiles | `Falco`, `Tetragon`, `eBPF`, `syscall`, `AppArmor` |
| `references/compliance-frameworks.md` | SOC2, HIPAA, PCI-DSS v4, FedRAMP, CIS | `SOC2`, `HIPAA`, `PCI`, `FedRAMP`, `CIS`, `NIST` |
| `references/policy-as-code.md` | OPA Rego, Gatekeeper, Kyverno policies | `Rego`, `ConstraintTemplate`, `ClusterPolicy`, `Kyverno` |
| `references/ai-agent-security.md` | LLM/agent threat model, prompt injection, agent RBAC | `prompt`, `LLM`, `agent`, `injection`, `sandbox` |
| `references/incident-response.md` | SIEM, alert pipelines, runbooks, forensics | `Falco`, `SIEM`, `alert`, `runbook`, `forensic` |
| `references/anti-patterns.md` | Security mistakes and fixes | check before delivery |

For controls not covered in references, fetch from Official Documentation URLs below.

## Asset Templates

| Template | Purpose |
|----------|---------|
| `assets/templates/hardened_deployment.yaml` | Full security-context deployment manifest |
| `assets/templates/network_policies.yaml` | Default-deny + selective allow NetworkPolicies |
| `assets/templates/falco_rules.yaml` | Custom Falco rules for container threats |
| `assets/templates/kyverno_security_policies.yaml` | Cluster-wide Kyverno enforcement policies |
| `assets/templates/vault_agent_config.yaml` | Vault Agent Injector K8s configuration |
| `assets/templates/supply_chain_ci.yaml` | GitHub Actions: Trivy + Cosign + Syft + SLSA |
| `assets/templates/spire_config.yaml` | SPIFFE/SPIRE server + agent K8s deployment |
| `assets/templates/opa_gatekeeper_policies.yaml` | OPA Gatekeeper ConstraintTemplates |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scaffold_security.py` | Generate complete security project: `--tier 1\|2\|3\|4 --compliance --cloud --secrets --runtime` |
| `scripts/security_mcp_server.py` | MCP server for security operations (5 tools) |

## Official Documentation

| Resource | URL | Use For |
|----------|-----|---------|
| Kubernetes Security | https://kubernetes.io/docs/concepts/security/ | PSS, RBAC, NetworkPolicy, audit |
| CIS Kubernetes Benchmark | https://www.cisecurity.org/benchmark/kubernetes | L1/L2 hardening controls |
| NIST 800-190 | https://csrc.nist.gov/publications/detail/sp/800-190/final | Container security guide |
| HashiCorp Vault | https://developer.hashicorp.com/vault/docs | Vault architecture, K8s auth, policies |
| External Secrets Operator | https://external-secrets.io/latest/ | ESO providers, SecretStore, ExternalSecret |
| Cosign / Sigstore | https://docs.sigstore.dev/ | Keyless signing, verification, policy |
| SLSA Framework | https://slsa.dev/spec/v1.0/ | Supply chain levels, provenance |
| Falco | https://falco.org/docs/ | Rules, output, Kubernetes deployment |
| OPA / Gatekeeper | https://open-policy-agent.github.io/gatekeeper/ | ConstraintTemplate, Constraint, Rego |
| Kyverno | https://kyverno.io/docs/ | ClusterPolicy, generate, verify-images |
| SPIFFE / SPIRE | https://spiffe.io/docs/ | SVID, workload API, K8s registration |
| Istio Security | https://istio.io/latest/docs/concepts/security/ | PeerAuthentication, AuthorizationPolicy |
| FedRAMP | https://www.fedramp.gov/documents/ | Authorization baseline, controls |
| OWASP Top 10 | https://owasp.org/www-project-top-ten/ | Application security risks |
| NIST 800-53 rev5 | https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final | Control catalog |

Last verified: February 2026 (K8s 1.32, Vault 1.18, Kyverno 1.13, Falco 0.39, Cosign 2.4, SLSA v1.0).
