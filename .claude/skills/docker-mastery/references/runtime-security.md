# Runtime Security

Deep-dive into Linux kernel primitives, mandatory access control, runtime
monitoring, and alternative runtimes that harden Docker containers in production.

---

## Container Isolation

Docker containers are isolated using Linux kernel namespaces and cgroups. Understanding
these primitives is essential for evaluating what containers actually protect against.

### Linux Namespaces

Each container gets its own set of namespaces, providing process-level isolation:

| Namespace | Flag            | What It Isolates                              |
|-----------|-----------------|-----------------------------------------------|
| PID       | `CLONE_NEWPID`  | Process IDs -- container sees only its own PIDs |
| Network   | `CLONE_NEWNET`  | Network interfaces, routing tables, iptables  |
| Mount     | `CLONE_NEWNS`   | Filesystem mount points                       |
| UTS       | `CLONE_NEWUTS`  | Hostname and domain name                      |
| IPC       | `CLONE_NEWIPC`  | System V IPC, POSIX message queues            |
| User      | `CLONE_NEWUSER` | UID/GID mappings (host root != container root)|

```bash
# Inspect namespaces for a running container
docker inspect --format '{{.State.Pid}}' mycontainer
ls -la /proc/<PID>/ns/

# Run container with host PID namespace (debugging only, never in production)
docker run --pid=host --rm alpine ps aux
```

### Cgroups v2

Cgroups v2 (unified hierarchy) enforces resource limits and prevents a single container
from starving the host or other containers.

```bash
# Set CPU limit to 1.5 cores and memory to 512MB
docker run --cpus=1.5 --memory=512m --memory-swap=512m myapp:latest

# Set CPU quota directly using cgroup v2 parameters
docker run --cpu-quota=150000 --cpu-period=100000 myapp:latest

# Assign container to a custom cgroup parent
docker run --cgroup-parent=/myapp myapp:latest

# Verify cgroup limits inside a running container
docker exec mycontainer cat /sys/fs/cgroup/cpu.max
docker exec mycontainer cat /sys/fs/cgroup/memory.max
```

Key cgroup v2 controllers and their files:

| Controller | File          | Example Value | Meaning                        |
|------------|---------------|---------------|--------------------------------|
| cpu        | `cpu.max`     | `150000 100000` | 1.5 CPU cores (quota/period) |
| memory     | `memory.max`  | `536870912`   | 512MB hard limit               |
| memory     | `memory.high` | `402653184`   | 384MB soft limit (throttle)    |
| io         | `io.max`      | `8:0 rbps=10485760` | 10MB/s read on device 8:0 |
| pids       | `pids.max`    | `256`         | Maximum 256 processes          |

---

## Seccomp Profiles

Seccomp (Secure Computing Mode) filters which Linux syscalls a container process can
invoke. Docker applies a default profile that blocks approximately 44 dangerous syscalls.

### Default Profile Behavior

Docker's default seccomp profile blocks syscalls including `reboot`, `kexec_load`,
`mount`, `umount`, `swapon`, `swapoff`, `pivot_root`, `keyctl`, `ptrace`, `acct`,
`settimeofday`, `clock_settime`, `add_key`, and others that could compromise the host.

```bash
# Explicitly apply the default profile
docker run --security-opt seccomp=default myapp:latest

# Disable seccomp entirely (dangerous, for debugging only)
docker run --security-opt seccomp=unconfined myapp:latest
```

### Custom Seccomp Profiles

Create a JSON profile that whitelists only the syscalls your application needs:

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"],
  "syscalls": [
    {
      "names": [
        "read", "write", "openat", "close", "fstat", "lseek",
        "mmap", "mprotect", "munmap", "brk", "rt_sigaction",
        "rt_sigprocmask", "ioctl", "pread64", "pwrite64",
        "readv", "writev", "access", "pipe", "select",
        "sched_yield", "mremap", "msync", "madvise",
        "socket", "connect", "accept", "sendto", "recvfrom",
        "bind", "listen", "getsockname", "getpeername",
        "setsockopt", "getsockopt", "clone", "execve",
        "exit", "exit_group", "wait4", "kill", "uname",
        "fcntl", "flock", "futex", "epoll_create1",
        "epoll_ctl", "epoll_wait", "epoll_pwait",
        "getrandom", "statx", "clock_gettime"
      ],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

```bash
# Apply the custom profile
docker run --security-opt seccomp=custom-seccomp.json myapp:latest

# Debug seccomp denials using strace (run outside the container)
strace -f -e trace=all -p $(docker inspect --format '{{.State.Pid}}' mycontainer) 2>&1 | grep EPERM

# Generate a profile from actual container usage with oci-seccomp-bpf-hook
sudo docker run --annotation io.containers.trace-syscall=of:/tmp/profile.json myapp:latest
```

---

## AppArmor Profiles

AppArmor is a Linux Security Module that confines programs by restricting their access
to files, network, and capabilities based on per-program profiles.

### Default Docker Profile

Docker automatically applies the `docker-default` AppArmor profile, which blocks
writing to `/proc`, `/sys`, and mounting filesystems inside the container.

```bash
# Check if AppArmor is active on the host
sudo aa-status

# Run with the default profile explicitly
docker run --security-opt apparmor=docker-default myapp:latest

# Disable AppArmor for a container (debugging only)
docker run --security-opt apparmor=unconfined myapp:latest
```

### Custom AppArmor Profile

```
#include <tunables/global>

profile docker-myapp flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>

  # Deny all network access except TCP
  network inet tcp,
  deny network raw,
  deny network packet,

  # Allow read-only access to application files
  /app/** r,
  /app/bin/myapp ix,

  # Allow writes only to /tmp and /var/log/app
  /tmp/** rw,
  /var/log/app/** rw,

  # Deny access to sensitive host paths
  deny /etc/shadow r,
  deny /etc/passwd w,
  deny /proc/*/mem rw,
  deny /sys/** w,
}
```

```bash
# Load the profile
sudo apparmor_parser -r /etc/apparmor.d/docker-myapp

# Run with the custom profile
docker run --security-opt apparmor=docker-myapp myapp:latest

# Inspect which profile a running container uses
docker inspect --format '{{.AppArmorProfile}}' mycontainer
```

---

## Linux Capabilities

Linux divides root privileges into distinct capabilities. Docker grants a default
subset, but production containers should drop all and add back only what is needed.

### Default Docker Capabilities

Docker grants these 14 capabilities by default: `AUDIT_WRITE`, `CHOWN`, `DAC_OVERRIDE`,
`FOWNER`, `FSETID`, `KILL`, `MKNOD`, `NET_BIND_SERVICE`, `NET_RAW`, `SETFCAP`,
`SETGID`, `SETPCAP`, `SETUID`, `SYS_CHROOT`.

```bash
# Drop ALL capabilities, add back only what is needed
docker run --cap-drop ALL --cap-add NET_BIND_SERVICE myapp:latest

# List capabilities inside a running container
docker exec mycontainer cat /proc/1/status | grep Cap
# Decode capability hex with capsh
capsh --decode=00000000a80425fb
```

### Minimum Capabilities Per Use Case

| Use Case               | Required Capabilities                  | Notes                                |
|------------------------|----------------------------------------|--------------------------------------|
| Static binary / worker | (none -- `--cap-drop ALL`)             | No special privileges needed         |
| Web server (port < 1024) | `NET_BIND_SERVICE`                   | Bind to ports 80, 443               |
| Health check with ping | `NET_RAW`                              | Raw sockets for ICMP                 |
| File processing        | `CHOWN`, `DAC_OVERRIDE`               | Change file ownership/permissions    |
| Container orchestrator | `SYS_ADMIN`, `NET_ADMIN`              | Dangerous -- use only if unavoidable |
| Logging agent          | `DAC_READ_SEARCH`                     | Read files regardless of permissions |
| Network debugging      | `NET_ADMIN`, `NET_RAW`                | Manipulate routing, raw packets      |
| Time sync (NTP)        | `SYS_TIME`                            | Set system clock                     |

### Why `--privileged` Is Dangerous

```bash
# NEVER use --privileged in production
# It grants ALL capabilities, disables seccomp, disables AppArmor,
# and gives full access to host devices under /dev
docker run --privileged myapp:latest   # DO NOT DO THIS

# What --privileged actually does (equivalent):
docker run \
  --cap-add ALL \
  --security-opt seccomp=unconfined \
  --security-opt apparmor=unconfined \
  --device /dev \
  --pid host \
  myapp:latest
```

A privileged container can load kernel modules, mount the host filesystem, and
escape to the host trivially. There is no legitimate production use case that
cannot be solved with specific capabilities instead.

---

## Falco Runtime Monitoring

Falco (by Sysdig/CNCF) detects anomalous runtime behavior by monitoring syscalls
via eBPF or a kernel module.

### Installation as DaemonSet

```bash
# Add Falco Helm repo
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm repo update

# Install Falco with eBPF driver (preferred over kernel module)
helm install falco falcosecurity/falco \
  --namespace falco --create-namespace \
  --set driver.kind=ebpf \
  --set falcosidekick.enabled=true \
  --set falcosidekick.config.slack.webhookurl=https://hooks.slack.com/services/XXX
```

### Custom Rules for Docker

```yaml
# /etc/falco/falco_rules.local.yaml

- rule: Shell Spawned in Container
  desc: Detect interactive shell in a running container
  condition: >
    spawned_process and container and
    proc.name in (bash, sh, zsh, dash, ash) and
    proc.pname != entrypoint.sh
  output: "Shell spawned in container (user=%user.name command=%proc.cmdline container=%container.name image=%container.image.repository)"
  priority: WARNING

- rule: Sensitive File Read in Container
  desc: Detect reads of sensitive files like /etc/shadow
  condition: >
    open_read and container and
    fd.name in (/etc/shadow, /etc/sudoers, /root/.ssh/authorized_keys, /root/.bash_history)
  output: "Sensitive file read (file=%fd.name user=%user.name container=%container.name)"
  priority: CRITICAL

- rule: Unexpected Outbound Connection
  desc: Detect outbound connections to non-approved IPs
  condition: >
    outbound and container and
    not fd.sip in (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
  output: "Unexpected outbound connection (command=%proc.cmdline connection=%fd.name container=%container.name)"
  priority: NOTICE
```

### Alert Channels (falco.yaml)

```yaml
# falcosidekick configuration for multiple alert channels
falcosidekick:
  config:
    slack:
      webhookurl: "https://hooks.slack.com/services/T00/B00/XXXX"
      minimumpriority: "warning"
    pagerduty:
      routingkey: "your-pagerduty-routing-key"
      minimumpriority: "critical"
    elasticsearch:
      hostport: "http://elasticsearch:9200"
      index: "falco"
      minimumpriority: "notice"
```

---

## gVisor (runsc)

gVisor interposes a user-space kernel between the container and the host kernel,
intercepting and reimplementing syscalls. This provides a strong isolation boundary
for untrusted workloads.

### Installation and Configuration

```bash
# Install gVisor runtime
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" | sudo tee /etc/apt/sources.list.d/gvisor.list
sudo apt-get update && sudo apt-get install -y runsc

# Register gVisor as a Docker runtime
sudo runsc install
sudo systemctl restart docker

# Run a container with gVisor
docker run --runtime=runsc nginx:alpine

# Set gVisor as the default runtime in /etc/docker/daemon.json
# { "default-runtime": "runsc", "runtimes": { "runsc": { "path": "/usr/bin/runsc" } } }
```

### Performance Tradeoffs

| Aspect              | Native (runc) | gVisor (runsc) | Impact                          |
|---------------------|---------------|----------------|----------------------------------|
| Syscall latency     | ~100ns        | ~10us          | 100x overhead per syscall        |
| Network throughput  | Full speed    | ~60-80%        | User-space network stack penalty |
| File I/O            | Full speed    | ~50-70%        | VFS reimplementation overhead    |
| Memory overhead     | Minimal       | +20-50MB       | Sentry process memory            |
| Startup time        | Fast          | +100-500ms     | Sentry initialization            |

**When to use gVisor**: multi-tenant platforms, running untrusted user code, CI/CD
build containers, serverless function runtimes, or any workload where the threat
model includes container escape. **Limitations**: not all syscalls are implemented
(~70% coverage), no GPU passthrough, and some applications (databases, JVM with
JIT) may fail or underperform.

---

## Rootless Docker

Rootless mode runs the Docker daemon and containers entirely as a non-root user,
eliminating the risk of a container escape granting host root access.

### Installation

```bash
# Prerequisites: uidmap package for user namespace mapping
sudo apt-get install -y uidmap dbus-user-session

# Install rootless Docker (run as the non-root user, NOT with sudo)
dockerd-rootless-setuptool.sh install

# Set environment variables (add to ~/.bashrc)
export PATH=$HOME/bin:$PATH
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock

# Verify rootless mode
docker info 2>/dev/null | grep -i "root"
# Should show: rootless: true

# Configure subuid/subgid for user namespace remapping
# /etc/subuid and /etc/subgid should have entries like:
# myuser:100000:65536
```

### Limitations

| Feature                    | Rootless Support | Workaround                          |
|----------------------------|------------------|-------------------------------------|
| Privileged ports (< 1024)  | No               | Use `sysctl net.ipv4.ip_unprivileged_port_start=0` or reverse proxy |
| Overlay2 storage driver    | Requires kernel 5.11+ | Use fuse-overlayfs on older kernels |
| AppArmor                   | No               | Use seccomp profiles instead        |
| Cgroup v2 resource limits  | Requires systemd user session | Enable `systemctl --user` lingering |
| `--net=host`               | Limited          | Use slirp4netns (default)           |

**When to use**: development environments, CI/CD runners, shared servers, or any
environment where the Docker daemon having root access is unacceptable.

---

## Podman Alternative

Podman is a daemonless, rootless-by-default container engine that is a drop-in
replacement for Docker CLI commands.

### Core Differences from Docker

| Feature            | Docker                    | Podman                         |
|--------------------|---------------------------|--------------------------------|
| Architecture       | Client-server (dockerd)   | Daemonless (fork-exec)         |
| Root requirement   | Root by default           | Rootless by default            |
| Systemd integration| Docker service            | `podman generate systemd`      |
| Compose            | Docker Compose            | `podman-compose` or `podman compose` |
| Pod support        | No (Swarm services)       | Native pods (Kubernetes-style) |
| Image format       | OCI / Docker              | OCI / Docker                   |

### Usage

```bash
# Install Podman
sudo apt-get install -y podman

# Drop-in alias for Docker compatibility
alias docker=podman

# Run containers identically to Docker
podman run -d --name web -p 8080:80 nginx:alpine

# Use Podman Compose (Docker Compose compatible)
pip install podman-compose
podman-compose up -d

# Or use the built-in compose command (Podman 4.7+)
podman compose up -d

# Generate systemd unit files from running containers
podman generate systemd --new --name web > ~/.config/systemd/user/web.service
systemctl --user enable --now web.service

# Build images with Buildah (Podman's build backend)
podman build -t myapp:latest -f Dockerfile .

# Create Kubernetes-style pods
podman pod create --name mypod -p 8080:80
podman run --pod mypod -d nginx:alpine
podman run --pod mypod -d redis:alpine
```

Podman requires no daemon process, reducing the attack surface. Each container
runs as a direct child of the calling process, making it straightforward to manage
with systemd. Use Podman when Docker's daemon architecture is a security concern or
when rootless operation is a hard requirement.
