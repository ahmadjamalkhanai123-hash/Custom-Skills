# Policy Engines — OPA/Gatekeeper + Kyverno

## OPA / Gatekeeper {#opa}

### Architecture

```
Admission Request
      │
      ▼
MutatingWebhookConfiguration ──► Gatekeeper Webhook ──► OPA Policy Engine
ValidatingWebhookConfiguration ──► Gatekeeper Webhook ──► ConstraintTemplate
                                                           └── Constraint
```

### Installation

```bash
# Gatekeeper v3.x
kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/v3.17.1/deploy/gatekeeper.yaml

# Verify
kubectl get pods -n gatekeeper-system
```

### ConstraintTemplate: Require Labels

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: requiredlabels
spec:
  crd:
    spec:
      names:
        kind: RequiredLabels
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
        package requiredlabels

        violation[{"msg": msg, "details": {"missing_labels": missing}}] {
          provided := {label | input.review.object.metadata.labels[label]}
          required := {label | label := input.parameters.labels[_]}
          missing := required - provided
          count(missing) > 0
          msg := sprintf("Missing required labels: %v", [missing])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: RequiredLabels
metadata:
  name: require-app-labels
spec:
  enforcementAction: deny        # deny | warn | dryrun
  match:
    kinds:
      - apiGroups: ["apps"]
        kinds: ["Deployment", "StatefulSet", "DaemonSet"]
    namespaces: []               # empty = all namespaces
    excludedNamespaces: ["kube-system", "gatekeeper-system"]
  parameters:
    labels:
      - "app.kubernetes.io/name"
      - "app.kubernetes.io/version"
      - "app.kubernetes.io/managed-by"
```

### ConstraintTemplate: No Privileged Containers

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: noprivilegedcontainers
spec:
  crd:
    spec:
      names:
        kind: NoPrivilegedContainers
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package noprivilegedcontainers

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          container.securityContext.privileged == true
          msg := sprintf("Container %v cannot be privileged", [container.name])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.initContainers[_]
          container.securityContext.privileged == true
          msg := sprintf("Init container %v cannot be privileged", [container.name])
        }
---
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: NoPrivilegedContainers
metadata:
  name: no-privileged-containers
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
    excludedNamespaces: ["kube-system"]
```

### ConstraintTemplate: Require Non-Root

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: requirenonroot
spec:
  crd:
    spec:
      names:
        kind: RequireNonRoot
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package requirenonroot

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          not container.securityContext.runAsNonRoot
          msg := sprintf("Container %v must set runAsNonRoot=true", [container.name])
        }

        violation[{"msg": msg}] {
          container := input.review.object.spec.containers[_]
          container.securityContext.runAsUser == 0
          msg := sprintf("Container %v cannot run as root (UID 0)", [container.name])
        }
```

### OPA Library: Gatekeeper Constraint Library

```bash
# Clone the official Gatekeeper library
git clone https://github.com/open-policy-agent/gatekeeper-library

# Apply all PSP-equivalent policies
kubectl apply -f gatekeeper-library/library/pod-security-policy/
```

---

## Kyverno {#kyverno}

### Architecture

```
Admission Request ──► Kyverno Admission Webhook
                            │
                    ClusterPolicy / Policy
                            │
                    validate / mutate / generate / verify-images
```

### Installation

```bash
# Kyverno v1.13+
kubectl create -f https://github.com/kyverno/kyverno/releases/download/v1.13.4/install.yaml

# Verify
kubectl get pods -n kyverno
```

### ClusterPolicy: Require Non-Root + Drop Capabilities

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-non-root-drop-caps
  annotations:
    policies.kyverno.io/title: Require Non-Root with Dropped Capabilities
    policies.kyverno.io/category: Pod Security
    policies.kyverno.io/severity: high
    policies.kyverno.io/description: >-
      Requires all containers to run as non-root and drop ALL capabilities.
spec:
  validationFailureAction: Enforce      # Enforce | Audit
  background: true
  rules:
    - name: check-runAsNonRoot
      match:
        any:
          - resources:
              kinds: ["Pod"]
      exclude:
        any:
          - resources:
              namespaces: ["kube-system", "kyverno"]
      validate:
        message: "Container must set runAsNonRoot=true and drop ALL capabilities."
        pattern:
          spec:
            containers:
              - securityContext:
                  runAsNonRoot: true
                  capabilities:
                    drop: ["ALL"]
            initContainers:
              - (name): "?*"
                securityContext:
                  runAsNonRoot: true
```

### ClusterPolicy: Disallow Latest Tag

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: disallow-latest-tag
  annotations:
    policies.kyverno.io/title: Disallow Latest Tag
    policies.kyverno.io/category: Best Practices
    policies.kyverno.io/severity: medium
spec:
  validationFailureAction: Enforce
  background: true
  rules:
    - name: require-image-tag
      match:
        any:
          - resources:
              kinds: ["Pod"]
      validate:
        message: "Using 'latest' image tag is not allowed. Use a specific version."
        foreach:
          - list: "request.object.spec.containers"
            deny:
              conditions:
                any:
                  - key: "{{element.image}}"
                    operator: Equals
                    value: "*:latest"
                  - key: "{{element.image}}"
                    operator: NotContains
                    value: ":"
```

### ClusterPolicy: Mutate — Add Default Labels

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: add-default-labels
spec:
  rules:
    - name: add-managed-by-label
      match:
        any:
          - resources:
              kinds: ["Deployment", "StatefulSet", "DaemonSet"]
      mutate:
        patchStrategicMerge:
          metadata:
            labels:
              app.kubernetes.io/managed-by: kyverno
          spec:
            template:
              metadata:
                labels:
                  app.kubernetes.io/managed-by: kyverno
```

### ClusterPolicy: Generate — Auto NetworkPolicy

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: generate-default-networkpolicy
spec:
  rules:
    - name: generate-default-deny
      match:
        any:
          - resources:
              kinds: ["Namespace"]
      generate:
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        name: default-deny-all
        namespace: "{{request.object.metadata.name}}"
        synchronize: true
        data:
          spec:
            podSelector: {}
            policyTypes:
              - Ingress
              - Egress
```

### ClusterPolicy: Verify Image Signatures (Cosign)

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-image-signatures
spec:
  validationFailureAction: Enforce
  rules:
    - name: check-image-signature
      match:
        any:
          - resources:
              kinds: ["Pod"]
      verifyImages:
        - imageReferences:
            - "registry.company.com/*"
          attestors:
            - count: 1
              entries:
                - keys:
                    publicKeys: |-
                      -----BEGIN PUBLIC KEY-----
                      <COSIGN_PUBLIC_KEY>
                      -----END PUBLIC KEY-----
```

## Kyverno Policy Library

```bash
# Apply Kyverno best-practice policy set
kubectl apply -f https://github.com/kyverno/kyverno/raw/main/config/best-practices/

# Apply PSA baseline equivalent
kubectl apply -f https://github.com/kyverno/policies/tree/main/pod-security/baseline/

# Apply PSA restricted equivalent
kubectl apply -f https://github.com/kyverno/policies/tree/main/pod-security/restricted/
```

## Policy Engine Comparison

| Feature | OPA/Gatekeeper | Kyverno |
|---------|---------------|---------|
| Language | Rego | YAML-native |
| Mutation | No (separate) | Yes |
| Generation | No | Yes |
| Image verify | No | Yes (Cosign) |
| Learning curve | High | Low |
| Library | gatekeeper-library | kyverno/policies |
| Audit mode | dryrun | Audit |
| Multi-tenancy | ConstraintTemplate | Policy/ClusterPolicy |

**Recommendation**: Use Kyverno for teams new to policy-as-code. Use OPA for complex Rego logic.
