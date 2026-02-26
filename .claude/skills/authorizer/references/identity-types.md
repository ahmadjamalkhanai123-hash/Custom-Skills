# Identity Types — Kubernetes Authorizer

## Human Users {#users}

Kubernetes has no built-in user objects. Users are authenticated externally via:

### OIDC Integration (Recommended)

```yaml
# kube-apiserver flags
--oidc-issuer-url=https://accounts.google.com         # or Dex/Keycloak/Okta
--oidc-client-id=kubernetes
--oidc-username-claim=email
--oidc-groups-claim=groups
--oidc-username-prefix=oidc:
--oidc-groups-prefix=oidc:
```

```bash
# kubeconfig with OIDC
users:
- name: alice@company.com
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      command: kubectl
      args: ["oidc-login", "get-token",
             "--oidc-issuer-url=https://sso.company.com",
             "--oidc-client-id=kubernetes",
             "--oidc-extra-scope=email,groups"]
```

### Dex (On-Prem OIDC Broker)

```yaml
# Dex connector for LDAP
connectors:
  - type: ldap
    id: ldap
    name: LDAP
    config:
      host: ldap.company.com:389
      bindDN: cn=service-account,dc=company,dc=com
      bindPW: "$LDAP_BIND_PW"
      userSearch:
        baseDN: ou=Users,dc=company,dc=com
        filter: "(objectClass=person)"
        username: uid
        idAttr: DN
        emailAttr: mail
        nameAttr: displayName
      groupSearch:
        baseDN: ou=Groups,dc=company,dc=com
        filter: "(objectClass=groupOfNames)"
        nameAttr: cn
```

### Keycloak OIDC

```yaml
# Keycloak realm client config
clientId: kubernetes
protocol: openid-connect
standardFlowEnabled: true
directAccessGrantsEnabled: false
attributes:
  "access.token.lifespan": 3600
protocolMappers:
  - name: groups
    protocol: openid-connect
    protocolMapper: oidc-group-membership-mapper
    config:
      claim.name: groups
      full.path: "false"
      id.token.claim: "true"
      access.token.claim: "true"
```

---

## Groups {#groups}

Groups are populated from OIDC `groups` claim or static tokens.

```yaml
# Group-based ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: bind-platform-engineers
subjects:
  - kind: Group
    name: "oidc:platform-engineers"   # prefix from --oidc-groups-prefix
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: authorizer:sre:platform-operator
  apiGroup: rbac.authorization.k8s.io
```

### Built-in Groups

| Group | Purpose |
|-------|---------|
| `system:masters` | Full cluster admin (maps to cluster-admin) |
| `system:authenticated` | All authenticated users |
| `system:unauthenticated` | Anonymous requests |
| `system:nodes` | All kubelets |
| `system:serviceaccounts` | All service accounts |
| `system:serviceaccounts:<namespace>` | SAs in specific namespace |

---

## Service Accounts {#service-accounts}

### Minimal Service Account (Least Privilege)

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: backend-app-sa
  namespace: team-backend
  annotations:
    # Cloud IAM binding (see cloud-auth-patterns.md)
    eks.amazonaws.com/role-arn: "arn:aws:iam::123456789:role/backend-app-role"
automountServiceAccountToken: false   # Disable auto-mount; use projected volumes
```

### Projected Service Account Token (Short-lived)

```yaml
apiVersion: v1
kind: Pod
spec:
  serviceAccountName: backend-app-sa
  volumes:
    - name: sa-token
      projected:
        sources:
          - serviceAccountToken:
              path: token
              expirationSeconds: 3600        # 1 hour (never >86400)
              audience: "https://kubernetes.default.svc"
  containers:
    - name: app
      volumeMounts:
        - name: sa-token
          mountPath: /var/run/secrets/kubernetes.io/serviceaccount
          readOnly: true
```

### ServiceAccount for Operators (Cross-Namespace)

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: operator-sa
  namespace: operators
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: authorizer:operator:watch-all
rules:
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
    verbs: ["update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: bind-operator-sa
subjects:
  - kind: ServiceAccount
    name: operator-sa
    namespace: operators
roleRef:
  kind: ClusterRole
  name: authorizer:operator:watch-all
  apiGroup: rbac.authorization.k8s.io
```

---

## AI / LLM Agents {#ai-agents}

AI agents running in Kubernetes need carefully scoped identity.

### Principles for AI Agent Authorization
1. **Minimal surface area**: Agents should only access resources they process
2. **No exec or portforward**: Never grant `pods/exec` to agent SAs
3. **Separate SA per agent**: Never share SAs between agents
4. **Egress NetworkPolicy**: Restrict outbound to specific endpoints
5. **ReadOnly by default**: Most agents need read-only cluster access

### AI Agent ServiceAccount Pattern

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: llm-agent-sa
  namespace: ai-workloads
  annotations:
    # AWS: bind to IAM role for model inference (Bedrock/SageMaker)
    eks.amazonaws.com/role-arn: "arn:aws:iam::123456789:role/llm-agent-bedrock"
    # GCP: bind to Google SA for Vertex AI
    iam.gke.io/gcp-service-account: "llm-agent@project.iam.gserviceaccount.com"
automountServiceAccountToken: false
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: authorizer:ai:agent-operator
  namespace: ai-workloads
rules:
  # Read workload status for orchestration decisions
  - apiGroups: [""]
    resources: ["pods", "services", "configmaps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch"]
  # Read-only secrets access (for model API keys via ExternalSecrets)
  - apiGroups: ["external-secrets.io"]
    resources: ["externalsecrets"]
    verbs: ["get", "list"]
  # NO: pods/exec, pods/portforward, secrets write
---
# Egress NetworkPolicy — agents can only reach model endpoints
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ai-agent-egress
  namespace: ai-workloads
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: ai-agent
  policyTypes: ["Egress"]
  egress:
    - to: []   # Deny all egress
    - ports:
        - port: 443  # HTTPS to model APIs only
      to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
```

### Multi-Agent Orchestration RBAC

```yaml
# Orchestrator agent: can schedule sub-agents
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: authorizer:ai:orchestrator
  namespace: ai-workloads
rules:
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["create", "get", "list", "watch", "delete"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
  # Can read results from ConfigMaps/Redis SA
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch", "create", "update"]
```

---

## Nodes / Kubelet {#nodes}

```yaml
# Node Authorizer handles node access automatically
# Kubelet uses: system:node:<nodeName> user, system:nodes group
# NodeRestriction admission plugin enforces kubelet can only modify its own node

# Verify node authorizer is enabled
kube-apiserver --authorization-mode=Node,RBAC,...

# For cluster-autoscaler: needs node management permissions
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: authorizer:infra:cluster-autoscaler
rules:
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["watch", "list", "get", "update", "patch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["watch", "list", "get", "delete"]
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["create", "patch"]
```

---

## Cluster Federation Identity {#clusters}

Used with Cluster API, GKE Hub, or ArgoCD multi-cluster.

```yaml
# ArgoCD cluster secret (registers remote cluster)
apiVersion: v1
kind: Secret
metadata:
  name: production-cluster
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: cluster
type: Opaque
stringData:
  name: production
  server: https://prod-cluster.example.com
  config: |
    {
      "bearerToken": "<token>",
      "tlsClientConfig": {
        "insecure": false,
        "caData": "<base64-ca>"
      }
    }
```

```yaml
# ClusterSet RBAC (Fleet / ACM)
# Hub cluster defines ManagedClusterSet RBAC
apiVersion: rbac.open-cluster-management.io/v1
kind: ManagedClusterSetBinding
metadata:
  name: default-clusterset
  namespace: team-backend
spec:
  clusterSet: default
```
