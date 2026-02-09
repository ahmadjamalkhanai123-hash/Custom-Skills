# CI/CD Integration

Production-ready Docker CI/CD patterns for GitHub Actions, GitLab CI, and Jenkins.

---

## GitHub Actions

```yaml
# .github/workflows/docker-publish.yml
name: Docker Build & Publish
on:
  push:
    branches: [main, develop]
    tags: ["v*.*.*"]
  pull_request:
    branches: [main]
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
permissions:
  contents: read
  packages: write
  id-token: write  # cosign keyless signing

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hadolint/hadolint-action@v3.1.0
        with:
          dockerfile: Dockerfile
          failure-threshold: warning

  build:
    needs: lint
    runs-on: ubuntu-latest
    strategy:
      matrix:
        platform: [linux/amd64, linux/arm64]
    outputs:
      digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
        with:
          platforms: ${{ matrix.platform }}
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,prefix=sha-,format=short
            type=ref,event=branch
            type=ref,event=pr,prefix=pr-
            type=raw,value=latest,enable={{is_default_branch}}
      - uses: docker/build-push-action@v6
        id: build
        with:
          context: .
          platforms: ${{ matrix.platform }}
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: true
          sbom: true

  test:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run container and test
        run: |
          docker run -d --name app -p 8080:8080 \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:sha-${GITHUB_SHA::7}
          sleep 5
          curl --fail --retry 3 --retry-delay 2 http://localhost:8080/health
          docker stop app

  scan:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: aquasecurity/trivy-action@0.28.0
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:sha-${{ github.sha }}
          format: sarif
          output: trivy-results.sarif
          severity: CRITICAL,HIGH
          exit-code: 1
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: trivy-results.sarif

  sign:
    needs: [test, scan]
    if: github.event_name != 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: sigstore/cosign-installer@v3.7.0
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Sign image (keyless)
        run: |
          cosign sign --yes \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build.outputs.digest }}
```

---

## GitLab CI

Two approaches: Docker-in-Docker (dind) and Kaniko (no Docker socket needed).

```yaml
# .gitlab-ci.yml
stages: [build, test, scan, push]
variables:
  IMAGE: $CI_REGISTRY_IMAGE
  TAG: $CI_COMMIT_SHORT_SHA

# --- Approach 1: Docker-in-Docker ---
build-dind:
  stage: build
  image: docker:27
  services: [docker:27-dind]
  variables:
    DOCKER_TLS_CERTDIR: "/certs"
    DOCKER_BUILDKIT: "1"
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
  script:
    - docker build --cache-from $IMAGE:latest --tag $IMAGE:$TAG --tag $IMAGE:latest .
    - docker push $IMAGE:$TAG && docker push $IMAGE:latest

# --- Approach 2: Kaniko (no Docker socket) ---
build-kaniko:
  stage: build
  image:
    name: gcr.io/kaniko-project/executor:v1.23.0-debug
    entrypoint: [""]
  script:
    - mkdir -p /kaniko/.docker
    - echo "{\"auths\":{\"$CI_REGISTRY\":{\"auth\":\"$(echo -n $CI_REGISTRY_USER:$CI_REGISTRY_PASSWORD | base64)\"}}}" > /kaniko/.docker/config.json
    - /kaniko/executor --context $CI_PROJECT_DIR --dockerfile Dockerfile
        --destination $IMAGE:$TAG --destination $IMAGE:latest
        --cache=true --cache-repo=$IMAGE/cache

test:
  stage: test
  image: docker:27
  services: [docker:27-dind]
  script:
    - docker run -d --name app -p 8080:8080 $IMAGE:$TAG
    - sleep 5 && apk add --no-cache curl
    - curl --fail http://docker:8080/health && docker stop app

scan:
  stage: scan
  image: { name: "aquasec/trivy:0.58.0", entrypoint: [""] }
  script:
    - trivy image --exit-code 1 --severity CRITICAL,HIGH $IMAGE:$TAG

push:
  stage: push
  image: docker:27
  services: [docker:27-dind]
  only: [tags]
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker pull $IMAGE:$TAG
    - docker tag $IMAGE:$TAG $IMAGE:$CI_COMMIT_TAG && docker push $IMAGE:$CI_COMMIT_TAG
```

---

## Jenkins

Declarative pipeline with Docker plugin and registry credential binding.

```groovy
// Jenkinsfile
pipeline {
    agent any
    environment {
        REGISTRY = 'ghcr.io'
        IMAGE    = "${REGISTRY}/myorg/myapp"
        GIT_SHA  = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
    }
    stages {
        stage('Checkout') { steps { checkout scm } }
        stage('Build') {
            steps {
                script {
                    docker.build("${IMAGE}:${GIT_SHA}", "--no-cache .")
                }
            }
        }
        stage('Scan') {
            agent { docker { image 'aquasec/trivy:0.58.0' } }
            steps {
                sh "trivy image --exit-code 1 --severity CRITICAL,HIGH ${IMAGE}:${GIT_SHA}"
            }
        }
        stage('Push') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'ghcr-registry',
                    usernameVariable: 'REG_USER',
                    passwordVariable: 'REG_PASS'
                )]) {
                    sh """
                        echo \$REG_PASS | docker login ${REGISTRY} -u \$REG_USER --password-stdin
                        docker push ${IMAGE}:${GIT_SHA}
                        docker push ${IMAGE}:latest
                        docker logout ${REGISTRY}
                    """
                }
            }
        }
    }
    post {
        always  { sh "docker rmi ${IMAGE}:${GIT_SHA} || true" }
        failure { echo 'Pipeline failed - image not pushed' }
    }
}
```

---

## Tagging Strategy

| Tag Pattern | Example | Purpose |
|---|---|---|
| `v{major}.{minor}.{patch}` | `v1.2.3` | Release version, immutable |
| `v{major}.{minor}` | `v1.2` | Floating minor, tracks patches |
| `sha-{short}` | `sha-abc123f` | Exact commit, always immutable |
| `{branch}` | `main`, `develop` | Latest on branch, mutable |
| `pr-{number}` | `pr-42` | Pull request preview, ephemeral |
| `latest` | `latest` | Dev convenience only, never production |

`docker/metadata-action` generates all tags automatically from Git context:

```yaml
- uses: docker/metadata-action@v5
  id: meta
  with:
    images: ghcr.io/myorg/myapp
    tags: |
      type=semver,pattern={{version}}       # v1.2.3
      type=semver,pattern={{major}}.{{minor}} # v1.2
      type=sha,prefix=sha-,format=short     # sha-abc123f
      type=ref,event=branch                 # main, develop
      type=ref,event=pr,prefix=pr-          # pr-42
      type=raw,value=latest,enable={{is_default_branch}}
```

Production rule: semver and SHA tags are **immutable** -- never overwrite. Branch and PR tags are mutable by design.

---

## Cache Optimization

BuildKit cache backends -- choose based on CI environment:

| Backend | Flag | Best For |
|---|---|---|
| `inline` | `--cache-from type=inline` | Simple, stored in image layers |
| `registry` | `--cache-to type=registry,ref=reg/cache` | Shared across runners, any registry |
| `gha` | `--cache-to type=gha,mode=max` | GitHub Actions, 10 GB free per repo |
| `local` | `--cache-to type=local,dest=/tmp/cache` | Self-hosted runners, persistent storage |
| `s3` | `--cache-to type=s3,region=us-east-1,bucket=cache` | AWS-native pipelines |

```yaml
# GitHub Actions cache (recommended for GHA)
cache-from: type=gha
cache-to: type=gha,mode=max

# Registry cache (recommended for GitLab / cross-CI)
cache-from: type=registry,ref=ghcr.io/myorg/myapp:cache
cache-to: type=registry,ref=ghcr.io/myorg/myapp:cache,mode=max

# S3 cache (recommended for AWS pipelines)
cache-from: type=s3,region=us-east-1,bucket=my-buildkit-cache,name=myapp
cache-to: type=s3,region=us-east-1,bucket=my-buildkit-cache,name=myapp,mode=max
```

`mode=max` caches all layers including intermediate stages. `mode=min` (default) caches only the final stage.

---

## Multi-Arch CI

**QEMU emulation (simple, slower):**

```yaml
- uses: docker/setup-qemu-action@v3
  with:
    platforms: linux/amd64,linux/arm64
- uses: docker/setup-buildx-action@v3
- uses: docker/build-push-action@v6
  with:
    platforms: linux/amd64,linux/arm64
    push: true
    tags: ghcr.io/myorg/myapp:latest
```

**Native builders (fast, requires arm64 runner):**

```yaml
- name: Create multi-node builder
  run: |
    docker buildx create --name multiarch --driver docker-container \
      --platform linux/amd64 --node amd64-node
    docker buildx create --name multiarch --append \
      --platform linux/arm64 --node arm64-node ssh://builder@arm64-host
    docker buildx use multiarch
```

**Matrix strategy for parallel platform builds:**

```yaml
strategy:
  matrix:
    platform: [linux/amd64, linux/arm64]
steps:
  - uses: docker/build-push-action@v6
    with:
      platforms: ${{ matrix.platform }}
      outputs: type=image,name=$IMAGE,push-by-digest=true,name-canonical=true

# Final job: merge per-platform digests into a manifest list
merge:
  needs: build
  steps:
    - run: |
        docker buildx imagetools create -t $IMAGE:latest \
          $IMAGE@$DIGEST_AMD64 $IMAGE@$DIGEST_ARM64
```

Matrix runs each platform on its own runner in parallel, then a merge job creates a single manifest list so `docker pull` resolves the correct architecture automatically.
