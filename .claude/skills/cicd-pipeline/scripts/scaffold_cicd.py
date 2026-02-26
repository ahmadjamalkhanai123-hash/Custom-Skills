#!/usr/bin/env python3
"""
CI/CD Pipeline Scaffold Generator
Generates a complete CI/CD project structure for any tier/platform combination.

Usage:
  python scaffold_cicd.py --tier 3 --ci github-actions --cd argocd \
                          --cloud aws --project-type microservices \
                          --app-name myapp --output ./output
"""

import argparse
import os
import sys
from pathlib import Path
from textwrap import dedent

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

TIERS = {
    1: "Developer (pre-commit + Makefile + local act)",
    2: "Standard (CI + basic deploy)",
    3: "Production (multi-stage + security scanning + OIDC)",
    4: "Microservices (matrix builds + GitOps + integration testing)",
    5: "Enterprise (multi-cloud + progressive delivery + compliance + DORA)",
}

CI_PLATFORMS = ["github-actions", "gitlab-ci", "jenkins", "azure-devops", "circleci", "bitbucket", "tekton"]
CD_PLATFORMS = ["direct-helm", "argocd", "flux", "spinnaker", "harness", "none"]
CLOUDS = ["aws", "gcp", "azure", "digitalocean", "on-prem", "multi-cloud"]
PROJECT_TYPES = ["single-app", "monorepo", "microservices", "agentic"]
LANGUAGES = ["python", "node", "go", "java", "rust"]

# ─────────────────────────────────────────────────────────────
# GENERATORS
# ─────────────────────────────────────────────────────────────

def generate_github_actions(app_name: str, tier: int, cloud: str, project_type: str) -> str:
    """Generate GitHub Actions workflow YAML."""
    oidc_step = ""
    if cloud == "aws" and tier >= 3:
        oidc_step = f"""
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{{{ secrets.AWS_ROLE_ARN }}}}
          aws-region: us-east-1"""
    elif cloud == "gcp" and tier >= 3:
        oidc_step = f"""
      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{{{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}}}
          service_account: ${{{{ secrets.GCP_SERVICE_ACCOUNT }}}}"""
    elif cloud == "azure" and tier >= 3:
        oidc_step = f"""
      - uses: azure/login@v2
        with:
          client-id: ${{{{ secrets.AZURE_CLIENT_ID }}}}
          tenant-id: ${{{{ secrets.AZURE_TENANT_ID }}}}
          subscription-id: ${{{{ secrets.AZURE_SUBSCRIPTION_ID }}}}"""

    security_stage = ""
    if tier >= 3:
        security_stage = """
  security-scan:
    name: Security Scan
    needs: [lint]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: semgrep/semgrep-action@v1
        with:
          config: "p/owasp-top-ten p/python"
      - uses: aquasecurity/trivy-action@0.28.0
        with:
          scan-type: fs
          exit-code: 1
          severity: CRITICAL,HIGH"""

    matrix_build = ""
    if project_type == "microservices" and tier >= 4:
        matrix_build = """
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.set-matrix.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            service-a: [services/service-a/**, shared/**]
            service-b: [services/service-b/**, shared/**]
      - id: set-matrix
        run: echo "matrix={\"service\":${{ steps.filter.outputs.changes }}}" >> $GITHUB_OUTPUT

  build-matrix:
    needs: detect-changes
    if: needs.detect-changes.outputs.matrix != '{"service":[]}'
    strategy:
      fail-fast: false
      matrix: ${{ fromJson(needs.detect-changes.outputs.matrix) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build ${{ matrix.service }}
        run: docker build -t myapp/${{ matrix.service }}:${{ github.sha }} services/${{ matrix.service }}/"""

    return dedent(f"""
        name: CI/CD Pipeline

        on:
          push:
            branches: [main, develop]
          pull_request:
            branches: [main]

        concurrency:
          group: ${{{{ github.workflow }}}}-${{{{ github.ref }}}}
          cancel-in-progress: true

        permissions:
          contents: read
          packages: write
          id-token: write
          security-events: write

        jobs:
          lint:
            name: Lint & Quality
            runs-on: ubuntu-latest
            timeout-minutes: 15
            steps:
              - uses: actions/checkout@v4
              - name: Lint
                run: echo "Add your lint command here"
        {security_stage}
          test:
            name: Test
            needs: [lint]
            runs-on: ubuntu-latest
            timeout-minutes: 20
            steps:
              - uses: actions/checkout@v4
              - name: Unit Tests
                run: echo "Add your test command here (add --cov-fail-under=80)"

          build:
            name: Build & Push
            needs: [test]
            runs-on: ubuntu-latest
            outputs:
              image-digest: ${{{{ steps.push.outputs.digest }}}}
            steps:
              - uses: actions/checkout@v4
              - uses: docker/setup-buildx-action@v3
        {oidc_step}
              - uses: docker/build-push-action@v6
                id: push
                with:
                  push: ${{{{ github.event_name != 'pull_request' }}}}
                  tags: ghcr.io/${{{{ github.repository }}}}:{app_name}:${{{{ github.sha }}}}
                  cache-from: type=gha
                  cache-to: type=gha,mode=max

          deploy-staging:
            name: Deploy Staging
            needs: [build]
            if: github.ref == 'refs/heads/main'
            environment:
              name: staging
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - name: Deploy
                run: |
                  helm upgrade --install {app_name} chart/ \\
                    --namespace staging \\
                    --set image.tag=${{{{ github.sha }}}} \\
                    --atomic --timeout 5m
        """).strip()


def generate_gitlab_ci(app_name: str, tier: int, cloud: str) -> str:
    """Generate GitLab CI YAML."""
    security = ""
    if tier >= 3:
        security = """
sast:
  stage: quality
  image: returntocorp/semgrep:latest
  before_script: []
  script:
    - semgrep --config "p/owasp-top-ten" src/ --error
"""

    return dedent(f"""
        stages:
          - quality
          - test
          - build
          - security
          - deploy

        variables:
          IMAGE_TAG: $CI_REGISTRY_IMAGE:{app_name}:$CI_COMMIT_SHA

        default:
          interruptible: true
          retry:
            max: 2
            when: [runner_system_failure]

        lint:
          stage: quality
          script:
            - echo "Add lint command"

        {security}
        unit-tests:
          stage: test
          script:
            - pytest tests/ --cov=src --cov-fail-under=80
          artifacts:
            reports:
              coverage_report:
                coverage_format: cobertura
                path: coverage.xml

        build-image:
          stage: build
          image: docker:24
          services:
            - docker:24-dind
          script:
            - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
            - docker build -t $IMAGE_TAG .
            - docker push $IMAGE_TAG

        deploy-staging:
          stage: deploy
          environment:
            name: staging
            url: https://staging.{app_name}.example.com
          script:
            - helm upgrade --install {app_name} chart/ --set image.tag=$CI_COMMIT_SHA
          rules:
            - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
    """).strip()


def generate_pre_commit_config() -> str:
    """Generate pre-commit configuration."""
    return dedent("""
        repos:
          - repo: https://github.com/pre-commit/pre-commit-hooks
            rev: v4.6.0
            hooks:
              - id: trailing-whitespace
              - id: end-of-file-fixer
              - id: check-yaml
              - id: check-json
              - id: detect-private-key
              - id: check-merge-conflict

          - repo: https://github.com/gitleaks/gitleaks
            rev: v8.21.0
            hooks:
              - id: gitleaks

          - repo: https://github.com/astral-sh/ruff-pre-commit
            rev: v0.8.4
            hooks:
              - id: ruff
                args: [--fix]
              - id: ruff-format

          - repo: https://github.com/commitizen-tools/commitizen
            rev: v4.1.0
            hooks:
              - id: commitizen
                stages: [commit-msg]

        default_language_version:
          python: python3.12
    """).strip()


def generate_argocd_app(app_name: str, gitops_repo: str) -> str:
    """Generate ArgoCD Application manifest."""
    return dedent(f"""
        apiVersion: argoproj.io/v1alpha1
        kind: Application
        metadata:
          name: {app_name}-staging
          namespace: argocd
          finalizers:
            - resources-finalizer.argocd.argoproj.io
        spec:
          project: default
          source:
            repoURL: {gitops_repo}
            targetRevision: main
            path: apps/{app_name}/overlays/staging
          destination:
            server: https://kubernetes.default.svc
            namespace: {app_name}-staging
          syncPolicy:
            automated:
              prune: true
              selfHeal: true
            syncOptions:
              - CreateNamespace=true
    """).strip()


def generate_makefile(app_name: str, language: str) -> str:
    """Generate project Makefile."""
    test_cmd = "pytest tests/ --cov=src --cov-fail-under=80"
    lint_cmd = "ruff check src/ && mypy src/"
    if language == "node":
        test_cmd = "npm test"
        lint_cmd = "eslint src/ && tsc --noEmit"
    elif language == "go":
        test_cmd = "go test ./... -race -coverprofile=coverage.out"
        lint_cmd = "golangci-lint run ./..."

    return dedent(f"""
        .DEFAULT_GOAL := help
        APP_NAME := {app_name}
        IMAGE_TAG ?= $(shell git rev-parse --short HEAD)

        help:
        \t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {{FS = ":.*?## "}}; {{printf "  %-20s %s\\n", $$1, $$2}}'

        install: ## Install dependencies
        \tpip install -r requirements-dev.txt && pre-commit install

        lint: ## Run linters
        \t{lint_cmd}

        test: ## Run tests
        \t{test_cmd}

        build: ## Build Docker image
        \tdocker build -t $(APP_NAME):$(IMAGE_TAG) .

        ci: ## Run full CI pipeline locally
        \t@$(MAKE) lint test build
        \t@echo "✓ All CI stages passed"
    """).strip()


def generate_smoke_test(app_name: str) -> str:
    """Generate smoke test script."""
    return dedent(f"""
        #!/bin/bash
        # Smoke test for {app_name}
        set -e

        BASE_URL="${{1:-http://localhost:8080}}"
        MAX_RETRIES=10
        RETRY_DELAY=5

        echo "Running smoke tests against $BASE_URL"

        for i in $(seq 1 $MAX_RETRIES); do
          STATUS=$(curl -s -o /dev/null -w "%{{http_code}}" "$BASE_URL/health")
          if [ "$STATUS" -eq 200 ]; then
            echo "✓ Health check passed ($STATUS)"
            break
          fi
          echo "Attempt $i/$MAX_RETRIES: Got $STATUS, retrying in ${{RETRY_DELAY}}s..."
          sleep $RETRY_DELAY
          if [ "$i" -eq "$MAX_RETRIES" ]; then
            echo "✗ Smoke test FAILED after $MAX_RETRIES attempts"
            exit 1
          fi
        done

        echo "✓ All smoke tests passed"
    """).strip()


# ─────────────────────────────────────────────────────────────
# DIRECTORY STRUCTURE GENERATORS
# ─────────────────────────────────────────────────────────────

def create_project_structure(output: Path, app_name: str, tier: int, ci: str,
                              cd: str, cloud: str, project_type: str, language: str):
    """Create the complete CI/CD project structure."""
    print(f"\n🏗  Scaffolding CI/CD for '{app_name}' (Tier {tier}, {ci}, {cd})")

    # Core directories
    dirs = [
        output / ".github" / "workflows",
        output / "chart" / "templates",
        output / "scripts",
        output / "tests" / "unit",
        output / "tests" / "integration",
        output / "src",
    ]

    if project_type == "microservices":
        dirs.extend([
            output / "services" / "service-a",
            output / "services" / "service-b",
            output / "shared" / "libs",
        ])

    if cd in ["argocd", "flux"]:
        dirs.extend([
            output / "gitops" / "apps" / app_name / "base",
            output / "gitops" / "apps" / app_name / "overlays" / "staging",
            output / "gitops" / "apps" / app_name / "overlays" / "production",
        ])

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Generate CI workflow
    if ci == "github-actions":
        workflow_content = generate_github_actions(app_name, tier, cloud, project_type)
        (output / ".github" / "workflows" / "ci.yml").write_text(workflow_content)

        if project_type == "microservices" and tier >= 4:
            ms_content = generate_github_actions(app_name, tier, cloud, "microservices")
            (output / ".github" / "workflows" / "microservices.yml").write_text(ms_content)

    elif ci == "gitlab-ci":
        (output / ".gitlab-ci.yml").write_text(generate_gitlab_ci(app_name, tier, cloud))

    # Pre-commit (Tier 1+)
    (output / ".pre-commit-config.yaml").write_text(generate_pre_commit_config())

    # Makefile (Tier 1+)
    (output / "Makefile").write_text(generate_makefile(app_name, language))

    # Smoke test script
    smoke_script = output / "scripts" / "smoke_test.sh"
    smoke_script.write_text(generate_smoke_test(app_name))
    smoke_script.chmod(0o755)

    # ArgoCD app (Tier 4+)
    if cd == "argocd" and tier >= 4:
        argocd_content = generate_argocd_app(app_name, "https://github.com/org/gitops-repo")
        (output / "gitops" / "apps" / app_name / "argocd-app.yaml").write_text(argocd_content)

    # .secrets.baseline (detect-secrets)
    (output / ".secrets.baseline").write_text('{"version": "1.5.0", "plugins_used": [], "results": {}}')

    # .gitleaks.toml
    (output / ".gitleaks.toml").write_text(dedent("""
        [allowlist]
          regexes = ["example\\.com", "placeholder", "PLACEHOLDER"]
    """).strip())

    # Helm chart skeleton
    (output / "chart" / "Chart.yaml").write_text(dedent(f"""
        apiVersion: v2
        name: {app_name}
        version: 0.1.0
        appVersion: "0.1.0"
        description: Helm chart for {app_name}
    """).strip())

    (output / "chart" / "values.yaml").write_text(dedent(f"""
        replicaCount: 2
        image:
          repository: ghcr.io/org/{app_name}
          pullPolicy: IfNotPresent
          tag: ""
        service:
          type: ClusterIP
          port: 80
        ingress:
          enabled: false
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
    """).strip())

    # Summary
    files = list(output.rglob("*"))
    file_count = len([f for f in files if f.is_file()])
    print(f"\n✅ Generated {file_count} files in {output}/")
    print(f"\nProject structure:")
    for f in sorted(output.rglob("*"))[:20]:
        if f.is_file():
            print(f"  {f.relative_to(output)}")
    if file_count > 20:
        print(f"  ... and {file_count - 20} more files")

    print(f"\n📋 Next steps:")
    print(f"  1. cd {output}")
    print(f"  2. git init && git add .")
    print(f"  3. pre-commit install")
    print(f"  4. make ci  # Validate locally before push")
    print(f"\nFor Tier {tier} details: see skill references/")


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CI/CD Pipeline Scaffold Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent("""
        Examples:
          # Tier 2: GitHub Actions + direct Helm deploy to GCP
          python scaffold_cicd.py --tier 2 --ci github-actions --cloud gcp --app-name myapp

          # Tier 3: Production with security scanning to AWS
          python scaffold_cicd.py --tier 3 --ci github-actions --cd argocd --cloud aws

          # Tier 4: Microservices with GitOps
          python scaffold_cicd.py --tier 4 --ci github-actions --cd argocd \\
                                  --project-type microservices --app-name platform

          # Tier 1: Developer local setup
          python scaffold_cicd.py --tier 1 --ci github-actions --app-name myapp
        """)
    )

    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4, 5], required=True,
                       help="Pipeline tier (1=Dev, 2=Standard, 3=Production, 4=Microservices, 5=Enterprise)")
    parser.add_argument("--ci", choices=CI_PLATFORMS, default="github-actions",
                       help="CI platform")
    parser.add_argument("--cd", choices=CD_PLATFORMS, default="direct-helm",
                       help="CD platform/strategy")
    parser.add_argument("--cloud", choices=CLOUDS, default="aws",
                       help="Cloud/deployment target")
    parser.add_argument("--project-type", choices=PROJECT_TYPES, default="single-app",
                       help="Project type")
    parser.add_argument("--language", choices=LANGUAGES, default="python",
                       help="Primary application language")
    parser.add_argument("--app-name", default="myapp",
                       help="Application name (lowercase, hyphens)")
    parser.add_argument("--output", default="./cicd-output",
                       help="Output directory")

    args = parser.parse_args()

    print(f"CI/CD Pipeline Scaffold — {TIERS[args.tier]}")
    print("=" * 60)
    print(f"  App:          {args.app_name}")
    print(f"  CI:           {args.ci}")
    print(f"  CD:           {args.cd}")
    print(f"  Cloud:        {args.cloud}")
    print(f"  Project Type: {args.project_type}")
    print(f"  Language:     {args.language}")

    output_path = Path(args.output)
    create_project_structure(
        output=output_path,
        app_name=args.app_name,
        tier=args.tier,
        ci=args.ci,
        cd=args.cd,
        cloud=args.cloud,
        project_type=args.project_type,
        language=args.language,
    )


if __name__ == "__main__":
    main()
