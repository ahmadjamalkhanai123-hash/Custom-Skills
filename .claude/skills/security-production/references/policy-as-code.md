# Policy-as-Code

## Policy Engine Selection

| Scenario | Recommended | Why |
|----------|-------------|-----|
| K8s-native, simple rules | **Kyverno** | YAML-based, no Rego, easy to read |
| Complex org-wide logic | **OPA Gatekeeper** | Full Rego power, cross-system reuse |
| Both simple + complex | **Kyverno + OPA** | Best combination for enterprises |
| Non-K8s (Terraform, API) | **OPA** | Works outside Kubernetes |

## Kyverno ClusterPolicies

### Non-Root Enforcement

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-non-root
  annotations:
    policies.kyverno.io/title: Require Non-Root Containers
    policies.kyverno.io/category: Pod Security
    policies.kyverno.io/severity: high
    policies.kyverno.io/description: >
      All containers must run as non-root user.
      Containers running as root increase the risk of host compromise.
spec:
  validationFailureAction: Enforce     # Enforce (reject) or Audit (log)
  background: true                      # Also scan existing resources
  rules:
    - name: validate-runAsNonRoot
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaces: ["production", "staging"]
      validate:
        message: "Containers must run as non-root. Set runAsNonRoot: true and runAsUser >= 1000."
        pattern:
          spec:
            =(securityContext):
              =(runAsNonRoot): true
            containers:
              - =(securityContext):
                  =(runAsNonRoot): true
                  =(runAsUser): ">999"
            =(initContainers):
              - =(securityContext):
                  =(runAsNonRoot): true
```

### Require Resource Limits

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-resource-limits
spec:
  validationFailureAction: Enforce
  background: true
  rules:
    - name: validate-resources
      match:
        any:
          - resources:
              kinds: [Pod]
      validate:
        message: "CPU and memory limits are required for all containers."
        foreach:
          - list: "request.object.spec.containers"
            deny:
              conditions:
                any:
                  - key: "{{ element.resources.limits.cpu || '' }}"
                    operator: Equals
                    value: ""
                  - key: "{{ element.resources.limits.memory || '' }}"
                    operator: Equals
                    value: ""
```

### Restrict Privileged Containers

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: restrict-privileged
spec:
  validationFailureAction: Enforce
  background: true
  rules:
    - name: no-privileged
      match:
        any:
          - resources:
              kinds: [Pod]
      validate:
        message: "Privileged containers are not allowed."
        pattern:
          spec:
            containers:
              - =(securityContext):
                  =(privileged): "false"
            =(initContainers):
              - =(securityContext):
                  =(privileged): "false"

    - name: no-host-namespaces
      match:
        any:
          - resources:
              kinds: [Pod]
      validate:
        message: "Host namespaces (hostNetwork, hostPID, hostIPC) are not allowed."
        pattern:
          spec:
            =(hostNetwork): "false"
            =(hostPID): "false"
            =(hostIPC): "false"
```

### Require Image Digest (Immutable)

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-image-digest
spec:
  validationFailureAction: Enforce
  background: true
  rules:
    - name: image-digest-required
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaces: ["production"]
      validate:
        message: "Production images must be pinned to a digest (@sha256:...), not a mutable tag."
        foreach:
          - list: "request.object.spec.containers"
            deny:
              conditions:
                all:
                  - key: "{{ contains(element.image, '@sha256:') }}"
                    operator: Equals
                    value: false
```

### Generate Default-Deny NetworkPolicy

```yaml
# Kyverno Generate: auto-create NetworkPolicy for every new namespace
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: generate-default-deny-netpol
spec:
  rules:
    - name: generate-deny-all
      match:
        any:
          - resources:
              kinds: [Namespace]
              selector:
                matchExpressions:
                  - key: kubernetes.io/metadata.name
                    operator: NotIn
                    values: ["kube-system", "kube-public", "kube-node-lease"]
      generate:
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        name: default-deny-all
        namespace: "{{request.object.metadata.name}}"
        synchronize: true       # Keep in sync if policy changes
        data:
          spec:
            podSelector: {}
            policyTypes: [Ingress, Egress]
```

### Verify Image Signatures (Cosign)

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-image-signatures
spec:
  validationFailureAction: Enforce
  background: false          # Signatures must be checked at admission
  webhookTimeoutSeconds: 30
  rules:
    - name: verify-signature
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaces: ["production"]
      verifyImages:
        - imageReferences:
            - "ghcr.io/myorg/*"
          attestors:
            - count: 1
              entries:
                - keyless:
                    subject: "https://github.com/myorg/*/.github/workflows/*.yaml@refs/heads/main"
                    issuer: "https://token.actions.githubusercontent.com"
          mutateDigest: true     # Rewrite tag to digest after verification
          required: true
```

---

## OPA Gatekeeper

### ConstraintTemplate: Require Labels

```yaml
# ConstraintTemplate defines the Rego logic + CRD schema
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: requirelabels
spec:
  crd:
    spec:
      names:
        kind: RequireLabels
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
        package requirelabels

        violation[{"msg": msg}] {
          provided := {label | input.review.object.metadata.labels[label]}
          required := {label | label := input.parameters.labels[_]}
          missing := required - provided
          count(missing) > 0
          msg := sprintf("Missing required labels: %v", [missing])
        }
---
# Constraint: apply the template to Deployments
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: RequireLabels
metadata:
  name: deployment-must-have-labels
spec:
  enforcementAction: deny     # deny | dryrun | warn
  match:
    kinds:
      - apiGroups: ["apps"]
        kinds: ["Deployment"]
    namespaces: ["production", "staging"]
  parameters:
    labels:
      - app
      - version
      - team
      - cost-center
```

### ConstraintTemplate: No Latest Tag

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: bannedimagetagstemplate
spec:
  crd:
    spec:
      names:
        kind: BannedImageTags
      validation:
        openAPIV3Schema:
          type: object
          properties:
            tags:
              type: array
              items: {type: string}
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package bannedimagetags

        violation[{"msg": msg}] {
          container := input_containers[_]
          tag := split(container.image, ":")[1]
          banned := input.parameters.tags[_]
          tag == banned
          msg := sprintf("Container '%s' uses banned tag '%s'. Use image@sha256:digest instead.", [container.name, tag])
        }

        # Also flag images with no tag (defaults to latest)
        violation[{"msg": msg}] {
          container := input_containers[_]
          not contains(container.image, ":")
          msg := sprintf("Container '%s' has no tag. Specify a digest.", [container.name])
        }

        input_containers[c] {
          c := input.review.object.spec.containers[_]
        }
        input_containers[c] {
          c := input.review.object.spec.initContainers[_]
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: BannedImageTags
metadata:
  name: ban-latest-tag
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: ["*"]
        kinds: ["Pod"]
  parameters:
    tags: ["latest", "master", "main", "dev", "test"]
```

### Gatekeeper Audit Mode

```bash
# Start with audit (dryrun) before enforcement
kubectl patch constraint <name> \
  --type=merge \
  -p '{"spec":{"enforcementAction":"dryrun"}}'

# Check audit violations
kubectl describe constraint <name>

# Promote to warn (allow but show warnings)
kubectl patch constraint <name> \
  --type=merge \
  -p '{"spec":{"enforcementAction":"warn"}}'

# Finally enforce (reject violations)
kubectl patch constraint <name> \
  --type=merge \
  -p '{"spec":{"enforcementAction":"deny"}}'
```

---

## Policy Pipeline: Dev to Prod

```
Developer commits → Pre-commit (conftest) → CI (kyverno test) → Staging (audit) → Prod (enforce)

1. Pre-commit: conftest test --policy ./policies/ ./manifests/
2. CI: kyverno test ./policies/ --test-case-path ./tests/
3. Staging: enforcementAction: warn (visible but not blocking)
4. Production: enforcementAction: deny (full enforcement)
```

### Conftest (Policy Testing in CI)

```bash
# Install conftest
brew install conftest   # or download from GitHub

# Test K8s manifests against OPA policies
conftest test deployment.yaml \
  --policy policies/ \
  --namespace kubernetes

# Test Terraform plans
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary > tfplan.json
conftest test tfplan.json --policy policies/terraform/
```

### Kyverno Policy Testing

```yaml
# tests/kyverno-test.yaml
name: require-non-root-test
policies:
  - ../policies/require-non-root.yaml
resources:
  - resources/pass-pod.yaml
  - resources/fail-pod.yaml
results:
  - policy: require-non-root
    rule: validate-runAsNonRoot
    resource: pass-pod
    result: pass
  - policy: require-non-root
    rule: validate-runAsNonRoot
    resource: fail-pod
    result: fail
```
