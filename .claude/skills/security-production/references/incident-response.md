# Incident Response

## Incident Severity Classification

| Severity | Definition | Response Time | Example |
|----------|-----------|--------------|---------|
| **P0 — Critical** | Active breach, data exfiltration, RCE in prod | Immediate (< 15 min) | Container escape, credential theft |
| **P1 — High** | Suspicious lateral movement, privilege escalation | 1 hour | Unexpected cluster-admin access |
| **P2 — Medium** | Policy violation, failed attack attempt | 4 hours | Trivy finds CRITICAL CVE in prod |
| **P3 — Low** | Informational, audit finding | 24 hours | Kyverno warn on namespace |

---

## Incident Response Runbooks

### Runbook: Container Escape Detected

```markdown
# IR-001: Container Escape Detected
Trigger: Falco alert "Container Escape via Mount" or "Privileged Container"

## Immediate Response (0-15 min)
1. ISOLATE: Cordon the affected node
   kubectl cordon <node-name>

2. CAPTURE: Take snapshot before killing pod
   kubectl exec -it <pod> -- ps aux > /tmp/incident-$DATE/procs.txt
   kubectl exec -it <pod> -- netstat -antp > /tmp/incident-$DATE/netstat.txt
   kubectl exec -it <pod> -- find / -newer /tmp -type f 2>/dev/null > /tmp/incident-$DATE/modified.txt

3. KILL: Delete the compromised pod
   kubectl delete pod <pod-name> --force --grace-period=0

4. CONTAIN: Block all traffic from the node
   kubectl label node <node-name> network-policy=quarantine

## Investigation (15 min - 4 hours)
5. Collect K8s audit logs for the affected pod's SA
   kubectl logs -n kube-system kube-apiserver-* | grep <service-account>

6. Check for lateral movement
   - Review SA token usage across namespaces
   - Check for new ClusterRoleBindings created in last 24h
   kubectl get clusterrolebindings --sort-by=.metadata.creationTimestamp | tail -20

7. Collect Falco events for timeline
   kubectl logs -n falco daemonset/falco | grep <container-name>

8. Check for persistence mechanisms
   kubectl get jobs,cronjobs --all-namespaces --sort-by=.metadata.creationTimestamp | tail -20
   kubectl get serviceaccounts --all-namespaces | grep -v default

## Remediation
9. Rotate credentials
   - Revoke affected ServiceAccount tokens
   - Rotate any cloud credentials the pod may have accessed
   - Rotate database credentials if DB was accessible

10. Patch the vulnerability
    - Update base image
    - Fix misconfiguration (add PSS Restricted, remove privileged flag)
    - Deploy Kyverno policy to prevent recurrence

## Post-Incident
11. Write PIR (Post-Incident Review) within 48 hours
12. Update Falco rules if detection could be improved
13. File compliance incident report (HIPAA/PCI if data was exposed)
```

### Runbook: Credential Exfiltration Detected

```markdown
# IR-002: Credentials Found in Logs/Secrets

## Immediate Response
1. Identify scope: what credentials, where used
   # Search logs for credential patterns
   kubectl logs --all-containers=true -l app=<service> | \
     grep -E "(password|token|key|secret)=[^&\s]+"

2. Rotate ALL potentially exposed credentials immediately
   # AWS: rotate access key
   aws iam create-access-key --user-name <username>
   aws iam delete-access-key --access-key-id OLD_KEY --user-name <username>

   # K8s ServiceAccount token: delete and recreate
   kubectl delete secret <sa-token-secret> -n <namespace>

   # Database password: use Vault dynamic credentials
   vault write -force database/rotate-root/payment-db

3. Revoke active sessions using old credentials
   aws sts get-caller-identity  # Identify active sessions
   # aws iam delete-login-profile etc. as appropriate

## Investigation
4. Check CloudTrail/audit log for API calls made with compromised credentials
5. Determine blast radius (what resources were accessible)
6. Timeline reconstruction from audit logs

## Remediation
7. Remove hardcoded credentials (git history cleanup with git-filter-repo)
8. Implement ESO/Vault for proper secrets management
9. Add detect-secrets pre-commit hook
10. Run GitLeaks on all repositories
```

---

## SIEM Integration

### Wazuh Architecture for K8s

```yaml
# wazuh-agent-daemonset.yaml — runs on every node
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: wazuh-agent
  namespace: security
spec:
  selector:
    matchLabels:
      app: wazuh-agent
  template:
    metadata:
      labels:
        app: wazuh-agent
    spec:
      hostPID: true          # Required for process monitoring
      hostNetwork: true      # Required for network monitoring
      tolerations:
        - effect: NoSchedule
          operator: Exists
      volumes:
        - name: var-log
          hostPath: {path: /var/log}
        - name: proc
          hostPath: {path: /proc}
        - name: ossec
          hostPath: {path: /var/ossec}
      containers:
        - name: wazuh-agent
          image: wazuh/wazuh-agent:4.9.0
          securityContext:
            privileged: true   # Required for Wazuh (document exception)
          env:
            - name: WAZUH_MANAGER
              value: "wazuh-manager.security.svc.cluster.local"
            - name: WAZUH_AGENT_GROUP
              value: "kubernetes-nodes"
          volumeMounts:
            - mountPath: /var/log
              name: var-log
            - mountPath: /proc
              name: proc
```

### Falco → Elasticsearch Pipeline

```yaml
# falcosidekick → elasticsearch → Kibana alerts
falcosidekick:
  config:
    elasticsearch:
      hostport: "elasticsearch.monitoring.svc:9200"
      index: "falco"
      type: "_doc"
      minimumpriority: "warning"
      mutualtls: true
      checkcert: true
      username: "falco-writer"
      password: "${ELASTIC_PASSWORD}"

# Kibana alert rule: CRITICAL Falco events → PagerDuty
POST /_watcher/watch/falco-critical-alert
{
  "trigger": {
    "schedule": {"interval": "1m"}
  },
  "input": {
    "search": {
      "request": {
        "indices": ["falco-*"],
        "body": {
          "query": {
            "bool": {
              "filter": [
                {"term": {"priority": "CRITICAL"}},
                {"range": {"@timestamp": {"gte": "now-1m"}}}
              ]
            }
          }
        }
      }
    }
  },
  "condition": {
    "compare": {"ctx.payload.hits.total": {"gt": 0}}
  },
  "actions": {
    "notify-pagerduty": {
      "webhook": {
        "scheme": "https",
        "host": "events.pagerduty.com",
        "port": 443,
        "method": "post",
        "path": "/v2/enqueue",
        "headers": {"Content-Type": "application/json"},
        "body": "{\"routing_key\": \"${PAGERDUTY_KEY}\", \"event_action\": \"trigger\", \"payload\": {\"summary\": \"CRITICAL Falco Security Alert\", \"severity\": \"critical\"}}"
      }
    }
  }
}
```

---

## Forensics Checklist

```bash
# CRITICAL: Capture before killing compromised pod
INCIDENT_DIR="/tmp/incident-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${INCIDENT_DIR}"

POD_NAME="compromised-pod-name"
NAMESPACE="production"

# 1. Process list
kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- ps auxf > "${INCIDENT_DIR}/processes.txt" 2>&1

# 2. Open network connections
kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- ss -antp > "${INCIDENT_DIR}/network.txt" 2>&1

# 3. Environment variables (check for leaked secrets)
kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- env > "${INCIDENT_DIR}/env.txt" 2>&1

# 4. Modified files
kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- find / -newer /etc/hostname -type f 2>/dev/null > "${INCIDENT_DIR}/modified-files.txt"

# 5. Mounted volumes
kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- mount > "${INCIDENT_DIR}/mounts.txt" 2>&1

# 6. Loaded kernel modules (if not distroless)
kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- lsmod > "${INCIDENT_DIR}/kernel-modules.txt" 2>&1

# 7. K8s audit events for this SA
SA_NAME=$(kubectl get pod -n "${NAMESPACE}" "${POD_NAME}" -o jsonpath='{.spec.serviceAccountName}')
kubectl get events -n "${NAMESPACE}" --field-selector reason=Evicted > "${INCIDENT_DIR}/k8s-events.txt"

# 8. Container image for offline analysis
CONTAINER_IMAGE=$(kubectl get pod -n "${NAMESPACE}" "${POD_NAME}" -o jsonpath='{.spec.containers[0].image}')
docker pull "${CONTAINER_IMAGE}"
docker save "${CONTAINER_IMAGE}" | gzip > "${INCIDENT_DIR}/image.tar.gz"

echo "Forensics data collected in ${INCIDENT_DIR}/"
```

---

## Alert Response Matrix

| Alert | Source | Auto-Response | Manual Action |
|-------|--------|--------------|--------------|
| Container escape | Falco | Cordon node | IR-001 runbook |
| Crypto mining | Falco | Kill pod | Investigate image |
| Credential in log | GitLeaks/detect-secrets | Block PR | Rotate, audit |
| CRITICAL CVE in prod | Trivy/Grype | Create Jira P1 | Patch within 24h |
| Cluster-admin granted | K8s audit | Alert SIEM | Review immediately |
| Failed policy (OPA) | Gatekeeper | Reject + log | Review in 4h |
| Unexpected outbound | Falco/Cilium | Log | Investigate src |
| SA token rotation fail | cert-manager | Alert | Manual rotation |
