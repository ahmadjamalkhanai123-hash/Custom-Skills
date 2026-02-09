# BuildKit Bake — Multi-target, Multi-arch Builds
# Usage: docker buildx bake
# Usage: docker buildx bake production
# Usage: docker buildx bake --set "*.platform=linux/amd64,linux/arm64"

# ── Variables ──────────────────────────────────────
variable "REGISTRY" {
  default = "ghcr.io/{{ORG}}"
}

variable "APP_NAME" {
  default = "{{APP_NAME}}"
}

variable "VERSION" {
  default = "latest"
}

variable "GIT_SHA" {
  default = ""
}

# ── Groups ─────────────────────────────────────────
group "default" {
  targets = ["app"]
}

group "all" {
  targets = ["app", "worker", "migration"]
}

group "ci" {
  targets = ["app-multiarch", "worker-multiarch"]
}

# ── Base target (inherited) ────────────────────────
target "_base" {
  dockerfile = "Dockerfile"
  context    = "."
  labels = {
    "org.opencontainers.image.source"   = "{{REPO_URL}}"
    "org.opencontainers.image.version"  = "${VERSION}"
    "org.opencontainers.image.revision" = "${GIT_SHA}"
  }
  cache-from = ["type=registry,ref=${REGISTRY}/${APP_NAME}:buildcache"]
  cache-to   = ["type=registry,ref=${REGISTRY}/${APP_NAME}:buildcache,mode=max"]
}

# ── Application ────────────────────────────────────
target "app" {
  inherits = ["_base"]
  target   = "production"
  tags = [
    "${REGISTRY}/${APP_NAME}:${VERSION}",
    "${REGISTRY}/${APP_NAME}:${GIT_SHA}",
    "${REGISTRY}/${APP_NAME}:latest",
  ]
}

target "app-multiarch" {
  inherits  = ["app"]
  platforms = ["linux/amd64", "linux/arm64"]
}

# ── Worker ─────────────────────────────────────────
target "worker" {
  inherits   = ["_base"]
  dockerfile = "Dockerfile.worker"
  target     = "production"
  tags = [
    "${REGISTRY}/${APP_NAME}-worker:${VERSION}",
    "${REGISTRY}/${APP_NAME}-worker:${GIT_SHA}",
  ]
}

target "worker-multiarch" {
  inherits  = ["worker"]
  platforms = ["linux/amd64", "linux/arm64"]
}

# ── Database Migration ─────────────────────────────
target "migration" {
  inherits   = ["_base"]
  dockerfile = "Dockerfile.migration"
  tags = [
    "${REGISTRY}/${APP_NAME}-migration:${VERSION}",
  ]
}

# ── Development ────────────────────────────────────
target "dev" {
  inherits = ["_base"]
  target   = "builder"
  tags     = ["${APP_NAME}:dev"]
  cache-to = []  # No cache push for dev
}

# ── Test ───────────────────────────────────────────
target "test" {
  inherits = ["_base"]
  target   = "test"
  output   = ["type=cacheonly"]  # Don't export, just run
}
