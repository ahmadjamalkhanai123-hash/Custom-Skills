# Networking & Storage

Docker networking controls how containers communicate with each other and the
outside world. Docker storage controls how data is persisted, shared, and
backed up. Both are critical for production-grade deployments.

---

## Network Drivers

Docker provides five built-in network drivers. Each serves a distinct use case.

| Driver | Isolation | Multi-Host | Performance | Use Case |
|-----------|-----------|------------|-------------|--------------------------------------|
| `bridge` | Yes | No | Good | Default; container-to-container on a single host |
| `host` | None | No | Best | Latency-sensitive apps (metrics, proxies) |
| `overlay` | Yes | Yes | Good | Swarm / multi-host clustering |
| `macvlan` | Yes | No | Good | Containers that must appear as physical devices on the LAN |
| `none` | Full | No | N/A | Security-hardened containers with no network access |

```bash
# Create a user-defined bridge network
docker network create --driver bridge app-net

# Create a macvlan network mapped to a host interface
docker network create -d macvlan \
  --subnet=192.168.1.0/24 --gateway=192.168.1.1 \
  -o parent=eth0 physical-net

# Create an overlay network (requires Swarm init)
docker network create -d overlay --attachable services-net

# Run a container with no networking
docker run --network none --rm alpine ip addr
```

**Decision guide:** Use `bridge` for most single-host workloads. Switch to `host`
only when you need to eliminate the network namespace overhead (e.g., a
Prometheus node exporter). Use `overlay` when services span multiple Docker
hosts. Use `macvlan` when legacy systems need to reach a container by MAC
address. Use `none` for batch jobs that must never touch the network.

---

## DNS Resolution

Containers on the default `bridge` network can only reach each other by IP.
User-defined networks enable automatic DNS resolution by container name.

```bash
# Containers on user-defined networks resolve each other by name
docker network create api-net
docker run -d --name redis --network api-net redis:7-alpine
docker run --rm --network api-net alpine ping -c2 redis   # resolves automatically

# Override DNS servers for a container
docker run --dns 8.8.8.8 --dns 1.1.1.1 --rm alpine nslookup example.com

# Add custom host entries
docker run --add-host db.local:10.0.0.5 --rm alpine ping -c1 db.local
```

**Service discovery patterns:**
- Same Compose project: use the service name directly (`http://api:8000`).
- Cross-project: attach both services to a shared external network.
- External service discovery: use Consul, etcd, or environment variables
  injected at deploy time.

---

## Network Isolation Patterns

Separate frontend and backend traffic using multiple networks. Only the
application tier bridges both; the database is unreachable from the internet.

```yaml
# compose.yaml -- three-tier network isolation
services:
  nginx:
    image: nginx:1.27-alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    networks:
      - frontend
    depends_on:
      - app

  app:
    build: .
    environment:
      DATABASE_URL: postgresql://user:pass@db:5432/mydb
    networks:
      - frontend
      - backend
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_pass
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - backend

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true      # no outbound internet access

volumes:
  pgdata:
```

With `internal: true`, containers on the `backend` network cannot reach the
internet. This prevents a compromised database container from phoning home.

**DMZ pattern:** Add a third `dmz` network for bastion/jump containers. Only
the bastion has SSH exposed; it connects to `frontend` but not `backend`.

---

## Service Mesh Integration

### Traefik -- Automatic Reverse Proxy with HTTPS

Traefik reads Docker labels to configure routing and provisions TLS
certificates automatically via Let's Encrypt.

```yaml
# compose.yaml -- Traefik with automatic HTTPS
services:
  traefik:
    image: traefik:v3.1
    command:
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.letsencrypt.acme.email=ops@example.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - letsencrypt:/letsencrypt
    networks:
      - proxy

  api:
    build: .
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=Host(`api.example.com`)"
      - "traefik.http.routers.api.entrypoints=websecure"
      - "traefik.http.routers.api.tls.certresolver=letsencrypt"
      - "traefik.http.services.api.loadbalancer.server.port=8000"
    networks:
      - proxy

networks:
  proxy:
    driver: bridge

volumes:
  letsencrypt:
```

**Consul Connect:** For full service mesh (mTLS, intentions, traffic
splitting), run Consul agents as sidecars. Each service registers with Consul
and communicates through an Envoy proxy injected automatically.

---

## Storage Drivers

The storage driver controls how image layers and the container writable layer
are stored on disk. This is distinct from volumes.

| Driver | Status | Backing FS | Best For |
|---------------|-------------|-----------------|------------------------------|
| `overlay2` | Recommended | ext4, xfs | All modern Linux hosts |
| `devicemapper`| Deprecated | direct-lvm | Legacy RHEL/CentOS (avoid) |
| `btrfs` | Supported | btrfs | Hosts already on btrfs |
| `zfs` | Supported | zfs | Hosts already on ZFS |

```bash
# Check current storage driver
docker info --format '{{.Driver}}'

# Set storage driver in /etc/docker/daemon.json
# { "storage-driver": "overlay2" }
```

**Rule of thumb:** Use `overlay2` unless you already run btrfs or ZFS at the
OS level. Never use `devicemapper` with loop-lvm in production.

---

## Volume Types

### Named Volumes

Managed by Docker, stored under `/var/lib/docker/volumes/`. Best for databases
and any data that must survive container recreation.

```yaml
services:
  postgres:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:          # Docker manages lifecycle and location
```

### Bind Mounts

Map a host directory directly into the container. Ideal for development where
you want live code reloading.

```yaml
services:
  app:
    build: .
    volumes:
      - ./src:/app/src        # host path : container path
      - ./config.yaml:/app/config.yaml:ro   # read-only bind
```

### tmpfs Mounts

In-memory storage. Data is never written to disk and disappears when the
container stops. Use for secrets or scratch space.

```yaml
services:
  app:
    image: myapp:latest
    tmpfs:
      - /tmp
      - /run/secrets:size=64k,mode=0700
```

### NFS Volumes

Shared storage accessible from multiple Docker hosts. Defined as a named
volume with driver options.

```yaml
volumes:
  shared-assets:
    driver: local
    driver_opts:
      type: nfs
      o: addr=nfs.example.com,rw,nfsvers=4.1
      device: ":/exports/assets"
```

---

## Volume Drivers

The default `local` driver supports NFS, CIFS, and other mount types through
`driver_opts`. Third-party drivers attach cloud block storage.

```yaml
# CIFS / SMB volume
volumes:
  smb-share:
    driver: local
    driver_opts:
      type: cifs
      o: username=user,password=pass,addr=fileserver.local
      device: "//fileserver.local/share"
```

**Cloud volume drivers** like REX-Ray (now maintenance mode) and the Portworx
plugin provision EBS, Azure Disk, or GCE PD volumes on demand:

```bash
# Install a volume plugin
docker plugin install rexray/ebs

# Create a cloud-backed volume
docker volume create --driver rexray/ebs --opt size=50 db-data
```

For Kubernetes-managed Docker hosts, prefer CSI drivers over Docker volume
plugins. In pure Docker / Swarm environments, evaluate Portworx, Longhorn, or
the local NFS approach shown above.

---

## Backup & Migration

### Volume Backup

Use a temporary container with `--volumes-from` to tar the data out:

```bash
# Back up a named volume to a tar file on the host
docker run --rm \
  --volumes-from my-postgres \
  -v "$(pwd)/backups:/backup" \
  alpine tar czf /backup/pgdata-$(date +%Y%m%d).tar.gz \
    -C /var/lib/postgresql data

# Restore into a new or empty volume
docker run --rm \
  -v pgdata-new:/var/lib/postgresql/data \
  -v "$(pwd)/backups:/backup" \
  alpine tar xzf /backup/pgdata-20260208.tar.gz \
    -C /var/lib/postgresql
```

### Data Migration Between Hosts

```bash
# Pipe a volume directly to a remote host over SSH
docker run --rm \
  -v pgdata:/data alpine tar czf - -C /data . \
  | ssh user@remote "docker run --rm -i -v pgdata:/data alpine tar xzf - -C /data"
```

### Volume Inspection and Cleanup

```bash
# List all volumes
docker volume ls

# Inspect a volume (mount point, driver, labels)
docker volume inspect pgdata

# Remove unused (dangling) volumes
docker volume prune -f

# Remove ALL unused volumes (including named ones not attached to containers)
docker volume prune -a -f
```

**Production tip:** Schedule nightly volume backups with cron or a sidecar
container. Always test restores periodically -- an untested backup is not a
backup.
