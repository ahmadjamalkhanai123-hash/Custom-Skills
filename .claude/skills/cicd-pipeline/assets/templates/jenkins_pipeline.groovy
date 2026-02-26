// Jenkins Declarative Pipeline — Tier 3 Production
// Requires: Docker, Kubernetes plugin, credentials: REGISTRY_CREDS, KUBECONFIG_STAGING, KUBECONFIG_PROD
// Replace: APP_NAME, REGISTRY, IMAGE_REPO, SLACK_CHANNEL

pipeline {
    agent {
        kubernetes {
            yaml '''
                apiVersion: v1
                kind: Pod
                metadata:
                  labels:
                    jenkins: agent
                spec:
                  serviceAccountName: jenkins-agent
                  containers:
                  - name: build
                    image: docker:27-dind
                    command: [cat]
                    tty: true
                    securityContext:
                      privileged: true
                    volumeMounts:
                    - name: docker-sock
                      mountPath: /var/run/docker.sock
                  - name: tools
                    image: python:3.12-slim
                    command: [cat]
                    tty: true
                  - name: kubectl
                    image: bitnami/kubectl:latest
                    command: [cat]
                    tty: true
                  volumes:
                  - name: docker-sock
                    hostPath:
                      path: /var/run/docker.sock
            '''
        }
    }

    // ─────────────────────────────────────────────────────────────
    // Environment Variables
    // ─────────────────────────────────────────────────────────────
    environment {
        APP_NAME        = 'myapp'
        REGISTRY        = 'registry.example.com'
        IMAGE_REPO      = "${REGISTRY}/${APP_NAME}"
        IMAGE_TAG       = "${env.GIT_COMMIT[0..7]}"
        IMAGE_FULL      = "${IMAGE_REPO}:${IMAGE_TAG}"
        SLACK_CHANNEL   = '#deployments'
        COVERAGE_MIN    = '80'

        // Credentials (set in Jenkins Credentials Manager)
        REGISTRY_CREDS  = credentials('registry-credentials')
        SONAR_TOKEN     = credentials('sonarqube-token')
        SLACK_TOKEN     = credentials('slack-bot-token')
    }

    // ─────────────────────────────────────────────────────────────
    // Pipeline Options
    // ─────────────────────────────────────────────────────────────
    options {
        timeout(time: 60, unit: 'MINUTES')
        disableConcurrentBuilds(abortPrevious: true)
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
        ansiColor('xterm')
    }

    // ─────────────────────────────────────────────────────────────
    // Triggers
    // ─────────────────────────────────────────────────────────────
    triggers {
        githubPush()
        cron('H 2 * * *')  // Nightly full build
    }

    // ─────────────────────────────────────────────────────────────
    // Stages
    // ─────────────────────────────────────────────────────────────
    stages {

        // Stage 1: Checkout & Setup
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.GIT_AUTHOR = sh(
                        script: "git log -1 --pretty=format:'%an'",
                        returnStdout: true
                    ).trim()
                    env.GIT_MESSAGE = sh(
                        script: "git log -1 --pretty=format:'%s'",
                        returnStdout: true
                    ).trim()
                }
                echo "Building: ${env.GIT_MESSAGE} by ${env.GIT_AUTHOR}"
            }
        }

        // Stage 2: Code Quality (parallel)
        stage('Quality') {
            parallel {
                stage('Lint') {
                    steps {
                        container('tools') {
                            sh '''
                                pip install uv --quiet
                                uv run ruff check src/ tests/ --output-format=junit > ruff-report.xml || true
                                uv run ruff format --check src/ tests/
                            '''
                            junit allowEmptyResults: true, testResults: 'ruff-report.xml'
                        }
                    }
                }

                stage('Type Check') {
                    steps {
                        container('tools') {
                            sh 'uv run mypy src/ --strict --junit-xml=mypy-report.xml || true'
                            junit allowEmptyResults: true, testResults: 'mypy-report.xml'
                        }
                    }
                }

                stage('Secret Scan') {
                    steps {
                        container('tools') {
                            sh '''
                                pip install gitleaks --quiet || \
                                    (curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.21.0/gitleaks_8.21.0_linux_x64.tar.gz | tar xz -C /usr/local/bin/)
                                gitleaks detect --source . --report-format sarif --report-path gitleaks-report.sarif || \
                                    echo "⚠️ Secrets found — review gitleaks-report.sarif"
                            '''
                            archiveArtifacts artifacts: 'gitleaks-report.sarif', allowEmptyArchive: true
                        }
                    }
                }

                stage('SAST') {
                    steps {
                        container('tools') {
                            sh '''
                                pip install semgrep --quiet
                                semgrep scan \
                                    --config=p/owasp-top-ten \
                                    --config=p/python \
                                    --junit-xml > semgrep-report.xml || true
                            '''
                            junit allowEmptyResults: true, testResults: 'semgrep-report.xml'
                        }
                    }
                }
            }
        }

        // Stage 3: Test
        stage('Test') {
            steps {
                container('tools') {
                    sh '''
                        uv sync --frozen
                        uv run pytest tests/unit/ \
                            --cov=src \
                            --cov-report=xml:coverage.xml \
                            --cov-report=html:coverage-html/ \
                            --cov-fail-under=${COVERAGE_MIN} \
                            --junit-xml=test-results.xml \
                            -v --tb=short
                    '''
                }
            }
            post {
                always {
                    junit testResults: 'test-results.xml', allowEmptyResults: true
                    publishHTML([
                        allowMissing: false,
                        alwaysLinkToLastBuild: true,
                        keepAll: true,
                        reportDir: 'coverage-html',
                        reportFiles: 'index.html',
                        reportName: 'Coverage Report'
                    ])
                    recordCoverage(tools: [[parser: 'COBERTURA', pattern: 'coverage.xml']])
                }
            }
        }

        // Stage 4: SonarQube Analysis (optional)
        stage('SonarQube') {
            when {
                anyOf {
                    branch 'main'
                    branch 'develop'
                    changeRequest()
                }
            }
            steps {
                container('tools') {
                    withSonarQubeEnv('SonarQube') {
                        sh '''
                            sonar-scanner \
                                -Dsonar.projectKey=${APP_NAME} \
                                -Dsonar.sources=src \
                                -Dsonar.tests=tests \
                                -Dsonar.python.coverage.reportPaths=coverage.xml \
                                -Dsonar.python.xunit.reportPath=test-results.xml
                        '''
                    }
                    // Quality gate check
                    timeout(time: 5, unit: 'MINUTES') {
                        waitForQualityGate abortPipeline: true
                    }
                }
            }
        }

        // Stage 5: Build Docker Image
        stage('Build') {
            steps {
                container('build') {
                    sh '''
                        docker login ${REGISTRY} \
                            -u ${REGISTRY_CREDS_USR} \
                            -p ${REGISTRY_CREDS_PSW}

                        DOCKER_BUILDKIT=1 docker build \
                            --build-arg GIT_SHA=${IMAGE_TAG} \
                            --build-arg BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
                            --cache-from ${IMAGE_REPO}:cache \
                            --tag ${IMAGE_FULL} \
                            --tag ${IMAGE_REPO}:latest \
                            .

                        docker push ${IMAGE_FULL}
                        docker push ${IMAGE_REPO}:latest

                        # Push cache layer
                        docker tag ${IMAGE_FULL} ${IMAGE_REPO}:cache
                        docker push ${IMAGE_REPO}:cache
                    '''
                }
            }
        }

        // Stage 6: Container Security Scan
        stage('Security Scan') {
            steps {
                container('build') {
                    sh '''
                        # Trivy image scan
                        docker run --rm \
                            -v /var/run/docker.sock:/var/run/docker.sock \
                            -v $(pwd):/output \
                            aquasec/trivy:latest image \
                            --format sarif \
                            --output /output/trivy-report.sarif \
                            --severity HIGH,CRITICAL \
                            --exit-code 1 \
                            ${IMAGE_FULL} || echo "⚠️ Vulnerabilities found — review trivy-report.sarif"
                    '''
                    archiveArtifacts artifacts: 'trivy-report.sarif', allowEmptyArchive: true
                }
            }
        }

        // Stage 7: Deploy to Staging
        stage('Deploy Staging') {
            when {
                branch 'main'
            }
            steps {
                container('kubectl') {
                    withCredentials([file(credentialsId: 'kubeconfig-staging', variable: 'KUBECONFIG')]) {
                        sh '''
                            helm upgrade --install ${APP_NAME} ./helm/${APP_NAME} \
                                --namespace ${APP_NAME}-staging \
                                --create-namespace \
                                --set image.repository=${IMAGE_REPO} \
                                --set image.tag=${IMAGE_TAG} \
                                --set environment=staging \
                                --wait \
                                --timeout=5m \
                                --atomic
                        '''
                    }
                }
            }
            post {
                success {
                    echo "✅ Deployed ${IMAGE_TAG} to staging"
                }
                failure {
                    echo "❌ Staging deployment failed"
                    slackSend(
                        channel: env.SLACK_CHANNEL,
                        color: 'danger',
                        message: "❌ *${APP_NAME}* staging deploy failed | ${env.BUILD_URL}"
                    )
                }
            }
        }

        // Stage 8: Smoke Test (Staging)
        stage('Smoke Test') {
            when {
                branch 'main'
            }
            steps {
                container('tools') {
                    sh '''
                        sleep 15  # Wait for pod readiness
                        python scripts/smoke_test.py \
                            --base-url https://${APP_NAME}-staging.example.com \
                            --timeout 30
                    '''
                }
            }
        }

        // Stage 9: Deploy to Production (manual gate)
        stage('Deploy Production') {
            when {
                allOf {
                    branch 'main'
                    expression { env.DEPLOY_PROD == 'true' || currentBuild.rawBuild.getCause(hudson.model.Cause$UserIdCause) != null }
                }
            }
            input {
                message 'Deploy to Production?'
                ok 'Deploy'
                submitter 'platform-team,devops-team'
                parameters {
                    choice(name: 'STRATEGY', choices: ['rolling', 'canary', 'blue-green'], description: 'Deployment strategy')
                }
            }
            steps {
                container('kubectl') {
                    withCredentials([file(credentialsId: 'kubeconfig-production', variable: 'KUBECONFIG')]) {
                        sh '''
                            helm upgrade --install ${APP_NAME} ./helm/${APP_NAME} \
                                --namespace ${APP_NAME} \
                                --create-namespace \
                                --set image.repository=${IMAGE_REPO} \
                                --set image.tag=${IMAGE_TAG} \
                                --set environment=production \
                                --set replicaCount=3 \
                                --wait \
                                --timeout=10m \
                                --atomic
                        '''
                    }
                }
            }
            post {
                success {
                    slackSend(
                        channel: env.SLACK_CHANNEL,
                        color: 'good',
                        message: "✅ *${APP_NAME}* `${IMAGE_TAG}` deployed to production | ${env.BUILD_URL}"
                    )
                }
            }
        }

    } // end stages

    // ─────────────────────────────────────────────────────────────
    // Post Actions
    // ─────────────────────────────────────────────────────────────
    post {
        always {
            cleanWs()
        }
        failure {
            slackSend(
                channel: env.SLACK_CHANNEL,
                color: 'danger',
                message: """❌ *Build Failed*
App: ${APP_NAME}
Branch: ${env.BRANCH_NAME}
Commit: ${env.GIT_MESSAGE} (${env.GIT_AUTHOR})
Build: ${env.BUILD_URL}"""
            )
        }
        success {
            script {
                if (env.BRANCH_NAME == 'main') {
                    slackSend(
                        channel: env.SLACK_CHANNEL,
                        color: 'good',
                        message: "✅ *${APP_NAME}* `${IMAGE_TAG}` — CI passed | ${env.BUILD_URL}"
                    )
                }
            }
        }
    }

} // end pipeline

// ─────────────────────────────────────────────────────────────
// Shared Library Usage (if using Jenkins Shared Libraries)
// ─────────────────────────────────────────────────────────────
// @Library('your-shared-lib') _
// cicdPipeline(
//   app: 'myapp',
//   registry: 'registry.example.com',
//   tier: 3
// )
