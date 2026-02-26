# Security Scanning Reference

SAST, DAST, SCA, container scanning, secret detection, image signing, and SBOM.

---

## Secret Detection (Always — All Tiers)

### Gitleaks (Pre-commit + CI)
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.0
    hooks:
      - id: gitleaks
        name: Detect hardcoded secrets
```

```yaml
# GitHub Actions
- name: Detect Secrets (Gitleaks)
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    GITLEAKS_LICENSE: ${{ secrets.GITLEAKS_LICENSE }}  # Optional for orgs
```

### TruffleHog (CI Deep Scan)
```yaml
- name: TruffleHog Secrets Scan
  uses: trufflesecurity/trufflehog@v3.63.11
  with:
    path: ./
    base: ${{ github.event.repository.default_branch }}
    head: HEAD
    extra_args: --only-verified  # Only confirmed active secrets
```

### detect-secrets (Baseline + CI)
```bash
# Initialize baseline (commit this file)
detect-secrets scan > .secrets.baseline

# In CI — audit against baseline
detect-secrets audit .secrets.baseline
detect-secrets scan --baseline .secrets.baseline
```

---

## SAST (Static Application Security Testing)

### Semgrep (Fast, Polyglot)
```yaml
# GitHub Actions
- name: Semgrep SAST
  uses: semgrep/semgrep-action@v1
  with:
    config: >-
      p/owasp-top-ten
      p/python
      p/javascript
      p/docker
      p/kubernetes
      p/secrets
    publishToken: ${{ secrets.SEMGREP_APP_TOKEN }}  # Optional for dashboard
  env:
    SEMGREP_APP_TOKEN: ${{ secrets.SEMGREP_APP_TOKEN }}
```

```bash
# Local / GitLab CI
semgrep --config "p/owasp-top-ten" --config "p/python" src/ \
  --json --output semgrep-results.json \
  --error  # Exit non-zero on findings
```

### CodeQL (GitHub Native)
```yaml
- name: Initialize CodeQL
  uses: github/codeql-action/init@v3
  with:
    languages: python, javascript, go
    queries: security-and-quality  # Or: security-extended

- name: Autobuild
  uses: github/codeql-action/autobuild@v3

- name: Analyze
  uses: github/codeql-action/analyze@v3
  with:
    category: "/language:python"
    upload: true  # Upload results to GitHub Security tab
```

### Checkov (IaC SAST)
```yaml
- name: Checkov IaC Scan
  uses: bridgecrewio/checkov-action@v12
  with:
    directory: .
    framework: all            # terraform, kubernetes, dockerfile, github_actions
    soft_fail: false          # Fail pipeline on HIGH+
    output_format: sarif
    output_file_path: checkov-results.sarif

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: checkov-results.sarif
```

---

## Dependency SCA (Software Composition Analysis)

### Snyk (Comprehensive)
```yaml
- name: Snyk Dependency Scan
  uses: snyk/actions/python@master
  with:
    args: --severity-threshold=high --fail-on=all
  env:
    SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}

- name: Snyk Monitor (Upload to Dashboard)
  uses: snyk/actions/python@master
  with:
    command: monitor
  env:
    SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
```

### Trivy (Dependency + Container, Open Source)
```yaml
- name: Trivy Vulnerability Scan (Filesystem / Deps)
  uses: aquasecurity/trivy-action@0.28.0
  with:
    scan-type: fs
    scan-ref: .
    severity: CRITICAL,HIGH
    format: sarif
    output: trivy-results.sarif
    exit-code: 1  # Fail on findings
```

### OWASP Dependency-Check
```yaml
- name: OWASP Dependency Check
  uses: dependency-check/Dependency-Check_Action@main
  with:
    project: myapp
    path: .
    format: HTML
    args: >
      --failOnCVSS 7
      --enableRetired
```

### Dependabot (GitHub Automated PRs)
```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 10
    groups:
      dev-dependencies:
        dependency-type: development
  - package-ecosystem: docker
    directory: /
    schedule:
      interval: weekly
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

---

## Container Image Scanning

### Trivy Image Scan
```yaml
- name: Scan Docker Image (Trivy)
  uses: aquasecurity/trivy-action@0.28.0
  with:
    image-ref: ${{ env.IMAGE_NAME }}:${{ github.sha }}
    format: sarif
    output: image-trivy.sarif
    severity: CRITICAL,HIGH
    exit-code: 1
    ignore-unfixed: true  # Skip vulnerabilities with no fix

- name: Upload Trivy results to GitHub Security
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: image-trivy.sarif
```

### Grype (Anchore)
```yaml
- name: Grype Container Scan
  uses: anchore/scan-action@v4
  with:
    image: ${{ env.IMAGE_NAME }}:${{ github.sha }}
    fail-build: true
    severity-cutoff: high
    output-format: sarif
```

### Dockerfile Linting (Hadolint)
```yaml
- name: Hadolint Dockerfile Lint
  uses: hadolint/hadolint-action@v3.1.0
  with:
    dockerfile: Dockerfile
    failure-threshold: warning
    ignore: DL3008,DL3009  # Ignore specific rules if needed
```

---

## DAST (Dynamic Application Security Testing)

### OWASP ZAP (Baseline Scan)
```yaml
# Run against deployed staging environment
- name: OWASP ZAP Baseline Scan
  uses: zaproxy/action-baseline@v0.12.0
  with:
    target: https://staging.example.com
    rules_file_name: .zap/rules.tsv
    cmd_options: -a  # Include ajax spider
    issue_title: ZAP Scan Report
    token: ${{ secrets.GITHUB_TOKEN }}
    fail_action: false  # Warn, don't fail (use 'true' for full block)
```

### OWASP ZAP Full Scan (Tier 3+)
```yaml
- name: ZAP Full Scan
  uses: zaproxy/action-full-scan@v0.10.0
  with:
    target: https://staging.example.com
    cmd_options: '-z "-config scanner.maxRuleDurationInMins=5"'
```

### Nuclei (Fast Template-Based)
```yaml
- name: Nuclei Security Scan
  uses: projectdiscovery/nuclei-action@v2
  with:
    target: https://staging.example.com
    flags: "-severity critical,high -t ~/nuclei-templates/http/"
    github-report: true
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Container Image Signing (Cosign Keyless)

### Keyless Signing (OIDC-based, no key management)
```yaml
- name: Install Cosign
  uses: sigstore/cosign-installer@v3.7.0

- name: Sign Image (Keyless via GitHub OIDC)
  run: |
    cosign sign --yes \
      --rekor-url https://rekor.sigstore.dev \
      ${REGISTRY}/${IMAGE_NAME}@${IMAGE_DIGEST}
  env:
    COSIGN_EXPERIMENTAL: 1

- name: Verify Signature
  run: |
    cosign verify \
      --certificate-identity-regexp "https://github.com/org/*" \
      --certificate-oidc-issuer https://token.actions.githubusercontent.com \
      ${REGISTRY}/${IMAGE_NAME}@${IMAGE_DIGEST}
```

### Cosign with Key (Tier 4+ self-managed)
```yaml
- name: Sign Image with Key
  run: |
    echo "${COSIGN_PRIVATE_KEY}" > cosign.key
    cosign sign --key cosign.key ${IMAGE_REF}
    rm cosign.key
  env:
    COSIGN_PRIVATE_KEY: ${{ secrets.COSIGN_PRIVATE_KEY }}
    COSIGN_PASSWORD: ${{ secrets.COSIGN_PASSWORD }}
```

### Admission Policy (Verify signatures on deploy)
```yaml
# Kyverno policy — require signed images
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-image-signature
spec:
  validationFailureAction: Enforce
  rules:
    - name: verify-signature
      match:
        resources:
          kinds: [Pod]
      verifyImages:
        - imageReferences: ["ghcr.io/org/*"]
          attestors:
            - entries:
                - keyless:
                    subject: "https://github.com/org/*"
                    issuer: "https://token.actions.githubusercontent.com"
                    rekor:
                      url: https://rekor.sigstore.dev
```

---

## SBOM Generation

### Syft (SPDX / CycloneDX)
```yaml
- name: Generate SBOM (Syft)
  uses: anchore/sbom-action@v0.17.9
  with:
    image: ${{ env.IMAGE_NAME }}:${{ github.sha }}
    format: spdx-json     # or: cyclonedx-json
    artifact-name: sbom.spdx.json
    upload-artifact: true

- name: Attest SBOM with Cosign
  run: |
    cosign attest --yes \
      --predicate sbom.spdx.json \
      --type spdxjson \
      ${IMAGE_REF}
```

### SLSA Provenance (Supply Chain Security)
```yaml
- name: Generate SLSA Provenance
  uses: slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml@v2.0.0
  with:
    image: ${{ env.IMAGE_NAME }}
    digest: ${{ steps.build.outputs.digest }}
    registry-username: ${{ github.actor }}
    registry-password: ${{ secrets.GITHUB_TOKEN }}
```

---

## Security Scan Summary in PR

```yaml
- name: Security Scan Summary
  if: always()
  run: |
    echo "## Security Scan Results" >> $GITHUB_STEP_SUMMARY
    echo "| Scan | Status |" >> $GITHUB_STEP_SUMMARY
    echo "|------|--------|" >> $GITHUB_STEP_SUMMARY
    echo "| Secret Detection | ${{ steps.gitleaks.outcome }} |" >> $GITHUB_STEP_SUMMARY
    echo "| SAST (Semgrep) | ${{ steps.semgrep.outcome }} |" >> $GITHUB_STEP_SUMMARY
    echo "| Dependency SCA | ${{ steps.snyk.outcome }} |" >> $GITHUB_STEP_SUMMARY
    echo "| Container Scan | ${{ steps.trivy.outcome }} |" >> $GITHUB_STEP_SUMMARY
    echo "| Image Signed | ✅ |" >> $GITHUB_STEP_SUMMARY
```
