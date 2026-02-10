#!/usr/bin/env python3
"""
Kubernetes Mastery — Project Scaffolder

Generates a complete Kubernetes setup for any project based on tier and options.

Usage:
    python scaffold_k8s.py <name> --tier <1|2|3|4|5> --path <output-dir>
        [--provider <eks|gke|aks|onprem>]
        [--packaging <helm|kustomize|raw>]
        [--gitops <argocd|flux|none>]
        [--mesh <none|istio|linkerd|cilium>]
        [--secrets <k8s|sealed|vault>]

Examples:
    python scaffold_k8s.py myapp --tier 1 --path ./myapp
    python scaffold_k8s.py api --tier 2 --path ./api --packaging helm
    python scaffold_k8s.py platform --tier 3 --path ./platform --gitops argocd --secrets vault
    python scaffold_k8s.py enterprise --tier 4 --path ./enterprise --mesh istio --secrets vault
    python scaffold_k8s.py fleet --tier 5 --path ./fleet --provider eks --mesh cilium
"""

import argparse
import os
import sys
import textwrap
from pathlib import Path

# ── Manifest Templates ───────────────────────────────────────────────────────

NAMESPACE_YAML = textwrap.dedent("""\
    apiVersion: v1
    kind: Namespace
    metadata:
      name: {namespace}
      labels:
        app.kubernetes.io/managed-by: k8s-mastery
        app.kubernetes.io/part-of: {name}
    {pss_labels}
""")

DEPLOYMENT_YAML = textwrap.dedent("""\
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: {name}
      namespace: {namespace}
      labels:
        app.kubernetes.io/name: {name}
        app.kubernetes.io/version: "1.0.0"
        app.kubernetes.io/component: server
    spec:
      replicas: {replicas}
      revisionHistoryLimit: 5
      selector:
        matchLabels:
          app.kubernetes.io/name: {name}
      strategy:
        type: RollingUpdate
        rollingUpdate:
          maxSurge: 1
          maxUnavailable: 0
      template:
        metadata:
          labels:
            app.kubernetes.io/name: {name}
            app.kubernetes.io/version: "1.0.0"
          annotations:
            prometheus.io/scrape: "true"
            prometheus.io/port: "8080"
        spec:
          serviceAccountName: {name}
          automountServiceAccountToken: false
          terminationGracePeriodSeconds: 30
          securityContext:
            runAsNonRoot: true
            runAsUser: 1001
            runAsGroup: 1001
            fsGroup: 1001
            seccompProfile:
              type: RuntimeDefault
          {topology_spread}
          containers:
            - name: {name}
              image: {image}
              ports:
                - name: http
                  containerPort: 8080
              envFrom:
                - configMapRef:
                    name: {name}-config
              resources:
                requests:
                  cpu: {cpu_request}
                  memory: {mem_request}
                limits:
                  cpu: {cpu_limit}
                  memory: {mem_limit}
              securityContext:
                allowPrivilegeEscalation: false
                readOnlyRootFilesystem: true
                capabilities:
                  drop: ["ALL"]
              {probes}
              volumeMounts:
                - name: tmp
                  mountPath: /tmp
          volumes:
            - name: tmp
              emptyDir:
                sizeLimit: 64Mi
""")

SERVICE_YAML = textwrap.dedent("""\
    apiVersion: v1
    kind: Service
    metadata:
      name: {name}
      namespace: {namespace}
      labels:
        app.kubernetes.io/name: {name}
    spec:
      type: ClusterIP
      ports:
        - port: 80
          targetPort: http
          protocol: TCP
          name: http
      selector:
        app.kubernetes.io/name: {name}
""")

CONFIGMAP_YAML = textwrap.dedent("""\
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: {name}-config
      namespace: {namespace}
    data:
      APP_ENV: "{env}"
      LOG_LEVEL: "info"
      PORT: "8080"
""")

SA_YAML = textwrap.dedent("""\
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: {name}
      namespace: {namespace}
      labels:
        app.kubernetes.io/name: {name}
    automountServiceAccountToken: false
""")

PDB_YAML = textwrap.dedent("""\
    apiVersion: policy/v1
    kind: PodDisruptionBudget
    metadata:
      name: {name}-pdb
      namespace: {namespace}
    spec:
      minAvailable: {min_available}
      selector:
        matchLabels:
          app.kubernetes.io/name: {name}
""")

HPA_YAML = textwrap.dedent("""\
    apiVersion: autoscaling/v2
    kind: HorizontalPodAutoscaler
    metadata:
      name: {name}-hpa
      namespace: {namespace}
    spec:
      scaleTargetRef:
        apiVersion: apps/v1
        kind: Deployment
        name: {name}
      minReplicas: {min_replicas}
      maxReplicas: {max_replicas}
      metrics:
        - type: Resource
          resource:
            name: cpu
            target:
              type: Utilization
              averageUtilization: 70
        - type: Resource
          resource:
            name: memory
            target:
              type: Utilization
              averageUtilization: 80
      behavior:
        scaleDown:
          stabilizationWindowSeconds: 300
        scaleUp:
          stabilizationWindowSeconds: 30
""")

NETPOL_DENY_YAML = textwrap.dedent("""\
    apiVersion: networking.k8s.io/v1
    kind: NetworkPolicy
    metadata:
      name: default-deny-all
      namespace: {namespace}
    spec:
      podSelector: {{}}
      policyTypes: [Ingress, Egress]
    ---
    apiVersion: networking.k8s.io/v1
    kind: NetworkPolicy
    metadata:
      name: allow-dns
      namespace: {namespace}
    spec:
      podSelector: {{}}
      policyTypes: [Egress]
      egress:
        - to:
            - namespaceSelector: {{}}
              podSelector:
                matchLabels:
                  k8s-app: kube-dns
          ports:
            - protocol: UDP
              port: 53
""")

RBAC_YAML = textwrap.dedent("""\
    apiVersion: rbac.authorization.k8s.io/v1
    kind: Role
    metadata:
      name: {name}-developer
      namespace: {namespace}
    rules:
      - apiGroups: ["apps"]
        resources: ["deployments", "replicasets"]
        verbs: ["get", "list", "watch", "create", "update", "patch"]
      - apiGroups: [""]
        resources: ["pods", "pods/log", "services", "configmaps", "events"]
        verbs: ["get", "list", "watch"]
    ---
    apiVersion: rbac.authorization.k8s.io/v1
    kind: RoleBinding
    metadata:
      name: {name}-developer-binding
      namespace: {namespace}
    subjects:
      - kind: Group
        name: "developers"
        apiGroup: rbac.authorization.k8s.io
    roleRef:
      kind: Role
      name: {name}-developer
      apiGroup: rbac.authorization.k8s.io
""")

INGRESS_YAML = textwrap.dedent("""\
    apiVersion: networking.k8s.io/v1
    kind: Ingress
    metadata:
      name: {name}-ingress
      namespace: {namespace}
      annotations:
        cert-manager.io/cluster-issuer: letsencrypt-prod
        nginx.ingress.kubernetes.io/ssl-redirect: "true"
    spec:
      ingressClassName: nginx
      tls:
        - hosts:
            - {name}.example.com
          secretName: {name}-tls
      rules:
        - host: {name}.example.com
          http:
            paths:
              - path: /
                pathType: Prefix
                backend:
                  service:
                    name: {name}
                    port:
                      name: http
""")

SERVICEMONITOR_YAML = textwrap.dedent("""\
    apiVersion: monitoring.coreos.com/v1
    kind: ServiceMonitor
    metadata:
      name: {name}-monitor
      namespace: {namespace}
    spec:
      selector:
        matchLabels:
          app.kubernetes.io/name: {name}
      endpoints:
        - port: http
          path: /metrics
          interval: 30s
""")

SEALED_SECRET_YAML = textwrap.dedent("""\
    # Generate with: kubeseal --format=yaml < secret.yaml > sealed-secret.yaml
    # This is a placeholder — replace encryptedData with actual sealed values
    apiVersion: bitnami.com/v1alpha1
    kind: SealedSecret
    metadata:
      name: {name}-secrets
      namespace: {namespace}
    spec:
      encryptedData:
        DB_PASSWORD: "<SEALED_VALUE>"
        API_KEY: "<SEALED_VALUE>"
      template:
        metadata:
          name: {name}-secrets
          namespace: {namespace}
        type: Opaque
""")

EXTERNAL_SECRET_YAML = textwrap.dedent("""\
    apiVersion: external-secrets.io/v1beta1
    kind: ExternalSecret
    metadata:
      name: {name}-secrets
      namespace: {namespace}
    spec:
      refreshInterval: 1h
      secretStoreRef:
        name: vault-backend
        kind: ClusterSecretStore
      target:
        name: {name}-secrets
        creationPolicy: Owner
      data:
        - secretKey: DB_PASSWORD
          remoteRef:
            key: services/{name}/database
            property: password
        - secretKey: API_KEY
          remoteRef:
            key: services/{name}/api
            property: key
""")

ARGOCD_APP_YAML = textwrap.dedent("""\
    apiVersion: argoproj.io/v1alpha1
    kind: Application
    metadata:
      name: {name}
      namespace: argocd
      finalizers:
        - resources-finalizer.argocd.argoproj.io
    spec:
      project: default
      source:
        repoURL: https://github.com/org/{name}-gitops
        targetRevision: main
        path: {gitops_path}
      destination:
        server: https://kubernetes.default.svc
        namespace: {namespace}
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
        retry:
          limit: 5
          backoff:
            duration: 5s
            factor: 2
            maxDuration: 3m
""")

VELERO_YAML = textwrap.dedent("""\
    apiVersion: velero.io/v1
    kind: Schedule
    metadata:
      name: {name}-daily-backup
      namespace: velero
    spec:
      schedule: "0 2 * * *"
      template:
        includedNamespaces: ["{namespace}"]
        storageLocation: default
        ttl: 720h
""")

KUSTOMIZATION_YAML = textwrap.dedent("""\
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization

    namespace: {namespace}

    resources:
    {resources}

    commonLabels:
      app.kubernetes.io/name: {name}
      app.kubernetes.io/managed-by: kustomize
""")

# ── Probe Templates ──────────────────────────────────────────────────────────

BASIC_PROBES = textwrap.dedent("""\
    livenessProbe:
                httpGet:
                  path: /health
                  port: http
                initialDelaySeconds: 15
                periodSeconds: 20
              readinessProbe:
                httpGet:
                  path: /health/ready
                  port: http
                initialDelaySeconds: 5
                periodSeconds: 10""")

FULL_PROBES = textwrap.dedent("""\
    startupProbe:
                httpGet:
                  path: /health
                  port: http
                initialDelaySeconds: 5
                periodSeconds: 5
                failureThreshold: 30
              livenessProbe:
                httpGet:
                  path: /health
                  port: http
                periodSeconds: 15
                timeoutSeconds: 3
                failureThreshold: 3
              readinessProbe:
                httpGet:
                  path: /health/ready
                  port: http
                periodSeconds: 5
                timeoutSeconds: 3
                failureThreshold: 3
              lifecycle:
                preStop:
                  exec:
                    command: ["/bin/sh", "-c", "sleep 5"]""")

TOPOLOGY_SPREAD = textwrap.dedent("""\
    topologySpreadConstraints:
            - maxSkew: 1
              topologyKey: topology.kubernetes.io/zone
              whenUnsatisfiable: DoNotSchedule
              labelSelector:
                matchLabels:
                  app.kubernetes.io/name: {name}
            - maxSkew: 1
              topologyKey: kubernetes.io/hostname
              whenUnsatisfiable: ScheduleAnyway
              labelSelector:
                matchLabels:
                  app.kubernetes.io/name: {name}""")

# ── Tier Configurations ──────────────────────────────────────────────────────

TIER_CONFIG = {
    1: {
        "replicas": 1, "cpu_request": "100m", "mem_request": "128Mi",
        "cpu_limit": "500m", "mem_limit": "512Mi",
        "probes": BASIC_PROBES, "topology": "", "pss": "",
        "files": ["namespace", "sa", "configmap", "deployment", "service"],
    },
    2: {
        "replicas": 3, "cpu_request": "250m", "mem_request": "256Mi",
        "cpu_limit": "1", "mem_limit": "1Gi",
        "probes": FULL_PROBES, "topology": TOPOLOGY_SPREAD, "pss": "restricted",
        "files": ["namespace", "sa", "rbac", "configmap", "deployment", "service",
                  "pdb", "hpa", "netpol", "ingress", "servicemonitor"],
    },
    3: {
        "replicas": 3, "cpu_request": "250m", "mem_request": "256Mi",
        "cpu_limit": "1", "mem_limit": "1Gi",
        "probes": FULL_PROBES, "topology": TOPOLOGY_SPREAD, "pss": "restricted",
        "files": ["namespace", "sa", "rbac", "configmap", "deployment", "service",
                  "pdb", "hpa", "netpol", "ingress", "servicemonitor", "argocd", "velero"],
    },
    4: {
        "replicas": 3, "cpu_request": "250m", "mem_request": "256Mi",
        "cpu_limit": "2", "mem_limit": "2Gi",
        "probes": FULL_PROBES, "topology": TOPOLOGY_SPREAD, "pss": "restricted",
        "files": ["namespace", "sa", "rbac", "configmap", "deployment", "service",
                  "pdb", "hpa", "netpol", "ingress", "servicemonitor", "argocd", "velero"],
    },
    5: {
        "replicas": 5, "cpu_request": "500m", "mem_request": "512Mi",
        "cpu_limit": "4", "mem_limit": "4Gi",
        "probes": FULL_PROBES, "topology": TOPOLOGY_SPREAD, "pss": "restricted",
        "files": ["namespace", "sa", "rbac", "configmap", "deployment", "service",
                  "pdb", "hpa", "netpol", "ingress", "servicemonitor", "argocd", "velero"],
    },
}

FILE_GENERATORS = {
    "namespace": ("namespace.yaml", NAMESPACE_YAML),
    "sa": ("serviceaccount.yaml", SA_YAML),
    "rbac": ("rbac.yaml", RBAC_YAML),
    "configmap": ("configmap.yaml", CONFIGMAP_YAML),
    "deployment": ("deployment.yaml", DEPLOYMENT_YAML),
    "service": ("service.yaml", SERVICE_YAML),
    "pdb": ("pdb.yaml", PDB_YAML),
    "hpa": ("hpa.yaml", HPA_YAML),
    "netpol": ("networkpolicy.yaml", NETPOL_DENY_YAML),
    "ingress": ("ingress.yaml", INGRESS_YAML),
    "servicemonitor": ("servicemonitor.yaml", SERVICEMONITOR_YAML),
    "argocd": ("argocd-application.yaml", ARGOCD_APP_YAML),
    "velero": ("velero-schedule.yaml", VELERO_YAML),
}


def write_file(path: Path, content: str):
    """Write content to file, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"  Created: {path}")


def generate_pss_labels(level: str) -> str:
    """Generate Pod Security Standards namespace labels."""
    if not level:
        return ""
    return textwrap.dedent(f"""\
        pod-security.kubernetes.io/enforce: {level}
        pod-security.kubernetes.io/audit: {level}
        pod-security.kubernetes.io/warn: {level}""")


def scaffold(args):
    """Generate Kubernetes project based on tier and options."""
    name = args.name
    tier = args.tier
    out = Path(args.path)
    packaging = args.packaging
    secrets = args.secrets
    gitops = args.gitops
    provider = args.provider

    config = TIER_CONFIG[tier]
    namespace = f"{name}-prod" if tier >= 2 else name
    env = "production" if tier >= 2 else "development"
    image = f"registry.company.com/{name}:1.0.0"

    params = {
        "name": name,
        "namespace": namespace,
        "env": env,
        "image": image,
        "replicas": config["replicas"],
        "cpu_request": config["cpu_request"],
        "mem_request": config["mem_request"],
        "cpu_limit": config["cpu_limit"],
        "mem_limit": config["mem_limit"],
        "probes": config["probes"],
        "topology_spread": config["topology"].format(name=name) if config["topology"] else "",
        "pss_labels": generate_pss_labels(config["pss"]),
        "min_available": max(1, config["replicas"] - 1),
        "min_replicas": config["replicas"],
        "max_replicas": config["replicas"] * 3,
        "gitops_path": f"manifests/{namespace}" if packaging == "raw" else f"charts/{name}",
    }

    print(f"\n{'='*60}")
    print(f"  K8s Mastery Scaffolder")
    print(f"  Name: {name} | Tier: {tier} | Provider: {provider}")
    print(f"  Packaging: {packaging} | Secrets: {secrets} | GitOps: {gitops}")
    print(f"{'='*60}\n")

    if packaging == "helm":
        _scaffold_helm(out, name, namespace, tier, config, params)
    elif packaging == "kustomize":
        _scaffold_kustomize(out, name, namespace, tier, config, params)
    else:
        _scaffold_raw(out, name, namespace, tier, config, params)

    # Add secrets based on method
    manifests_dir = out / "manifests" if packaging == "raw" else out / "base" if packaging == "kustomize" else out
    if secrets == "sealed" and tier >= 2:
        write_file(manifests_dir / "sealed-secret.yaml", SEALED_SECRET_YAML.format(**params))
    elif secrets == "vault" and tier >= 3:
        write_file(manifests_dir / "external-secret.yaml", EXTERNAL_SECRET_YAML.format(**params))

    # Generate README
    _generate_readme(out, name, tier, packaging, secrets, gitops, provider)

    print(f"\n  Done! Project generated at: {out}")
    print(f"  Total tier: {tier} ({'Foundation' if tier == 1 else 'Production' if tier == 2 else 'Enterprise' if tier == 3 else 'Multi-Cluster' if tier == 4 else 'Hyperscale'})")
    print(f"  Files: {sum(1 for _ in out.rglob('*') if _.is_file())}")
    print()


def _scaffold_raw(out: Path, name: str, namespace: str, tier: int, config: dict, params: dict):
    """Generate raw YAML manifests."""
    manifests = out / "manifests"
    for file_key in config["files"]:
        filename, template = FILE_GENERATORS[file_key]
        content = template.format(**params)
        write_file(manifests / filename, content)


def _scaffold_kustomize(out: Path, name: str, namespace: str, tier: int, config: dict, params: dict):
    """Generate Kustomize project with base + overlays."""
    base = out / "base"
    for file_key in config["files"]:
        if file_key in ("argocd", "velero"):
            continue  # These go in separate dirs
        filename, template = FILE_GENERATORS[file_key]
        write_file(base / filename, template.format(**params))

    # Base kustomization.yaml
    resource_list = "\n".join(
        f"  - {FILE_GENERATORS[f][0]}"
        for f in config["files"]
        if f not in ("argocd", "velero")
    )
    write_file(base / "kustomization.yaml", KUSTOMIZATION_YAML.format(
        namespace=namespace, name=name, resources=resource_list
    ))

    # Overlays
    for env_name in ["dev", "staging", "prod"]:
        overlay = out / "overlays" / env_name
        replicas = 1 if env_name == "dev" else 2 if env_name == "staging" else config["replicas"]
        overlay_content = textwrap.dedent(f"""\
            apiVersion: kustomize.config.k8s.io/v1beta1
            kind: Kustomization
            namespace: {name}-{env_name}
            resources:
              - ../../base
            replicas:
              - name: {name}
                count: {replicas}
        """)
        write_file(overlay / "kustomization.yaml", overlay_content)

    # ArgoCD + Velero at T3+
    if tier >= 3 and "argocd" in config["files"]:
        argocd_params = {**params, "gitops_path": f"overlays/prod"}
        write_file(out / "argocd-application.yaml", ARGOCD_APP_YAML.format(**argocd_params))
    if tier >= 3 and "velero" in config["files"]:
        write_file(out / "velero-schedule.yaml", VELERO_YAML.format(**params))


def _scaffold_helm(out: Path, name: str, namespace: str, tier: int, config: dict, params: dict):
    """Generate Helm chart structure."""
    chart_dir = out
    templates = chart_dir / "templates"

    # Chart.yaml
    write_file(chart_dir / "Chart.yaml", textwrap.dedent(f"""\
        apiVersion: v2
        name: {name}
        description: Kubernetes deployment for {name} (Tier {tier})
        type: application
        version: 0.1.0
        appVersion: "1.0.0"
        kubeVersion: ">=1.28.0"
    """))

    # values.yaml
    write_file(chart_dir / "values.yaml", textwrap.dedent(f"""\
        replicaCount: {config['replicas']}
        image:
          repository: registry.company.com/{name}
          tag: ""
          pullPolicy: IfNotPresent
        service:
          type: ClusterIP
          port: 80
          targetPort: 8080
        resources:
          requests:
            cpu: {config['cpu_request']}
            memory: {config['mem_request']}
          limits:
            cpu: "{config['cpu_limit']}"
            memory: {config['mem_limit']}
        autoscaling:
          enabled: {'true' if tier >= 2 else 'false'}
          minReplicas: {config['replicas']}
          maxReplicas: {config['replicas'] * 3}
        pdb:
          enabled: {'true' if tier >= 2 else 'false'}
          minAvailable: {max(1, config['replicas'] - 1)}
        networkPolicy:
          enabled: {'true' if tier >= 2 else 'false'}
        serviceMonitor:
          enabled: {'true' if tier >= 2 else 'false'}
        ingress:
          enabled: {'true' if tier >= 2 else 'false'}
          className: nginx
          hosts:
            - host: {name}.example.com
              paths:
                - path: /
                  pathType: Prefix
    """))

    # templates/
    write_file(templates / "deployment.yaml", "# See helm_chart/templates/deployment.yaml in k8s-mastery assets")
    write_file(templates / "service.yaml", "# See helm_chart/templates/service.yaml in k8s-mastery assets")
    write_file(templates / "_helpers.tpl", "# See helm_chart/templates/_helpers.tpl in k8s-mastery assets")

    if tier >= 2:
        for tpl in ["ingress.yaml", "hpa.yaml", "pdb.yaml", "networkpolicy.yaml",
                     "serviceaccount.yaml", "servicemonitor.yaml"]:
            write_file(templates / tpl, f"# See helm_chart/templates/{tpl} in k8s-mastery assets")

    # Environment-specific values
    if tier >= 2:
        for env_name in ["dev", "staging", "prod"]:
            replicas = 1 if env_name == "dev" else 2 if env_name == "staging" else config["replicas"]
            write_file(chart_dir / f"values-{env_name}.yaml", textwrap.dedent(f"""\
                replicaCount: {replicas}
                ingress:
                  hosts:
                    - host: {name}-{env_name}.example.com
                      paths:
                        - path: /
                          pathType: Prefix
            """))

    # ArgoCD
    if tier >= 3:
        argocd_params = {**params, "gitops_path": f"charts/{name}"}
        write_file(chart_dir / "argocd-application.yaml", ARGOCD_APP_YAML.format(**argocd_params))


def _generate_readme(out: Path, name: str, tier: int, packaging: str, secrets: str, gitops: str, provider: str):
    """Generate project README."""
    tier_names = {1: "Foundation", 2: "Production", 3: "Enterprise", 4: "Multi-Cluster", 5: "Hyperscale"}

    if packaging == "helm":
        deploy_cmd = f"helm install {name} . -n {name}-prod --create-namespace -f values-prod.yaml"
    elif packaging == "kustomize":
        deploy_cmd = f"kubectl apply -k overlays/prod"
    else:
        deploy_cmd = f"kubectl apply -f manifests/"

    content = textwrap.dedent(f"""\
        # {name} — Kubernetes Deployment

        **Tier**: {tier} ({tier_names[tier]})
        **Provider**: {provider}
        **Packaging**: {packaging}
        **Secrets**: {secrets}
        **GitOps**: {gitops}

        Generated by k8s-mastery scaffold.

        ## Deploy

        ```bash
        {deploy_cmd}
        ```

        ## Components

        | Component | Status |
        |-----------|--------|
        | Deployment | Included |
        | Service | Included |
        | RBAC | {'Included' if tier >= 2 else 'Not included'} |
        | NetworkPolicy | {'Included' if tier >= 2 else 'Not included'} |
        | HPA | {'Included' if tier >= 2 else 'Not included'} |
        | PDB | {'Included' if tier >= 2 else 'Not included'} |
        | Ingress | {'Included' if tier >= 2 else 'Not included'} |
        | ServiceMonitor | {'Included' if tier >= 2 else 'Not included'} |
        | GitOps (ArgoCD) | {'Included' if tier >= 3 else 'Not included'} |
        | Velero Backup | {'Included' if tier >= 3 else 'Not included'} |
        | Sealed Secrets | {'Included' if secrets == 'sealed' else 'Not included'} |
        | External Secrets + Vault | {'Included' if secrets == 'vault' else 'Not included'} |

        ## Tier {tier} Features

        {'- Basic deployment with resource limits' if tier >= 1 else ''}
        {'- Security context (non-root, read-only FS, dropped caps)' if tier >= 1 else ''}
        {'- RBAC (namespace-scoped roles)' if tier >= 2 else ''}
        {'- Pod Security Standards (restricted)' if tier >= 2 else ''}
        {'- NetworkPolicy (default deny + explicit allow)' if tier >= 2 else ''}
        {'- HPA + PDB for reliability' if tier >= 2 else ''}
        {'- ArgoCD GitOps deployment' if tier >= 3 else ''}
        {'- Vault secret management' if tier >= 3 and secrets == 'vault' else ''}
        {'- Velero backup schedules' if tier >= 3 else ''}
        {'- Multi-cluster service mesh' if tier >= 4 else ''}
        {'- Fleet management + Karpenter' if tier >= 5 else ''}
    """)
    write_file(out / "README.md", content)


def main():
    parser = argparse.ArgumentParser(
        description="K8s Mastery — Kubernetes Project Scaffolder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Tiers:
              1  Foundation   — Single workload, basic resources
              2  Production   — Hardened, RBAC, HPA, PDB, NetworkPolicy
              3  Enterprise   — GitOps, Vault, observability, compliance
              4  Multi-Cluster — Federation, service mesh, multi-region
              5  Hyperscale   — Fleet management, platform engineering
        """),
    )
    parser.add_argument("name", help="Project/application name")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4, 5], required=True, help="Scale tier (1-5)")
    parser.add_argument("--path", required=True, help="Output directory")
    parser.add_argument("--provider", choices=["eks", "gke", "aks", "onprem"], default="eks", help="Cloud provider")
    parser.add_argument("--packaging", choices=["helm", "kustomize", "raw"], default="raw", help="Packaging format")
    parser.add_argument("--gitops", choices=["argocd", "flux", "none"], default="none", help="GitOps tool")
    parser.add_argument("--mesh", choices=["none", "istio", "linkerd", "cilium"], default="none", help="Service mesh")
    parser.add_argument("--secrets", choices=["k8s", "sealed", "vault"], default="k8s", help="Secrets method")

    args = parser.parse_args()

    if args.tier >= 3 and args.gitops == "none":
        args.gitops = "argocd"
        print(f"  Note: Tier {args.tier} defaults to ArgoCD for GitOps.")

    if args.tier >= 2 and args.secrets == "k8s":
        args.secrets = "sealed"
        print(f"  Note: Tier {args.tier} defaults to Sealed Secrets.")

    if args.tier >= 3 and args.secrets == "sealed":
        args.secrets = "vault"
        print(f"  Note: Tier {args.tier} defaults to Vault + External Secrets.")

    scaffold(args)


if __name__ == "__main__":
    main()
