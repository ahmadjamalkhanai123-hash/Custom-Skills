# Performance Optimization

Concrete techniques for faster builds, smaller images, and maximum runtime throughput.
Every recommendation includes a measurable command or benchmark target.

---

## Build Speed

### BuildKit Parallelism

Enable BuildKit and exploit concurrent stage execution:

```bash
export DOCKER_BUILDKIT=1

# Parallel multi-stage builds — independent stages run concurrently
# BuildKit automatically detects independent stages and schedules them in parallel
FROM golang:1.22 AS backend
RUN go build -o /app .

FROM node:20 AS frontend
RUN npm ci && npm run build

FROM alpine:3.19 AS final
COPY --from=backend /app /app
COPY --from=frontend /dist /dist
```

Set max parallelism explicitly:

```bash
docker buildx build --max-parallelism 4 .
```

### Cache Mounts for Package Managers

Persist package caches across builds — eliminates re-downloading dependencies:

```dockerfile
# Go module cache (saves 30-60s per build)
RUN --mount=type=cache,target=/go/pkg/mod go build -o /app .

# pip cache (saves 15-40s)
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

# npm cache (saves 20-50s)
RUN --mount=type=cache,target=/root/.npm npm ci

# apt cache (saves 10-30s)
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && apt-get install -y --no-install-recommends curl
```

### Remote Cache Backends

Share build cache across CI runners and team members:

```bash
# Registry-backed cache (OCI image format)
docker buildx build \
  --cache-to type=registry,ref=registry.example.com/myapp:buildcache,mode=max \
  --cache-from type=registry,ref=registry.example.com/myapp:buildcache .

# S3 backend (ideal for AWS-native CI)
docker buildx build \
  --cache-to type=s3,region=us-east-1,bucket=docker-cache,name=myapp \
  --cache-from type=s3,region=us-east-1,bucket=docker-cache,name=myapp .

# GitHub Actions cache (free within GHA limits)
docker buildx build \
  --cache-to type=gha,scope=main \
  --cache-from type=gha,scope=main .
```

### Build Context and Layer Ordering

Minimize context size with `.dockerignore`:

```text
# .dockerignore — reduces context from ~500MB to ~5MB on typical projects
.git
node_modules
__pycache__
*.pyc
.venv
dist
build
.env*
```

Order layers from least-changed to most-changed for maximum cache hits:

```dockerfile
COPY go.mod go.sum ./          # Changes rarely — cached
RUN go mod download            # Cached until deps change
COPY . .                       # Changes every commit — last
RUN go build -o /app .
```

Debug build performance with plain progress output:

```bash
docker build --progress=plain --no-cache . 2>&1 | tee build.log
```

---

## Image Size Optimization

### Size Budgets per Language

| Language | Base Image             | Target Size | Max Acceptable |
|----------|------------------------|-------------|----------------|
| Go       | scratch / distroless   | <10MB       | <20MB          |
| Rust     | scratch / distroless   | <10MB       | <15MB          |
| Python   | python:3.12-slim       | <50MB       | <80MB          |
| Node.js  | node:20-slim           | <70MB       | <100MB         |
| Java     | eclipse-temurin:21-jre | <90MB       | <120MB         |

### Base Image Size Comparison

| Base             | Compressed Size | Use Case                          |
|------------------|-----------------|-----------------------------------|
| scratch          | 0MB             | Static Go/Rust binaries           |
| distroless       | ~2MB            | Static binaries needing ca-certs  |
| alpine:3.19      | ~3.4MB          | When shell access is needed       |
| debian:bookworm-slim | ~28MB      | When glibc compatibility required |
| ubuntu:24.04     | ~29MB           | Full ecosystem support            |

### Layer Analysis with dive

```bash
# Install dive for layer-by-layer analysis
docker run --rm -it \
  -v /var/run/docker.sock:/var/run/docker.sock \
  wagoodman/dive:latest myapp:latest

# CI mode — fail build if wasted space exceeds threshold
CI=true dive myapp:latest --highestWastedBytes 20MB
```

### Automatic Minification with slim

```bash
# Automatically shrink images by 3-30x
slim build --target myapp:latest --tag myapp:slim

# Analyze without building
slim xray --target myapp:latest
```

### Dependency Trimming

```dockerfile
# apt: skip recommended packages (saves 50-200MB)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && rm -rf /var/lib/apt/lists/*

# pip: disable cache (saves 20-80MB per build)
RUN pip install --no-cache-dir -r requirements.txt

# npm: production only (saves 100-400MB)
RUN npm ci --omit=dev

# Multi-stage: copy only the artifact
FROM python:3.12-slim AS final
COPY --from=builder /app/dist /app
```

---

## Runtime Performance

### CPU Pinning and NUMA

```bash
# Pin container to specific CPU cores (reduces context switching by ~15%)
docker run --cpuset-cpus="0,1" myapp

# Pin to NUMA node 0 CPUs for memory-locality (measurable on multi-socket hosts)
docker run --cpuset-cpus="0-7" --cpuset-mems="0" myapp

# Guarantee 2 full CPUs (hard limit — no oversubscription)
docker run --cpus="2.0" myapp
```

### Memory and Huge Pages

```bash
# JVM/database workloads: increase shared memory (default 64MB is too low)
docker run --shm-size=1g postgres:16

# Enable huge pages for JVM (requires host: echo 512 > /proc/sys/vm/nr_hugepages)
docker run --shm-size=1g --ulimit memlock=-1:-1 \
  -e JAVA_OPTS="-XX:+UseLargePages" myapp-jvm
```

### Ulimits and OOM Control

```bash
# Raise file descriptor limit (default 1024 is too low for high-concurrency servers)
docker run --ulimit nofile=65536:65536 myapp

# Raise process limit for fork-heavy apps
docker run --ulimit nproc=4096:4096 myapp

# CAUTION: --oom-kill-disable can hang the entire host if the container leaks memory
# Only use with a hard memory limit
docker run -m 2g --oom-kill-disable myapp  # acceptable — has limit
# docker run --oom-kill-disable myapp       # DANGEROUS — never do this
```

### Process Management

```bash
# Use tini as PID 1 (proper signal forwarding, zombie reaping)
docker run --init myapp

# Or embed in Dockerfile
RUN apt-get install -y tini
ENTRYPOINT ["tini", "--"]
CMD ["./myapp"]
```

---

## I/O Optimization

### Storage Drivers

| Driver    | Read Perf | Write Perf | Copy-on-Write Overhead | Recommendation         |
|-----------|-----------|------------|------------------------|------------------------|
| overlay2  | Excellent | Good       | Low (first write only)  | Default — use this     |
| btrfs     | Good      | Good       | Medium                 | If host uses btrfs     |
| zfs       | Good      | Good       | Medium                 | Enterprise storage     |
| devicemapper | Fair   | Fair       | High                   | Avoid — legacy         |

### Volume Mount Performance

```bash
# Linux: native mounts — no performance penalty
docker run -v /data/app:/app myapp

# macOS: use VirtioFS (Docker Desktop 4.22+) for near-native performance
# Settings > General > "Use VirtioFS" — 2-5x faster than gRPC-FUSE

# tmpfs for temporary files (RAM-backed, no disk I/O)
docker run --tmpfs /tmp:rw,noexec,nosuid,size=256m myapp

# Named volumes outperform bind mounts for database workloads
docker volume create pgdata
docker run -v pgdata:/var/lib/postgresql/data postgres:16
```

### Container Storage Limits

```bash
# Limit container writable layer to prevent runaway log/temp file growth
docker run --storage-opt size=10G myapp

# Requires overlay2 with xfs backing filesystem and pquota mount option
```

---

## Network Performance

### Host Networking

```bash
# Bypass docker bridge for max throughput (~10% gain, eliminates NAT overhead)
docker run --network=host myapp

# Only for trusted containers — exposes all host ports
# Benchmark: iperf3 shows ~9.4 Gbps (host) vs ~8.5 Gbps (bridge) on 10GbE
```

### MTU and TCP Tuning

```bash
# Match MTU to physical network (jumbo frames if available)
docker network create --opt com.docker.network.driver.mtu=9000 perf-net

# TCP tuning via sysctl (high-throughput workloads)
docker run --sysctl net.core.somaxconn=65535 \
           --sysctl net.ipv4.tcp_max_syn_backlog=65535 \
           --sysctl net.ipv4.tcp_tw_reuse=1 \
           myapp
```

### DNS and Connection Pooling

```bash
# Embedded DNS caching (add to container entrypoint or use dnsmasq sidecar)
# Reduces DNS lookup latency from ~5ms to <0.1ms for repeated queries

# Connection pooling: configure at the application level
# PostgreSQL: PgBouncer sidecar — reduces connection overhead by 80%
docker run -d --name pgbouncer --network=app-net \
  -e DATABASE_URL="postgres://db:5432/mydb" \
  edoburu/pgbouncer:latest
```

---

## Benchmarking

### Real-Time Monitoring

```bash
# Live resource usage (CPU, memory, network, I/O per container)
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"

# Storage analysis — identify space waste
docker system df -v
```

### Build Time Benchmarking

```bash
# Baseline build time measurement
time docker build --no-cache -t myapp:bench . 2>&1 | tail -5

# Compare cached vs uncached builds
time docker build -t myapp:cached .           # Expect 5-10x faster with warm cache

# BuildKit trace for stage-level timing
BUILDKIT_PROGRESS=plain docker build . 2>&1 | grep -E "^#[0-9]+ DONE"
```

### Container Performance Benchmarks

```bash
# CPU benchmark with sysbench
docker run --rm severalnines/sysbench sysbench cpu --threads=4 run

# Memory throughput
docker run --rm severalnines/sysbench sysbench memory --threads=4 run

# Disk I/O benchmark with fio
docker run --rm -v /tmp/fio-test:/data ljishen/fio \
  --name=randwrite --ioengine=libaio --iodepth=16 \
  --rw=randwrite --bs=4k --size=1G --numjobs=4 \
  --directory=/data --group_reporting

# Network throughput between containers
docker run -d --name iperf-server --network=bench-net networkstatic/iperf3 -s
docker run --rm --network=bench-net networkstatic/iperf3 -c iperf-server -t 10
```

### Optimization Verification Checklist

```bash
# 1. Image size within budget
docker images myapp --format "{{.Size}}"

# 2. No wasted layers
dive myapp:latest --ci --highestWastedBytes 10MB

# 3. Build time under target (e.g., <60s cached)
time docker build -t myapp .

# 4. Runtime resource baseline
docker stats myapp --no-stream

# 5. No excessive storage consumption
docker system df
```
