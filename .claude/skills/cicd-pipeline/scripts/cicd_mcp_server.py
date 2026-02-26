#!/usr/bin/env python3
"""
CI/CD Pipeline MCP Server
Provides AI-assisted CI/CD operations via Model Context Protocol.

Tools:
  - pipeline_status: Check pipeline run status across CI platforms
  - validate_config: Lint and validate CI YAML/Groovy configs
  - security_audit: Audit pipeline files for security anti-patterns
  - generate_workflow: Generate workflow YAML for given platform + tier
  - dora_metrics: Calculate DORA metrics from deployment history

Usage:
  python cicd_mcp_server.py  (stdio transport — works with Claude Code)

Configure in claude_desktop_config.json or Claude Code settings:
  {
    "mcpServers": {
      "cicd-pipeline": {
        "command": "python",
        "args": ["/path/to/cicd_mcp_server.py"],
        "env": {
          "GITHUB_TOKEN": "your-token",
          "GITLAB_TOKEN": "your-token"
        }
      }
    }
  }
"""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("cicd-pipeline")

# ─────────────────────────────────────────────────────────────
# TOOL: pipeline_status
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def pipeline_status(
    platform: str,
    repo: str,
    limit: int = 5,
    ctx: Context = None,
) -> dict:
    """
    Check recent pipeline run status for a repository.

    Args:
        platform: CI platform ('github', 'gitlab', 'local')
        repo: Repository in 'owner/name' format (or local path for 'local')
        limit: Number of recent runs to return (max 20)

    Returns dict with pipeline runs, statuses, and durations.
    """
    if ctx:
        await ctx.info(f"Fetching pipeline status for {repo} on {platform}")

    limit = min(limit, 20)

    try:
        if platform == "github":
            return await _github_pipeline_status(repo, limit, ctx)
        elif platform == "gitlab":
            return await _gitlab_pipeline_status(repo, limit, ctx)
        elif platform == "local":
            return _local_git_log(repo, limit)
        else:
            return {"error": f"Unsupported platform: {platform}. Use: github, gitlab, local"}
    except Exception as e:
        if ctx:
            await ctx.error(f"Pipeline status error: {e}")
        return {"error": str(e), "retryable": False}


async def _github_pipeline_status(repo: str, limit: int, ctx) -> dict:
    """Fetch GitHub Actions workflow runs via gh CLI."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return {"error": "GITHUB_TOKEN not set. Set it in MCP server env config."}

    try:
        result = subprocess.run(
            ["gh", "run", "list", "--repo", repo, "--limit", str(limit), "--json",
             "status,conclusion,workflowName,headBranch,createdAt,updatedAt,databaseId,url"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "GH_TOKEN": token}
        )

        if result.returncode != 0:
            return {"error": f"gh CLI error: {result.stderr.strip()}"}

        runs = json.loads(result.stdout)
        formatted = []
        for run in runs:
            status = run.get("conclusion") or run.get("status", "unknown")
            created = run.get("createdAt", "")
            updated = run.get("updatedAt", "")
            duration = ""
            if created and updated:
                try:
                    dt_start = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    dt_end = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    secs = int((dt_end - dt_start).total_seconds())
                    duration = f"{secs // 60}m {secs % 60}s"
                except Exception:
                    pass

            formatted.append({
                "id": run.get("databaseId"),
                "workflow": run.get("workflowName"),
                "branch": run.get("headBranch"),
                "status": status,
                "duration": duration,
                "url": run.get("url"),
                "created_at": created,
            })

        if ctx:
            await ctx.info(f"Found {len(formatted)} recent runs for {repo}")

        return {
            "platform": "github",
            "repo": repo,
            "runs": formatted,
            "count": len(formatted),
        }
    except FileNotFoundError:
        return {"error": "gh CLI not found. Install: https://cli.github.com"}
    except subprocess.TimeoutExpired:
        return {"error": "GitHub API request timed out", "retryable": True}


async def _gitlab_pipeline_status(repo: str, limit: int, ctx) -> dict:
    """Fetch GitLab pipelines via API."""
    token = os.environ.get("GITLAB_TOKEN", "")
    gitlab_host = os.environ.get("GITLAB_HOST", "gitlab.com")
    if not token:
        return {"error": "GITLAB_TOKEN not set. Set it in MCP server env config."}

    try:
        import httpx
        encoded_repo = repo.replace("/", "%2F")
        url = f"https://{gitlab_host}/api/v4/projects/{encoded_repo}/pipelines"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"PRIVATE-TOKEN": token},
                params={"per_page": limit, "order_by": "updated_at", "sort": "desc"},
                timeout=15
            )
            resp.raise_for_status()
            pipelines = resp.json()

        formatted = [{
            "id": p.get("id"),
            "branch": p.get("ref"),
            "status": p.get("status"),
            "sha": p.get("sha", "")[:8],
            "web_url": p.get("web_url"),
            "created_at": p.get("created_at"),
            "updated_at": p.get("updated_at"),
        } for p in pipelines]

        return {"platform": "gitlab", "repo": repo, "pipelines": formatted, "count": len(formatted)}
    except ImportError:
        return {"error": "httpx not installed. Run: pip install httpx"}
    except Exception as e:
        return {"error": str(e), "retryable": True}


def _local_git_log(path: str, limit: int) -> dict:
    """Show recent git commits as 'pipelines' for local repos."""
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={limit}", "--pretty=format:%H|%s|%an|%ai", "--no-merges"],
            capture_output=True, text=True, cwd=path or ".", timeout=10
        )
        if result.returncode != 0:
            return {"error": f"Git error: {result.stderr}"}

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append({
                    "sha": parts[0][:8],
                    "message": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                })

        return {"platform": "local", "path": path, "commits": commits}
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────
# TOOL: validate_config
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def validate_config(
    file_path: str,
    platform: str = "auto",
    ctx: Context = None,
) -> dict:
    """
    Validate a CI/CD configuration file for syntax errors and best practices.

    Args:
        file_path: Path to CI config file (.yml, .yaml, Jenkinsfile, etc.)
        platform: Platform hint ('github-actions', 'gitlab-ci', 'jenkins', 'auto')

    Returns validation results with errors and warnings.
    """
    if ctx:
        await ctx.info(f"Validating {file_path}")

    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    content = path.read_text()
    filename = path.name.lower()

    # Auto-detect platform
    if platform == "auto":
        if filename in [".gitlab-ci.yml", ".gitlab-ci.yaml"]:
            platform = "gitlab-ci"
        elif "jenkinsfile" in filename:
            platform = "jenkins"
        else:
            platform = "github-actions"  # Default

    errors = []
    warnings = []

    if platform in ["github-actions", "gitlab-ci"]:
        import yaml
        try:
            parsed = yaml.safe_load(content)
            if ctx:
                await ctx.info("YAML syntax valid")
        except yaml.YAMLError as e:
            return {
                "valid": False,
                "errors": [f"YAML syntax error: {e}"],
                "warnings": [],
                "platform": platform,
            }

        # GitHub Actions checks
        if platform == "github-actions":
            if not content.startswith("name:") and "name:" not in content[:200]:
                warnings.append("Missing 'name:' field — add a descriptive workflow name")
            if "concurrency:" not in content:
                warnings.append("Missing 'concurrency:' — add to cancel superseded PR runs")
            if "timeout-minutes:" not in content:
                warnings.append("Missing job timeouts — add 'timeout-minutes:' to prevent runaway jobs")
            if "permissions:" not in content:
                warnings.append("Missing 'permissions:' — restrict to least-privilege")
            if "@main" in content or "@latest" in content:
                errors.append("Unpinned action versions found (@main or @latest) — pin to semver or SHA")
            if "continue-on-error: true" in content:
                warnings.append("'continue-on-error: true' found — verify it's not on security stages")
            if "AWS_ACCESS_KEY_ID" in content and "configure-aws-credentials" not in content:
                errors.append("Static AWS credentials detected — use OIDC (configure-aws-credentials action)")

        # GitLab CI checks
        elif platform == "gitlab-ci":
            if "interruptible: true" not in content:
                warnings.append("Add 'interruptible: true' to cancel superseded pipeline jobs")
            if "timeout:" not in content and "timeout-minutes:" not in content:
                warnings.append("No job timeouts configured")

    # Common checks (all platforms)
    if "password" in content.lower() and "${{" not in content and "${" not in content:
        errors.append("Possible hardcoded password found")
    if re.search(r'[A-Z0-9]{20,}', content) and "${{" not in content:
        warnings.append("Long uppercase string found — verify it's not a hardcoded API key")

    valid = len(errors) == 0

    if ctx:
        await ctx.info(f"Validation complete: {len(errors)} errors, {len(warnings)} warnings")

    return {
        "valid": valid,
        "platform": platform,
        "file": str(file_path),
        "errors": errors,
        "warnings": warnings,
        "summary": f"{'✅ Valid' if valid else '❌ Invalid'} — {len(errors)} errors, {len(warnings)} warnings",
    }


# ─────────────────────────────────────────────────────────────
# TOOL: security_audit
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def security_audit(
    directory: str = ".",
    ctx: Context = None,
) -> dict:
    """
    Audit CI/CD pipeline files for security anti-patterns.

    Args:
        directory: Root directory to scan for pipeline files

    Returns security findings with severity levels and remediation advice.
    """
    if ctx:
        await ctx.info(f"Auditing CI/CD security in {directory}")

    findings = []
    scanned_files = []
    base = Path(directory)

    # Find CI files
    patterns = [
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        ".gitlab-ci.yml",
        ".gitlab-ci.yaml",
        "Jenkinsfile",
        "Jenkinsfile.*",
        "azure-pipelines.yml",
        ".circleci/config.yml",
        "bitbucket-pipelines.yml",
        "Makefile",
    ]

    ci_files = []
    for pattern in patterns:
        ci_files.extend(base.glob(pattern))
        ci_files.extend(base.glob(f"**/{pattern}"))

    ci_files = list(set(ci_files))[:50]  # Limit to 50 files

    if not ci_files:
        return {"error": f"No CI/CD files found in {directory}", "patterns_searched": patterns}

    security_rules = [
        {
            "id": "SEC-001",
            "severity": "CRITICAL",
            "pattern": r"AWS_ACCESS_KEY_ID\s*=\s*[A-Z0-9]{20}",
            "message": "Hardcoded AWS access key detected",
            "fix": "Use OIDC with aws-actions/configure-aws-credentials (no stored keys)",
        },
        {
            "id": "SEC-002",
            "severity": "HIGH",
            "pattern": r"@(main|master|latest)(?!\s*#)",
            "message": "Unpinned action/image version detected",
            "fix": "Pin to semver tag or commit SHA: uses: actions/checkout@v4 or @sha256:",
        },
        {
            "id": "SEC-003",
            "severity": "HIGH",
            "pattern": r"continue-on-error:\s*true",
            "message": "continue-on-error: true — may suppress security scan failures",
            "fix": "Remove from security scanning stages (SAST, SCA, container scan)",
        },
        {
            "id": "SEC-004",
            "severity": "MEDIUM",
            "pattern": r"set\s+-x",
            "message": "set -x in shell — may print secrets to logs",
            "fix": "Remove set -x from scripts that access secrets",
        },
        {
            "id": "SEC-005",
            "severity": "MEDIUM",
            "pattern": r"permissions:\s*write-all",
            "message": "Overly broad permissions: write-all",
            "fix": "Use minimal permissions per job (contents: read, packages: write, etc.)",
        },
        {
            "id": "SEC-006",
            "severity": "HIGH",
            "pattern": r'password\s*[=:]\s*["\']?[a-zA-Z0-9+/]{12,}["\']?(?!\$)',
            "message": "Possible hardcoded password",
            "fix": "Use secrets: ${{ secrets.PASSWORD }} or external secret manager",
        },
        {
            "id": "SEC-007",
            "severity": "LOW",
            "pattern": r"timeout-minutes:",
            "message": "No timeout configured (missing)",
            "fix": "Add timeout-minutes: to prevent runaway builds consuming quota",
            "invert": True,  # Flag when pattern is MISSING
        },
        {
            "id": "SEC-008",
            "severity": "HIGH",
            "pattern": r"docker build.*--no-cache",
            "message": "Building without cache from scratch on every run",
            "fix": "Use BuildKit cache (--cache-from / cache-to: type=gha) for consistency",
        },
    ]

    for ci_file in ci_files:
        try:
            content = ci_file.read_text()
            scanned_files.append(str(ci_file.relative_to(base)))

            for rule in security_rules:
                if rule.get("invert"):
                    # Flag when pattern is MISSING
                    if not re.search(rule["pattern"], content):
                        findings.append({
                            "rule_id": rule["id"],
                            "severity": rule["severity"],
                            "file": str(ci_file.relative_to(base)),
                            "message": rule["message"],
                            "fix": rule["fix"],
                        })
                else:
                    matches = re.finditer(rule["pattern"], content)
                    for match in matches:
                        line_num = content[:match.start()].count("\n") + 1
                        findings.append({
                            "rule_id": rule["id"],
                            "severity": rule["severity"],
                            "file": str(ci_file.relative_to(base)),
                            "line": line_num,
                            "snippet": match.group(0)[:80],
                            "message": rule["message"],
                            "fix": rule["fix"],
                        })
        except Exception:
            continue

    # Severity summary
    by_severity = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
    for f in findings:
        by_severity.get(f["severity"], []).append(f)

    if ctx:
        await ctx.info(f"Audit complete: {len(findings)} findings in {len(scanned_files)} files")

    return {
        "directory": str(directory),
        "files_scanned": len(scanned_files),
        "total_findings": len(findings),
        "critical": len(by_severity["CRITICAL"]),
        "high": len(by_severity["HIGH"]),
        "medium": len(by_severity["MEDIUM"]),
        "low": len(by_severity["LOW"]),
        "findings": findings,
        "passed": len(findings) == 0,
        "summary": f"{'✅ No issues' if not findings else f'🚨 {len(findings)} security issues found'} in {len(scanned_files)} files",
    }


# ─────────────────────────────────────────────────────────────
# TOOL: generate_workflow
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def generate_workflow(
    platform: str,
    tier: int,
    app_name: str = "myapp",
    language: str = "python",
    cloud: str = "aws",
    ctx: Context = None,
) -> dict:
    """
    Generate a CI/CD workflow configuration for the specified platform and tier.

    Args:
        platform: CI platform ('github-actions', 'gitlab-ci', 'jenkins')
        tier: Pipeline tier (1=Dev, 2=Standard, 3=Production, 4=Microservices, 5=Enterprise)
        app_name: Application name
        language: Primary language ('python', 'node', 'go', 'java')
        cloud: Cloud target ('aws', 'gcp', 'azure', 'kubernetes')

    Returns generated workflow content and setup instructions.
    """
    if ctx:
        await ctx.info(f"Generating {platform} Tier {tier} workflow for {app_name}")

    if tier not in range(1, 6):
        return {"error": "Tier must be 1-5"}
    if platform not in ["github-actions", "gitlab-ci", "jenkins", "azure-devops"]:
        return {"error": f"Unsupported platform: {platform}"}

    # Import generator from scaffold script
    import sys
    scripts_dir = Path(__file__).parent
    sys.path.insert(0, str(scripts_dir))

    try:
        from scaffold_cicd import generate_github_actions, generate_gitlab_ci, generate_makefile

        if platform == "github-actions":
            content = generate_github_actions(app_name, tier, cloud, "single-app")
            filename = ".github/workflows/ci.yml"
            setup = [
                "mkdir -p .github/workflows",
                f"# Save content to {filename}",
                "# Configure secrets in GitHub → Settings → Secrets and variables",
                f"# Required secrets for Tier {tier}:" + (
                    "\n#   AWS_ROLE_ARN (OIDC role)" if cloud == "aws" and tier >= 3 else
                    "\n#   KUBECONFIG (base64-encoded)" if tier <= 2 else ""
                ),
            ]
        elif platform == "gitlab-ci":
            content = generate_gitlab_ci(app_name, tier, cloud)
            filename = ".gitlab-ci.yml"
            setup = [
                f"# Save content to {filename}",
                "# Configure CI/CD variables in GitLab → Settings → CI/CD → Variables",
            ]
        else:
            content = f"# {platform} workflow for {app_name} (Tier {tier})\n# Full template in assets/templates/"
            filename = f"{platform}-pipeline.yml"
            setup = [f"# See assets/templates/ for complete {platform} template"]

        return {
            "platform": platform,
            "tier": tier,
            "app_name": app_name,
            "filename": filename,
            "content": content,
            "setup_instructions": setup,
            "next_steps": [
                f"1. Save content to {filename}",
                "2. make install  (installs pre-commit hooks)",
                "3. git add . && git commit -m 'ci: add pipeline configuration'",
                "4. Configure required secrets/variables in your CI platform",
                "5. Push and verify first pipeline run",
            ],
        }
    except ImportError as e:
        return {"error": f"Could not load scaffold module: {e}", "content": "See assets/templates/ for templates"}


# ─────────────────────────────────────────────────────────────
# TOOL: dora_metrics
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def dora_metrics(
    repo: str,
    platform: str = "github",
    days: int = 30,
    branch: str = "main",
    ctx: Context = None,
) -> dict:
    """
    Calculate DORA metrics from pipeline/deployment history.

    Args:
        repo: Repository path (GitHub: 'owner/repo', local: filesystem path)
        platform: 'github', 'gitlab', or 'local'
        days: Number of days to analyze (default: 30)
        branch: Branch to analyze (default: 'main')

    Returns DORA metrics: deployment frequency, lead time, MTTR, change failure rate.
    """
    if ctx:
        await ctx.info(f"Calculating DORA metrics for {repo} (last {days} days)")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    if platform == "local":
        return _local_dora_metrics(repo, days, branch, start_date, end_date)

    if platform == "github":
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            return {"error": "GITHUB_TOKEN required for GitHub DORA metrics"}
        return await _github_dora_metrics(repo, days, branch, token, ctx)

    return {"error": f"Platform '{platform}' not yet supported for DORA metrics"}


def _local_dora_metrics(path: str, days: int, branch: str, start: datetime, end: datetime) -> dict:
    """Calculate DORA metrics from local git log."""
    try:
        since = start.strftime("%Y-%m-%d")
        result = subprocess.run(
            ["git", "log", branch,
             f"--since={since}",
             "--pretty=format:%H|%ai|%s",
             "--no-merges"],
            capture_output=True, text=True, cwd=path or ".", timeout=15
        )

        if result.returncode != 0:
            return {"error": f"Git error: {result.stderr}"}

        commits = [l for l in result.stdout.strip().split("\n") if l]
        total_commits = len(commits)

        # Estimate metrics from commit frequency
        deploy_frequency = total_commits / days if days > 0 else 0
        category = (
            "Elite (Multiple/day)" if deploy_frequency >= 1 else
            "High (Daily-Weekly)" if deploy_frequency >= 0.14 else
            "Medium (Weekly-Monthly)" if deploy_frequency >= 0.03 else
            "Low (Monthly+)"
        )

        return {
            "platform": "local (git log estimate)",
            "repo": path,
            "period_days": days,
            "branch": branch,
            "total_commits": total_commits,
            "metrics": {
                "deployment_frequency": {
                    "value": f"{deploy_frequency:.2f} commits/day",
                    "category": category,
                    "note": "Based on commit frequency — actual deploy frequency may differ"
                },
                "lead_time_for_changes": {"value": "N/A", "note": "Not available from local git"},
                "mttr": {"value": "N/A", "note": "Not available from local git"},
                "change_failure_rate": {"value": "N/A", "note": "Not available from local git"},
            },
            "note": "For accurate DORA metrics, use GitHub/GitLab platform with deployment tracking",
        }
    except Exception as e:
        return {"error": str(e)}


async def _github_dora_metrics(repo: str, days: int, branch: str, token: str, ctx) -> dict:
    """Calculate DORA metrics from GitHub Actions deployments."""
    try:
        # Get deployment events
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/deployments",
             "--paginate", "--jq",
             f'[.[] | select(.created_at > "{(datetime.now() - timedelta(days=days)).isoformat()}Z")]'],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "GH_TOKEN": token}
        )

        if result.returncode != 0:
            return {"error": f"Could not fetch deployments: {result.stderr}"}

        try:
            deployments = json.loads(result.stdout) if result.stdout.strip() else []
        except json.JSONDecodeError:
            deployments = []

        total_deployments = len(deployments)
        deploy_freq = total_deployments / days if days > 0 else 0

        category = (
            "Elite (Multiple/day)" if deploy_freq >= 1 else
            "High (Daily-Weekly)" if deploy_freq >= 0.14 else
            "Medium (Weekly-Monthly)" if deploy_freq >= 0.03 else
            "Low (Monthly+)"
        )

        if ctx:
            await ctx.info(f"Found {total_deployments} deployments in last {days} days")

        return {
            "platform": "github",
            "repo": repo,
            "period_days": days,
            "branch": branch,
            "total_deployments": total_deployments,
            "metrics": {
                "deployment_frequency": {
                    "value": f"{deploy_freq:.2f} deploys/day ({total_deployments} total)",
                    "category": category,
                },
                "lead_time_for_changes": {
                    "value": "Requires commit timestamp tracking",
                    "note": "Add deployment event tracking in CI to measure accurately"
                },
                "mttr": {
                    "value": "Requires incident tracking integration",
                    "note": "Integrate with PagerDuty/OpsGenie for MTTR"
                },
                "change_failure_rate": {
                    "value": "Requires failed deployment tracking",
                    "note": "Tag deployments as success/failure to calculate CFR"
                },
            },
            "elite_targets": {
                "deployment_frequency": "Multiple times/day",
                "lead_time": "< 1 hour",
                "mttr": "< 1 hour",
                "change_failure_rate": "< 5%",
            },
        }
    except FileNotFoundError:
        return {"error": "gh CLI not found. Install: https://cli.github.com"}
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────
# RESOURCES
# ─────────────────────────────────────────────────────────────

@mcp.resource("cicd://platforms")
async def list_platforms() -> str:
    """Supported CI/CD platforms and their key features."""
    return json.dumps({
        "ci_platforms": {
            "github-actions": "OIDC, Marketplace 20k+, reusable workflows, matrix builds",
            "gitlab-ci": "Native registry, SAST, DAST, SBOM built-in, includes",
            "jenkins": "Plugins 1800+, shared libraries, Kubernetes agents, full control",
            "azure-devops": "Azure integration, boards + repos + pipelines, YAML + classic",
            "circleci": "DLC, orbs, test splitting, performance-focused",
            "bitbucket": "Jira native, Atlassian ecosystem, simple YAML",
            "tekton": "K8s-native CRDs, reusable tasks, catalog",
        },
        "cd_platforms": {
            "argocd": "GitOps pull model, multi-cluster, UI dashboard, rollback",
            "flux": "GitOps pull model, Helm automation, image policy, lightweight",
            "argo-rollouts": "Progressive delivery, canary, blue-green, metric analysis",
            "spinnaker": "Multi-cloud, complex promotion, Netflix/Google patterns",
            "harness": "SaaS, AI-assisted, cost management, enterprise",
        }
    }, indent=2)


@mcp.resource("cicd://security-checklist")
async def security_checklist() -> str:
    """Security checklist for production CI/CD pipelines."""
    return """
# CI/CD Security Checklist

## Critical (Block if missing)
- [ ] OIDC auth to cloud (no static credentials)
- [ ] All action versions pinned (SHA or semver)
- [ ] Secret detection on every commit (Gitleaks/TruffleHog)
- [ ] SAST before build (fail on HIGH+)
- [ ] Dependencies SCA (fail on CRITICAL)
- [ ] Container scan (fail on CRITICAL/HIGH)
- [ ] No continue-on-error on security stages

## High (Required for Production)
- [ ] Minimal permissions per job (least-privilege)
- [ ] Timeout on all jobs
- [ ] CODEOWNERS for pipeline files
- [ ] Coverage threshold enforced
- [ ] Smoke test after every deploy
- [ ] Automated rollback on health check failure

## Medium (Best Practices)
- [ ] Concurrency control (cancel superseded)
- [ ] Artifact retention policy (≤30 days)
- [ ] Image signing (Cosign keyless)
- [ ] SBOM generated and attested
- [ ] DORA metrics tracked
"""


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
