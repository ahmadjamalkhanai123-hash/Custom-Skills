# Kubernetes Policy Engine Patterns

> Production policy engines: Kyverno, OPA Gatekeeper, ValidatingAdmissionPolicy — enforce standards at admission time.

---

## Kyverno

Kyverno is a Kubernetes-native policy engine. Policies are written as Kubernetes resources (no Rego). It supports validate, mutate, generate, and verifyImages rules.

### Installation

```bash
helm repo add kyverno https://kyverno.github.io/kyverno
helm install kyverno kyverno/kyverno \
  --namespace kyverno --create-namespace \
  --set replicaCount=3 \
  --set backgroundController.replicas=2
```

### Validate: Require Labels

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-labels
  annotations:
    policies.kyverno.io/title: Require Labels
    policies.kyverno.io/severity: medium
spec:
  validationFailureAction: Enforce
  background: true
  rules:
    - name: require-team-label
      match:
        any:
          - resources:
              kinds:
                - Deployment
                - StatefulSet
                - DaemonSet
              namespaces:
                - production
                - staging
      validate:
        message: >-
          Resources must have labels: app.kubernetes.io/name,
          app.kubernetes.io/team, app.kubernetes.io/env
        pattern:
          metadata:
            labels:
              app.kubernetes.io/name: "?*"
              app.kubernetes.io/team: "?*"
              app.kubernetes.io/env: "production | staging | development"
```

### Validate: Trusted Image Registries

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: restrict-image-registries
spec:
  validationFailureAction: Enforce
  background: true
  rules:
    - name: trusted-registries-only
      match:
        any:
          - resources:
              kinds:
                - Pod
      validate:
        message: "Images must come from trusted registries: ghcr.io/myorg or registry.internal.io"
        pattern:
          spec:
            containers:
              - image: "ghcr.io/myorg/* | registry.internal.io/*"
            =(initContainers):
              - image: "ghcr.io/myorg/* | registry.internal.io/*"
            =(ephemeralContainers):
              - image: "ghcr.io/myorg/* | registry.internal.io/*"
```

### Validate: Require Resource Limits

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-resource-limits
spec:
  validationFailureAction: Enforce
  background: true
  rules:
    - name: require-limits
      match:
        any:
          - resources:
              kinds:
                - Pod
              namespaces:
                - production
      validate:
        message: "All containers must have CPU and memory requests and limits."
        pattern:
          spec:
            containers:
              - resources:
                  requests:
                    cpu: "?*"
                    memory: "?*"
                  limits:
                    cpu: "?*"
                    memory: "?*"
    - name: memory-limit-cap
      match:
        any:
          - resources:
              kinds:
                - Pod
              namespaces:
                - production
      validate:
        message: "Memory limit must not exceed 4Gi."
        deny:
          conditions:
            any:
              - key: "{{ request.object.spec.containers[].resources.limits.memory }}"
                operator: GreaterThan
                value: "4Gi"
```

### Mutate: Add Defaults

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: add-defaults
spec:
  rules:
    - name: add-default-security-context
      match:
        any:
          - resources:
              kinds:
                - Pod
              namespaces:
                - production
                - staging
      mutate:
        patchStrategicMerge:
          spec:
            securityContext:
              runAsNonRoot: true
              seccompProfile:
                type: RuntimeDefault
            containers:
              - (name): "*"
                securityContext:
                  allowPrivilegeEscalation: false
                  readOnlyRootFilesystem: true
                  capabilities:
                    drop:
                      - ALL
    - name: add-default-tolerations
      match:
        any:
          - resources:
              kinds:
                - Pod
      mutate:
        patchStrategicMerge:
          spec:
            =(tolerations):
              - key: "node.kubernetes.io/not-ready"
                operator: "Exists"
                effect: "NoExecute"
                tolerationSeconds: 300
```

### Mutate: Inject Sidecar

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: inject-logging-sidecar
spec:
  rules:
    - name: inject-fluentbit
      match:
        any:
          - resources:
              kinds:
                - Deployment
              selector:
                matchLabels:
                  logging: enabled
      mutate:
        patchStrategicMerge:
          spec:
            template:
              spec:
                containers:
                  - name: fluentbit
                    image: fluent/fluent-bit:3.1
                    resources:
                      requests:
                        cpu: 50m
                        memory: 64Mi
                      limits:
                        cpu: 200m
                        memory: 128Mi
                    volumeMounts:
                      - name: app-logs
                        mountPath: /var/log/app
                        readOnly: true
                volumes:
                  - name: app-logs
                    emptyDir: {}
```

### Generate: Create NetworkPolicy on Namespace

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: generate-default-deny
spec:
  rules:
    - name: default-deny-on-namespace-creation
      match:
        any:
          - resources:
              kinds:
                - Namespace
              selector:
                matchLabels:
                  env: production
      exclude:
        any:
          - resources:
              namespaces:
                - kube-system
                - kube-public
                - kube-node-lease
      generate:
        synchronize: true  # Keep in sync if policy changes
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        name: default-deny-all
        namespace: "{{ request.object.metadata.name }}"
        data:
          spec:
            podSelector: {}
            policyTypes:
              - Ingress
              - Egress
```

### Verify Images: Cosign Signatures

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-image-signatures
spec:
  validationFailureAction: Enforce
  webhookTimeoutSeconds: 30
  rules:
    - name: verify-cosign
      match:
        any:
          - resources:
              kinds:
                - Pod
              namespaces:
                - production
      verifyImages:
        - imageReferences:
            - "ghcr.io/myorg/*"
          attestors:
            - entries:
                - keys:
                    publicKeys: |-
                      -----BEGIN PUBLIC KEY-----
                      MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...
                      -----END PUBLIC KEY-----
          mutateDigest: true
          verifyDigest: true
          required: true
    - name: verify-sbom-attestation
      match:
        any:
          - resources:
              kinds:
                - Pod
              namespaces:
                - production
      verifyImages:
        - imageReferences:
            - "ghcr.io/myorg/*"
          attestations:
            - type: https://cyclonedx.org/bom
              conditions:
                - all:
                    - key: "{{ components[].licenses[].expression }}"
                      operator: AllNotIn
                      value:
                        - "GPL-3.0"
                        - "AGPL-3.0"
```

---

## OPA Gatekeeper

Gatekeeper uses Open Policy Agent with Rego for policy logic. Policies have two parts: a `ConstraintTemplate` (defines the Rego logic) and a `Constraint` (applies it with parameters).

### Installation

```bash
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm install gatekeeper gatekeeper/gatekeeper \
  --namespace gatekeeper-system --create-namespace \
  --set replicas=3 \
  --set audit.replicas=2
```

### ConstraintTemplate: Required Labels

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequiredlabels
spec:
  crd:
    spec:
      names:
        kind: K8sRequiredLabels
      validation:
        openAPIV3Schema:
          type: object
          properties:
            labels:
              type: array
              items:
                type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequiredlabels

        violation[{"msg": msg}] {
          provided := {label | input.review.object.metadata.labels[label]}
          required := {label | label := input.parameters.labels[_]}
          missing := required - provided
          count(missing) > 0
          msg := sprintf("Missing required labels: %v", [missing])
        }
```

### Constraint: Apply Required Labels

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredLabels
metadata:
  name: require-team-labels
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: ["apps"]
        kinds: ["Deployment", "StatefulSet"]
    namespaces:
      - production
      - staging
  parameters:
    labels:
      - "app.kubernetes.io/name"
      - "app.kubernetes.io/team"
```

### ConstraintTemplate: Trusted Registries

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8strustedregistries
spec:
  crd:
    spec:
      names:
        kind: K8sTrustedRegistries
      validation:
        openAPIV3Schema:
          type: object
          properties:
            registries:
              type: array
              items:
                type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8strustedregistries

        violation[{"msg": msg}] {
          container := input_containers[_]
          not trusted_registry(container.image)
          msg := sprintf("Image '%v' is not from a trusted registry. Allowed: %v",
                         [container.image, input.parameters.registries])
        }

        trusted_registry(image) {
          registry := input.parameters.registries[_]
          startswith(image, registry)
        }

        input_containers[c] {
          c := input.review.object.spec.containers[_]
        }
        input_containers[c] {
          c := input.review.object.spec.initContainers[_]
        }
        input_containers[c] {
          c := input.review.object.spec.ephemeralContainers[_]
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sTrustedRegistries
metadata:
  name: trusted-registries
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
    namespaces:
      - production
  parameters:
    registries:
      - "ghcr.io/myorg/"
      - "registry.internal.io/"
```

### ConstraintTemplate: Resource Limits Required

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8sresourcelimits
spec:
  crd:
    spec:
      names:
        kind: K8sResourceLimits
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8sresourcelimits

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.resources.limits.memory
          msg := sprintf("Container '%v' has no memory limit", [container.name])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.resources.limits.cpu
          msg := sprintf("Container '%v' has no CPU limit", [container.name])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.resources.requests.memory
          msg := sprintf("Container '%v' has no memory request", [container.name])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.resources.requests.cpu
          msg := sprintf("Container '%v' has no CPU request", [container.name])
        }
```

---

## ValidatingAdmissionPolicy (K8s Native, v1.30+)

Kubernetes 1.30 graduated `ValidatingAdmissionPolicy` to GA. Policies use CEL (Common Expression Language) — no webhook, no external controller.

### Require Non-Root Containers

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: require-non-root
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
    namespaceSelector:
      matchLabels:
        env: production
  validations:
    - expression: >-
        object.spec.containers.all(c,
          has(c.securityContext) &&
          has(c.securityContext.runAsNonRoot) &&
          c.securityContext.runAsNonRoot == true
        )
      message: "All containers must set securityContext.runAsNonRoot to true."
    - expression: >-
        !has(object.spec.initContainers) ||
        object.spec.initContainers.all(c,
          has(c.securityContext) &&
          has(c.securityContext.runAsNonRoot) &&
          c.securityContext.runAsNonRoot == true
        )
      message: "All init containers must set securityContext.runAsNonRoot to true."
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: require-non-root-binding
spec:
  policyName: require-non-root
  validationActions:
    - Deny
  matchResources:
    namespaceSelector:
      matchLabels:
        env: production
```

### Require Resource Limits

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: require-resource-limits
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
  validations:
    - expression: >-
        object.spec.containers.all(c,
          has(c.resources) &&
          has(c.resources.limits) &&
          has(c.resources.limits.memory) &&
          has(c.resources.limits.cpu) &&
          has(c.resources.requests) &&
          has(c.resources.requests.memory) &&
          has(c.resources.requests.cpu)
        )
      message: "All containers must specify CPU and memory requests and limits."
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: require-resource-limits-binding
spec:
  policyName: require-resource-limits
  validationActions:
    - Deny
  matchResources:
    namespaceSelector:
      matchLabels:
        env: production
```

### Trusted Registries with Parameterized Policy

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: trusted-registries
spec:
  failurePolicy: Fail
  paramKind:
    apiVersion: v1
    kind: ConfigMap
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
  validations:
    - expression: >-
        object.spec.containers.all(c,
          params.data.registries.split(",").exists(r,
            c.image.startsWith(r)
          )
        )
      message: "Images must come from a trusted registry."
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: trusted-registries-params
  namespace: production
data:
  registries: "ghcr.io/myorg/,registry.internal.io/"
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: trusted-registries-binding
spec:
  policyName: trusted-registries
  paramRef:
    name: trusted-registries-params
    namespace: production
    parameterNotFoundAction: Deny
  validationActions:
    - Deny
  matchResources:
    namespaceSelector:
      matchLabels:
        env: production
```

---

## Policy Selection Decision Tree

| Criteria | Kyverno | OPA Gatekeeper | ValidatingAdmissionPolicy |
|---|---|---|---|
| **Policy language** | YAML patterns | Rego | CEL |
| **Learning curve** | Low | High (Rego) | Medium (CEL) |
| **Mutation support** | Yes (native) | Yes (assign/modify) | No |
| **Generation support** | Yes (create resources) | No | No |
| **Image verification** | Yes (Cosign, Notary) | No (use external) | No |
| **External dependency** | Kyverno controller | Gatekeeper controller | None (built-in) |
| **K8s version** | 1.25+ | 1.25+ | 1.30+ (GA) |
| **Best for** | Full policy lifecycle | Complex logic, existing OPA | Simple validation, no deps |

**Decision rules:**
1. Need mutation, generation, or image verification? **Kyverno** (only option with all three).
2. Existing OPA/Rego expertise or very complex policy logic? **Gatekeeper**.
3. Simple validation with zero external dependencies on K8s 1.30+? **ValidatingAdmissionPolicy**.
4. Running multiple? Use ValidatingAdmissionPolicy for basic checks + Kyverno for mutation/generation.

---

## Policy Library: Top 15 Production Policies

| # | Policy | Type | Engine |
|---|---|---|---|
| 1 | Require resource limits on all containers | Validate | Any |
| 2 | Restrict image registries to trusted sources | Validate | Any |
| 3 | Require standard labels (name, team, env) | Validate | Any |
| 4 | Enforce runAsNonRoot on all pods | Validate | Any |
| 5 | Enforce readOnlyRootFilesystem | Validate | Any |
| 6 | Drop ALL capabilities | Validate | Any |
| 7 | Disallow privileged containers | Validate | Any |
| 8 | Disallow hostNetwork, hostPID, hostIPC | Validate | Any |
| 9 | Require Cosign image signatures | VerifyImages | Kyverno |
| 10 | Auto-add security context defaults | Mutate | Kyverno |
| 11 | Generate default-deny NetworkPolicy on namespace | Generate | Kyverno |
| 12 | Disallow latest tag | Validate | Any |
| 13 | Enforce PDB exists for Deployments with >1 replica | Validate | Kyverno/Gatekeeper |
| 14 | Require liveness and readiness probes | Validate | Any |
| 15 | Enforce namespace quotas on creation | Generate | Kyverno |

---

## Audit Mode vs Enforce Mode Migration

### Phase 1: Audit Only (Week 1-2)

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-resource-limits
spec:
  validationFailureAction: Audit  # Log violations, don't block
  background: true                # Scan existing resources
  rules:
    - name: require-limits
      match:
        any:
          - resources:
              kinds:
                - Pod
      validate:
        message: "Resource limits are required."
        pattern:
          spec:
            containers:
              - resources:
                  limits:
                    cpu: "?*"
                    memory: "?*"
```

Check violations:

```bash
# Kyverno: check policy reports
kubectl get policyreport -A -o wide
kubectl get clusterpolicyreport -o wide

# Gatekeeper: check audit results
kubectl get constraints -o json | jq '.items[].status.violations'
```

### Phase 2: Warn (Week 3-4)

For OPA Gatekeeper, use `enforcementAction: warn`:

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sResourceLimits
metadata:
  name: require-limits
spec:
  enforcementAction: warn  # Warn in API response, don't block
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
```

For ValidatingAdmissionPolicy, use `Warn` action:

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: require-limits-binding
spec:
  policyName: require-resource-limits
  validationActions:
    - Warn   # Warn users, don't block
    - Audit  # Also log to audit log
```

### Phase 3: Enforce (Week 5+)

```yaml
# Kyverno
spec:
  validationFailureAction: Enforce

# Gatekeeper
spec:
  enforcementAction: deny

# ValidatingAdmissionPolicy
spec:
  validationActions:
    - Deny
```

Migration checklist:
1. Deploy policy in Audit mode.
2. Run background scan on all existing resources.
3. Fix all existing violations (or add exemptions).
4. Switch to Warn mode for 1-2 weeks.
5. Monitor for unexpected warnings in CI/CD pipelines.
6. Switch to Enforce mode.
7. Add policy to CI/CD pipeline (kyverno apply --dry-run, gator test).

---

## Quick Reference: Engine Capabilities

| Capability | Kyverno | Gatekeeper | VAP (Native) |
|---|---|---|---|
| Validate | YAML patterns | Rego | CEL |
| Mutate | patchStrategicMerge, patchesJson6902 | Assign, ModifySet | Not supported |
| Generate | Create/sync resources | Not supported | Not supported |
| Verify images | Cosign, Notary, keyless | Not supported | Not supported |
| Background scan | Yes (PolicyReport) | Yes (audit) | Yes (audit log) |
| Dry-run CLI | `kyverno apply` | `gator test` | N/A |
| Exemptions | PolicyException | Config (exempt namespaces) | matchResources |
| Webhook overhead | Medium (~50ms) | Medium (~50ms) | None (in-process) |
