---
name: authorizer
description: |
  Creates production-ready Kubernetes authorization configurations covering every identity
  type (Users, Groups, Service Accounts, AI Agents, Federated Clusters, Environments) and
  every authorization mechanism (RBAC, ABAC, OPA/Gatekeeper, Kyverno, SPIFFE/SPIRE,
  cert-manager, IRSA, Workload Identity, mTLS, zero-trust) for any tier from local dev
  to global enterprise multi-cluster platforms with SOC 2 / HIPAA / PCI-DSS / FedRAMP
  compliance. This skill should be used when teams need to authorize Kubernetes identities,
  enforce policy-as-code, implement zero-trust networking, integrate cloud IAM with cluster
  RBAC, harden multi-cluster authorization, secure AI/LLM agent workloads, implement
  least-privilege service accounts, perform RBAC audits, or achieve industry compliance.
---

# Kubernetes Authorizer

Implement airtight Kubernetes authorization for every identity, every environment, every
compliance regime — from `kubectl` local dev to global zero-trust enterprise fleets.

## What This Skill Builds

| Tier | Scope | Use Case |
|------|-------|----------|
| **1 — Developer** | RBAC + ServiceAccounts, local cluster (kind/minikube/k3s) | Solo dev, learning, local microservices |
| **2 — Standard** | Namespace RBAC, Network Policies, Kyverno baseline | Small teams, staging, single-cluster SaaS |
| **3 — Production** | OPA/Gatekeeper + Kyverno, cert-manager, Audit Logging, OIDC | Regulated SaaS, HIPAA/SOC 2 workloads |
| **4 — Enterprise** | SPIFFE/SPIRE, IRSA/Workload Identity, mTLS mesh, ABAC | Multi-team, microservices, cloud-native |
| **5 — Multi-Cluster** | Cross-cluster identity federation, Fleet RBAC, zero-trust overlay | Global platforms, multi-cloud, FedRAMP |

## What This Skill Does NOT Do

- Provision Kubernetes clusters (use `k8s-mastery`)
- Write application business logic (auth policies only, not app code)
- Replace runtime WAF or network firewalls (secures K8s API plane, not application)
- Manage cloud IAM roles directly (generates annotations/references, not cloud configs)
- Create CI/CD pipelines (use `cicd-pipeline`)

---

## Before Implementation

| Source | Gather |
|--------|--------|
| **Codebase** | Existing RBAC YAMLs, Helm values, Kustomize overlays, NetworkPolicy files |
| **Conversation** | Tier, identity types needed, cloud provider, compliance requirements, mesh |
| **Skill References** | `references/` — patterns, templates, cloud auth, zero-trust, compliance |
| **User Guidelines** | Namespace conventions, team structure, existing IdP (LDAP/OIDC/AD) |

Only ask for THEIR requirements — domain expertise is embedded in `references/`.

---

## Clarifications

Ask in two rounds — start with most critical:

### Round 1: Environment + Scope

| Question | Options |
|----------|---------|
| **Target tier?** | 1=Dev / 2=Standard / 3=Production / 4=Enterprise / 5=Multi-Cluster |
| **Identity types?** | Users, Groups, ServiceAccounts, AI Agents, Federated Clusters (multi-select) |
| **Cloud provider?** | AWS (IRSA) / GCP (Workload Identity) / Azure (AAD Pod Identity/KIAM) / On-prem / Bare metal |
| **Compliance regime?** | None / SOC 2 / HIPAA / PCI-DSS / FedRAMP / CIS Benchmark |

### Round 2: Authorization Stack (after Round 1)

| Question | Options |
|----------|---------|
| **Policy engine?** | OPA/Gatekeeper / Kyverno / Both / None (RBAC only) |
| **Zero-trust/mTLS?** | SPIFFE/SPIRE / Istio mTLS / Linkerd mTLS / cert-manager / None |
| **Multi-cluster?** | Single / Fleet (GKE Hub / ArgoCD) / Admiralty / Liqo |
| **Existing IdP?** | None / Dex / Keycloak / Okta / Azure AD / Google Cloud Identity |

**Graceful defaults** — if user skips: Tier 2, RBAC + Kyverno, cert-manager, no IdP.

---

## Authorization Architecture

### Identity Hierarchy (all tiers)

```
Human Users ──► OIDC/IdP ──► Kubernetes UserInfo
Groups       ──► OIDC claims ──► K8s Group bindings
ServiceAccounts ──► TokenRequest ──► Pod identity
AI Agents    ──► SA + IRSA/WI ──► Cloud IAM chained
Nodes        ──► Node Authorizer ──► kubelet identity
Clusters     ──► kubeconfig / ClusterSet ──► Fleet RBAC
```

### Authorization Decision Layers

```
Request ──► 1. AuthN (who are you?)
         ──► 2. AuthZ (what can you do?) [RBAC + ABAC + Webhook]
         ──► 3. AdmissionControl (is it allowed?) [OPA/Kyverno]
         ──► 4. NetworkPolicy (can it reach?) [CNI enforcement]
         ──► 5. mTLS/SPIFFE (is the workload who it claims?) [mesh]
```

See `references/identity-types.md` for per-identity configuration patterns.

---

## Tier Decision Tree

```
Tier 1 (Dev):   RBAC only → ServiceAccount per app → kind/k3s → minimal NetworkPolicy
Tier 2 (Std):   + Kyverno baseline → Namespace isolation → OIDC basic
Tier 3 (Prod):  + OPA/Gatekeeper → cert-manager → Audit log → OIDC+groups
Tier 4 (Ent):   + SPIFFE/SPIRE → IRSA/WI → mTLS → PSA enforced → Falco runtime
Tier 5 (Multi): + ClusterSet RBAC → SubjectAccessReview federation → zero-trust overlay
```

---

## Identity Type Configurations

| Identity | Mechanism | Cloud Binding | Reference |
|----------|-----------|---------------|-----------|
| Human User | OIDC → ClusterRoleBinding | IdP group claim | `references/identity-types.md#users` |
| Group | OIDC groups claim → RoleBinding | IdP/AD group | `references/identity-types.md#groups` |
| ServiceAccount | TokenRequest API + projected volumes | IRSA / Workload Identity | `references/identity-types.md#service-accounts` |
| AI Agent | SA + scoped ClusterRole + NetworkPolicy egress | IRSA role chaining | `references/identity-types.md#ai-agents` |
| Node/Kubelet | Node Authorizer + NodeRestriction admission | cloud-provider IAM | `references/identity-types.md#nodes` |
| Cluster (federated) | ClusterSet + SubjectAccessReview | Fleet Hub / ACM | `references/multi-cluster-auth.md` |

---

## Authorization Mechanisms

| Mechanism | When | Reference |
|-----------|------|-----------|
| **RBAC** | Always — least-privilege roles + bindings | `references/rbac-patterns.md` |
| **ABAC** | Attribute-based dynamic policies (rare, legacy) | `references/rbac-patterns.md#abac` |
| **OPA/Gatekeeper** | ConstraintTemplate + Constraint enforcement | `references/policy-engines.md#opa` |
| **Kyverno** | ClusterPolicy validate/mutate/generate | `references/policy-engines.md#kyverno` |
| **IRSA** | AWS EKS SA ↔ IAM Role via OIDC | `references/cloud-auth-patterns.md#irsa` |
| **Workload Identity** | GKE SA ↔ GCP Service Account | `references/cloud-auth-patterns.md#workload-identity` |
| **cert-manager** | TLS lifecycle, mTLS bootstrap | `references/zero-trust-patterns.md#cert-manager` |
| **SPIFFE/SPIRE** | SVID issuance, workload attestation | `references/zero-trust-patterns.md#spire` |
| **mTLS (mesh)** | Istio/Linkerd peer auth + authz policies | `references/zero-trust-patterns.md#mtls` |

---

## Environment Integration Patterns

| Environment | Auth Pattern | Key Config |
|-------------|-------------|------------|
| **kind/minikube (local)** | Static kubeconfig + basic RBAC | `--extra-config=apiserver.authorization-mode=RBAC` |
| **k3s (edge/dev)** | Lightweight RBAC + Traefik ingress SA | Token projection + NetworkPolicy |
| **EKS** | IRSA + aws-auth ConfigMap + EKS Pod Identity | OIDC issuer → IAM role trust |
| **GKE** | Workload Identity + Config Connector SA | gke-metadata-server → Google SA |
| **AKS** | Azure AD workload identity + AAD Pod Identity | federated credential → Azure AD app |
| **OpenShift** | SCCs + OAuth server + project-based RBAC | `oc adm policy` + SCCs |
| **On-prem/Bare-metal** | Dex/Keycloak OIDC + cert-manager CA | static token file → OIDC webhook |

See `references/environment-tiers.md` for full environment configs.

---

## Output Specification

For each invocation, deliver:

1. **RBAC Manifests** — Roles/ClusterRoles, bindings per identity type + namespace
2. **Policy Engine Configs** — OPA ConstraintTemplates or Kyverno ClusterPolicies
3. **Zero-Trust Configs** — SPIRE entries / cert-manager Issuers / mTLS PeerAuthentication
4. **Cloud IAM Annotations** — SA annotations for IRSA/Workload Identity
5. **Audit Policy** — `--audit-policy-file` rules for API server
6. **NetworkPolicy** — Ingress/egress per workload namespace
7. **Compliance Checklist** — CIS benchmark mappings for requested regime
8. **Scaffold Script** — `scaffold_authz.py` call with flags for the user's config

---

## Implementation Workflow

```
Step 1: Read existing auth configs (Glob/Grep codebase)
Step 2: Identify identity types + tiers from conversation
Step 3: Load relevant references/ sections
Step 4: Generate RBAC (least-privilege, aggregated roles)
Step 5: Layer policy engine (OPA or Kyverno) on top of RBAC
Step 6: Add zero-trust (cert-manager → SPIRE → mTLS) if Tier 4+
Step 7: Bind cloud IAM (IRSA/Workload Identity) for cloud SAs
Step 8: Configure audit logging + Falco rules
Step 9: Apply NetworkPolicy (default-deny + allow-list per SA)
Step 10: Generate compliance evidence mapping
Step 11: Run scaffold_authz.py to produce project structure
Step 12: Output validation checklist
```

---

## Quality Standards

All outputs MUST meet:

- **Least privilege**: No `*` verbs unless explicitly justified and documented
- **No cluster-admin bindings** to non-operators (flag and refuse unless user confirms)
- **Short-lived tokens**: `expirationSeconds: 3600` on all projected ServiceAccount tokens
- **Namespace isolation**: Every SA scoped to its namespace; ClusterRole only when necessary
- **Audit coverage**: Log `RequestReceived`, `ResponseStarted` for auth-sensitive resources
- **Policy-as-code**: All policies in version-controlled YAMLs, no imperative `kubectl`
- **CIS K8s Benchmark 1.9+**: Controls 5.x (RBAC), 4.x (Network) automatically applied
- **mTLS everywhere (Tier 4+)**: PeerAuthentication `STRICT` mode, no `PERMISSIVE` in prod

See `references/audit-compliance.md` for CIS/HIPAA/SOC 2/FedRAMP control mappings.

---

## Deliverables Checklist

- [ ] ClusterRole + Role per identity type (named `authorizer:<team>:<verb>-<resource>`)
- [ ] RoleBinding/ClusterRoleBinding per namespace per identity
- [ ] Kyverno or OPA policies: no latest tag, no host-path, require labels, PSA enforce
- [ ] cert-manager Issuer/ClusterIssuer + Certificate resources
- [ ] SPIRE Server + Agent config (Tier 4+)
- [ ] SA annotation for IRSA/Workload Identity (cloud tiers)
- [ ] AuditPolicy resource with level mapping
- [ ] NetworkPolicy default-deny + workload allow-list
- [ ] Compliance mapping table (CIS control → YAML file reference)
- [ ] `scaffold_authz.py --tier N --identities ... --cloud ... --policy ...` command

---

## Reference Index

| File | Contents |
|------|----------|
| `references/rbac-patterns.md` | Roles, ClusterRoles, aggregation, ABAC, audit |
| `references/identity-types.md` | Users, Groups, SAs, AI Agents, Nodes, Clusters |
| `references/policy-engines.md` | OPA/Gatekeeper ConstraintTemplates, Kyverno ClusterPolicies |
| `references/cloud-auth-patterns.md` | IRSA, Workload Identity, AKS AAD, OIDC federation |
| `references/zero-trust-patterns.md` | SPIFFE/SPIRE, cert-manager, mTLS, PeerAuthentication |
| `references/multi-cluster-auth.md` | ClusterSet, Fleet RBAC, SubjectAccessReview, ACM |
| `references/environment-tiers.md` | kind, k3s, EKS, GKE, AKS, OpenShift, bare-metal |
| `references/audit-compliance.md` | CIS 1.9, SOC 2, HIPAA, PCI-DSS, FedRAMP mappings |
| `references/anti-patterns.md` | 25 auth anti-patterns with CVEs and remediation |

**Search hint**: `grep -r "PATTERN" .claude/skills/authorizer/references/` to locate specific configs.

---

## Official Documentation URLs

| Tool | Official Docs | Notes |
|------|--------------|-------|
| K8s RBAC | https://kubernetes.io/docs/reference/access-authn-authz/rbac/ | Core reference |
| K8s Audit | https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/ | Policy format |
| Kyverno | https://kyverno.io/docs/ | Policy authoring |
| OPA/Gatekeeper | https://open-policy-agent.github.io/gatekeeper/ | Rego policies |
| cert-manager | https://cert-manager.io/docs/ | Issuers + Certificates |
| SPIFFE/SPIRE | https://spiffe.io/docs/ | Workload identity |
| Istio AuthZ | https://istio.io/latest/docs/concepts/security/ | mTLS + policies |
| AWS IRSA | https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html | EKS |
| GKE Workload Identity | https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity | GKE |
| Azure Workload Identity | https://azure.github.io/azure-workload-identity/docs/ | AKS |
| CIS K8s Benchmark | https://www.cisecurity.org/benchmark/kubernetes | Compliance |

> **Version check**: Always verify tool versions against official docs before applying configs.
> Last verified: February 2026. Install URLs in `references/` use pinned versions — check latest on release pages.
