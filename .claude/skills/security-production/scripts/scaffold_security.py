#!/usr/bin/env python3
"""
scaffold_security.py — Security Production Scaffold Generator

Generates a complete security configuration project based on tier, compliance
requirements, cloud provider, and security components needed.

Usage:
    python scaffold_security.py --help
    python scaffold_security.py --name myapp --tier 2 --cloud aws --compliance soc2
    python scaffold_security.py --name myapp --tier 3 --cloud gcp --compliance hipaa --secrets vault
    python scaffold_security.py --name myapp --tier 4 --cloud aws --compliance fedramp --runtime falco --mesh istio
    python scaffold_security.py --audit --namespace production    # Compliance gap audit
"""

import argparse
import os
import sys
import json
from pathlib import Path
from datetime import datetime


# ─────────────────────────────────────────────
# Configuration Maps
# ─────────────────────────────────────────────

TIER_DESCRIPTIONS = {
    1: "Hardened Dev (non-root, NetworkPolicy, RBAC, Trivy)",
    2: "Production (PSS Restricted, mTLS, Sealed Secrets, Falco, SOC2 readiness)",
    3: "Enterprise (Zero-trust SPIFFE/SPIRE, Vault HA, OPA+Kyverno, HIPAA/SOC2 Type II)",
    4: "Regulated (FIPS 140-2, HSM, FedRAMP, PCI-DSS v4, immutable audit)",
}

COMPLIANCE_CONTROLS = {
    "soc2": {
        "name": "SOC 2 Type II",
        "controls": ["CC6.1", "CC6.2", "CC6.3", "CC6.6", "CC6.7", "CC7.1", "CC7.2", "CC7.3", "CC8.1"],
        "min_tier": 2,
        "requires": ["rbac", "networkpolicy", "audit_logging", "tls"],
    },
    "hipaa": {
        "name": "HIPAA Technical Safeguards",
        "controls": ["164.312(a)", "164.312(b)", "164.312(c)", "164.312(e)"],
        "min_tier": 3,
        "requires": ["rbac", "networkpolicy", "encryption_at_rest", "audit_logging", "mfa", "tls"],
    },
    "pci": {
        "name": "PCI-DSS v4",
        "controls": ["Req 1", "Req 2", "Req 3", "Req 4", "Req 7", "Req 8", "Req 10", "Req 12"],
        "min_tier": 3,
        "requires": ["networkpolicy", "encryption", "audit_logging", "mfa", "vulnerability_scanning"],
    },
    "fedramp": {
        "name": "FedRAMP Moderate/High",
        "controls": ["AC-2", "AC-3", "AU-2", "AU-12", "CM-6", "IA-2", "SC-8", "SI-2"],
        "min_tier": 4,
        "requires": ["fips_140_2", "hsm", "mfa", "audit_logging", "vulnerability_scanning", "pen_test"],
    },
    "cis": {
        "name": "CIS Kubernetes Benchmark L2",
        "controls": ["1.1", "1.2", "2.1", "3.1", "4.1", "4.2", "5.1", "5.2", "5.4"],
        "min_tier": 2,
        "requires": ["rbac", "pss", "networkpolicy", "audit_logging"],
    },
}


def create_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, content: str, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        print(f"  [skip] {path} (already exists)")
        return
    path.write_text(content)
    print(f"  [ok] {path}")


# ─────────────────────────────────────────────
# File Generators
# ─────────────────────────────────────────────

def gen_namespace_yaml(app: str, namespace: str, tier: int) -> str:
    pss_level = "restricted" if tier >= 2 else "baseline"
    return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    pod-security.kubernetes.io/enforce: {pss_level}
    pod-security.kubernetes.io/enforce-version: v1.32
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/audit: restricted
    app.kubernetes.io/managed-by: security-production
    security-tier: "tier-{tier}"
"""


def gen_serviceaccount_yaml(app: str, namespace: str, cloud: str) -> str:
    annotations = ""
    if cloud == "aws":
        annotations = f"""  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT_ID:role/{app}-role"""
    elif cloud == "gcp":
        annotations = f"""  annotations:
    iam.gke.io/gcp-service-account: {app}@PROJECT_ID.iam.gserviceaccount.com"""
    elif cloud == "azure":
        annotations = f"""  annotations:
    azure.workload.identity/client-id: "CLIENT_ID"
    azure.workload.identity/tenant-id: "TENANT_ID" """

    return f"""apiVersion: v1
kind: ServiceAccount
metadata:
  name: {app}
  namespace: {namespace}
{annotations}
  labels:
    app: {app}
automountServiceAccountToken: false
"""


def gen_rbac_yaml(app: str, namespace: str) -> str:
    return f"""apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: {app}-role
  namespace: {namespace}
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["{app}-config"]
    verbs: ["get", "watch"]
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["{app}-secrets"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: {app}-binding
  namespace: {namespace}
subjects:
  - kind: ServiceAccount
    name: {app}
    namespace: {namespace}
roleRef:
  kind: Role
  apiVersion: rbac.authorization.k8s.io/v1
  name: {app}-role
"""


def gen_deployment_yaml(app: str, namespace: str, tier: int) -> str:
    seccomp = "RuntimeDefault" if tier >= 2 else "RuntimeDefault"
    return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app}
  namespace: {namespace}
  labels:
    app: {app}
    version: "1.0.0"
spec:
  replicas: {3 if tier >= 2 else 1}
  selector:
    matchLabels:
      app: {app}
  template:
    metadata:
      labels:
        app: {app}
      annotations:
        container.apparmor.security.beta.kubernetes.io/{app}: runtime/default
    spec:
      serviceAccountName: {app}
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 65534
        runAsGroup: 65534
        fsGroup: 65534
        seccompProfile:
          type: {seccomp}
      containers:
        - name: {app}
          image: ghcr.io/myorg/{app}@sha256:REPLACE_WITH_DIGEST
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            runAsUser: 65534
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              memory: "64Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "1000m"
          livenessProbe:
            httpGet: {{path: /health/live, port: 8080}}
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet: {{path: /health/ready, port: 8080}}
            initialDelaySeconds: 5
            periodSeconds: 10
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            medium: Memory
            sizeLimit: 100Mi
"""


def gen_networkpolicy_yaml(app: str, namespace: str) -> str:
    return f"""# Default-deny-all for {namespace}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: {namespace}
spec:
  podSelector: {{}}
  policyTypes: [Ingress, Egress]
---
# Allow DNS
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: {namespace}
spec:
  podSelector: {{}}
  policyTypes: [Egress]
  egress:
    - ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
---
# Allow {app} ingress from API Gateway
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {app}-ingress
  namespace: {namespace}
spec:
  podSelector:
    matchLabels:
      app: {app}
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
      ports:
        - port: 8080
"""


def gen_compliance_matrix(compliance: str, tier: int, app: str) -> str:
    if compliance not in COMPLIANCE_CONTROLS:
        return "# No compliance matrix selected\n"

    ctrl = COMPLIANCE_CONTROLS[compliance]
    controls_list = "\n".join(f"# - {c}" for c in ctrl["controls"])
    requires_list = "\n".join(f"# - {r}" for r in ctrl["requires"])

    return f"""# Compliance Matrix: {ctrl['name']}
# Generated: {datetime.now().strftime('%Y-%m-%d')}
# Application: {app}
# Tier: {tier}
#
# Applicable Controls:
{controls_list}
#
# Technical Requirements:
{requires_list}
#
# Control Implementation Status:
# Use this as the basis for your compliance evidence collection.
# Each control must have:
#   1. Technical implementation (configs in this project)
#   2. Evidence collection (automated or manual)
#   3. Testing procedure (how to verify)
#   4. Review schedule (how often to audit)
#
# See references/compliance-frameworks.md for detailed implementation guide.
"""


def gen_makefile(app: str, namespace: str, tier: int) -> str:
    return f"""# Makefile — Security Operations for {app}
# Usage: make help

.PHONY: help scan apply audit rotate-secrets

help:
\t@echo "Security Operations for {app}"
\t@echo ""
\t@echo "  make scan         Run Trivy vulnerability scan"
\t@echo "  make apply        Apply all security configurations"
\t@echo "  make audit        Run security audit (kube-bench + policy check)"
\t@echo "  make rotate       Rotate secrets"
\t@echo "  make compliance   Generate compliance evidence"

scan:
\t@echo "Running Trivy scan..."
\ttrivy image ghcr.io/myorg/{app}:latest --severity CRITICAL,HIGH --exit-code 1

apply:
\t@echo "Applying security configurations..."
\tkubectl apply -f manifests/namespace.yaml
\tkubectl apply -f manifests/serviceaccount.yaml
\tkubectl apply -f manifests/rbac.yaml
\tkubectl apply -f manifests/networkpolicies.yaml
\tkubectl apply -f manifests/deployment.yaml
\t@echo "Done. Verify with: kubectl get pods -n {namespace}"

audit:
\t@echo "Running security audit..."
\tkubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job.yaml
\tkubectl wait --for=condition=complete job/kube-bench --timeout=120s
\tkubectl logs -l app=kube-bench
\t@echo "Checking Kyverno policy violations..."
\tkubectl get policyreport -n {namespace} -o json | jq '.items[].results[] | select(.result=="fail")'

rotate-secrets:
\t@echo "Rotating secrets for {app}..."
\t# If using Vault: vault write -force auth/kubernetes/role/{app}
\t# If using Sealed Secrets: kubeseal --rotate-credentials
\t@echo "Manual rotation required - see references/secrets-management.md"

compliance:
\t@echo "Collecting compliance evidence for {app}..."
\tmkdir -p compliance-evidence-$$(date +%Y%m)
\tkubectl get networkpolicies -n {namespace} -o yaml > compliance-evidence-$$(date +%Y%m)/networkpolicies.yaml
\tkubectl get roles,rolebindings -n {namespace} -o yaml > compliance-evidence-$$(date +%Y%m)/rbac.yaml
\tkubectl get pods -n {namespace} -o json | jq '[.items[] | {{name: .metadata.name, securityContext: .spec.securityContext}}]' > compliance-evidence-$$(date +%Y%m)/pod-security.json
\t@echo "Evidence collected in compliance-evidence-$$(date +%Y%m)/"
"""


# ─────────────────────────────────────────────
# Main Scaffold Function
# ─────────────────────────────────────────────

def scaffold_project(args: argparse.Namespace) -> None:
    app = args.name
    namespace = args.namespace or app
    tier = args.tier
    cloud = args.cloud
    compliance = args.compliance
    output_dir = Path(args.output or f"security-{app}")

    print(f"\n{'='*60}")
    print(f"Security Production Scaffold")
    print(f"{'='*60}")
    print(f"  App:        {app}")
    print(f"  Namespace:  {namespace}")
    print(f"  Tier:       {tier} — {TIER_DESCRIPTIONS[tier]}")
    print(f"  Cloud:      {cloud}")
    print(f"  Compliance: {compliance}")
    print(f"  Output:     {output_dir}")
    print(f"{'='*60}\n")

    # Validate compliance tier
    if compliance in COMPLIANCE_CONTROLS:
        min_tier = COMPLIANCE_CONTROLS[compliance]["min_tier"]
        if tier < min_tier:
            print(f"WARNING: {compliance.upper()} requires Tier {min_tier}+. Upgrading tier to {min_tier}.")
            tier = min_tier

    # Create directory structure
    dirs = [
        output_dir / "manifests",
        output_dir / "policies" / "kyverno",
        output_dir / "policies" / "opa",
        output_dir / "compliance-evidence",
        output_dir / "scripts",
    ]
    if tier >= 3:
        dirs.append(output_dir / "vault")
    if tier >= 3:
        dirs.append(output_dir / "monitoring")

    for d in dirs:
        create_dir(d)
        print(f"  mkdir: {d}")

    print()

    # Generate manifests
    write_file(output_dir / "manifests" / "namespace.yaml", gen_namespace_yaml(app, namespace, tier))
    write_file(output_dir / "manifests" / "serviceaccount.yaml", gen_serviceaccount_yaml(app, namespace, cloud))
    write_file(output_dir / "manifests" / "rbac.yaml", gen_rbac_yaml(app, namespace))
    write_file(output_dir / "manifests" / "deployment.yaml", gen_deployment_yaml(app, namespace, tier))
    write_file(output_dir / "manifests" / "networkpolicies.yaml", gen_networkpolicy_yaml(app, namespace))

    # Generate Kyverno policies
    kyverno_src = Path(__file__).parent.parent / "assets" / "templates" / "kyverno_security_policies.yaml"
    if kyverno_src.exists():
        write_file(output_dir / "policies" / "kyverno" / "cluster-policies.yaml", kyverno_src.read_text())

    # Generate compliance matrix
    write_file(
        output_dir / "compliance-evidence" / f"{compliance}-controls.md",
        gen_compliance_matrix(compliance, tier, app)
    )

    # Generate Makefile
    write_file(output_dir / "Makefile", gen_makefile(app, namespace, tier))

    # Generate README
    write_file(output_dir / "README.md", gen_readme(app, namespace, tier, cloud, compliance))

    print(f"\n{'='*60}")
    print(f"Project generated: {output_dir}/")
    print(f"\nNext steps:")
    print(f"  1. cd {output_dir}")
    print(f"  2. Update IMAGE digest in manifests/deployment.yaml")
    print(f"  3. Review and customize policies/kyverno/cluster-policies.yaml")
    print(f"  4. make apply")
    print(f"  5. make audit")
    print(f"  6. make compliance")
    print(f"{'='*60}\n")


def gen_readme(app: str, namespace: str, tier: int, cloud: str, compliance: str) -> str:
    return f"""# Security Configuration — {app}

Generated by security-production skill on {datetime.now().strftime('%Y-%m-%d')}.

## Configuration

| Setting | Value |
|---------|-------|
| Application | {app} |
| Namespace | {namespace} |
| Security Tier | {tier} — {TIER_DESCRIPTIONS[tier]} |
| Cloud Provider | {cloud.upper()} |
| Compliance Target | {compliance.upper()} |

## Contents

- `manifests/` — Kubernetes manifests (namespace, SA, RBAC, deployment, NetworkPolicy)
- `policies/kyverno/` — Kyverno ClusterPolicies for admission control
- `policies/opa/` — OPA Gatekeeper ConstraintTemplates
- `compliance-evidence/` — Compliance control matrix
- `Makefile` — Security operations commands

## Quick Start

```bash
# Apply all security configurations
make apply

# Run security audit
make audit

# Scan container image
make scan

# Collect compliance evidence
make compliance
```

## References

See `.claude/skills/security-production/references/` for detailed documentation:
- `cloud-security.md` — Cloud provider controls
- `k8s-security.md` — Kubernetes hardening
- `container-security.md` — Container hardening
- `secrets-management.md` — Vault / ESO / Sealed Secrets
- `supply-chain-security.md` — Cosign / SBOM / SLSA
- `compliance-frameworks.md` — {compliance.upper()} control details
"""


def audit_mode(args: argparse.Namespace) -> None:
    """Run a quick security audit against current cluster config."""
    namespace = args.namespace or "production"
    print(f"\nSecurity Audit — Namespace: {namespace}")
    print("=" * 50)
    print("Run these commands to assess your security posture:\n")

    checks = [
        ("RBAC: cluster-admin bindings", "kubectl get clusterrolebindings -o json | jq '.items[] | select(.roleRef.name == \"cluster-admin\") | .subjects'"),
        ("RBAC: privileged SA", "kubectl get pods -n " + namespace + " -o json | jq -r '.items[] | .metadata.name + \" → SA: \" + .spec.serviceAccountName'"),
        ("Pods running as root", "kubectl get pods -n " + namespace + ' -o json | jq \'.items[] | select(.spec.securityContext.runAsUser == 0 or .spec.containers[].securityContext.runAsUser == 0) | .metadata.name\''),
        ("Missing NetworkPolicies", "kubectl get namespaces -o name | while read ns; do count=$(kubectl get networkpolicies -n ${ns#*/} 2>/dev/null | wc -l); [ $count -le 1 ] && echo \"No NetworkPolicy: ${ns}\"; done"),
        ("Secrets in env vars", "kubectl get pods -n " + namespace + " -o json | jq '.items[].spec.containers[].env[] | select(.value != null and (.name | test(\"PASSWORD|SECRET|TOKEN|KEY\"; \"i\"))) | .name'"),
        ("CIS Benchmark", "kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job.yaml && kubectl wait --for=condition=complete job/kube-bench --timeout=120s && kubectl logs -l app=kube-bench"),
    ]

    for name, cmd in checks:
        print(f"# {name}")
        print(f"$ {cmd}\n")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Security Production Scaffold Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scaffold_security.py --name myapp --tier 2 --cloud aws
  python scaffold_security.py --name myapp --tier 3 --compliance hipaa --secrets vault
  python scaffold_security.py --name myapp --tier 4 --compliance fedramp --cloud aws
  python scaffold_security.py --audit --namespace production
        """
    )

    parser.add_argument("--name", "-n", help="Application name")
    parser.add_argument("--namespace", help="Kubernetes namespace (defaults to app name)")
    parser.add_argument("--tier", "-t", type=int, choices=[1, 2, 3, 4], default=2,
                        help="Security tier (1=dev, 2=prod, 3=enterprise, 4=regulated)")
    parser.add_argument("--cloud", "-c", choices=["aws", "gcp", "azure", "onprem"], default="aws",
                        help="Cloud provider")
    parser.add_argument("--compliance", choices=["soc2", "hipaa", "pci", "fedramp", "cis", "none"],
                        default="soc2", help="Compliance framework")
    parser.add_argument("--secrets", choices=["vault", "sealed-secrets", "eso", "sops"],
                        default="vault", help="Secrets management backend")
    parser.add_argument("--runtime", choices=["falco", "tetragon", "none"],
                        default="falco", help="Runtime security tool")
    parser.add_argument("--mesh", choices=["istio", "cilium", "none"],
                        default="none", help="Service mesh (required for Tier 3+)")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--audit", action="store_true", help="Run audit mode only")

    args = parser.parse_args()

    if args.audit:
        audit_mode(args)
        return

    if not args.name:
        parser.error("--name is required unless using --audit")

    scaffold_project(args)


if __name__ == "__main__":
    main()
