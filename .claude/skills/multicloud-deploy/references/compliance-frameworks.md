# Compliance Frameworks Reference

## SOC 2 Type II

SOC 2 evaluates controls around 5 Trust Service Criteria (TSC).
For multi-cloud: CC6 (Logical Access), CC7 (System Operations), CC8 (Change Management).

### Key Controls for Multi-Cloud

| Control | Requirement | Multi-Cloud Implementation |
|---------|------------|---------------------------|
| **CC6.1** | Logical access restrictions | RBAC on all clusters; IRSA/WIF; no shared accounts |
| **CC6.2** | Access provisioning | IaC-driven account creation; no manual console access |
| **CC6.3** | Termination of access | Automated deprovisioning; K8s SA TTL |
| **CC6.6** | Security boundaries | Network policies; mTLS; VPN for inter-cloud |
| **CC6.7** | Encryption | KMS at rest; TLS 1.2+ in transit; Vault for secrets |
| **CC7.1** | Detection capabilities | Falco + GuardDuty + GCP SCC + Azure Defender |
| **CC7.2** | Monitor system components | Prometheus + AlertManager; CloudTrail; Audit logs |
| **CC7.3** | Evaluate security events | SIEM (Splunk/Elastic); incident response runbook |
| **CC8.1** | Change management | GitOps only; ArgoCD self-heal; Terraform plan/apply review |
| **CC9.2** | Vendor risk | Cloud provider BAAs; SOC 2 reports from cloud vendors |

### Audit Evidence to Collect

```bash
# Kubernetes audit logs (enable in all clusters)
# EKS: enable via CloudWatch Logs
# GKE: enable via Cloud Audit Logs
# AKS: enable via Azure Monitor

# AWS CloudTrail (all regions, S3 + CloudWatch)
aws cloudtrail describe-trails
aws cloudtrail get-trail-status --name prod-trail

# Generate RBAC access report
kubectl auth can-i --list --as=system:serviceaccount:payments:checkout-api

# List all ClusterRoleBindings (for access review)
kubectl get clusterrolebindings -o json | \
  jq '.items[] | {name: .metadata.name, subjects: .subjects, role: .roleRef}'
```

---

## HIPAA §164.312 — Technical Safeguards

HIPAA applies to any system handling Protected Health Information (PHI).
In multi-cloud: apply controls EVERYWHERE PHI could traverse.

### Required Controls

| Safeguard | §164.312 | Multi-Cloud Implementation |
|-----------|----------|---------------------------|
| **Access Control** | (a)(1) | Unique user IDs; IRSA; no root access |
| **Audit Controls** | (b) | CloudTrail + K8s audit + application audit logs |
| **Integrity** | (c)(1) | Checksums; immutable logs (S3 Object Lock, GCS retention) |
| **Authentication** | (d) | MFA on all cloud consoles; OIDC for service accounts |
| **Encryption in Transit** | (e)(2)(ii) | TLS 1.2+ everywhere; Istio mTLS STRICT |
| **Encryption at Rest** | addressable | KMS-encrypted PVs; encrypted RDS/GCS/Azure Storage |

### HIPAA-Specific Configurations

```yaml
# K8s: Label namespaces containing PHI
apiVersion: v1
kind: Namespace
metadata:
  name: healthcare
  labels:
    hipaa: "true"
    data-classification: "phi"
    compliance: "hipaa"

---
# NetworkPolicy: isolate PHI namespace from non-PHI
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: phi-isolation
  namespace: healthcare
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              hipaa: "true"    # only from other HIPAA namespaces
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              hipaa: "true"
    - ports:                   # allow DNS
        - port: 53
          protocol: UDP
```

```yaml
# Kyverno: enforce encryption labels on PHI storage
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-phi-encryption
spec:
  validationFailureAction: enforce
  rules:
    - name: require-encrypted-pvc
      match:
        resources:
          kinds: [PersistentVolumeClaim]
          namespaceSelector:
            matchLabels:
              hipaa: "true"
      validate:
        message: "PHI namespaces must use encrypted storage class"
        pattern:
          spec:
            storageClassName: "*encrypted*|gp3-encrypted|pd-ssd-encrypted"
```

### BAA Requirements
- AWS: Sign BAA in AWS console (Business Associate Agreement)
- GCP: Sign BAA via Google Cloud HIPAA compliance
- Azure: Covered by Microsoft Online Services Agreement + HIPAA BAA

---

## PCI-DSS v4.0

PCI-DSS v4.0 (March 2024) replaces v3.2.1. Key changes: risk-based approach, multi-factor auth required everywhere.

### Cardholder Data Environment (CDE) Isolation

The CDE must be strictly isolated from non-CDE systems.

```
┌──────────────────────────────────────────┐
│  Cardholder Data Environment (CDE)       │
│  Namespace: pci-cde                      │
│  Network: isolated VPC/subnet            │
│  ┌────────────┐  ┌──────────────────┐   │
│  │ Payment API│  │ Card Vault       │   │
│  │ (tokenize) │  │ (HSM or Vault)   │   │
│  └────────────┘  └──────────────────┘   │
└──────────────────────────────────────────┘
           │ tokenized card only
┌──────────────────────────────────────────┐
│  Non-CDE (other microservices)           │
│  Uses tokens, never raw card data        │
└──────────────────────────────────────────┘
```

### PCI-DSS v4.0 Key Requirements

| Req | Requirement | Implementation |
|-----|-------------|----------------|
| **1.3** | Network access controls to/from CDE | Kubernetes NetworkPolicy + Istio AuthorizationPolicy |
| **2.2** | System components hardened | CIS Benchmark for K8s; no root containers |
| **3.4** | PANs masked when displayed | Application-level masking; no PANs in logs |
| **3.5** | PANs secured in storage | AES-256 encryption + HSM or Vault Transit |
| **4.2.1** | Strong cryptography in transit | TLS 1.2+ (TLS 1.3 preferred); no SSLv3/TLS 1.0 |
| **6.4** | Web-facing apps protected | WAF (Cloudflare/AWS WAF/Cloud Armor) |
| **7.2** | Least-privilege access | RBAC review quarterly; no wildcard permissions |
| **8.4** | MFA for all CDE access | MFA on cloud consoles; Vault MFA for operator access |
| **10.2** | Audit logs all access | K8s audit + CloudTrail + application audit |
| **10.3** | Logs protected from modification | S3 Object Lock; GCS retention; immutable log sinks |
| **11.3** | Penetration testing annually | Quarterly ASV scans; annual pen test |
| **12.3.1** | Targeted risk analysis | Risk register per service; reviewed quarterly |

### Automated PCI Compliance (Kyverno)

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: pci-cde-hardening
spec:
  validationFailureAction: enforce
  rules:
    # Req 2.2: No root containers in CDE
    - name: no-root-in-cde
      match:
        resources:
          kinds: [Pod]
          namespaceSelector:
            matchLabels:
              pci: "cde"
      validate:
        message: "CDE containers must not run as root"
        pattern:
          spec:
            containers:
              - securityContext:
                  runAsNonRoot: true
                  allowPrivilegeEscalation: false
                  readOnlyRootFilesystem: true

    # Req 7.2: Block wildcard ClusterRoleBindings
    - name: no-wildcard-in-cde
      match:
        resources:
          kinds: [ClusterRole]
      validate:
        message: "Wildcard permissions not allowed"
        deny:
          conditions:
            any:
              - key: "{{ request.object.rules[].verbs[] | contains(@, '*') }}"
                operator: Equals
                value: true
```

---

## FedRAMP / NIST 800-53 Rev 5

FedRAMP authorizes cloud systems for US Federal use.
Impact levels: Low (LL), Moderate (ML), High (HL). Most agencies require Moderate+.

### Key Control Families

| Family | Controls | Multi-Cloud Implementation |
|--------|----------|---------------------------|
| **AC** Access Control | AC-2, AC-3, AC-6, AC-17 | RBAC; IRSA; MFA; least privilege |
| **AU** Audit | AU-2, AU-3, AU-9, AU-12 | CloudTrail; K8s audit; immutable logs |
| **CM** Config Mgmt | CM-2, CM-6, CM-7, CM-8 | Terraform IaC; GitOps; inventory via Kyverno |
| **IA** Identification/Auth | IA-2, IA-5, IA-8 | MFA; OIDC; workload identity |
| **IR** Incident Response | IR-4, IR-5, IR-6 | PagerDuty; runbooks; SIEM |
| **SC** System Comms | SC-8, SC-28 | mTLS; KMS encryption |
| **SI** System Integrity | SI-2, SI-3, SI-7 | Patch management; Trivy scanning; integrity checks |

### FedRAMP Continuous Monitoring Requirements

```bash
# Monthly: Vulnerability scanning
trivy image --format sarif --output results.sarif \
  us-east-1.dkr.ecr.amazonaws.com/checkout-api:latest

# Weekly: Configuration compliance check
aws securityhub get-findings \
  --filters '{"SeverityLabel": [{"Value": "HIGH", "Comparison": "EQUALS"}]}' \
  --query 'Findings[].{Title:Title,Resource:Resources[0].Id}'

# Daily: Access review alerts (new admin role bindings)
kubectl get clusterrolebindings \
  -o json --all-namespaces | \
  jq '.items[] | select(.roleRef.name == "cluster-admin")'
```

### FIPS 140-2 Compliance (High Impact)

For FedRAMP High, use FIPS-validated cryptography:
- EKS: Use FIPS-compliant node AMIs (Amazon Linux 2 FIPS)
- GKE: Enable FIPS mode on node pools
- Istio: Use FIPS-compliant image (`proxyv2` with BoringSSL)
- Vault: Use FIPS 140-2 build

---

## Unified Compliance Tooling

### AWS Security Hub (Multi-Account + GCP/Azure via integration)

```hcl
resource "aws_securityhub_account" "main" {}

resource "aws_securityhub_standards_subscription" "cis" {
  standards_arn = "arn:aws:securityhub:::ruleset/cis-aws-foundations-benchmark/v/1.4.0"
}

resource "aws_securityhub_standards_subscription" "pci" {
  standards_arn = "arn:aws:securityhub:us-east-1::standards/pci-dss/v/3.2.1"
}
```

### Compliance Dashboard (Grafana)

Create a compliance dashboard with panels for:
1. **Policy violations count** by cloud/namespace (from Kyverno metrics)
2. **Security Hub findings** severity by service
3. **Audit log anomalies** (unusual access patterns)
4. **Certificate expiry** countdown (from cert-manager metrics)
5. **Failed logins** count across clouds

---

## Compliance Checklist (Multi-Cloud)

### Pre-Production Gate

- [ ] All namespaces labeled with data-classification and compliance
- [ ] mTLS STRICT enforced in all production namespaces
- [ ] No containers run as root in production
- [ ] All secrets in Vault or ESO — none in ConfigMaps/env vars
- [ ] Audit logging enabled on all K8s clusters (CloudTrail/GCP Audit/Azure Monitor)
- [ ] Immutable log storage configured (S3 Object Lock, GCS retention)
- [ ] MFA enabled on all cloud console accounts
- [ ] Network policies isolate CDE/PHI namespaces
- [ ] Vulnerability scanning in CI/CD pipeline (Trivy, Snyk)
- [ ] Penetration test scheduled for first 30 days of production

### Quarterly Review

- [ ] RBAC access review (remove unused bindings)
- [ ] Rotate all long-lived credentials
- [ ] Review Kyverno policy exception requests
- [ ] Update compliance evidence for audit
- [ ] Patch nodes and update base images
