# Kubernetes Troubleshooting Guide

Systematic debugging workflows for every K8s failure mode.

---

## Diagnostic Decision Tree

```
Pod not running?
├── Pending → Check scheduling (resources, taints, affinity, PVC)
├── CrashLoopBackOff → Check logs, probes, OOM, entrypoint
├── ImagePullBackOff → Check image name, registry auth, pull secret
├── Init:Error → Check init container logs
├── Terminating (stuck) → Check finalizers, PDB, graceful shutdown
└── Running but unhealthy → Check readiness probe, service selector

Service not reachable?
├── No endpoints → Check selector matches pod labels
├── Connection refused → Check containerPort, targetPort match
├── Timeout → Check NetworkPolicy, firewall rules
├── 502/503 from Ingress → Check readiness probe, backend health
└── DNS not resolving → Check CoreDNS pods, service name format

Deployment not progressing?
├── Pods not created → Check RBAC, ResourceQuota, LimitRange
├── Rolling update stuck → Check PDB, maxUnavailable, resource limits
├── ReplicaSet not scaling → Check HPA metrics, metrics-server
└── OOMKilled → Increase memory limits, profile application
```

---

## Essential kubectl Debug Commands

### Pod Diagnostics

```bash
# Quick status overview
kubectl get pods -n <ns> -o wide --show-labels

# Detailed pod info (events, conditions, volumes)
kubectl describe pod <pod> -n <ns>

# Current logs
kubectl logs <pod> -n <ns> -c <container>

# Previous crash logs (critical for CrashLoopBackOff)
kubectl logs <pod> -n <ns> -c <container> --previous

# Follow logs in real-time
kubectl logs -f <pod> -n <ns> --all-containers=true

# Multi-pod log streaming by label
kubectl logs -l app=myapp -n <ns> --all-containers=true --prefix=true

# Ephemeral debug container (K8s 1.25+)
kubectl debug -it <pod> -n <ns> --image=busybox:1.36 --target=<container>

# Debug with full networking tools
kubectl debug -it <pod> -n <ns> --image=nicolaka/netshoot --target=<container>

# Copy pod for debugging (non-disruptive)
kubectl debug <pod> -n <ns> --copy-to=debug-pod --container=debug --image=busybox
```

### Event Analysis

```bash
# Namespace events sorted by time
kubectl get events -n <ns> --sort-by='.lastTimestamp'

# Watch events in real-time
kubectl get events -n <ns> --watch

# Filter warning events only
kubectl get events -n <ns> --field-selector type=Warning

# Cluster-wide events (admin)
kubectl get events -A --sort-by='.lastTimestamp' | head -50
```

### Resource Inspection

```bash
# Check resource usage vs limits
kubectl top pods -n <ns> --sort-by=memory
kubectl top nodes --sort-by=cpu

# Get pod YAML (see actual applied config)
kubectl get pod <pod> -n <ns> -o yaml

# Check container statuses
kubectl get pod <pod> -n <ns> -o jsonpath='{.status.containerStatuses[*].state}'

# Check last termination reason
kubectl get pod <pod> -n <ns> -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'
```

### Network Debugging

```bash
# Check service endpoints
kubectl get endpoints <service> -n <ns>

# DNS resolution test
kubectl run dns-test --rm -it --image=busybox:1.36 --restart=Never -- nslookup <service>.<ns>.svc.cluster.local

# TCP connectivity test
kubectl run net-test --rm -it --image=nicolaka/netshoot --restart=Never -- curl -v http://<service>.<ns>:port

# Check NetworkPolicy effect
kubectl get networkpolicy -n <ns> -o yaml

# Verify ingress controller health
kubectl get pods -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --tail=50
```

---

## Failure Resolution Playbooks

### CrashLoopBackOff

```
1. kubectl logs <pod> --previous          → Check application error
2. kubectl describe pod <pod>             → Check exit code
   - Exit 1: Application error (check code/config)
   - Exit 137: OOMKilled (increase memory limit)
   - Exit 139: Segfault (check binary/dependencies)
3. Check probes:
   - Liveness probe too aggressive? → Increase initialDelaySeconds
   - Startup probe missing? → Add startupProbe for slow-starting apps
4. Check ConfigMap/Secret mounts → Volume not found = crash
5. Check resource limits → CPU throttling can cause health check timeout
```

### ImagePullBackOff

```
1. kubectl describe pod <pod>  → Check exact image name + error
2. Verify image exists:
   - docker pull <image> (or crane digest <image>)
3. Check pull secret:
   kubectl get secret <pull-secret> -n <ns> -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d
4. Verify ServiceAccount has imagePullSecrets:
   kubectl get sa <sa-name> -n <ns> -o yaml
5. Private registry? Create pull secret:
   kubectl create secret docker-registry regcred \
     --docker-server=<registry> --docker-username=<user> --docker-password=<pass> -n <ns>
```

### Pending (Unschedulable)

```
1. kubectl describe pod <pod>   → Check events for reason
2. Insufficient resources?
   kubectl describe nodes | grep -A5 "Allocated resources"
3. Taint/toleration mismatch?
   kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints
4. Node affinity not matching?
   kubectl get nodes --show-labels | grep <required-label>
5. PVC not bound?
   kubectl get pvc -n <ns>
   kubectl describe pvc <pvc> -n <ns>
6. ResourceQuota exceeded?
   kubectl describe resourcequota -n <ns>
```

### OOMKilled

```
1. Confirm OOM:
   kubectl get pod <pod> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason}'
2. Check actual usage before kill:
   kubectl top pod <pod> -n <ns> --containers
3. Options:
   a. Increase memory limit (if app legitimately needs more)
   b. Fix memory leak (check heap dumps, profiling)
   c. Add JVM flags: -XX:MaxRAMPercentage=75.0 (for Java)
   d. Set memory request = limit (QoS Guaranteed, avoids node-level OOM)
4. Long-term: Set up VPA to right-size automatically
```

### RBAC 403 Forbidden

```
1. Check what's denied:
   kubectl auth can-i <verb> <resource> -n <ns> --as=<user>
2. List user's roles:
   kubectl get rolebindings,clusterrolebindings -A -o jsonpath='{range .items[?(@.subjects[0].name=="<user>")]}...'
3. Test with kubectl auth:
   kubectl auth can-i --list --as=<user> -n <ns>
4. Common fixes:
   - Missing RoleBinding (not just Role)
   - RoleBinding in wrong namespace
   - ServiceAccount name mismatch (system:serviceaccount:<ns>:<name>)
   - ClusterRole needed but only Role created
```

### NetworkPolicy Blocking Traffic

```
1. Verify policy exists:
   kubectl get networkpolicy -n <ns>
2. Check pod label matches policy selector:
   kubectl get pods -n <ns> --show-labels
   kubectl get networkpolicy <name> -n <ns> -o yaml | grep -A10 podSelector
3. Common DNS fix — must allow egress to kube-system:
   egress:
   - to:
     - namespaceSelector:
         matchLabels:
           kubernetes.io/metadata.name: kube-system
     ports:
     - protocol: UDP
       port: 53
4. Test connectivity:
   kubectl exec -it <pod> -n <ns> -- wget -qO- --timeout=2 http://<target-svc>.<target-ns>:port
```

### Ingress/Gateway 502/503

```
1. Check backend pods are Ready:
   kubectl get pods -n <ns> -l <app-label> -o wide
2. Check endpoints populated:
   kubectl get endpoints <service> -n <ns>
3. Check readiness probe is passing:
   kubectl describe pod <pod> -n <ns> | grep -A3 Readiness
4. Check ingress controller logs:
   kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --tail=100
5. Verify service port matches:
   kubectl get svc <service> -n <ns> -o yaml | grep -A5 ports
```

### HPA Not Scaling

```
1. Check HPA status:
   kubectl get hpa -n <ns>
   kubectl describe hpa <name> -n <ns>
2. Verify metrics-server running:
   kubectl get pods -n kube-system -l k8s-app=metrics-server
   kubectl top pods -n <ns>
3. Check if custom metrics available:
   kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1 | jq
4. Common issues:
   - resource requests not set (HPA needs requests to calculate %)
   - metrics-server not installed
   - KEDA scaler misconfigured
```

### ArgoCD Sync Failed

```
1. Check sync status:
   argocd app get <app-name>
2. Check diff:
   argocd app diff <app-name>
3. Common causes:
   - Schema validation error → check CRD installed
   - RBAC → ArgoCD SA missing permissions
   - Namespace doesn't exist → add CreateNamespace=true
   - Resource hooks failing → check hook pod logs
4. Force sync (careful):
   argocd app sync <app-name> --force
```

---

## Node-Level Debugging

```bash
# SSH or debug node
kubectl debug node/<node-name> -it --image=busybox

# Check kubelet logs
journalctl -u kubelet --since "10 minutes ago" --no-pager

# Check container runtime
crictl ps -a                    # List all containers
crictl logs <container-id>      # Container logs
crictl inspect <container-id>   # Container details

# Check disk pressure
df -h /var/lib/kubelet
df -h /var/lib/containerd

# Check system resources
top -bn1 | head -20
free -h
```

---

## Monitoring-Based Debugging

### Prometheus Queries for Troubleshooting

```promql
# Pods restarting frequently
increase(kube_pod_container_status_restarts_total[1h]) > 3

# Pods in non-ready state
kube_pod_status_ready{condition="false"} == 1

# Containers being OOMKilled
increase(kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}[1h]) > 0

# CPU throttling
rate(container_cpu_cfs_throttled_periods_total[5m]) / rate(container_cpu_cfs_periods_total[5m]) > 0.5

# Nodes not ready
kube_node_status_condition{condition="Ready",status="true"} == 0

# PVC near capacity
kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes > 0.85

# High error rate by service
sum(rate(http_requests_total{code=~"5.."}[5m])) by (service)
/ sum(rate(http_requests_total[5m])) by (service) > 0.01
```

### Grafana Alert Queries

```yaml
# Pod restart alert
- alert: PodCrashLooping
  expr: increase(kube_pod_container_status_restarts_total[1h]) > 5
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Pod {{ $labels.pod }} restarting frequently"

# Node disk pressure
- alert: NodeDiskPressure
  expr: kube_node_status_condition{condition="DiskPressure",status="true"} == 1
  for: 5m
  labels:
    severity: critical
```

---

## Quick Reference: Exit Codes

| Exit Code | Meaning | Action |
|-----------|---------|--------|
| 0 | Success (but pod restarting) | Check restartPolicy, liveness probe |
| 1 | Application error | Check logs for stack trace |
| 126 | Permission denied | Check file permissions, securityContext |
| 127 | Command not found | Check image, entrypoint, PATH |
| 128 | Invalid exit argument | Check entrypoint script |
| 137 | SIGKILL (OOMKilled or preStop timeout) | Check memory limits or terminationGracePeriod |
| 139 | SIGSEGV (segfault) | Check binary compatibility, native deps |
| 143 | SIGTERM (graceful shutdown) | Normal during rolling update |

---

## Quick Reference: Pod Conditions

| Condition | Meaning | Debug |
|-----------|---------|-------|
| PodScheduled=False | Can't find a node | Check resources, taints, affinity |
| Initialized=False | Init containers failing | Check init container logs |
| ContainersReady=False | Readiness probe failing | Check probe config, app health |
| Ready=False | Pod not serving traffic | Check all above + readinessGates |

