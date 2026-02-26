#!/usr/bin/env python3
"""
scaffold_authz.py — Kubernetes Authorization Scaffold Generator
Generates a complete authorization project for any tier and identity mix.

Usage:
  python scaffold_authz.py --tier 3 --namespace team-backend --team backend \
    --app-name payment-service --cloud aws --identities users,groups,sa,ai-agents \
    --policy kyverno --zero-trust cert-manager --compliance soc2,hipaa \
    --output ./output/

Options:
  --tier        1-5 (1=Dev, 2=Std, 3=Prod, 4=Enterprise, 5=Multi-Cluster)
  --namespace   Target Kubernetes namespace
  --team        Team name (used in role naming)
  --app-name    Application name
  --cloud       aws|gcp|azure|on-prem|none
  --identities  Comma-separated: users,groups,sa,ai-agents,nodes,clusters
  --policy      kyverno|opa|both|none
  --zero-trust  cert-manager|spire|istio|linkerd|none
  --compliance  soc2|hipaa|pci|fedramp|cis (comma-separated)
  --oidc-group  OIDC group name for user bindings
  --output      Output directory (default: ./authz-output/)
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
from textwrap import dedent


# ── Tier definitions ─────────────────────────────────────────────────────────

TIER_NAMES = {
    1: "Developer (Local)",
    2: "Standard (Staging)",
    3: "Production (Regulated)",
    4: "Enterprise (Cloud + Zero-Trust)",
    5: "Multi-Cluster (Fleet)",
}

TIER_DEFAULTS = {
    1: {"policy": "none", "zero_trust": "none", "psa": "privileged"},
    2: {"policy": "kyverno", "zero_trust": "none", "psa": "baseline"},
    3: {"policy": "kyverno", "zero_trust": "cert-manager", "psa": "restricted"},
    4: {"policy": "both", "zero_trust": "spire", "psa": "restricted"},
    5: {"policy": "both", "zero_trust": "spire", "psa": "restricted"},
}


# ── YAML generators ──────────────────────────────────────────────────────────

def gen_namespace(args) -> str:
    psa = TIER_DEFAULTS[args.tier]["psa"]
    return dedent(f"""\
        apiVersion: v1
        kind: Namespace
        metadata:
          name: {args.namespace}
          labels:
            environment: {_env_label(args.tier)}
            team: {args.team}
            pod-security.kubernetes.io/enforce: {psa}
            pod-security.kubernetes.io/enforce-version: latest
            pod-security.kubernetes.io/audit: restricted
            pod-security.kubernetes.io/warn: restricted
            authorizer.io/tier: "{args.tier}"
            authorizer.io/managed: "true"
          annotations:
            authorizer.io/compliance: "{','.join(args.compliance)}"
            authorizer.io/generated: "{datetime.now().isoformat()}"
    """)


def gen_service_account(args) -> str:
    cloud_annotation = _cloud_annotation(args)
    return dedent(f"""\
        apiVersion: v1
        kind: ServiceAccount
        metadata:
          name: {args.app_name}-sa
          namespace: {args.namespace}
          labels:
            app.kubernetes.io/name: {args.app_name}
            app.kubernetes.io/component: service-account
            team: {args.team}
            rbac.authorizer.io/managed: "true"
          annotations:
            rbac.authorizer.io/owner: "{args.team}@company.com"
        {cloud_annotation}
        automountServiceAccountToken: false
    """)


def gen_ai_agent_sa(args) -> str:
    cloud_annotation = _cloud_annotation(args, role_suffix="ai-agent")
    return dedent(f"""\
        # AI Agent ServiceAccount — restricted identity
        apiVersion: v1
        kind: ServiceAccount
        metadata:
          name: {args.app_name}-ai-agent-sa
          namespace: {args.namespace}
          labels:
            app.kubernetes.io/name: {args.app_name}-ai-agent
            app.kubernetes.io/component: ai-agent
            team: {args.team}
            rbac.authorizer.io/managed: "true"
          annotations:
            rbac.authorizer.io/purpose: "AI/LLM agent identity — restricted scope"
        {cloud_annotation}
        automountServiceAccountToken: false
    """)


def gen_roles(args) -> str:
    parts = [dedent(f"""\
        # Role: {args.app_name} application operator (namespace-scoped)
        apiVersion: rbac.authorization.k8s.io/v1
        kind: Role
        metadata:
          name: authorizer:{args.team}:{args.app_name}-operator
          namespace: {args.namespace}
          labels:
            rbac.authorizer.io/tier: "application"
            rbac.authorizer.io/team: "{args.team}"
        rules:
          - apiGroups: [""]
            resources: ["pods", "pods/log", "services", "configmaps", "endpoints"]
            verbs: ["get", "list", "watch"]
          - apiGroups: [""]
            resources: ["secrets"]
            resourceNames: ["{args.app_name}-config", "{args.app_name}-tls"]
            verbs: ["get"]
          - apiGroups: ["apps"]
            resources: ["deployments"]
            resourceNames: ["{args.app_name}"]
            verbs: ["get", "list", "watch"]
    """)]

    if "ai-agents" in args.identities:
        parts.append(dedent(f"""\
            # Role: AI Agent (read-only cluster info)
            apiVersion: rbac.authorization.k8s.io/v1
            kind: Role
            metadata:
              name: authorizer:{args.team}:ai-agent-reader
              namespace: {args.namespace}
            rules:
              - apiGroups: [""]
                resources: ["pods", "services", "configmaps"]
                verbs: ["get", "list", "watch"]
              - apiGroups: ["apps"]
                resources: ["deployments"]
                verbs: ["get", "list", "watch"]
              # NO: exec, portforward, secrets write
        """))

    if "users" in args.identities or "groups" in args.identities:
        parts.append(dedent(f"""\
            # ClusterRole: Namespace developer (human users/groups)
            apiVersion: rbac.authorization.k8s.io/v1
            kind: ClusterRole
            metadata:
              name: authorizer:{args.team}:namespace-developer
              labels:
                rbac.authorizer.io/tier: "human-developer"
                rbac.authorizer.io/team: "{args.team}"
            rules:
              - apiGroups: [""]
                resources: ["pods", "pods/log", "services", "configmaps", "events"]
                verbs: ["get", "list", "watch", "create", "update", "patch"]
              - apiGroups: ["apps"]
                resources: ["deployments", "replicasets"]
                verbs: ["get", "list", "watch", "create", "update", "patch"]
              - apiGroups: [""]
                resources: ["secrets"]
                verbs: ["get", "list"]
        """))

    return "\n---\n".join(parts)


def gen_bindings(args) -> str:
    parts = [dedent(f"""\
        # RoleBinding: app SA to operator role
        apiVersion: rbac.authorization.k8s.io/v1
        kind: RoleBinding
        metadata:
          name: bind-{args.app_name}-sa
          namespace: {args.namespace}
          labels:
            rbac.authorizer.io/managed: "true"
        subjects:
          - kind: ServiceAccount
            name: {args.app_name}-sa
            namespace: {args.namespace}
        roleRef:
          kind: Role
          name: authorizer:{args.team}:{args.app_name}-operator
          apiGroup: rbac.authorization.k8s.io
    """)]

    if "groups" in args.identities and args.oidc_group:
        parts.append(dedent(f"""\
            # RoleBinding: OIDC group → developer role
            apiVersion: rbac.authorization.k8s.io/v1
            kind: RoleBinding
            metadata:
              name: bind-{args.oidc_group}-developers
              namespace: {args.namespace}
            subjects:
              - kind: Group
                name: "oidc:{args.oidc_group}"
                apiGroup: rbac.authorization.k8s.io
            roleRef:
              kind: ClusterRole
              name: authorizer:{args.team}:namespace-developer
              apiGroup: rbac.authorization.k8s.io
        """))

    if "ai-agents" in args.identities:
        parts.append(dedent(f"""\
            # RoleBinding: AI agent SA → reader role
            apiVersion: rbac.authorization.k8s.io/v1
            kind: RoleBinding
            metadata:
              name: bind-{args.app_name}-ai-agent
              namespace: {args.namespace}
            subjects:
              - kind: ServiceAccount
                name: {args.app_name}-ai-agent-sa
                namespace: {args.namespace}
            roleRef:
              kind: Role
              name: authorizer:{args.team}:ai-agent-reader
              apiGroup: rbac.authorization.k8s.io
        """))

    return "\n---\n".join(parts)


def gen_network_policy(args) -> str:
    return dedent(f"""\
        # NetworkPolicy: default deny all
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: default-deny-all
          namespace: {args.namespace}
          labels:
            authorizer.io/managed: "true"
        spec:
          podSelector: {{}}
          policyTypes:
            - Ingress
            - Egress
        ---
        # NetworkPolicy: allow {args.app_name} traffic
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: allow-{args.app_name}
          namespace: {args.namespace}
        spec:
          podSelector:
            matchLabels:
              app.kubernetes.io/name: {args.app_name}
          policyTypes:
            - Ingress
            - Egress
          ingress:
            - from:
                - namespaceSelector:
                    matchLabels:
                      kubernetes.io/metadata.name: ingress-nginx
              ports:
                - port: 8080
                  protocol: TCP
          egress:
            - to:
                - namespaceSelector:
                    matchLabels:
                      kubernetes.io/metadata.name: kube-system
                  podSelector:
                    matchLabels:
                      k8s-app: kube-dns
              ports:
                - port: 53
                  protocol: UDP
    """)


def gen_kyverno_policy(args) -> str:
    return dedent(f"""\
        # Kyverno ClusterPolicy: enforce security baseline for {args.namespace}
        apiVersion: kyverno.io/v1
        kind: ClusterPolicy
        metadata:
          name: {args.team}-security-baseline
          annotations:
            policies.kyverno.io/title: "{args.team} Security Baseline"
            policies.kyverno.io/severity: high
        spec:
          validationFailureAction: {"Enforce" if args.tier >= 3 else "Audit"}
          background: true
          rules:
            - name: require-non-root
              match:
                any:
                  - resources:
                      kinds: ["Pod"]
                      namespaces: ["{args.namespace}"]
              validate:
                message: "Containers must run as non-root and drop ALL capabilities."
                pattern:
                  spec:
                    containers:
                      - securityContext:
                          runAsNonRoot: true
                          allowPrivilegeEscalation: false
                          capabilities:
                            drop: ["ALL"]
            - name: disallow-latest-tag
              match:
                any:
                  - resources:
                      kinds: ["Pod"]
                      namespaces: ["{args.namespace}"]
              validate:
                message: "Use specific image tags, not 'latest'."
                foreach:
                  - list: "request.object.spec.containers"
                    deny:
                      conditions:
                        any:
                          - key: "{{{{element.image}}}}"
                            operator: Equals
                            value: "*:latest"
            - name: require-resource-limits
              match:
                any:
                  - resources:
                      kinds: ["Pod"]
                      namespaces: ["{args.namespace}"]
              validate:
                message: "Containers must define CPU and memory limits."
                pattern:
                  spec:
                    containers:
                      - resources:
                          limits:
                            cpu: "?*"
                            memory: "?*"
    """)


def gen_cert_manager(args) -> str:
    if args.tier <= 1:
        issuer = "selfsigned-root"
    elif args.tier <= 2:
        issuer = "letsencrypt-staging"
    else:
        issuer = "letsencrypt-prod"

    return dedent(f"""\
        # cert-manager Certificate: {args.app_name} TLS
        apiVersion: cert-manager.io/v1
        kind: Certificate
        metadata:
          name: {args.app_name}-tls
          namespace: {args.namespace}
        spec:
          secretName: {args.app_name}-tls
          duration: {"8760h" if args.tier <= 1 else "24h"}
          renewBefore: {"720h" if args.tier <= 1 else "8h"}
          privateKey:
            algorithm: ECDSA
            size: 384
            rotationPolicy: Always
          usages:
            - server auth
            - client auth
          commonName: {args.app_name}.{args.namespace}.svc.cluster.local
          dnsNames:
            - {args.app_name}
            - {args.app_name}.{args.namespace}
            - {args.app_name}.{args.namespace}.svc
            - {args.app_name}.{args.namespace}.svc.cluster.local
          issuerRef:
            name: {issuer}
            kind: ClusterIssuer
            group: cert-manager.io
    """)


def gen_compliance_checklist(args) -> str:
    lines = [f"# Compliance Checklist — {args.namespace}/{args.app_name}",
             f"# Tier {args.tier}: {TIER_NAMES[args.tier]}",
             f"# Generated: {datetime.now().isoformat()}",
             f"# Compliance: {', '.join(args.compliance).upper() or 'None'}",
             "", "## CIS Kubernetes Benchmark 1.9"]

    cis = [
        ("5.1.1", "cluster-admin only to admins", "rbac_roles.yaml — no cluster-admin bindings"),
        ("5.1.2", "Minimize secret access", "rbac_roles.yaml — resourceNames restriction"),
        ("5.1.4", "No auto-mount SA tokens", "service_account.yaml — automountServiceAccountToken: false"),
        ("5.2.2", "No privileged containers", "kyverno_policy.yaml — disallow-privileged"),
        ("5.2.5", "Non-root containers", "kyverno_policy.yaml — require-non-root"),
        ("1.2.13", "Audit log enabled", "audit_policy.yaml"),
        ("4.2.x", "NetworkPolicy applied", "network_policy.yaml — default-deny"),
    ]
    for ctrl, desc, file in cis:
        lines.append(f"- [{ctrl}] {desc} → {file}")

    if "soc2" in args.compliance:
        lines.extend(["", "## SOC 2 Type II",
                      "- [CC6.1] Logical access → RBAC + OIDC groups",
                      "- [CC6.6] Privileged access restricted → kyverno + rbac",
                      "- [CC7.1] Monitoring → audit_policy.yaml",
                      "- [CC9.2] Change management → GitOps (apply via PR)"])

    if "hipaa" in args.compliance:
        lines.extend(["", "## HIPAA Technical Safeguards",
                      "- [164.312(a)] Access Control → RBAC + OIDC MFA",
                      "- [164.312(b)] Audit Controls → audit_policy.yaml",
                      "- [164.312(e)] Transmission Security → cert-manager TLS"])

    if "pci" in args.compliance:
        lines.extend(["", "## PCI-DSS v4.0",
                      "- [7.2] Least privilege → scoped Roles/RoleBindings",
                      "- [8.3] MFA for admin → OIDC IdP with MFA required",
                      "- [10.2] Audit events → audit_policy.yaml"])

    lines.extend(["", "## Action Items",
                  "- [ ] Replace <PLACEHOLDER> values in all YAMLs",
                  "- [ ] Configure OIDC issuer URL in kube-apiserver",
                  "- [ ] Apply Kyverno/OPA policies before workloads",
                  "- [ ] Verify: kubectl auth can-i --list --as=system:serviceaccount:{args.namespace}:{args.app_name}-sa",
                  "- [ ] Run audit: scripts/rbac_audit.sh",
                  "- [ ] Review anti-patterns: references/anti-patterns.md"])

    return "\n".join(lines)


def gen_rbac_audit_script(args) -> str:
    return dedent(f"""\
        #!/bin/bash
        # rbac_audit.sh — Quick RBAC audit for {args.namespace}
        # Generated by scaffold_authz.py

        NS="{args.namespace}"
        APP="{args.app_name}"

        echo "=== Checking cluster-admin bindings ==="
        kubectl get clusterrolebindings -o json | \\
          jq -r '.items[] | select(.roleRef.name=="cluster-admin") | "\\(.metadata.name): \\(.subjects[].name)"'

        echo ""
        echo "=== Permissions for $APP SA ==="
        kubectl auth can-i --list \\
          --as=system:serviceaccount:$NS:$APP-sa \\
          --namespace=$NS 2>/dev/null | head -20

        echo ""
        echo "=== Namespaces without NetworkPolicy ==="
        for ns in $(kubectl get namespaces -o name | cut -d/ -f2); do
          count=$(kubectl get networkpolicies -n $ns --no-headers 2>/dev/null | wc -l)
          [ "$count" -eq 0 ] && echo "  WARNING: $ns has no NetworkPolicy"
        done

        echo ""
        echo "=== SAs with auto-mount enabled in $NS ==="
        kubectl get sa -n $NS -o json | \\
          jq -r '.items[] | select(.automountServiceAccountToken != false) | "  WARNING: \\(.metadata.name) has automount enabled"'

        echo ""
        echo "=== PSA labels on $NS ==="
        kubectl get namespace $NS -o jsonpath='{{.metadata.labels}}' | jq .

        echo ""
        echo "Audit complete."
    """)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _env_label(tier: int) -> str:
    return {1: "dev", 2: "staging", 3: "production", 4: "enterprise", 5: "fleet"}[tier]


def _cloud_annotation(args, role_suffix: str = "") -> str:
    suffix = f"-{role_suffix}" if role_suffix else ""
    if args.cloud == "aws":
        return f'    eks.amazonaws.com/role-arn: "arn:aws:iam::ACCOUNT_ID:role/{args.team}-{args.app_name}{suffix}-role"\n    eks.amazonaws.com/sts-regional-endpoints: "true"'
    elif args.cloud == "gcp":
        return f'    iam.gke.io/gcp-service-account: "{args.app_name}{suffix}@PROJECT_ID.iam.gserviceaccount.com"'
    elif args.cloud == "azure":
        return f'    azure.workload.identity/client-id: "AZURE_CLIENT_ID"\n    azure.workload.identity/tenant-id: "AZURE_TENANT_ID"'
    return ""


def write_file(path: Path, content: str, mode: int = 0o644):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(mode)
        print(f"  Created: {path}")
    except OSError as e:
        print(f"  ERROR writing {path}: {e}", file=sys.stderr)
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Scaffold Kubernetes authorization configs",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tier", type=int, default=2, choices=[1, 2, 3, 4, 5])
    parser.add_argument("--namespace", default="team-backend")
    parser.add_argument("--team", default="backend")
    parser.add_argument("--app-name", default="my-app")
    parser.add_argument("--cloud", default="none", choices=["aws", "gcp", "azure", "on-prem", "none"])
    parser.add_argument("--identities", default="sa,users,groups",
                        help="Comma-separated: users,groups,sa,ai-agents,nodes,clusters")
    parser.add_argument("--policy", default=None, choices=["kyverno", "opa", "both", "none"])
    parser.add_argument("--zero-trust", default=None, choices=["cert-manager", "spire", "istio", "linkerd", "none"])
    parser.add_argument("--compliance", default="", help="Comma-separated: soc2,hipaa,pci,fedramp,cis")
    parser.add_argument("--oidc-group", default="team-developers")
    parser.add_argument("--output", default="./authz-output/")
    return parser.parse_args()


def main():
    args = parse_args()
    args.identities = [i.strip() for i in args.identities.split(",")]
    args.compliance = [c.strip().lower() for c in args.compliance.split(",") if c.strip()]

    # Apply tier defaults
    defaults = TIER_DEFAULTS[args.tier]
    if args.policy is None:
        args.policy = defaults["policy"]
    if args.zero_trust is None:
        args.zero_trust = defaults["zero_trust"]

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print(f"\nAuthorizer Scaffold — Tier {args.tier}: {TIER_NAMES[args.tier]}")
    print(f"  Namespace: {args.namespace}  |  Team: {args.team}  |  App: {args.app_name}")
    print(f"  Cloud: {args.cloud}  |  Policy: {args.policy}  |  Zero-trust: {args.zero_trust}")
    print(f"  Identities: {', '.join(args.identities)}")
    print(f"  Compliance: {', '.join(args.compliance) or 'none'}\n")
    print("Generating files...")

    write_file(out / "namespace.yaml", gen_namespace(args))
    write_file(out / "service_account.yaml", gen_service_account(args))

    if "ai-agents" in args.identities:
        with open(out / "service_account.yaml", "a") as f:
            f.write("\n---\n" + gen_ai_agent_sa(args))

    write_file(out / "rbac_roles.yaml", gen_roles(args))
    write_file(out / "rbac_bindings.yaml", gen_bindings(args))
    write_file(out / "network_policy.yaml", gen_network_policy(args))

    if args.policy in ("kyverno", "both"):
        write_file(out / "kyverno_policy.yaml", gen_kyverno_policy(args))

    if args.zero_trust in ("cert-manager",):
        write_file(out / "cert_manager.yaml", gen_cert_manager(args))

    # Copy audit policy template
    import shutil
    skill_assets = Path(__file__).parent.parent / "assets" / "audit_policy.yaml"
    if skill_assets.exists():
        shutil.copy(skill_assets, out / "audit_policy.yaml")
        print(f"  Copied: {out / 'audit_policy.yaml'}")

    write_file(out / "COMPLIANCE_CHECKLIST.md", gen_compliance_checklist(args))
    write_file(out / "scripts" / "rbac_audit.sh", gen_rbac_audit_script(args), mode=0o755)

    # Generate kustomization.yaml
    kustomize_resources = [
        "namespace.yaml",
        "service_account.yaml",
        "rbac_roles.yaml",
        "rbac_bindings.yaml",
        "network_policy.yaml",
    ]
    if args.policy in ("kyverno", "both"):
        kustomize_resources.append("kyverno_policy.yaml")
    if args.zero_trust == "cert-manager":
        kustomize_resources.append("cert_manager.yaml")
    kustomize_resources.append("audit_policy.yaml")

    kustomize = "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n"
    kustomize += "".join(f"  - {r}\n" for r in kustomize_resources)
    write_file(out / "kustomization.yaml", kustomize)

    print(f"\nScaffold complete! {len(list(out.rglob('*')))} files generated.")
    print(f"\nNext steps:")
    print(f"  1. cd {out}")
    print(f"  2. Replace all <PLACEHOLDER> values")
    print(f"  3. kubectl apply -k .")
    print(f"  4. bash scripts/rbac_audit.sh")
    print(f"  5. Review COMPLIANCE_CHECKLIST.md")
    if args.policy in ("kyverno", "both"):
        print(f"\nPolicy testing:")
        print(f"  kyverno test .   # requires kyverno CLI: https://kyverno.io/docs/kyverno-cli/")
    if args.policy in ("opa", "both"):
        print(f"  conftest test .  # requires conftest: https://www.conftest.dev/")


if __name__ == "__main__":
    main()
