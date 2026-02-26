# CI Platforms Reference

Platform-specific syntax, patterns, and best practices for all major CI systems.

---

## GitHub Actions

### Workflow Structure
```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
    paths-ignore: ['**.md', 'docs/**']
  pull_request:
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        options: [staging, production]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true  # Cancel superseded runs on PRs

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

permissions:
  contents: read
  packages: write
  id-token: write  # Required for OIDC
```

### Reusable Workflow Pattern
```yaml
# .github/workflows/reusable-build.yml
on:
  workflow_call:
    inputs:
      service:
        required: true
        type: string
      environment:
        required: true
        type: string
    secrets:
      REGISTRY_TOKEN:
        required: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build ${{ inputs.service }}
        run: docker build -t ${{ inputs.service }} .
```

### Caching Strategy
```yaml
# Python/pip cache
- uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}
    restore-keys: |
      ${{ runner.os }}-pip-

# Node.js cache
- uses: actions/setup-node@v4
  with:
    node-version: '20'
    cache: 'npm'

# Go build cache
- uses: actions/cache@v4
  with:
    path: |
      ~/go/pkg/mod
      ~/.cache/go-build
    key: ${{ runner.os }}-go-${{ hashFiles('**/go.sum') }}

# Docker layer cache (using GitHub Actions cache)
- uses: docker/setup-buildx-action@v3
- uses: docker/build-push-action@v6
  with:
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

### OIDC to AWS (Keyless Auth)
```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::123456789012:role/github-actions-role
    aws-region: us-east-1
    # No keys needed — OIDC token exchange
```

### OIDC to GCP
```yaml
- uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: projects/123/locations/global/workloadIdentityPools/pool/providers/github
    service_account: ci@project.iam.gserviceaccount.com
```

### OIDC to Azure
```yaml
- uses: azure/login@v2
  with:
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    # Uses federated identity — no client secret
```

### Matrix Build
```yaml
strategy:
  fail-fast: false
  matrix:
    service: [auth, orders, payments, notifications]
    include:
      - service: auth
        port: 8080
      - service: payments
        port: 8082
        needs-pci: true
```

### Environment Protection Rules
```yaml
jobs:
  deploy-production:
    environment:
      name: production
      url: https://app.example.com
    # Requires "required reviewers" configured in GitHub environment settings
```

### Artifact Upload/Download
```yaml
- uses: actions/upload-artifact@v4
  with:
    name: test-results
    path: coverage/
    retention-days: 7

- uses: actions/download-artifact@v4
  with:
    name: test-results
```

---

## GitLab CI

### Pipeline Structure
```yaml
# .gitlab-ci.yml
stages:
  - lint
  - build
  - test
  - security
  - package
  - deploy-staging
  - deploy-production

default:
  image: python:3.12-slim
  before_script:
    - pip install -r requirements-dev.txt
  retry:
    max: 2
    when: [runner_system_failure, stuck_or_timeout_failure]

variables:
  DOCKER_DRIVER: overlay2
  DOCKER_TLS_CERTDIR: "/certs"
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"
```

### GitLab CI Caching
```yaml
.python-cache: &python-cache
  cache:
    key:
      files:
        - requirements*.txt
    paths:
      - .cache/pip
      - venv/

lint:
  <<: *python-cache
  stage: lint
  script:
    - flake8 src/ --max-line-length=120
    - mypy src/
    - black --check src/
```

### GitLab Native Container Registry
```yaml
build-image:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build
        --cache-from $CI_REGISTRY_IMAGE:cache
        --tag $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
        --tag $CI_REGISTRY_IMAGE:latest .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
    - docker push $CI_REGISTRY_IMAGE:cache
```

### OIDC to Cloud (GitLab)
```yaml
deploy-aws:
  stage: deploy-staging
  id_tokens:
    AWS_OIDC_TOKEN:
      aud: https://gitlab.com
  script:
    - |
      CREDS=$(aws sts assume-role-with-web-identity \
        --role-arn $AWS_ROLE_ARN \
        --role-session-name gitlab-ci \
        --web-identity-token $AWS_OIDC_TOKEN \
        --query 'Credentials' --output json)
      export AWS_ACCESS_KEY_ID=$(echo $CREDS | jq -r '.AccessKeyId')
      export AWS_SECRET_ACCESS_KEY=$(echo $CREDS | jq -r '.SecretAccessKey')
      export AWS_SESSION_TOKEN=$(echo $CREDS | jq -r '.SessionToken')
```

### GitLab Environments + Manual Gate
```yaml
deploy-production:
  stage: deploy-production
  environment:
    name: production
    url: https://app.example.com
  when: manual
  only:
    - tags
  script:
    - helm upgrade --install app chart/ -n production
```

### GitLab Include (Reusable Configs)
```yaml
include:
  - project: 'platform/ci-templates'
    file: '/templates/docker-build.yml'
  - local: '.gitlab/ci/security.yml'
  - template: 'Security/SAST.gitlab-ci.yml'  # GitLab native SAST
```

---

## Jenkins (Declarative Pipeline)

### Jenkinsfile Structure
```groovy
pipeline {
    agent {
        kubernetes {
            yaml """
                apiVersion: v1
                kind: Pod
                spec:
                  containers:
                  - name: builder
                    image: python:3.12-slim
                    command: ['cat']
                    tty: true
                  - name: docker
                    image: docker:24-dind
                    securityContext:
                      privileged: true
            """
        }
    }

    options {
        timeout(time: 60, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
    }

    environment {
        REGISTRY = credentials('docker-registry-creds')
        KUBECONFIG = credentials('k8s-kubeconfig')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Lint & SAST') {
            parallel {
                stage('Lint') {
                    steps {
                        container('builder') {
                            sh 'pip install flake8 && flake8 src/'
                        }
                    }
                }
                stage('SAST') {
                    steps {
                        container('builder') {
                            sh 'pip install semgrep && semgrep --config auto src/'
                        }
                    }
                }
            }
        }

        stage('Test') {
            steps {
                container('builder') {
                    sh 'pip install pytest pytest-cov && pytest --cov=src --cov-fail-under=80'
                }
            }
            post {
                always {
                    junit 'reports/*.xml'
                    publishCoverage adapters: [coberturaAdapter('coverage.xml')]
                }
            }
        }

        stage('Build Image') {
            steps {
                container('docker') {
                    sh """
                        docker build -t ${REGISTRY}/myapp:${GIT_COMMIT} .
                        docker push ${REGISTRY}/myapp:${GIT_COMMIT}
                    """
                }
            }
        }

        stage('Deploy to Staging') {
            when { branch 'main' }
            steps {
                sh 'helm upgrade --install myapp chart/ -n staging --set image.tag=${GIT_COMMIT}'
            }
        }

        stage('Deploy to Production') {
            when { buildingTag() }
            input {
                message "Deploy ${TAG_NAME} to production?"
                ok "Deploy"
                submitter "devops-leads"
            }
            steps {
                sh 'helm upgrade --install myapp chart/ -n production --set image.tag=${GIT_COMMIT}'
            }
        }
    }

    post {
        failure {
            slackSend(color: 'danger', message: "Pipeline failed: ${BUILD_URL}")
        }
        success {
            slackSend(color: 'good', message: "Deployed ${GIT_COMMIT} to ${BRANCH_NAME}")
        }
    }
}
```

### Jenkins Shared Library
```groovy
// vars/buildAndPush.groovy
def call(Map config) {
    def registry = config.registry ?: 'registry.example.com'
    def image = config.image
    def tag = config.tag ?: env.GIT_COMMIT

    sh """
        docker build -t ${registry}/${image}:${tag} .
        docker push ${registry}/${image}:${tag}
    """
    return "${registry}/${image}:${tag}"
}
```

---

## Azure DevOps Pipelines

### YAML Pipeline Structure
```yaml
# azure-pipelines.yml
trigger:
  branches:
    include: [main, develop]
  paths:
    exclude: ['docs/**', '*.md']

pr:
  branches:
    include: [main]

variables:
  - group: production-secrets       # Variable group from Azure Key Vault
  - name: containerRegistry
    value: 'myacr.azurecr.io'
  - name: imageRepository
    value: 'myapp'

pool:
  vmImage: 'ubuntu-latest'

stages:
  - stage: Build
    jobs:
      - job: BuildAndTest
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '3.12'

          - script: |
              pip install -r requirements-dev.txt
              flake8 src/
              pytest --junitxml=reports/test-results.xml --cov=src --cov-report=xml
            displayName: 'Lint and Test'

          - task: PublishTestResults@2
            inputs:
              testResultsFiles: 'reports/test-results.xml'

          - task: Docker@2
            inputs:
              command: buildAndPush
              repository: $(imageRepository)
              containerRegistry: $(containerRegistry)  # Service connection
              tags: |
                $(Build.SourceVersion)
                latest

  - stage: DeployStaging
    dependsOn: Build
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - deployment: DeployStaging
        environment: staging
        strategy:
          runOnce:
            deploy:
              steps:
                - task: HelmDeploy@1
                  inputs:
                    command: upgrade
                    chartName: myapp
                    releaseName: myapp-staging
                    namespace: staging

  - stage: DeployProduction
    dependsOn: DeployStaging
    condition: and(succeeded(), startsWith(variables['Build.SourceBranch'], 'refs/tags/v'))
    jobs:
      - deployment: DeployProduction
        environment: production  # Requires approval gate in Azure DevOps
        strategy:
          runOnce:
            deploy:
              steps:
                - task: HelmDeploy@1
                  inputs:
                    command: upgrade
                    chartName: myapp
                    releaseName: myapp-production
                    namespace: production
```

### Azure Workload Identity Federation
```yaml
- task: AzureCLI@2
  inputs:
    azureSubscription: 'production-service-connection'  # Federated credentials
    scriptType: bash
    script: |
      az acr login --name myacr
      # No password needed — federated identity
```

---

## CircleCI

### config.yml Structure
```yaml
# .circleci/config.yml
version: 2.1

orbs:
  python: circleci/python@2.1
  docker: circleci/docker@2.6
  aws-cli: circleci/aws-cli@4.0

executors:
  python-executor:
    docker:
      - image: cimg/python:3.12
    resource_class: medium

jobs:
  lint-and-test:
    executor: python-executor
    steps:
      - checkout
      - python/install-packages:
          pip-dependency-file: requirements-dev.txt
          pkg-manager: pip
      - run:
          name: Lint
          command: flake8 src/ && mypy src/
      - run:
          name: Test
          command: pytest --junitxml=test-results/results.xml --cov=src --cov-fail-under=80
      - store_test_results:
          path: test-results
      - store_artifacts:
          path: coverage/

  build-image:
    machine:
      image: ubuntu-2204:current
    steps:
      - checkout
      - docker/check
      - docker/build:
          image: myapp
          tag: $CIRCLE_SHA1
      - docker/push:
          image: myapp
          tag: $CIRCLE_SHA1

workflows:
  ci-cd:
    jobs:
      - lint-and-test
      - build-image:
          requires: [lint-and-test]
          context: aws-production  # Org-level context with OIDC
      - deploy-staging:
          requires: [build-image]
          filters:
            branches:
              only: main
      - approve-production:
          type: approval
          requires: [deploy-staging]
      - deploy-production:
          requires: [approve-production]
          filters:
            branches:
              only: main
```

### CircleCI Dynamic Layer Cache (DLC)
```yaml
# Requires DLC feature on plan
- restore_cache:
    keys:
      - docker-cache-{{ .Branch }}-{{ .Revision }}
      - docker-cache-{{ .Branch }}-
      - docker-cache-
- run: docker build -t myapp .
- save_cache:
    key: docker-cache-{{ .Branch }}-{{ .Revision }}
    paths:
      - /tmp/docker-cache
```

---

## Bitbucket Pipelines

### bitbucket-pipelines.yml
```yaml
image: python:3.12-slim

definitions:
  caches:
    pip: ~/.cache/pip
  steps:
    - step: &lint-test
        name: Lint and Test
        caches: [pip]
        script:
          - pip install -r requirements-dev.txt
          - flake8 src/
          - pytest --junitxml=test-results.xml --cov=src --cov-fail-under=80
        artifacts:
          - test-results.xml
          - coverage/

    - step: &build-image
        name: Build Docker Image
        services: [docker]
        script:
          - docker login -u $DOCKER_HUB_USER -p $DOCKER_HUB_PASSWORD
          - docker build -t myapp:$BITBUCKET_COMMIT .
          - docker push myapp:$BITBUCKET_COMMIT

pipelines:
  default:
    - step: *lint-test

  branches:
    main:
      - step: *lint-test
      - step: *build-image
      - step:
          name: Deploy to Staging
          deployment: staging
          script:
            - helm upgrade --install myapp chart/ -n staging

    'release/*':
      - step: *lint-test
      - step: *build-image
      - step:
          name: Deploy to Production
          deployment: production
          trigger: manual
          script:
            - helm upgrade --install myapp chart/ -n production
```

---

## Tekton (Kubernetes-Native)

### Task + Pipeline CRDs
```yaml
# task.yaml — reusable task
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: python-test
spec:
  params:
    - name: coverage-threshold
      default: "80"
  workspaces:
    - name: source
  steps:
    - name: test
      image: python:3.12-slim
      workingDir: $(workspaces.source.path)
      script: |
        pip install -r requirements-dev.txt
        pytest --cov=src --cov-fail-under=$(params.coverage-threshold)
---
# pipeline.yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: ci-pipeline
spec:
  params:
    - name: git-url
    - name: git-revision
  workspaces:
    - name: shared-workspace
  tasks:
    - name: fetch-source
      taskRef:
        name: git-clone
        kind: ClusterTask
      params:
        - name: url
          value: $(params.git-url)
      workspaces:
        - name: output
          workspace: shared-workspace
    - name: run-tests
      runAfter: [fetch-source]
      taskRef:
        name: python-test
      workspaces:
        - name: source
          workspace: shared-workspace
```
