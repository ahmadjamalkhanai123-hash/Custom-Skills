#!/usr/bin/env python3
"""
Apache Kafka MCP Server — Context-Optimized
Provides Kafka cluster management tools for Claude Code.

Tools: cluster_health, topic_manage, consumer_groups, config_audit, schema_validate

Install: pip install mcp confluent-kafka requests
Run: python kafka_mcp_server.py (stdio transport)

Configure in .claude/settings.json:
{
  "mcpServers": {
    "kafka": {
      "command": "python",
      "args": ["scripts/kafka_mcp_server.py"],
      "env": {"KAFKA_BOOTSTRAP": "localhost:9092"}
    }
  }
}
"""

import json
import os
import subprocess
import sys

try:
    from mcp.server.fastmcp import FastMCP, Context
except ImportError:
    print("Install MCP SDK: pip install mcp", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP("kafka-tools")

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
SCHEMA_REGISTRY = os.environ.get("SCHEMA_REGISTRY_URL", "http://localhost:8081")

# ── Helpers ──────────────────────────────────────────────────────────────────

def _run_kafka_cmd(cmd: list[str], timeout: int = 30) -> dict:
    """Execute kafka CLI command and return structured result."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "code": "CMD_FAILED"}
        return {"output": result.stdout.strip()}
    except FileNotFoundError:
        return {"error": "Kafka CLI tools not found. Install Apache Kafka.", "code": "NOT_FOUND"}
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s", "code": "TIMEOUT"}


def _parse_topic_list(output: str) -> list[dict]:
    """Parse kafka-topics.sh --list output."""
    topics = [t.strip() for t in output.split("\n") if t.strip()]
    return [{"name": t} for t in topics]


def _parse_consumer_groups(output: str) -> list[dict]:
    """Parse kafka-consumer-groups.sh --describe output."""
    lines = output.strip().split("\n")
    if len(lines) < 2:
        return []
    groups = []
    for line in lines[1:]:  # skip header
        parts = line.split()
        if len(parts) >= 6:
            groups.append({
                "group": parts[0], "topic": parts[1], "partition": parts[2],
                "current_offset": parts[3], "log_end_offset": parts[4], "lag": parts[5],
            })
    return groups


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
async def cluster_health(*, ctx: Context) -> dict:
    """Check Kafka cluster health: broker status, controller, ISR state."""
    ctx.info("Checking cluster health...")

    # Topic health (under-replicated)
    topic_result = _run_kafka_cmd([
        "kafka-topics.sh", "--bootstrap-server", BOOTSTRAP,
        "--describe", "--under-replicated-partitions",
    ])

    health = {
        "bootstrap": BOOTSTRAP,
        "under_replicated": topic_result.get("output", "Unable to check"),
        "status": "healthy" if not topic_result.get("output") else "degraded",
    }

    # Try broker API versions as connectivity check
    api_result = _run_kafka_cmd([
        "kafka-broker-api-versions.sh", "--bootstrap-server", BOOTSTRAP,
    ])
    if "error" in api_result:
        health["status"] = "unreachable"
        health["error"] = api_result["error"]
    else:
        lines = api_result["output"].split("\n")
        broker_lines = [l for l in lines if l.startswith("broker")]
        health["brokers"] = len(broker_lines) if broker_lines else "unknown"

    ctx.info(f"Cluster status: {health['status']}")
    return health


@mcp.tool()
async def topic_manage(
    action: str = "list",
    topic: str = "",
    partitions: int = 6,
    replication_factor: int = 3,
    config: str = "",
    *, ctx: Context,
) -> dict:
    """Manage Kafka topics. Actions: list, describe, create, delete, alter-config.

    Args:
        action: list | describe | create | delete | alter-config
        topic: Topic name (required for describe/create/delete/alter-config)
        partitions: Number of partitions (create only, default 6)
        replication_factor: Replication factor (create only, default 3)
        config: Topic config overrides (e.g., 'retention.ms=604800000,compression.type=lz4')
    """
    ctx.info(f"Topic action: {action} {topic}")

    if action == "list":
        result = _run_kafka_cmd([
            "kafka-topics.sh", "--bootstrap-server", BOOTSTRAP, "--list",
        ])
        if "error" in result:
            return result
        return {"topics": _parse_topic_list(result["output"])}

    if not topic:
        return {"error": "Topic name required for this action", "code": "MISSING_PARAM"}

    if action == "describe":
        result = _run_kafka_cmd([
            "kafka-topics.sh", "--bootstrap-server", BOOTSTRAP,
            "--describe", "--topic", topic,
        ])
        return result

    if action == "create":
        cmd = [
            "kafka-topics.sh", "--bootstrap-server", BOOTSTRAP, "--create",
            "--topic", topic, "--partitions", str(partitions),
            "--replication-factor", str(replication_factor),
        ]
        if config:
            for c in config.split(","):
                cmd.extend(["--config", c.strip()])
        result = _run_kafka_cmd(cmd)
        return result

    if action == "delete":
        return _run_kafka_cmd([
            "kafka-topics.sh", "--bootstrap-server", BOOTSTRAP,
            "--delete", "--topic", topic,
        ])

    if action == "alter-config":
        if not config:
            return {"error": "Config required for alter-config", "code": "MISSING_PARAM"}
        return _run_kafka_cmd([
            "kafka-configs.sh", "--bootstrap-server", BOOTSTRAP,
            "--alter", "--entity-type", "topics", "--entity-name", topic,
            "--add-config", config,
        ])

    return {"error": f"Unknown action: {action}", "code": "INVALID_ACTION"}


@mcp.tool()
async def consumer_groups(
    action: str = "list",
    group: str = "",
    *, ctx: Context,
) -> dict:
    """Monitor Kafka consumer groups and lag.

    Args:
        action: list | describe | lag-summary
        group: Consumer group ID (required for describe)
    """
    ctx.info(f"Consumer groups action: {action}")

    if action == "list":
        result = _run_kafka_cmd([
            "kafka-consumer-groups.sh", "--bootstrap-server", BOOTSTRAP, "--list",
        ])
        if "error" in result:
            return result
        groups = [g.strip() for g in result["output"].split("\n") if g.strip()]
        return {"groups": groups, "count": len(groups)}

    if action == "describe":
        if not group:
            return {"error": "Group ID required", "code": "MISSING_PARAM"}
        result = _run_kafka_cmd([
            "kafka-consumer-groups.sh", "--bootstrap-server", BOOTSTRAP,
            "--describe", "--group", group,
        ])
        if "error" in result:
            return result
        return {"group": group, "members": _parse_consumer_groups(result["output"])}

    if action == "lag-summary":
        result = _run_kafka_cmd([
            "kafka-consumer-groups.sh", "--bootstrap-server", BOOTSTRAP,
            "--list",
        ])
        if "error" in result:
            return result
        groups = [g.strip() for g in result["output"].split("\n") if g.strip()]
        summary = []
        for g in groups[:20]:  # limit to 20 for context efficiency
            desc = _run_kafka_cmd([
                "kafka-consumer-groups.sh", "--bootstrap-server", BOOTSTRAP,
                "--describe", "--group", g,
            ])
            if "output" in desc:
                members = _parse_consumer_groups(desc["output"])
                total_lag = sum(int(m.get("lag", 0)) for m in members if m.get("lag", "").isdigit())
                summary.append({"group": g, "total_lag": total_lag, "partitions": len(members)})
        return {"lag_summary": summary}

    return {"error": f"Unknown action: {action}", "code": "INVALID_ACTION"}


@mcp.tool()
async def config_audit(
    entity: str = "broker",
    entity_name: str = "",
    *, ctx: Context,
) -> dict:
    """Audit Kafka configuration against production best practices.

    Args:
        entity: broker | topic (what to audit)
        entity_name: Broker ID or topic name
    """
    ctx.info(f"Auditing {entity} config...")

    BEST_PRACTICES = {
        "broker": {
            "min.insync.replicas": {"recommended": "2", "severity": "critical"},
            "default.replication.factor": {"recommended": "3", "severity": "critical"},
            "unclean.leader.election.enable": {"recommended": "false", "severity": "critical"},
            "auto.create.topics.enable": {"recommended": "false", "severity": "warning"},
            "compression.type": {"recommended": "producer", "severity": "info"},
            "log.retention.hours": {"recommended": "168", "severity": "info"},
        },
        "topic": {
            "min.insync.replicas": {"recommended": "2", "severity": "critical"},
            "compression.type": {"recommended": "lz4", "severity": "info"},
        },
    }

    if entity == "broker":
        cmd = ["kafka-configs.sh", "--bootstrap-server", BOOTSTRAP,
               "--describe", "--entity-type", "brokers", "--all"]
        if entity_name:
            cmd.extend(["--entity-name", entity_name])
        else:
            cmd.append("--entity-default")
    elif entity == "topic":
        if not entity_name:
            return {"error": "Topic name required", "code": "MISSING_PARAM"}
        cmd = ["kafka-configs.sh", "--bootstrap-server", BOOTSTRAP,
               "--describe", "--entity-type", "topics", "--entity-name", entity_name]
    else:
        return {"error": "Entity must be 'broker' or 'topic'", "code": "INVALID_PARAM"}

    result = _run_kafka_cmd(cmd)
    if "error" in result:
        return result

    # Parse config output into key-value dict for exact matching
    configs = {}
    for line in result.get("output", "").split("\n"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            configs[k.strip()] = v.strip()

    findings = []
    practices = BEST_PRACTICES.get(entity, {})
    for key, rec in practices.items():
        if key not in configs:
            findings.append({
                "config": key, "status": "not_set",
                "recommended": rec["recommended"], "severity": rec["severity"],
            })
        elif configs[key] != rec["recommended"]:
            findings.append({
                "config": key, "status": "non_optimal", "current": configs[key],
                "recommended": rec["recommended"], "severity": rec["severity"],
            })

    return {
        "entity": entity, "entity_name": entity_name or "default",
        "findings": findings,
        "score": "pass" if not any(f["severity"] == "critical" for f in findings) else "fail",
    }


@mcp.tool()
async def schema_validate(
    action: str = "list",
    subject: str = "",
    schema: str = "",
    compatibility: str = "",
    *, ctx: Context,
) -> dict:
    """Validate and manage schemas in Confluent Schema Registry.

    Args:
        action: list | get | check-compatibility | set-compatibility
        subject: Schema subject name (e.g., 'orders.order.created.v1-value')
        schema: JSON schema string (for check-compatibility)
        compatibility: BACKWARD | FORWARD | FULL | NONE (for set-compatibility)
    """
    import urllib.request
    import urllib.error

    ctx.info(f"Schema action: {action}")

    def _sr_request(path: str, method: str = "GET", data: dict | None = None) -> dict:
        url = f"{SCHEMA_REGISTRY}{path}"
        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/vnd.schemaregistry.v1+json")
        if data:
            req.data = json.dumps(data).encode()
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode()}", "code": "SR_ERROR"}
        except urllib.error.URLError as e:
            return {"error": f"Cannot reach Schema Registry: {e}", "code": "UNREACHABLE"}

    if action == "list":
        subjects = _sr_request("/subjects")
        return {"subjects": subjects} if isinstance(subjects, list) else subjects

    if action == "get":
        if not subject:
            return {"error": "Subject required", "code": "MISSING_PARAM"}
        return _sr_request(f"/subjects/{subject}/versions/latest")

    if action == "check-compatibility":
        if not subject or not schema:
            return {"error": "Subject and schema required", "code": "MISSING_PARAM"}
        return _sr_request(
            f"/compatibility/subjects/{subject}/versions/latest",
            method="POST", data={"schema": schema},
        )

    if action == "set-compatibility":
        if not subject or not compatibility:
            return {"error": "Subject and compatibility required", "code": "MISSING_PARAM"}
        return _sr_request(
            f"/config/{subject}", method="PUT",
            data={"compatibility": compatibility.upper()},
        )

    return {"error": f"Unknown action: {action}", "code": "INVALID_ACTION"}


# ── Resources (read-only context) ───────────────────────────────────────────

@mcp.resource("kafka://best-practices")
async def best_practices() -> str:
    """Kafka production best practices summary."""
    return json.dumps({
        "producer": {"acks": "all", "idempotence": True, "compression": "lz4", "batch_size": 65536},
        "consumer": {"auto_commit": False, "isolation": "read_committed", "assignor": "cooperative-sticky"},
        "cluster": {"replication_factor": 3, "min_isr": 2, "unclean_election": False},
        "monitoring": ["UnderReplicatedPartitions", "ActiveControllerCount", "consumer_lag"],
    })


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
