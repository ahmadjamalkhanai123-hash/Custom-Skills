const fs = require("fs");
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Header, Footer, AlignmentType, LevelFormat, HeadingLevel, BorderStyle,
        WidthType, ShadingType, VerticalAlign, PageNumber, PageBreak } = require("docx");

const TB = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const CB = { top: TB, bottom: TB, left: TB, right: TB };
const BLUE = "1B4F72";
const LIGHT_BLUE = "D6EAF8";
const GRAY = "F2F3F4";

function hdrCell(text, width) {
  return new TableCell({
    borders: CB, width: { size: width, type: WidthType.DXA },
    shading: { fill: BLUE, type: ShadingType.CLEAR },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text, bold: true, color: "FFFFFF", size: 20, font: "Arial" })] })]
  });
}

function cell(text, width, opts = {}) {
  return new TableCell({
    borders: CB, width: { size: width, type: WidthType.DXA },
    shading: opts.shade ? { fill: GRAY, type: ShadingType.CLEAR } : undefined,
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ spacing: { before: 40, after: 40 },
      children: [new TextRun({ text, size: 20, font: "Arial", bold: !!opts.bold, color: opts.color || "333333" })] })]
  });
}

function h1(text) { return new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 200 }, children: [new TextRun({ text })] }); }
function h2(text) { return new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 280, after: 160 }, children: [new TextRun({ text })] }); }
function p(text) { return new Paragraph({ spacing: { before: 80, after: 80 }, children: [new TextRun({ text, size: 22, font: "Arial" })] }); }
function pb(text) { return new Paragraph({ spacing: { before: 80, after: 80 }, children: [new TextRun({ text, size: 22, font: "Arial", bold: true })] }); }

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal",
        run: { size: 52, bold: true, color: BLUE, font: "Arial" },
        paragraph: { spacing: { before: 0, after: 200 }, alignment: AlignmentType.CENTER } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: BLUE, font: "Arial" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, color: "2C3E50", font: "Arial" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
    ]
  },
  numbering: {
    config: [
      { reference: "bl1", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "bl2", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "bl3", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "bl4", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "bl5", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "bl6", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [{
    properties: {
      page: { margin: { top: 1440, right: 1260, bottom: 1440, left: 1260 } }
    },
    headers: {
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: "K8s Mastery \u2014 Skill Architecture Documentation", italics: true, size: 18, color: "888888", font: "Arial" })] })] })
    },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "Page ", size: 18, font: "Arial", color: "888888" }), new TextRun({ children: [PageNumber.CURRENT], size: 18, font: "Arial", color: "888888" }), new TextRun({ text: " of ", size: 18, font: "Arial", color: "888888" }), new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, font: "Arial", color: "888888" })] })] })
    },
    children: [
      // ── TITLE PAGE ──
      new Paragraph({ spacing: { before: 3600 } , children: [] }),
      new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("K8s Mastery")] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
        children: [new TextRun({ text: "Skill Architecture Documentation", size: 28, color: "555555", font: "Arial" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
        children: [new TextRun({ text: "Zero to Hyperscale Production Orchestration", size: 24, color: "777777", font: "Arial", italics: true })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 600 },
        children: [new TextRun({ text: "February 2026  |  Version 1.0", size: 20, color: "999999", font: "Arial" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200 },
        children: [new TextRun({ text: "Global Standard: Google, Meta, Netflix, Uber, Stripe-grade Infrastructure", size: 20, color: "999999", font: "Arial" })] }),

      new Paragraph({ children: [new PageBreak()] }),

      // ── 1. EXECUTIVE SUMMARY ──
      h1("1. Executive Summary"),
      p("K8s Mastery is a production-grade Builder skill that creates Kubernetes infrastructure across five progressive tiers \u2014 from single-workload deployments to hyperscale fleet platforms managing 100K+ workloads across 200+ clusters."),
      p("The skill embeds deep domain expertise from official Kubernetes documentation, CNCF ecosystem tools, and enterprise patterns used at Google, Meta, Netflix, Uber, and Stripe. It operates as a zero-shot Kubernetes expert: users provide THEIR requirements, and the skill already knows how to build it."),
      pb("Key Capabilities:"),
      new Paragraph({ numbering: { reference: "bl1", level: 0 }, children: [new TextRun({ text: "Multi-layer RBAC: User \u2192 Namespace \u2192 Cluster \u2192 Federation authorization", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl1", level: 0 }, children: [new TextRun({ text: "Secrets maturity: K8s Secrets \u2192 Sealed Secrets \u2192 Vault + ESO \u2192 CSI + HSM", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl1", level: 0 }, children: [new TextRun({ text: "Service mesh: Istio, Linkerd, Cilium with mTLS and L7 authorization", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl1", level: 0 }, children: [new TextRun({ text: "GitOps: ArgoCD app-of-apps, progressive delivery with Argo Rollouts", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl1", level: 0 }, children: [new TextRun({ text: "Policy engines: Kyverno and OPA Gatekeeper for compliance enforcement", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl1", level: 0 }, children: [new TextRun({ text: "Observability: Prometheus, Grafana, Loki, Tempo, Thanos with SLO alerting", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl1", level: 0 }, children: [new TextRun({ text: "Compliance: SOC 2, HIPAA, PCI-DSS, FedRAMP mapped to K8s implementations", size: 22, font: "Arial" })] }),

      pb("Skill Metadata:"),
      new Table({ columnWidths: [3120, 6240], rows: [
        new TableRow({ children: [cell("Skill Name", 3120, { bold: true, shade: true }), cell("k8s-mastery", 6240)] }),
        new TableRow({ children: [cell("Type", 3120, { bold: true, shade: true }), cell("Builder", 6240)] }),
        new TableRow({ children: [cell("SKILL.md Lines", 3120, { bold: true, shade: true }), cell("412 (under 500 limit)", 6240)] }),
        new TableRow({ children: [cell("Reference Files", 3120, { bold: true, shade: true }), cell("17 files, 12,259 lines total", 6240)] }),
        new TableRow({ children: [cell("Asset Templates", 3120, { bold: true, shade: true }), cell("15+ templates including full Helm chart skeleton", 6240)] }),
        new TableRow({ children: [cell("Scaffold Script", 3120, { bold: true, shade: true }), cell("scaffold_k8s.py \u2014 generates projects for all 5 tiers", 6240)] }),
        new TableRow({ children: [cell("Target Score", 3120, { bold: true, shade: true }), cell("90+ (Production)", 6240)] }),
      ]}),

      new Paragraph({ children: [new PageBreak()] }),

      // ── 2. FIVE-TIER ARCHITECTURE ──
      h1("2. Five-Tier Architecture"),
      p("The skill uses progressive tiers to match infrastructure complexity to actual needs. Each tier includes all components from previous tiers plus additional capabilities."),
      new Table({ columnWidths: [1200, 1600, 2000, 2000, 2560], rows: [
        new TableRow({ tableHeader: true, children: [hdrCell("Tier", 1200), hdrCell("Scale", 1600), hdrCell("Clusters/Nodes", 2000), hdrCell("Key Features", 2000), hdrCell("Target", 2560)] }),
        new TableRow({ children: [cell("1: Foundation", 1200, { bold: true }), cell("1\u20135 workloads", 1600), cell("1 cluster, 1\u20135 nodes", 2000), cell("Deployment, Service, ConfigMap, basic probes", 2000), cell("Learning, dev, hobby", 2560)] }),
        new TableRow({ children: [cell("2: Production", 1200, { bold: true }), cell("5\u201350 workloads", 1600), cell("1 cluster, 5\u201350 nodes", 2000), cell("RBAC, Sealed Secrets, HPA, PDB, NetworkPolicy, PSS", 2000), cell("Startups, single team", 2560)] }),
        new TableRow({ children: [cell("3: Enterprise", 1200, { bold: true }), cell("50\u2013200 workloads", 1600), cell("1\u20133 clusters, 50\u2013200 nodes", 2000), cell("Kyverno/OPA, Vault+ESO, Gateway API, ArgoCD, Prometheus stack", 2000), cell("Multi-team, compliance", 2560)] }),
        new TableRow({ children: [cell("4: Multi-Cluster", 1200, { bold: true }), cell("200\u20132K workloads", 1600), cell("3\u201320 clusters, 200\u20132K nodes", 2000), cell("Federation, Istio mesh, multi-region DR, Thanos, Argo Rollouts", 2000), cell("Large enterprise, SaaS", 2560)] }),
        new TableRow({ children: [cell("5: Hyperscale", 1200, { bold: true }), cell("2K\u2013100K+ workloads", 1600), cell("20\u2013200+ clusters, 2K\u201350K+ nodes", 2000), cell("Fleet mgmt, Crossplane, Kubebuilder, eBPF, Karpenter, vcluster", 2000), cell("FAANG-scale", 2560)] }),
      ]}),

      h2("Tier Selection Decision Tree"),
      new Paragraph({ numbering: { reference: "bl2", level: 0 }, children: [new TextRun({ text: "Single workload for dev/learning? \u2192 Tier 1", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl2", level: 0 }, children: [new TextRun({ text: "Harden a single cluster for one team? \u2192 Tier 2", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl2", level: 0 }, children: [new TextRun({ text: "Multi-team org with compliance + policy? \u2192 Tier 3", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl2", level: 0 }, children: [new TextRun({ text: "Multi-region with DR + federation + mesh? \u2192 Tier 4", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl2", level: 0 }, children: [new TextRun({ text: "Google/Meta-scale fleet + platform engineering? \u2192 Tier 5", size: 22, font: "Arial" })] }),

      new Paragraph({ children: [new PageBreak()] }),

      // ── 3. RBAC & AUTHORIZATION ──
      h1("3. RBAC & Authorization Model"),
      p("The skill implements a 4-layer authorization model that maps to enterprise security requirements and compliance frameworks."),
      new Table({ columnWidths: [1400, 2200, 2800, 2960], rows: [
        new TableRow({ tableHeader: true, children: [hdrCell("Layer", 1400), hdrCell("Function", 2200), hdrCell("Implementation", 2800), hdrCell("Tier", 2960)] }),
        new TableRow({ children: [cell("1: Authentication", 1400, { bold: true }), cell("WHO is accessing?", 2200), cell("OIDC (Dex/Keycloak/Okta), ServiceAccount tokens, Cloud IAM (IRSA, Workload Identity)", 2800), cell("T2+", 2960)] }),
        new TableRow({ children: [cell("2: RBAC", 1400, { bold: true }), cell("WHAT can they do?", 2200), cell("Role/ClusterRole + RoleBinding/ClusterRoleBinding, aggregated roles, hierarchical RBAC", 2800), cell("T1+", 2960)] }),
        new TableRow({ children: [cell("3: Admission Control", 1400, { bold: true }), cell("WHAT is allowed?", 2200), cell("Pod Security Standards, Kyverno/OPA Gatekeeper, ValidatingAdmissionPolicy, image verification", 2800), cell("T2+", 2960)] }),
        new TableRow({ children: [cell("4: Runtime Enforcement", 1400, { bold: true }), cell("Runtime protection", 2200), cell("NetworkPolicy, Istio AuthorizationPolicy, Seccomp/AppArmor, Falco/Tetragon", 2800), cell("T2+", 2960)] }),
      ]}),
      h2("RBAC Progression by Tier"),
      new Paragraph({ numbering: { reference: "bl3", level: 0 }, children: [new TextRun({ text: "Tier 1: cluster-admin (acceptable for learning/dev only)", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl3", level: 0 }, children: [new TextRun({ text: "Tier 2: Namespace-scoped Roles (developer, SRE, readonly) with least-privilege", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl3", level: 0 }, children: [new TextRun({ text: "Tier 3: Aggregated ClusterRoles with label selectors + hierarchical namespaces", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl3", level: 0 }, children: [new TextRun({ text: "Tier 4\u20135: Cross-cluster OIDC federation with group mapping via Dex/Okta", size: 22, font: "Arial" })] }),

      new Paragraph({ children: [new PageBreak()] }),

      // ── 4. SECRETS MANAGEMENT ──
      h1("4. Secrets Management Maturity Model"),
      p("Each tier introduces progressively stronger secrets management, from basic K8s Secrets to HSM-backed dynamic credentials."),
      new Table({ columnWidths: [1000, 2400, 2000, 1800, 2160], rows: [
        new TableRow({ tableHeader: true, children: [hdrCell("Tier", 1000), hdrCell("Method", 2400), hdrCell("Encryption", 2000), hdrCell("Rotation", 1800), hdrCell("Audit", 2160)] }),
        new TableRow({ children: [cell("1", 1000, { bold: true }), cell("K8s Secrets (base64)", 2400), cell("etcd encryption at rest", 2000), cell("Manual", 1800), cell("None", 2160)] }),
        new TableRow({ children: [cell("2", 1000, { bold: true }), cell("Sealed Secrets (kubeseal)", 2400), cell("Asymmetric RSA", 2000), cell("Manual, GitOps-safe", 1800), cell("kubectl audit", 2160)] }),
        new TableRow({ children: [cell("3", 1000, { bold: true }), cell("External Secrets + Vault", 2400), cell("AES-256-GCM + TLS", 2000), cell("Automatic (Vault lease)", 1800), cell("Full audit log", 2160)] }),
        new TableRow({ children: [cell("4", 1000, { bold: true }), cell("Vault HA + Auto-Unseal", 2400), cell("HSM-backed (FIPS)", 2000), cell("Dynamic DB credentials", 1800), cell("SIEM integration", 2160)] }),
        new TableRow({ children: [cell("5", 1000, { bold: true }), cell("Multi-tenant Vault + CSI Driver", 2400), cell("HSM + cross-region replication", 2000), cell("Zero-touch rotation", 1800), cell("Compliance-mapped", 2160)] }),
      ]}),

      new Paragraph({ children: [new PageBreak()] }),

      // ── 5. COMPONENT INVENTORY ──
      h1("5. Component Inventory"),
      h2("5.1 Reference Files (17 files, 12,259 lines)"),
      new Table({ columnWidths: [3600, 3000, 2760], rows: [
        new TableRow({ tableHeader: true, children: [hdrCell("File", 3600), hdrCell("Domain", 3000), hdrCell("Lines", 2760)] }),
        new TableRow({ children: [cell("core-resources.md", 3600), cell("Deployment, Service, StatefulSet, Jobs", 3000), cell("898", 2760)] }),
        new TableRow({ children: [cell("namespace-patterns.md", 3600), cell("Namespace strategy, ResourceQuota, HNC", 3000), cell("674", 2760)] }),
        new TableRow({ children: [cell("rbac-patterns.md", 3600), cell("Roles, Bindings, OIDC, Aggregation", 3000), cell("711", 2760)] }),
        new TableRow({ children: [cell("secrets-management.md", 3600), cell("K8s Secrets, Sealed, ESO, Vault, CSI", 3000), cell("832", 2760)] }),
        new TableRow({ children: [cell("networking.md", 3600), cell("NetworkPolicy, Gateway API, Ingress", 3000), cell("666", 2760)] }),
        new TableRow({ children: [cell("service-mesh.md", 3600), cell("Istio, Linkerd, Cilium mesh, mTLS", 3000), cell("518", 2760)] }),
        new TableRow({ children: [cell("security.md", 3600), cell("Pod Security Standards, Falco, Tetragon", 3000), cell("582", 2760)] }),
        new TableRow({ children: [cell("policy-engines.md", 3600), cell("Kyverno, OPA Gatekeeper, VAP", 3000), cell("805", 2760)] }),
        new TableRow({ children: [cell("observability.md", 3600), cell("Prometheus, Grafana, Loki, Thanos, SLOs", 3000), cell("919", 2760)] }),
        new TableRow({ children: [cell("gitops-patterns.md", 3600), cell("ArgoCD, Flux, app-of-apps, Rollouts", 3000), cell("805", 2760)] }),
        new TableRow({ children: [cell("multi-cluster.md", 3600), cell("Federation, cross-cluster, hub-spoke", 3000), cell("786", 2760)] }),
        new TableRow({ children: [cell("hyperscale-patterns.md", 3600), cell("Fleet mgmt, Crossplane, Kubebuilder", 3000), cell("1,041", 2760)] }),
        new TableRow({ children: [cell("disaster-recovery.md", 3600), cell("Velero, etcd backup, multi-region", 3000), cell("523", 2760)] }),
        new TableRow({ children: [cell("cost-optimization.md", 3600), cell("VPA, Karpenter, spot, Kubecost", 3000), cell("522", 2760)] }),
        new TableRow({ children: [cell("production-hardening.md", 3600), cell("Checklist, compliance, audit", 3000), cell("587", 2760)] }),
        new TableRow({ children: [cell("helm-kustomize.md", 3600), cell("Helm charts, Kustomize overlays", 3000), cell("923", 2760)] }),
        new TableRow({ children: [cell("anti-patterns.md", 3600), cell("25+ common K8s mistakes + fixes", 3000), cell("467", 2760)] }),
      ]}),

      h2("5.2 Asset Templates (15+ templates)"),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "deployment_basic.yaml \u2014 Tier 1 complete deployment with security context", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "deployment_production.yaml \u2014 Tier 2 hardened (HPA, PDB, probes, topology spread, RBAC, NetworkPolicy, ServiceMonitor)", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "namespace_enterprise.yaml \u2014 Tier 3 namespace with ResourceQuota, LimitRange, RBAC, NetworkPolicy", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "helm_chart/ \u2014 Complete Helm chart skeleton (Chart.yaml, values.yaml, 7 templates)", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "kustomize_base/ + kustomize_overlays/ \u2014 Base + dev/staging/prod overlays", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "argocd_app_of_apps.yaml + argocd_applicationset.yaml \u2014 GitOps patterns", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "kyverno_policies.yaml \u2014 9 production policies (registries, digests, limits, PSS, signatures)", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "external_secret.yaml \u2014 Vault + ESO integration with templating", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "prometheus_rules.yaml \u2014 SLO/SLI alerting (availability, latency, error rate, infra)", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "velero_schedule.yaml \u2014 Daily/hourly/weekly backup schedules with cross-region DR", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "gateway_api.yaml \u2014 Gateway + HTTPRoute with canary and weighted routing", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "karpenter_nodepool.yaml \u2014 General, memory-optimized, and GPU NodePools", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl4", level: 0 }, children: [new TextRun({ text: "istio_authz.yaml \u2014 PeerAuthentication, AuthorizationPolicy, VirtualService, DestinationRule", size: 22, font: "Arial" })] }),

      h2("5.3 Scaffold Script"),
      p("scaffold_k8s.py generates complete K8s projects for any tier with configurable options:"),
      p("python scaffold_k8s.py <name> --tier <1|2|3|4|5> --path <dir> [--provider <eks|gke|aks|onprem>] [--packaging <helm|kustomize|raw>] [--gitops <argocd|flux|none>] [--mesh <none|istio|linkerd|cilium>] [--secrets <k8s|sealed|vault>]"),

      new Paragraph({ children: [new PageBreak()] }),

      // ── 6. STANDARDIZATION NOTES ──
      h1("6. Official K8s Documentation Standardization"),
      p("All manifests and patterns were verified against official Kubernetes documentation (February 2026). Key standardization points:"),
      h2("6.1 API Versions Verified"),
      new Table({ columnWidths: [3200, 3600, 2560], rows: [
        new TableRow({ tableHeader: true, children: [hdrCell("Resource", 3200), hdrCell("apiVersion", 3600), hdrCell("Status", 2560)] }),
        new TableRow({ children: [cell("Deployment, StatefulSet, DaemonSet", 3200), cell("apps/v1", 3600), cell("Stable", 2560)] }),
        new TableRow({ children: [cell("Service, Secret, ConfigMap, Pod", 3200), cell("v1", 3600), cell("Stable", 2560)] }),
        new TableRow({ children: [cell("Role, ClusterRole, RoleBinding", 3200), cell("rbac.authorization.k8s.io/v1", 3600), cell("Stable", 2560)] }),
        new TableRow({ children: [cell("NetworkPolicy", 3200), cell("networking.k8s.io/v1", 3600), cell("Stable", 2560)] }),
        new TableRow({ children: [cell("Gateway, HTTPRoute, GRPCRoute", 3200), cell("gateway.networking.k8s.io/v1", 3600), cell("GA (v1.4)", 2560)] }),
        new TableRow({ children: [cell("HorizontalPodAutoscaler", 3200), cell("autoscaling/v2", 3600), cell("Stable", 2560)] }),
        new TableRow({ children: [cell("PodDisruptionBudget", 3200), cell("policy/v1", 3600), cell("Stable", 2560)] }),
        new TableRow({ children: [cell("BackendTLSPolicy", 3200), cell("gateway.networking.k8s.io/v1", 3600), cell("GA (v1.4)", 2560)] }),
      ]}),
      h2("6.2 Deprecation Compliance"),
      new Paragraph({ numbering: { reference: "bl5", level: 0 }, children: [new TextRun({ text: "PodSecurityPolicy (removed K8s 1.25): Replaced with Pod Security Admission namespace labels", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl5", level: 0 }, children: [new TextRun({ text: "ServiceAccount token Secrets (deprecated 1.22): Using TokenRequest API + projected volumes", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl5", level: 0 }, children: [new TextRun({ text: "Endpoints API (deprecated 1.33): Using EndpointSlices (stable since 1.21)", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl5", level: 0 }, children: [new TextRun({ text: "BackendTLSPolicy: Promoted to GA in Gateway API v1.4 (October 2025)", size: 22, font: "Arial" })] }),
      h2("6.3 Security Best Practices (from official docs)"),
      new Paragraph({ numbering: { reference: "bl6", level: 0 }, children: [new TextRun({ text: "Never use wildcard (*) permissions in RBAC", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl6", level: 0 }, children: [new TextRun({ text: "Never add users to system:masters group (bypasses ALL RBAC)", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl6", level: 0 }, children: [new TextRun({ text: "Set automountServiceAccountToken: false by default", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl6", level: 0 }, children: [new TextRun({ text: "Pod Security Standards: restricted level enforced via namespace labels", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl6", level: 0 }, children: [new TextRun({ text: "Secrets encrypted at rest using EncryptionConfiguration", size: 22, font: "Arial" })] }),
      new Paragraph({ numbering: { reference: "bl6", level: 0 }, children: [new TextRun({ text: "Use external secret stores (Vault) via Secrets Store CSI Driver for production", size: 22, font: "Arial" })] }),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/home/jamalafridi/AI-Project/claude-code-skills-lab-main/specs/k8s-mastery-skill-documentation.docx", buffer);
  console.log("DOCX created successfully!");
});
