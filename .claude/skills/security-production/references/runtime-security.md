# Runtime Security

## Falco: Cloud-Native Runtime Threat Detection

### Architecture

```
Falco (DaemonSet) → syscall events (eBPF driver or kernel module)
    ↓
Falco Rules Engine → matches rules against events
    ↓
Falco Alerts → stdout / webhook / gRPC / Falcosidekick
    ↓
Falcosidekick → Slack / PagerDuty / Elasticsearch / SIEM
```

### Critical Falco Rules

```yaml
# /etc/falco/rules.d/custom-rules.yaml

# --- Container Escape Attempts ---
- rule: Container Escape via Mount
  desc: Detect attempts to escape container via mount syscall
  condition: >
    spawned_process and container
    and proc.name in (mount, umount)
    and not proc.pname in (runc, containerd, docker)
  output: >
    Container escape via mount attempt
    (user=%user.name container=%container.name image=%container.image.repository:%container.image.tag
     cmd=%proc.cmdline pid=%proc.pid ppid=%proc.ppid parent=%proc.pname)
  priority: CRITICAL
  tags: [container, escape, MITRE_T1611]

- rule: Privileged Container Detected
  desc: Detect privileged container being started
  condition: >
    container_started
    and container.privileged=true
    and not (container.image.repository in (known_privileged_images))
  output: >
    Privileged container started (image=%container.image.repository:%container.image.tag
     container=%container.name pod=%k8s.pod.name ns=%k8s.ns.name)
  priority: CRITICAL
  tags: [container, privilege, CIS, MITRE_T1611]

# --- Privilege Escalation ---
- rule: Sudo or Setuid Execution
  desc: Detect execution of setuid/setgid binaries
  condition: >
    spawned_process and container
    and (proc.name = "sudo" or proc.name = "su"
         or proc.vpid != proc.pid)
  output: >
    Privilege escalation attempt (user=%user.name cmd=%proc.cmdline
     container=%container.name image=%container.image.repository)
  priority: WARNING
  tags: [privilege_escalation, MITRE_T1548]

- rule: Shell Spawned in Container
  desc: Detect shell spawned in running container (may indicate intrusion)
  condition: >
    spawned_process and container
    and shell_procs
    and not proc.pname in (docker, containerd, kubectl, runc, bash, sh)
    and not container.image.repository in (allowed_debug_images)
  output: >
    Shell spawned in container (user=%user.name shell=%proc.name parent=%proc.pname
     container=%container.name image=%container.image.repository cmd=%proc.cmdline)
  priority: WARNING
  tags: [shell, container, MITRE_T1059]

# --- Sensitive File Access ---
- rule: Read Sensitive File Untrusted
  desc: Access to sensitive files outside expected processes
  condition: >
    open_read and container
    and (fd.name startswith /etc/shadow
         or fd.name startswith /etc/sudoers
         or fd.name startswith /root/.ssh
         or fd.name startswith /proc/1/environ)
    and not proc.name in (known_readers)
  output: >
    Sensitive file read (user=%user.name file=%fd.name
     container=%container.name proc=%proc.name)
  priority: HIGH
  tags: [filesystem, MITRE_T1552]

# --- Network Anomalies ---
- rule: Unexpected Outbound Connection
  desc: Detect unexpected outbound network connection
  condition: >
    outbound and container
    and not (
      fd.port in (80, 443, 8080, 8443, 5432, 6379, 9090)
      or fd.sip in (trusted_cidr_ranges)
    )
    and container.image.repository not in (known_network_images)
  output: >
    Unexpected outbound connection (container=%container.name dst=%fd.rip:%fd.rport
     image=%container.image.repository proc=%proc.name)
  priority: WARNING
  tags: [network, anomaly, MITRE_T1071]

# --- Cryptocurrency Mining ---
- rule: Crypto Mining Process
  desc: Detect known cryptocurrency mining processes
  condition: >
    spawned_process and container
    and (proc.name in (xmrig, minergate, ethminer, nbminer, teamredminer)
         or proc.cmdline contains "stratum+tcp://"
         or proc.cmdline contains "mining.pool")
  output: >
    Cryptocurrency mining detected (container=%container.name
     proc=%proc.name cmd=%proc.cmdline image=%container.image.repository)
  priority: CRITICAL
  tags: [crypto_mining, MITRE_T1496]

# --- K8s API Abuse ---
- rule: K8s Serviceaccount Token Accessed
  desc: Detect access to serviceaccount tokens (lateral movement risk)
  condition: >
    open_read and container
    and fd.name startswith /var/run/secrets/kubernetes.io/serviceaccount/token
    and not proc.name in (known_k8s_sa_readers)
  output: >
    K8s ServiceAccount token accessed (user=%user.name container=%container.name
     proc=%proc.name image=%container.image.repository)
  priority: HIGH
  tags: [k8s, lateral_movement, MITRE_T1552]
```

### Falco Kubernetes Deployment

```yaml
# Install via Helm (eBPF driver — no kernel module needed)
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm install falco falcosecurity/falco \
  --namespace falco \
  --create-namespace \
  --set driver.kind=ebpf \
  --set falcosidekick.enabled=true \
  --set falcosidekick.config.slack.webhookurl="https://hooks.slack.com/..." \
  --set falcosidekick.config.pagerduty.routingkey="..." \
  --set falcosidekick.config.elasticsearch.hostport="elasticsearch:9200" \
  --set collectors.kubernetes.enabled=true \
  --set falco.json_output=true \
  --set falco.log_level=info \
  -f custom-falco-values.yaml
```

---

## Tetragon: eBPF Security Observability

### Tetragon TracingPolicy

```yaml
# Detect and kill processes accessing /etc/passwd from container
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: block-sensitive-file-access
spec:
  kprobes:
    - call: "security_file_open"
      syscall: false
      args:
        - index: 0
          type: "file"
      selectors:
        - matchArgs:
            - index: 0
              operator: "Postfix"
              values:
                - "/etc/shadow"
                - "/etc/sudoers"
          matchNamespaces:
            - namespace: Pid
              operator: NotIn
              values:
                - "host_ns"
          matchActions:
            - action: Sigkill    # Kill the process immediately
```

---

## seccomp: Custom Profile Development

### Profile Generation Workflow

```bash
# Step 1: Run app with trace profile (log all syscalls)
docker run --security-opt seccomp=unconfined \
  --name syscall-trace \
  myapp:latest

# Step 2: Extract used syscalls
strace -p $(docker inspect --format '{{.State.Pid}}' syscall-trace) \
  -e trace=all 2>&1 | grep -oP 'syscall: \K\w+' | sort -u

# Step 3: Generate profile with seccomp-gen
# https://github.com/genuinetools/bpfd
bpfd trace -p $(pgrep -f myapp) --interval 60

# Step 4: Use Security Profiles Operator (K8s)
# https://sigs.k8s.io/security-profiles-operator
```

### Security Profiles Operator

```yaml
# SeccompProfile CRD
apiVersion: security-profiles-operator.x-k8s.io/v1beta1
kind: SeccompProfile
metadata:
  name: payment-service-seccomp
  namespace: payments
spec:
  defaultAction: SCMP_ACT_ERRNO
  architectures: [SCMP_ARCH_X86_64]
  syscalls:
    - action: SCMP_ACT_ALLOW
      names:
        - accept4
        - bind
        - brk
        - clone
        - close
        - connect
        - epoll_pwait
        - exit_group
        - futex
        - getpid
        - ioctl
        - madvise
        - mmap
        - mprotect
        - munmap
        - nanosleep
        - openat
        - read
        - recvfrom
        - recvmsg
        - rt_sigaction
        - rt_sigprocmask
        - sendmsg
        - sendto
        - set_robust_list
        - set_tid_address
        - socket
        - stat
        - statx
        - tgkill
        - wait4
        - write
        - writev
---
# Reference the profile in pod
apiVersion: v1
kind: Pod
spec:
  securityContext:
    seccompProfile:
      type: Localhost
      localhostProfile: operator/payments/payment-service-seccomp.json
```

---

## Runtime Security Monitoring Stack

```yaml
# Falcosidekick → Elasticsearch → Grafana
services:
  falcosidekick:
    image: falcosecurity/falcosidekick:2.30.0
    environment:
      ELASTICSEARCH_HOSTPORT: elasticsearch:9200
      ELASTICSEARCH_INDEX: falco
      ELASTICSEARCH_TYPE: _doc
      SLACK_WEBHOOKURL: "${SLACK_WEBHOOK}"
      SLACK_MINIMUMPRIORITY: WARNING
      PAGERDUTY_ROUTINGKEY: "${PAGERDUTY_KEY}"
      PAGERDUTY_MINIMUMPRIORITY: CRITICAL
      PROMETHEUS_EXTRALABELS: "cluster=production"
```

---

## Detection Coverage (MITRE ATT&CK for Containers)

| MITRE Tactic | Technique | Falco Rule | Severity |
|-------------|-----------|-----------|---------|
| Initial Access | T1190 Exploit Public App | Shell in container | HIGH |
| Execution | T1059 Command Interpreter | Shell spawned | WARNING |
| Persistence | T1543 Create/Modify System Process | Cron modification | HIGH |
| Privilege Escalation | T1548 Abuse Elevation Control | sudo/setuid exec | WARNING |
| Defense Evasion | T1562 Impair Defenses | iptables modification | HIGH |
| Credential Access | T1552 Unsecured Credentials | SA token access | HIGH |
| Discovery | T1082 System Information | uname/hostname | INFO |
| Lateral Movement | T1210 Exploitation of Services | Unexpected outbound | WARNING |
| Collection | T1005 Data from Local System | Sensitive file read | HIGH |
| Exfiltration | T1041 Exfil Over C2 Channel | DNS tunneling | CRITICAL |
| Impact | T1496 Resource Hijacking | Crypto mining | CRITICAL |
| Impact | T1611 Escape to Host | Mount/privileged | CRITICAL |
