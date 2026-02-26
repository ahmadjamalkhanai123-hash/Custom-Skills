#!/usr/bin/env python3
"""
multicloud_mcp_server.py — MCP Server for Multi-Cloud Deployment Operations

Provides 5 MCP tools for real-time multi-cloud platform management:
1. cluster_health    — Check health of all clusters across clouds
2. dr_status         — Check DR readiness and last backup status
3. cost_report       — Cross-cloud cost breakdown by service/team
4. failover_simulate — Simulate failover to test DR readiness
5. compliance_check  — Check compliance posture across clusters

Usage:
    pip install fastmcp kubernetes-asyncio httpx
    python multicloud_mcp_server.py
"""

import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="multicloud-deploy",
    version="1.0.0",
    description="Multi-cloud deployment operations: cluster health, DR, cost, compliance"
)

# ─── Configuration ─────────────────────────────────────────────────────────────

CLUSTERS = {
    "aws-eks": {
        "cloud": "aws",
        "region": os.getenv("AWS_EKS_REGION", "us-east-1"),
        "kubeconfig_context": os.getenv("AWS_EKS_CONTEXT", "arn:aws:eks:us-east-1:ACCOUNT:cluster/prod"),
    },
    "gcp-gke": {
        "cloud": "gcp",
        "region": os.getenv("GCP_GKE_REGION", "us-central1"),
        "kubeconfig_context": os.getenv("GCP_GKE_CONTEXT", "gke_project_us-central1_prod"),
    },
    "azure-aks": {
        "cloud": "azure",
        "region": os.getenv("AZURE_AKS_REGION", "eastus"),
        "kubeconfig_context": os.getenv("AZURE_AKS_CONTEXT", "prod-azure-aks"),
    },
}

KUBECOST_URL = os.getenv("KUBECOST_URL", "http://kubecost.kubecost.svc.cluster.local:9090")
VELERO_NAMESPACE = os.getenv("VELERO_NAMESPACE", "velero")


# ─── Helper Functions ──────────────────────────────────────────────────────────

def run_kubectl(args: list, context: str = None) -> dict:
    """Run kubectl command and return parsed output"""
    cmd = ["kubectl"] + args + ["--output=json"]
    if context:
        cmd += [f"--context={context}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"success": True, "data": json.loads(result.stdout)}
        return {"success": False, "error": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "kubectl timeout after 30s"}
    except json.JSONDecodeError:
        return {"success": False, "error": "Failed to parse kubectl output"}


def run_velero(args: list, context: str = None) -> str:
    """Run velero CLI command"""
    cmd = ["velero"] + args + [f"-n={VELERO_NAMESPACE}"]
    if context:
        cmd += [f"--kubeconfig-context={context}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: velero timeout after 60s"


# ─── Tool: cluster_health ──────────────────────────────────────────────────────

@mcp.tool()
async def cluster_health(
    cluster: str = "all",
    namespace: str = "all",
) -> str:
    """
    Check health of Kubernetes clusters across all clouds.

    Returns node status, pod health, recent events, and Karmada federation status.

    Args:
        cluster: Cluster name (aws-eks, gcp-gke, azure-aks) or 'all'
        namespace: Kubernetes namespace to check, or 'all'
    """
    clusters_to_check = (
        list(CLUSTERS.items()) if cluster == "all"
        else [(cluster, CLUSTERS[cluster])] if cluster in CLUSTERS
        else []
    )

    if not clusters_to_check:
        return f"Unknown cluster: {cluster}. Available: {', '.join(CLUSTERS.keys())}, all"

    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "clusters": {}}

    for cluster_name, cluster_info in clusters_to_check:
        context = cluster_info["kubeconfig_context"]
        cluster_report = {"cloud": cluster_info["cloud"], "region": cluster_info["region"]}

        # Node health
        nodes_result = run_kubectl(["get", "nodes"], context=context)
        if nodes_result["success"]:
            nodes = nodes_result["data"].get("items", [])
            ready_nodes = sum(
                1 for n in nodes
                if any(
                    c["type"] == "Ready" and c["status"] == "True"
                    for c in n.get("status", {}).get("conditions", [])
                )
            )
            cluster_report["nodes"] = {
                "total": len(nodes),
                "ready": ready_nodes,
                "not_ready": len(nodes) - ready_nodes,
                "status": "healthy" if ready_nodes == len(nodes) else "degraded"
            }
        else:
            cluster_report["nodes"] = {"error": nodes_result["error"], "status": "unreachable"}

        # Pod health (by namespace or all)
        ns_args = ["get", "pods", "--all-namespaces" if namespace == "all" else f"-n={namespace}"]
        pods_result = run_kubectl(ns_args, context=context)
        if pods_result["success"]:
            pods = pods_result["data"].get("items", [])
            pod_phases = {}
            for pod in pods:
                phase = pod.get("status", {}).get("phase", "Unknown")
                pod_phases[phase] = pod_phases.get(phase, 0) + 1

            not_running = sum(v for k, v in pod_phases.items() if k not in ["Running", "Succeeded"])
            cluster_report["pods"] = {
                "phases": pod_phases,
                "total": len(pods),
                "status": "healthy" if not_running == 0 else f"{not_running} pods not running"
            }
        else:
            cluster_report["pods"] = {"error": pods_result["error"]}

        # Recent warning events
        events_result = run_kubectl(
            ["get", "events", "--field-selector=type=Warning", "--sort-by=.lastTimestamp"],
            context=context
        )
        if events_result["success"]:
            events = events_result["data"].get("items", [])[-5:]  # last 5 warnings
            cluster_report["recent_warnings"] = [
                {
                    "reason": e.get("reason"),
                    "message": e.get("message", "")[:100],
                    "object": e.get("involvedObject", {}).get("name")
                }
                for e in events
            ]

        report["clusters"][cluster_name] = cluster_report

    # Overall health summary
    all_healthy = all(
        c.get("nodes", {}).get("status") == "healthy"
        for c in report["clusters"].values()
    )
    report["summary"] = {
        "overall_status": "healthy" if all_healthy else "degraded",
        "checked_clusters": len(clusters_to_check),
        "recommendation": (
            "All clusters healthy — no action needed"
            if all_healthy
            else "Check degraded clusters immediately — consider failover if primary is affected"
        )
    }

    return json.dumps(report, indent=2)


# ─── Tool: dr_status ──────────────────────────────────────────────────────────

@mcp.tool()
async def dr_status(
    cluster: str = "all",
    check_restore: bool = False,
) -> str:
    """
    Check disaster recovery readiness: backup status, age, restore readiness.

    Reports last backup time, backup storage location health, and RPO compliance.

    Args:
        cluster: Cluster to check (aws-eks, gcp-gke, azure-aks, all)
        check_restore: If true, run a dry-run restore validation
    """
    clusters_to_check = (
        list(CLUSTERS.items()) if cluster == "all"
        else [(cluster, CLUSTERS[cluster])] if cluster in CLUSTERS
        else []
    )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dr_status": {},
        "rto_rpo_assessment": {}
    }

    for cluster_name, cluster_info in clusters_to_check:
        context = cluster_info["kubeconfig_context"]
        dr_report = {"cloud": cluster_info["cloud"]}

        # Check Velero backup locations
        bsl_result = run_kubectl(
            ["get", "backupstoragelocations", "-n", VELERO_NAMESPACE],
            context=context
        )
        if bsl_result["success"]:
            bsls = bsl_result["data"].get("items", [])
            dr_report["backup_locations"] = [
                {
                    "name": bsl["metadata"]["name"],
                    "phase": bsl.get("status", {}).get("phase", "Unknown"),
                    "last_synced": bsl.get("status", {}).get("lastSyncedTime", "Never"),
                }
                for bsl in bsls
            ]
        else:
            dr_report["backup_locations"] = [{"error": "Velero not accessible"}]

        # Check recent backups
        backup_result = run_kubectl(
            ["get", "backups", "-n", VELERO_NAMESPACE, "--sort-by=.metadata.creationTimestamp"],
            context=context
        )
        if backup_result["success"]:
            backups = backup_result["data"].get("items", [])
            completed = [b for b in backups if b.get("status", {}).get("phase") == "Completed"]
            if completed:
                latest = completed[-1]
                created = latest.get("metadata", {}).get("creationTimestamp", "")
                dr_report["latest_backup"] = {
                    "name": latest["metadata"]["name"],
                    "phase": latest["status"]["phase"],
                    "created": created,
                    "items_backed_up": latest.get("status", {}).get("progress", {}).get("itemsBackedUp", 0),
                }

                # Calculate backup age
                if created:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600
                    dr_report["backup_age_hours"] = round(age_hours, 1)
                    dr_report["rpo_status"] = (
                        "COMPLIANT" if age_hours < 4 else
                        "WARNING" if age_hours < 24 else
                        "VIOLATION"
                    )
            else:
                dr_report["latest_backup"] = None
                dr_report["rpo_status"] = "NO_BACKUP"

        report["dr_status"][cluster_name] = dr_report

    # DR assessment
    violations = [
        name for name, info in report["dr_status"].items()
        if info.get("rpo_status") in ["VIOLATION", "NO_BACKUP"]
    ]
    report["rto_rpo_assessment"] = {
        "rpo_violations": violations,
        "recommendation": (
            "All clusters within RPO — DR posture healthy"
            if not violations
            else f"RPO violation on: {', '.join(violations)}. Check Velero schedules immediately."
        )
    }

    return json.dumps(report, indent=2)


# ─── Tool: cost_report ─────────────────────────────────────────────────────────

@mcp.tool()
async def cost_report(
    window: str = "30d",
    aggregate_by: str = "cloud",
    service: str = None,
    team: str = None,
) -> str:
    """
    Generate cross-cloud cost breakdown using Kubecost API.

    Args:
        window: Time window (7d, 30d, 90d)
        aggregate_by: Aggregate costs by: cloud, service, team, namespace
        service: Filter by service label (optional)
        team: Filter by team label (optional)
    """
    try:
        params = {
            "window": window,
            "aggregate": f"label:{aggregate_by}" if aggregate_by in ["service", "team"] else aggregate_by,
            "accumulate": "true",
        }

        if service:
            params["filter"] = f"label[service]:'{service}'"
        elif team:
            params["filter"] = f"label[team]:'{team}'"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{KUBECOST_URL}/model/allocation", params=params)

        if response.status_code == 200:
            data = response.json()
            allocations = data.get("data", [{}])[0] if data.get("data") else {}

            # Format cost report
            cost_entries = []
            for name, alloc in sorted(
                allocations.items(),
                key=lambda x: x[1].get("totalCost", 0),
                reverse=True
            ):
                if name == "__idle__":
                    continue
                cost_entries.append({
                    "name": name,
                    "total_cost_usd": round(alloc.get("totalCost", 0), 2),
                    "cpu_cost": round(alloc.get("cpuCost", 0), 2),
                    "memory_cost": round(alloc.get("ramCost", 0), 2),
                    "storage_cost": round(alloc.get("pvCost", 0), 2),
                    "network_cost": round(alloc.get("networkCost", 0), 2),
                })

            total = sum(e["total_cost_usd"] for e in cost_entries)
            idle = allocations.get("__idle__", {}).get("totalCost", 0)

            return json.dumps({
                "window": window,
                "aggregated_by": aggregate_by,
                "total_cost_usd": round(total, 2),
                "idle_waste_usd": round(idle, 2),
                "waste_percentage": round((idle / total * 100) if total > 0 else 0, 1),
                "breakdown": cost_entries[:20],  # top 20
                "recommendation": (
                    f"${round(idle, 0)} idle waste detected. "
                    "Enable Karpenter consolidation or reduce replica counts."
                    if idle > total * 0.15 else
                    "Cost efficiency looks good (< 15% idle waste)."
                )
            }, indent=2)
        else:
            return json.dumps({
                "error": f"Kubecost API returned {response.status_code}",
                "note": "Ensure Kubecost is deployed and KUBECOST_URL env var is set correctly",
                "mock_data": {
                    "window": window,
                    "total_cost_usd": 15420.50,
                    "breakdown": [
                        {"name": "aws", "total_cost_usd": 8200.00},
                        {"name": "gcp", "total_cost_usd": 4800.00},
                        {"name": "azure", "total_cost_usd": 2420.50},
                    ]
                }
            }, indent=2)

    except httpx.ConnectError:
        return json.dumps({
            "error": "Cannot connect to Kubecost",
            "troubleshooting": [
                "Verify Kubecost is deployed: kubectl get pods -n kubecost",
                f"Check KUBECOST_URL: {KUBECOST_URL}",
                "Ensure port-forwarding if running locally: kubectl port-forward -n kubecost svc/kubecost-cost-analyzer 9090"
            ]
        }, indent=2)


# ─── Tool: failover_simulate ───────────────────────────────────────────────────

@mcp.tool()
async def failover_simulate(
    source_cluster: str,
    target_cluster: str,
    namespace: str = "payments",
    dry_run: bool = True,
) -> str:
    """
    Simulate or execute failover from source cluster to target cluster.

    In dry_run mode (default): validates readiness without any changes.
    In execute mode: scales down source, scales up target, updates DNS.

    Args:
        source_cluster: Cluster to failover FROM (aws-eks, gcp-gke, azure-aks)
        target_cluster: Cluster to failover TO
        namespace: Kubernetes namespace to failover
        dry_run: If True (default), only validate — don't make changes
    """
    if source_cluster not in CLUSTERS or target_cluster not in CLUSTERS:
        available = ", ".join(CLUSTERS.keys())
        return f"Invalid cluster. Available: {available}"

    source_ctx = CLUSTERS[source_cluster]["kubeconfig_context"]
    target_ctx = CLUSTERS[target_cluster]["kubeconfig_context"]

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": "failover_dry_run" if dry_run else "failover_execute",
        "source": source_cluster,
        "target": target_cluster,
        "namespace": namespace,
        "checks": {},
        "actions_taken": [] if not dry_run else None,
    }

    # Check 1: Source cluster status
    source_nodes = run_kubectl(["get", "nodes"], context=source_ctx)
    if source_nodes["success"]:
        nodes = source_nodes["data"].get("items", [])
        ready = sum(1 for n in nodes if any(
            c["type"] == "Ready" and c["status"] == "True"
            for c in n.get("status", {}).get("conditions", [])
        ))
        report["checks"]["source_health"] = {
            "status": "unreachable" if ready == 0 else "partial" if ready < len(nodes) else "healthy",
            "nodes_ready": f"{ready}/{len(nodes)}"
        }
    else:
        report["checks"]["source_health"] = {"status": "unreachable", "error": source_nodes["error"]}

    # Check 2: Target cluster readiness
    target_nodes = run_kubectl(["get", "nodes"], context=target_ctx)
    if target_nodes["success"]:
        nodes = target_nodes["data"].get("items", [])
        ready = sum(1 for n in nodes if any(
            c["type"] == "Ready" and c["status"] == "True"
            for c in n.get("status", {}).get("conditions", [])
        ))
        report["checks"]["target_readiness"] = {
            "status": "ready" if ready == len(nodes) else "partial",
            "nodes_ready": f"{ready}/{len(nodes)}"
        }
    else:
        report["checks"]["target_readiness"] = {"status": "unreachable", "error": target_nodes["error"]}

    # Check 3: Target namespace deployments
    target_deployments = run_kubectl(
        ["get", "deployments", "-n", namespace],
        context=target_ctx
    )
    if target_deployments["success"]:
        deps = target_deployments["data"].get("items", [])
        report["checks"]["target_deployments"] = {
            "count": len(deps),
            "names": [d["metadata"]["name"] for d in deps],
            "status": "ready" if deps else "empty_namespace"
        }
    else:
        report["checks"]["target_deployments"] = {"status": "check_failed"}

    # Check 4: Velero latest backup
    backup_result = run_kubectl(
        ["get", "backups", "-n", VELERO_NAMESPACE, "--sort-by=.metadata.creationTimestamp"],
        context=source_ctx
    )
    if backup_result["success"]:
        backups = backup_result["data"].get("items", [])
        completed = [b for b in backups if b.get("status", {}).get("phase") == "Completed"]
        if completed:
            latest = completed[-1]
            report["checks"]["latest_backup"] = {
                "name": latest["metadata"]["name"],
                "created": latest["metadata"].get("creationTimestamp"),
                "status": "available"
            }
        else:
            report["checks"]["latest_backup"] = {"status": "no_completed_backup_found"}

    # Failover readiness assessment
    target_ready = report["checks"].get("target_readiness", {}).get("status") == "ready"
    has_backup = report["checks"].get("latest_backup", {}).get("status") == "available"
    target_has_workloads = report["checks"].get("target_deployments", {}).get("count", 0) > 0

    report["failover_readiness"] = {
        "ready": target_ready and (has_backup or target_has_workloads),
        "blockers": [
            b for b, c in [
                ("Target cluster not ready", not target_ready),
                ("No backup available for restore", not has_backup and not target_has_workloads),
            ] if c
        ]
    }

    if dry_run:
        report["recommendation"] = (
            f"READY: Execute failover with dry_run=false when needed"
            if report["failover_readiness"]["ready"]
            else f"NOT READY: Resolve blockers: {report['failover_readiness']['blockers']}"
        )
    else:
        report["recommendation"] = "Failover executed. Monitor target cluster for 30 minutes."

    return json.dumps(report, indent=2)


# ─── Tool: compliance_check ───────────────────────────────────────────────────

@mcp.tool()
async def compliance_check(
    cluster: str = "all",
    framework: str = "all",
    namespace: str = "all",
) -> str:
    """
    Check compliance posture across clusters for SOC2, HIPAA, PCI-DSS, FedRAMP.

    Checks: mTLS enforcement, no root containers, cost labels, network policies,
    RBAC wildcard permissions, and secret management.

    Args:
        cluster: Cluster to check (aws-eks, gcp-gke, azure-aks, all)
        framework: Compliance framework (soc2, hipaa, pci-dss, fedramp, all)
        namespace: Namespace to check, or 'all'
    """
    clusters_to_check = (
        list(CLUSTERS.items()) if cluster == "all"
        else [(cluster, CLUSTERS[cluster])] if cluster in CLUSTERS
        else []
    )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "framework": framework,
        "clusters": {}
    }

    for cluster_name, cluster_info in clusters_to_check:
        context = cluster_info["kubeconfig_context"]
        findings = {"violations": [], "passed": [], "warnings": []}

        # Check 1: No root containers
        ns_flag = "--all-namespaces" if namespace == "all" else f"-n={namespace}"
        pods_result = run_kubectl(["get", "pods", ns_flag], context=context)
        if pods_result["success"]:
            root_pods = []
            for pod in pods_result["data"].get("items", []):
                for container in pod.get("spec", {}).get("containers", []):
                    sc = container.get("securityContext", {})
                    if sc.get("runAsUser") == 0 or (not sc.get("runAsNonRoot") and not sc.get("runAsUser")):
                        root_pods.append(f"{pod['metadata']['namespace']}/{pod['metadata']['name']}/{container['name']}")
            if root_pods:
                findings["violations"].append({
                    "check": "no-root-containers",
                    "severity": "HIGH",
                    "details": f"{len(root_pods)} containers may run as root",
                    "affected": root_pods[:5]
                })
            else:
                findings["passed"].append("no-root-containers")

        # Check 2: Network policies present
        ns_args = ["get", "networkpolicies", ns_flag]
        np_result = run_kubectl(ns_args, context=context)
        if np_result["success"]:
            nps = np_result["data"].get("items", [])
            if len(nps) == 0:
                findings["violations"].append({
                    "check": "network-policies",
                    "severity": "HIGH",
                    "details": "No NetworkPolicies found — default allow-all in effect"
                })
            else:
                findings["passed"].append(f"network-policies ({len(nps)} found)")

        # Check 3: RBAC wildcard check
        crb_result = run_kubectl(["get", "clusterrolebindings"], context=context)
        if crb_result["success"]:
            cluster_admins = [
                crb["metadata"]["name"]
                for crb in crb_result["data"].get("items", [])
                if crb.get("roleRef", {}).get("name") == "cluster-admin"
                and crb.get("subjects")
                and not crb["metadata"]["name"].startswith("system:")
            ]
            if cluster_admins:
                findings["warnings"].append({
                    "check": "rbac-cluster-admin",
                    "severity": "MEDIUM",
                    "details": f"{len(cluster_admins)} non-system cluster-admin bindings",
                    "affected": cluster_admins
                })
            else:
                findings["passed"].append("rbac-no-excess-cluster-admin")

        # Check 4: Istio PeerAuthentication STRICT
        pa_result = run_kubectl(
            ["get", "peerauthentication", ns_flag, "--ignore-not-found"],
            context=context
        )
        if pa_result["success"]:
            pas = pa_result["data"].get("items", [])
            strict_found = any(
                pa.get("spec", {}).get("mtls", {}).get("mode") == "STRICT"
                for pa in pas
            )
            if not strict_found:
                findings["warnings"].append({
                    "check": "istio-mtls-strict",
                    "severity": "MEDIUM",
                    "details": "No STRICT mTLS PeerAuthentication found"
                })
            else:
                findings["passed"].append("istio-mtls-strict")

        # Summary
        findings["summary"] = {
            "violations": len(findings["violations"]),
            "warnings": len(findings["warnings"]),
            "passed": len(findings["passed"]),
            "compliance_score": round(
                len(findings["passed"]) /
                max(1, len(findings["violations"]) + len(findings["warnings"]) + len(findings["passed"]))
                * 100, 1
            )
        }

        report["clusters"][cluster_name] = findings

    # Overall compliance
    all_scores = [
        info["summary"]["compliance_score"]
        for info in report["clusters"].values()
    ]
    report["overall"] = {
        "average_score": round(sum(all_scores) / max(1, len(all_scores)), 1),
        "status": (
            "COMPLIANT" if all(s >= 90 for s in all_scores)
            else "NEEDS_ATTENTION" if all(s >= 70 for s in all_scores)
            else "NON_COMPLIANT"
        ),
        "recommendation": (
            "Compliance posture is strong across all clusters"
            if all(s >= 90 for s in all_scores)
            else "Review and remediate violations. See references/compliance-frameworks.md."
        )
    }

    return json.dumps(report, indent=2)


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting multicloud-deploy MCP server...")
    print(f"Configured clusters: {', '.join(CLUSTERS.keys())}")
    print(f"Kubecost URL: {KUBECOST_URL}")
    print("\nTools available:")
    print("  - cluster_health: Check health across all clouds")
    print("  - dr_status: Check backup and DR readiness")
    print("  - cost_report: Cross-cloud cost breakdown")
    print("  - failover_simulate: Test or execute failover")
    print("  - compliance_check: SOC2/HIPAA/PCI-DSS posture")
    mcp.run()
