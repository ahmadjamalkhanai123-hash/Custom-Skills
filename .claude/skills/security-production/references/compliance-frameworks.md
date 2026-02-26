# Compliance Frameworks

## SOC 2 Type II

### Trust Service Criteria (TSC) for Cloud-Native

| Criteria | Control | K8s Implementation |
|----------|---------|-------------------|
| CC6.1 Logical access | RBAC least-privilege | ClusterRole + RoleBinding |
| CC6.2 Authentication | MFA + OIDC | OIDC integration + MFA enforcement |
| CC6.3 Authorization | PSS Restricted | PodSecurity admission |
| CC6.6 Network segmentation | Zero-trust networking | NetworkPolicy + Istio |
| CC6.7 Encrypt data in transit | TLS 1.3 everywhere | Istio mTLS + cert-manager |
| CC6.8 Detect unauthorized | Runtime detection | Falco + SIEM |
| CC7.1 System monitoring | Full observability | Prometheus + Grafana + alerts |
| CC7.2 Anomaly detection | Behavioral analysis | Falco + ML-based detection |
| CC7.3 Security events | Audit trail | K8s audit log + SIEM |
| CC8.1 Change management | GitOps + approval | ArgoCD + GitHub PR review |
| A1.1 Availability monitoring | SLO/SLA tracking | Prometheus SLO alerts |
| A1.2 Backups | Velero + tested restores | Velero DailySchedule |
| PI1.1 Data processing integrity | Input validation + checksums | Admission webhooks |
| C1.1 Confidentiality | Encryption at rest + transit | KMS + TLS |

### SOC 2 Evidence Collection

```bash
# Automated evidence collection script
#!/bin/bash
EVIDENCE_DIR="soc2-evidence-$(date +%Y%m)"

# CC6.1 — RBAC configuration
kubectl get clusterroles,clusterrolebindings -o yaml > "${EVIDENCE_DIR}/rbac-config.yaml"
kubectl get roles,rolebindings --all-namespaces -o yaml >> "${EVIDENCE_DIR}/rbac-config.yaml"

# CC6.3 — Pod Security Standards
kubectl get namespaces -o yaml | grep -A5 "pod-security" > "${EVIDENCE_DIR}/pss-config.yaml"

# CC6.6 — NetworkPolicies
kubectl get networkpolicies --all-namespaces -o yaml > "${EVIDENCE_DIR}/netpol-config.yaml"

# CC7.3 — Audit log sample
kubectl logs -n kube-system kube-apiserver-* | head -1000 > "${EVIDENCE_DIR}/audit-sample.log"

# CIS Benchmark scan
kubectl apply -f kube-bench-job.yaml
kubectl logs -l app=kube-bench > "${EVIDENCE_DIR}/kube-bench-report.txt"

echo "Evidence collected in ${EVIDENCE_DIR}/"
```

---

## HIPAA Technical Safeguards (45 CFR § 164.312)

### Control Implementation Map

| HIPAA Control | § Reference | K8s Control |
|--------------|------------|-------------|
| Access control | 164.312(a)(1) | RBAC + OIDC + MFA |
| Automatic logoff | 164.312(a)(2)(iii) | Session timeout in apps |
| Encryption/decryption | 164.312(a)(2)(iv) | TLS 1.3 + KMS encryption at rest |
| Audit controls | 164.312(b) | K8s audit log + Falco + SIEM |
| Integrity | 164.312(c)(1) | Cosign image signing + admission |
| Transmission security | 164.312(e)(1) | mTLS (Istio STRICT) + TLS 1.3 |
| Person authentication | 164.312(d) | OIDC + MFA |

### HIPAA-Specific Controls

```yaml
# PHI namespace: extra controls
apiVersion: v1
kind: Namespace
metadata:
  name: phi-processing
  labels:
    pod-security.kubernetes.io/enforce: restricted
    compliance: hipaa
    data-classification: phi
---
# PHI NetworkPolicy: extreme isolation
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: phi-strict-isolation
  namespace: phi-processing
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              compliance: hipaa
              approved-phi-access: "true"
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              compliance: hipaa
    - ports:           # DNS only external
        - port: 53
          protocol: UDP
```

### HIPAA Breach Notification Automation

```python
# breach_detection.py — integrate with Falco webhook
from datetime import datetime
import json

HIPAA_DATA_INDICATORS = [
    "ssn", "dob", "medical_record", "diagnosis",
    "treatment", "patient_id", "phi", "health_record"
]

def assess_breach_severity(falco_event: dict) -> dict:
    """Assess if Falco event constitutes HIPAA breach."""
    event_output = falco_event.get("output", "").lower()
    is_phi_related = any(ind in event_output for ind in HIPAA_DATA_INDICATORS)

    severity = "LOW"
    notification_required = False

    if falco_event["priority"] == "CRITICAL" and is_phi_related:
        severity = "CRITICAL"
        notification_required = True  # 60-day notification window starts
    elif falco_event["priority"] in ("ERROR", "WARNING") and is_phi_related:
        severity = "HIGH"
        notification_required = True

    return {
        "breach_detected": notification_required,
        "severity": severity,
        "phi_involved": is_phi_related,
        "detection_time": datetime.utcnow().isoformat(),
        "notification_deadline": None if not notification_required else "60 days",
        "falco_rule": falco_event.get("rule"),
        "container": falco_event.get("output_fields", {}).get("container.name"),
    }
```

---

## PCI-DSS v4 (Payment Card Industry)

### Applicable Requirements for K8s

| PCI Req | Title | K8s Control |
|---------|-------|-------------|
| 1.3 | Network access controls | NetworkPolicy + Firewall rules |
| 2.2 | Secure configurations | CIS Benchmark + Kyverno enforce |
| 3.5 | Primary Account Number protection | Field-level encryption + tokenization |
| 4.2 | Strong cryptography in transit | TLS 1.2+ (1.3 preferred) |
| 5.3 | Anti-malware | Falco + runtime protection |
| 6.4 | Web-facing app protection | WAF + OWASP controls |
| 7.2 | Least privilege access | RBAC + periodic review |
| 8.3 | Strong authentication | MFA for all users |
| 10.2 | Audit log implementation | K8s audit + Falco → SIEM |
| 10.5 | Audit log protection | Immutable log storage |
| 11.3 | External and internal pen testing | Annual pen test + quarterly scans |
| 12.3 | Targeted risk analysis | Threat modeling per service |

### PCI DSS Network Segmentation

```yaml
# Cardholder Data Environment (CDE) namespace: maximum isolation
apiVersion: v1
kind: Namespace
metadata:
  name: cde-payment
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pci-scope: "in-scope"
    data-classification: cardholder-data
---
# CDE: only accept traffic from payment-gateway
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: cde-isolation
  namespace: cde-payment
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              pci-scope: "payment-gateway"
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              pci-scope: "payment-processor"
    - ports:
        - port: 53
          protocol: UDP    # DNS
---
# PCI DSS Req 10.5: Immutable audit logs
# Use S3 Object Lock (WORM) or equivalent
# AWS: aws s3api put-object-lock-configuration
# --object-lock-configuration Mode=COMPLIANCE,Rule={...}
```

---

## FedRAMP / NIST 800-53 Rev5

### High-Impact Control Families

| Family | Controls | K8s Implementation |
|--------|---------|-------------------|
| **AC** Access Control | AC-2, AC-3, AC-6, AC-17 | RBAC + OIDC + VPN access |
| **AU** Audit & Accountability | AU-2, AU-3, AU-9, AU-12 | K8s audit + Falco + SIEM |
| **CM** Config Management | CM-2, CM-6, CM-7, CM-8 | GitOps + Kyverno + SBOM |
| **IA** Identification & Auth | IA-2, IA-5, IA-8 | OIDC + MFA + SPIFFE |
| **IR** Incident Response | IR-4, IR-5, IR-6 | Runbooks + SIEM + PagerDuty |
| **RA** Risk Assessment | RA-5 | Vulnerability scanning (Trivy) |
| **SC** System & Comms Protection | SC-5, SC-7, SC-8, SC-12 | mTLS + NetworkPolicy + KMS |
| **SI** System & Info Integrity | SI-2, SI-3, SI-10 | Patch management + Falco |

### FIPS 140-2 Compliance

```bash
# Use FIPS-validated base images
# Red Hat UBI (FIPS): registry.access.redhat.com/ubi9/ubi:latest
# or Ubuntu FIPS: ubuntu.com/security/fips

# Enable FIPS mode in Go application
# Build with GOFLAGS=-tags=boringcrypto
go build -tags=boringcrypto -o app ./cmd/app

# Verify FIPS mode active
openssl version -f | grep -i "fips"

# Kubernetes cluster on FIPS-enabled nodes (EKS):
# eksctl create cluster --with-oidc --managed --node-fips-enabled
```

---

## CIS Kubernetes Benchmark L2

### Critical CIS Controls

```bash
# CIS 1.1.1: Ensure API server pod spec file permissions
chmod 600 /etc/kubernetes/manifests/kube-apiserver.yaml

# CIS 1.1.11: Ensure etcd data directory permissions
chmod 700 /var/lib/etcd

# CIS 1.2.1: Ensure anonymous-auth is set to false
kube-apiserver --anonymous-auth=false

# CIS 1.2.6: Ensure insecure-port is disabled (default in K8s 1.24+)
# No --insecure-port flag needed

# CIS 1.3.2: Ensure profiling is disabled (scheduler)
kube-scheduler --profiling=false

# CIS 4.2.6: Ensure kubelet protectKernelDefaults is set
# kubelet config:
protectKernelDefaults: true

# CIS 5.2.1: Ensure privileged containers are not admitted
# → Use PSS/PSA Restricted profile

# Automated check with kube-bench
kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job.yaml
kubectl wait --for=condition=complete job/kube-bench --timeout=60s
kubectl logs -l app=kube-bench
```

---

## Compliance Control Matrix

| Control Domain | SOC 2 CC | HIPAA | PCI-DSS | FedRAMP |
|---------------|---------|-------|---------|---------|
| Identity & Access | CC6.1-6.3 | 164.312(a) | Req 7, 8 | AC-2, AC-3 |
| Encryption in Transit | CC6.7 | 164.312(e) | Req 4.2 | SC-8 |
| Encryption at Rest | CC6.7 | 164.312(a)(2)(iv) | Req 3.5 | SC-28 |
| Audit Logging | CC7.3 | 164.312(b) | Req 10 | AU-2, AU-12 |
| Vulnerability Mgmt | CC7.1 | - | Req 6, 11 | RA-5, SI-2 |
| Incident Response | CC7.4 | Breach notification | Req 12.10 | IR-4, IR-6 |
| Change Management | CC8.1 | - | Req 6.5 | CM-3, CM-6 |
| Network Security | CC6.6 | 164.312(e) | Req 1, 4 | SC-7 |
| System Monitoring | CC7.2 | - | Req 10.6 | SI-4 |
| Data Integrity | PI1.1 | 164.312(c) | Req 6.4 | SI-10 |
