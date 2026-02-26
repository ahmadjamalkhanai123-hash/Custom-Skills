#!/usr/bin/env python3
"""
security_mcp_server.py — Security Production MCP Server

Provides 5 security tools for CI/CD integration and ongoing security operations.

Tools:
  1. scan_image          — Trivy image vulnerability scan
  2. audit_rbac          — RBAC over-privilege detection
  3. check_policies      — Validate Kyverno/OPA policy reports
  4. validate_secrets    — Check for secret misconfigurations
  5. compliance_check    — Map controls to compliance frameworks

Usage:
  python security_mcp_server.py          # stdio transport (for Claude)
  Add to ~/.claude/claude_desktop_config.json as MCP server

Dependencies:
  pip install fastmcp anthropic
"""

import json
import subprocess
import sys
from typing import Any

try:
    from fastmcp import FastMCP
except ImportError:
    print("FastMCP not installed. Run: pip install fastmcp", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP(
    name="security-production",
    version="1.0.0",
    description="Production security operations: image scanning, RBAC audit, policy validation, secrets check, compliance mapping",
)


# ─────────────────────────────────────────────
# Helper: run kubectl safely
# ─────────────────────────────────────────────

def kubectl(args: list[str], namespace: str | None = None) -> dict[str, Any]:
    """Run kubectl command and return parsed JSON output."""
    cmd = ["kubectl"]
    if namespace:
        cmd.extend(["-n", namespace])
    cmd.extend(args)
    cmd.extend(["-o", "json"])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=False
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "command": " ".join(cmd)}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "kubectl command timed out", "command": " ".join(cmd)}
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse kubectl output: {e}", "raw": result.stdout[:500]}
    except FileNotFoundError:
        return {"error": "kubectl not found. Install kubectl and configure kubeconfig."}


def run_cmd(cmd: list[str]) -> dict[str, Any]:
    """Run a shell command and return stdout/stderr."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, check=False
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out", "command": " ".join(cmd)}
    except FileNotFoundError:
        return {"error": f"Command not found: {cmd[0]}"}


# ─────────────────────────────────────────────
# Tool 1: scan_image
# ─────────────────────────────────────────────

@mcp.tool()
def scan_image(
    image: str,
    severity: str = "CRITICAL,HIGH",
    format: str = "summary",
    ignore_unfixed: bool = True,
) -> dict[str, Any]:
    """
    Scan a container image for vulnerabilities using Trivy.

    Args:
        image: Container image reference (e.g., ghcr.io/myorg/myapp:v1.2.3 or @sha256:...)
        severity: Comma-separated severity levels to check (CRITICAL,HIGH,MEDIUM,LOW,UNKNOWN)
        format: Output format: "summary" (counts by severity) or "full" (all CVEs)
        ignore_unfixed: Only report vulnerabilities with available fixes

    Returns:
        Vulnerability counts, critical CVEs, and scan status (pass/fail)
    """
    if not image:
        return {"error": "image parameter is required"}

    # Run Trivy
    cmd = [
        "trivy", "image",
        "--format", "json",
        "--severity", severity,
        "--scanners", "vuln,secret,misconfig",
        "--quiet",
    ]
    if ignore_unfixed:
        cmd.append("--ignore-unfixed")
    cmd.append(image)

    result = run_cmd(cmd)

    if "error" in result:
        return result

    try:
        data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {
            "scan_available": False,
            "message": "Trivy not installed or image not accessible",
            "install_cmd": "curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh",
            "image": image,
        }

    # Parse results
    total_vulns = {s: 0 for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]}
    critical_cves = []

    for result_item in data.get("Results", []):
        for vuln in result_item.get("Vulnerabilities", []) or []:
            sev = vuln.get("Severity", "UNKNOWN")
            total_vulns[sev] = total_vulns.get(sev, 0) + 1

            if sev == "CRITICAL":
                critical_cves.append({
                    "id": vuln.get("VulnerabilityID"),
                    "package": vuln.get("PkgName"),
                    "installed": vuln.get("InstalledVersion"),
                    "fixed_in": vuln.get("FixedVersion"),
                    "title": vuln.get("Title", "")[:100],
                })

    # Determine scan result
    requested_severities = [s.strip() for s in severity.split(",")]
    blocking_count = sum(total_vulns.get(s, 0) for s in ["CRITICAL", "HIGH"]
                         if s in requested_severities)

    scan_passed = blocking_count == 0

    output = {
        "image": image,
        "scan_passed": scan_passed,
        "gate_status": "PASS" if scan_passed else "FAIL",
        "severity_threshold": severity,
        "vulnerability_counts": total_vulns,
        "blocking_vulnerabilities": blocking_count,
        "recommendation": "Image is safe to deploy" if scan_passed else f"Block deployment — {blocking_count} blocking vulnerabilities found",
    }

    if format == "full" or critical_cves:
        output["critical_cves"] = critical_cves[:20]  # Limit to 20 for readability

    return output


# ─────────────────────────────────────────────
# Tool 2: audit_rbac
# ─────────────────────────────────────────────

@mcp.tool()
def audit_rbac(
    namespace: str = "",
    check_cluster_admin: bool = True,
    check_exec: bool = True,
    check_secrets_access: bool = True,
    check_wildcard_verbs: bool = True,
) -> dict[str, Any]:
    """
    Audit Kubernetes RBAC configurations for over-privileged roles and bindings.

    Args:
        namespace: Namespace to audit (empty = cluster-wide)
        check_cluster_admin: Check for cluster-admin bindings
        check_exec: Check for pod exec permissions
        check_secrets_access: Check for broad secrets access
        check_wildcard_verbs: Check for wildcard verb usage

    Returns:
        List of RBAC violations with severity and remediation advice
    """
    findings = []
    ns = namespace if namespace else None

    # Check cluster-admin bindings
    if check_cluster_admin:
        crbs = kubectl(["get", "clusterrolebindings"])
        if "error" not in crbs:
            for crb in crbs.get("items", []):
                if crb.get("roleRef", {}).get("name") == "cluster-admin":
                    subjects = crb.get("subjects", [])
                    for subject in subjects:
                        if subject.get("kind") == "ServiceAccount":
                            findings.append({
                                "severity": "CRITICAL",
                                "finding": "ServiceAccount with cluster-admin",
                                "resource": crb.get("metadata", {}).get("name"),
                                "subject": f"{subject.get('namespace')}/{subject.get('name')}",
                                "remediation": "Remove cluster-admin binding. Create a least-privilege Role instead.",
                            })

    # Check for wildcard verbs in roles
    if check_wildcard_verbs:
        roles_data = kubectl(["get", "roles", "--all-namespaces"] if not ns else ["get", "roles"], namespace=ns)
        if "error" not in roles_data:
            for role in roles_data.get("items", []):
                role_name = role.get("metadata", {}).get("name")
                role_ns = role.get("metadata", {}).get("namespace")
                for rule in role.get("rules", []):
                    if "*" in rule.get("verbs", []) or "*" in rule.get("resources", []):
                        findings.append({
                            "severity": "HIGH",
                            "finding": "Wildcard RBAC rule",
                            "resource": f"Role/{role_ns}/{role_name}",
                            "rule": rule,
                            "remediation": "Replace wildcard (*) with specific verbs and resources.",
                        })

    # Check for pod exec permissions
    if check_exec:
        all_roles = kubectl(["get", "roles", "--all-namespaces"] if not ns else ["get", "roles"], namespace=ns)
        if "error" not in all_roles:
            for role in all_roles.get("items", []):
                role_name = role.get("metadata", {}).get("name")
                for rule in role.get("rules", []):
                    if "pods/exec" in rule.get("resources", []):
                        findings.append({
                            "severity": "HIGH",
                            "finding": "pods/exec access granted",
                            "resource": f"Role/{role.get('metadata', {}).get('namespace')}/{role_name}",
                            "remediation": "Remove pods/exec permission. This enables interactive shell access and privilege escalation.",
                        })

    # Check for automounted default SA tokens
    if check_secrets_access:
        pods = kubectl(["get", "pods", "--all-namespaces"] if not ns else ["get", "pods"], namespace=ns)
        if "error" not in pods:
            for pod in pods.get("items", []):
                pod_name = pod.get("metadata", {}).get("name")
                pod_ns = pod.get("metadata", {}).get("namespace")
                sa = pod.get("spec", {}).get("serviceAccountName", "default")
                automount = pod.get("spec", {}).get("automountServiceAccountToken", True)

                if sa == "default" and pod_ns not in ("kube-system", "kube-public"):
                    findings.append({
                        "severity": "MEDIUM",
                        "finding": "Pod using default ServiceAccount",
                        "resource": f"Pod/{pod_ns}/{pod_name}",
                        "remediation": f"Create a dedicated ServiceAccount for this workload. Don't use 'default'.",
                    })

    # Summary
    severity_counts = {}
    for f in findings:
        sev = f["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "audit_scope": namespace or "cluster-wide",
        "total_findings": len(findings),
        "severity_counts": severity_counts,
        "findings": findings,
        "rbac_posture": "FAIL" if any(f["severity"] == "CRITICAL" for f in findings) else "WARN" if findings else "PASS",
        "recommendation": "Review CRITICAL findings immediately" if severity_counts.get("CRITICAL", 0) > 0 else "Address HIGH findings within 24h" if severity_counts.get("HIGH", 0) > 0 else "RBAC looks good",
    }


# ─────────────────────────────────────────────
# Tool 3: check_policies
# ─────────────────────────────────────────────

@mcp.tool()
def check_policies(
    namespace: str = "",
    engine: str = "kyverno",
    show_passing: bool = False,
) -> dict[str, Any]:
    """
    Check Kyverno or OPA Gatekeeper policy violation reports.

    Args:
        namespace: Namespace to check (empty = all namespaces)
        engine: Policy engine: "kyverno" or "gatekeeper"
        show_passing: Include passing resources in output

    Returns:
        Policy violations grouped by severity with remediation guidance
    """
    violations = []
    passing = []

    if engine == "kyverno":
        # Get Kyverno PolicyReports
        if namespace:
            reports = kubectl(["get", "policyreport", "-n", namespace])
        else:
            reports = kubectl(["get", "policyreport", "--all-namespaces"])

        if "error" in reports:
            return {
                "engine": "kyverno",
                "available": False,
                "message": "Kyverno not installed or no policy reports found",
                "install": "helm install kyverno kyverno/kyverno --namespace kyverno --create-namespace",
            }

        for report in reports.get("items", []):
            ns = report.get("metadata", {}).get("namespace", "cluster")
            for result in report.get("results", []):
                entry = {
                    "namespace": ns,
                    "resource": result.get("resource", {}),
                    "policy": result.get("policy"),
                    "rule": result.get("rule"),
                    "severity": result.get("severity", "medium").upper(),
                    "message": result.get("message", ""),
                    "status": result.get("result"),
                }
                if result.get("result") == "fail":
                    violations.append(entry)
                elif show_passing and result.get("result") == "pass":
                    passing.append(entry)

    elif engine == "gatekeeper":
        # Get OPA Gatekeeper constraint violations
        constraints = kubectl(["get", "constraints", "--all-namespaces"])

        if "error" in constraints:
            return {
                "engine": "gatekeeper",
                "available": False,
                "message": "OPA Gatekeeper not installed or no constraints found",
            }

        for constraint in constraints.get("items", []):
            violations_list = constraint.get("status", {}).get("violations", [])
            for v in violations_list:
                violations.append({
                    "constraint": constraint.get("metadata", {}).get("name"),
                    "resource": f"{v.get('kind')}/{v.get('namespace', 'cluster')}/{v.get('name')}",
                    "message": v.get("message"),
                    "enforcement": constraint.get("spec", {}).get("enforcementAction"),
                })

    # Count by severity
    severity_counts = {}
    for v in violations:
        sev = v.get("severity", "MEDIUM")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "engine": engine,
        "scope": namespace or "all-namespaces",
        "total_violations": len(violations),
        "severity_counts": severity_counts,
        "violations": violations[:50],  # Limit output
        "passing_count": len(passing),
        "posture": "FAIL" if violations else "PASS",
        "recommendation": f"Fix {len(violations)} policy violations" if violations else "All policies passing",
    }


# ─────────────────────────────────────────────
# Tool 4: validate_secrets
# ─────────────────────────────────────────────

@mcp.tool()
def validate_secrets(
    namespace: str = "",
    check_env_vars: bool = True,
    check_default_sa: bool = True,
    check_auto_mount: bool = True,
) -> dict[str, Any]:
    """
    Validate secrets management practices in a Kubernetes namespace.

    Args:
        namespace: Namespace to check (empty = all namespaces)
        check_env_vars: Check for secrets in environment variables
        check_default_sa: Check for use of default ServiceAccount
        check_auto_mount: Check for auto-mounted ServiceAccount tokens

    Returns:
        Secret management findings with risk ratings and remediation steps
    """
    findings = []
    ns = namespace if namespace else None

    pods = kubectl(["get", "pods", "--all-namespaces"] if not ns else ["get", "pods"], namespace=ns)

    if "error" in pods:
        return {"error": "Cannot access pods", "details": pods}

    secret_patterns = [
        "PASSWORD", "SECRET", "TOKEN", "KEY", "API_KEY",
        "PRIVATE_KEY", "ACCESS_KEY", "AUTH", "CREDENTIAL",
        "PASSWD", "PASS", "PWD"
    ]

    for pod in pods.get("items", []):
        pod_name = pod.get("metadata", {}).get("name")
        pod_ns = pod.get("metadata", {}).get("namespace")

        if pod_ns in ("kube-system", "kube-public", "kube-node-lease"):
            continue

        spec = pod.get("spec", {})

        # Check env vars for plaintext secrets
        if check_env_vars:
            for container in spec.get("containers", []) + spec.get("initContainers", []):
                for env in container.get("env", []):
                    env_name = env.get("name", "").upper()
                    if any(pattern in env_name for pattern in secret_patterns):
                        if "value" in env and env.get("value"):  # Plaintext value
                            findings.append({
                                "severity": "CRITICAL",
                                "finding": "Plaintext secret in environment variable",
                                "pod": f"{pod_ns}/{pod_name}",
                                "container": container.get("name"),
                                "env_var": env.get("name"),
                                "remediation": "Use Vault Agent Injector, External Secrets Operator, or Sealed Secrets instead of env value.",
                            })

        # Check for auto-mounted SA tokens
        if check_auto_mount:
            automount = spec.get("automountServiceAccountToken", True)
            if automount is True or automount is None:
                sa = spec.get("serviceAccountName", "default")
                findings.append({
                    "severity": "MEDIUM",
                    "finding": "ServiceAccount token auto-mounted",
                    "pod": f"{pod_ns}/{pod_name}",
                    "serviceAccount": sa,
                    "remediation": "Set automountServiceAccountToken: false in pod spec and use projected tokens if needed.",
                })

        # Check for default SA
        if check_default_sa:
            sa = spec.get("serviceAccountName", "default")
            if sa == "default":
                findings.append({
                    "severity": "MEDIUM",
                    "finding": "Pod using default ServiceAccount",
                    "pod": f"{pod_ns}/{pod_name}",
                    "remediation": "Create a dedicated ServiceAccount per workload with minimal RBAC permissions.",
                })

    severity_counts = {}
    for f in findings:
        sev = f["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "scope": namespace or "all-namespaces",
        "total_findings": len(findings),
        "severity_counts": severity_counts,
        "findings": findings,
        "secrets_posture": "FAIL" if severity_counts.get("CRITICAL", 0) > 0 else "WARN" if findings else "PASS",
        "recommendation": (
            "CRITICAL: Remove plaintext secrets from env vars immediately"
            if severity_counts.get("CRITICAL", 0) > 0
            else "Implement proper secrets management (Vault/ESO/Sealed Secrets)"
            if findings
            else "Secrets management practices look good"
        ),
    }


# ─────────────────────────────────────────────
# Tool 5: compliance_check
# ─────────────────────────────────────────────

@mcp.tool()
def compliance_check(
    framework: str,
    namespace: str = "production",
) -> dict[str, Any]:
    """
    Check compliance posture against a security framework.

    Performs automated checks for relevant controls and provides
    a gap analysis with remediation priorities.

    Args:
        framework: Compliance framework to check:
                   "soc2", "hipaa", "pci", "fedramp", "cis"
        namespace: Kubernetes namespace to evaluate

    Returns:
        Compliance gap analysis with control status and remediation guidance
    """
    FRAMEWORKS = {
        "soc2": {
            "name": "SOC 2 Type II",
            "controls": {
                "CC6.1": "Logical access controls",
                "CC6.3": "Pod Security Standards",
                "CC6.6": "Network segmentation",
                "CC6.7": "Encryption in transit",
                "CC7.1": "System monitoring",
                "CC7.3": "Security event logging",
                "CC8.1": "Change management (GitOps)",
            }
        },
        "hipaa": {
            "name": "HIPAA Technical Safeguards",
            "controls": {
                "164.312(a)(1)": "Access control",
                "164.312(b)": "Audit controls",
                "164.312(c)(1)": "Data integrity",
                "164.312(d)": "Person authentication",
                "164.312(e)(1)": "Transmission security",
            }
        },
        "pci": {
            "name": "PCI-DSS v4",
            "controls": {
                "Req 1": "Network access controls",
                "Req 2": "Secure system configurations",
                "Req 4": "Encryption in transit",
                "Req 7": "Least privilege access",
                "Req 10": "Audit logging",
                "Req 12.3": "Targeted risk analysis",
            }
        },
        "fedramp": {
            "name": "FedRAMP Moderate",
            "controls": {
                "AC-2": "Account management",
                "AC-3": "Access enforcement",
                "AU-2": "Auditable events",
                "AU-12": "Audit record generation",
                "IA-2": "Identification & authentication",
                "SC-8": "Transmission confidentiality",
                "SI-2": "Flaw remediation",
            }
        },
        "cis": {
            "name": "CIS Kubernetes Benchmark L2",
            "controls": {
                "1.2.1": "API server anonymous-auth=false",
                "1.2.6": "API server insecure-port disabled",
                "4.2.6": "Kubelet protectKernelDefaults",
                "5.1.1": "No cluster-admin for SA",
                "5.2.1": "No privileged containers",
                "5.4.1": "Secrets not in env vars",
            }
        }
    }

    if framework not in FRAMEWORKS:
        return {
            "error": f"Unknown framework: {framework}",
            "available_frameworks": list(FRAMEWORKS.keys())
        }

    fw = FRAMEWORKS[framework]
    ns = namespace

    # Automated checks
    checks = {}

    # Check: NetworkPolicies exist
    netpols = kubectl(["get", "networkpolicies"], namespace=ns)
    checks["network_segmentation"] = {
        "status": "PASS" if netpols.get("items") else "FAIL",
        "detail": f"{len(netpols.get('items', []))} NetworkPolicies found in {ns}",
        "remediation": "Apply default-deny-all NetworkPolicy and selective allows" if not netpols.get("items") else None,
    }

    # Check: PSS labels on namespace
    ns_data = kubectl(["get", "namespace", ns])
    ns_labels = ns_data.get("metadata", {}).get("labels", {})
    pss_enforce = ns_labels.get("pod-security.kubernetes.io/enforce")
    checks["pod_security_standards"] = {
        "status": "PASS" if pss_enforce in ("restricted", "baseline") else "FAIL",
        "detail": f"PSS enforce level: {pss_enforce or 'NOT SET'}",
        "remediation": "Add PSS labels to namespace: pod-security.kubernetes.io/enforce: restricted" if not pss_enforce else None,
    }

    # Check: Kyverno policies
    kyverno_policies = kubectl(["get", "clusterpolicies"])
    checks["policy_as_code"] = {
        "status": "PASS" if kyverno_policies.get("items") else "WARN",
        "detail": f"{len(kyverno_policies.get('items', []))} Kyverno ClusterPolicies found",
        "remediation": "Deploy Kyverno ClusterPolicies for admission control" if not kyverno_policies.get("items") else None,
    }

    # Check: cluster-admin bindings
    crbs = kubectl(["get", "clusterrolebindings"])
    admin_sas = [
        crb for crb in crbs.get("items", [])
        if crb.get("roleRef", {}).get("name") == "cluster-admin"
        and any(s.get("kind") == "ServiceAccount" for s in crb.get("subjects", []))
    ]
    checks["least_privilege_rbac"] = {
        "status": "FAIL" if admin_sas else "PASS",
        "detail": f"{len(admin_sas)} ServiceAccounts with cluster-admin found",
        "remediation": "Remove cluster-admin from workload ServiceAccounts" if admin_sas else None,
    }

    # Map automated checks to framework controls
    control_status = {}
    for control_id, control_name in fw["controls"].items():
        control_status[control_id] = {
            "name": control_name,
            "status": "REQUIRES_MANUAL_VERIFICATION",
            "automated_check": None,
        }

    # Link automated results to controls
    if framework in ("soc2", "hipaa", "pci", "fedramp", "cis"):
        control_status.get(list(fw["controls"].keys())[0], {}).update({
            "automated_check": checks.get("network_segmentation"),
        })

    # Overall assessment
    auto_fails = sum(1 for c in checks.values() if c["status"] == "FAIL")
    auto_warns = sum(1 for c in checks.values() if c["status"] == "WARN")

    return {
        "framework": fw["name"],
        "namespace": namespace,
        "automated_checks": checks,
        "control_mapping": control_status,
        "automated_summary": {
            "passed": sum(1 for c in checks.values() if c["status"] == "PASS"),
            "failed": auto_fails,
            "warnings": auto_warns,
            "total": len(checks),
        },
        "overall_posture": "FAIL" if auto_fails > 0 else "WARN" if auto_warns > 0 else "PASS",
        "next_steps": [
            "Fix all FAIL automated checks first",
            "Manual verification required for controls marked REQUIRES_MANUAL_VERIFICATION",
            f"See references/compliance-frameworks.md for {framework.upper()} implementation details",
            "Run kube-bench for CIS Kubernetes Benchmark automated assessment",
        ],
        "evidence_collection": f"make compliance FRAMEWORK={framework} (see generated Makefile)",
    }


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
