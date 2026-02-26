# Cost Optimization Reference (FinOps)

## FinOps Foundation FOCUS Model

FinOps = Financial + DevOps. Enables cloud cost governance at scale.

### Three Phases

1. **Inform** — Visibility: who spends what, where
2. **Optimize** — Right-size, use discounts, eliminate waste
3. **Operate** — Govern continuously, set budgets, enforce policies

### FOCUS (FinOps Open Cost & Usage Specification)

Common schema for multi-cloud cost data:
```
BilledCost | EffectiveCost | ServiceCategory | ResourceType
Provider   | Region        | Tags            | UsageType
```

Use FOCUS-compliant exporters to unify AWS CUR + GCP BigQuery + Azure EA exports.

---

## Kubecost — Kubernetes Cost Monitoring

### Installation

```bash
# Install via Helm with cloud billing integration
helm repo add kubecost https://kubecost.github.io/cost-analyzer/
helm upgrade --install kubecost kubecost/cost-analyzer \
  --namespace kubecost --create-namespace \
  --set kubecostToken="${KUBECOST_LICENSE_KEY}" \
  --set global.prometheus.enabled=true \
  --set global.grafana.enabled=true \
  --set global.cloudIntegrations.aws.enabled=true \
  --set global.cloudIntegrations.gcp.enabled=true \
  --set global.cloudIntegrations.azure.enabled=true
```

### AWS Cloud Integration
```yaml
# values.yaml — AWS Cost and Usage Report
global:
  cloudIntegrations:
    aws:
      enabled: true
      s3:
        bucket: my-cur-bucket
        region: us-east-1
        path: cur/prefix/
      athena:
        database: cost_and_usage_db
        table: cost_and_usage_table
        workgroup: primary
        region: us-east-1
      serviceAccount:
        annotations:
          eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/kubecost-role
```

### GCP Cloud Integration
```yaml
global:
  cloudIntegrations:
    gcp:
      enabled: true
      projectID: "my-gcp-project"
      bigQueryBillingDataset: "billing_export.gcp_billing_export_v1_PROJECT"
```

### Cost Allocation Labels

**Enforce these labels on ALL resources** via Kyverno/OPA:
```yaml
# Kyverno policy — require cost labels
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-cost-labels
spec:
  validationFailureAction: enforce
  rules:
    - name: require-team-label
      match:
        resources:
          kinds: [Deployment, StatefulSet, DaemonSet]
      validate:
        message: "Resources must have team, service, and environment labels"
        pattern:
          metadata:
            labels:
              team: "?*"
              service: "?*"
              environment: "?*"
```

### Cost Allocation API (Kubecost)

```bash
# Get cost by namespace for last 7 days
curl "http://kubecost/model/allocation?window=7d&aggregate=namespace&accumulate=true"

# Get cost by service label
curl "http://kubecost/model/allocation?window=30d&aggregate=label:service"

# Export to CSV for FinOps team
curl "http://kubecost/model/allocation?window=30d&aggregate=team&format=csv" \
  > cost-by-team-$(date +%Y%m).csv
```

---

## OpenCost (OSS Alternative to Kubecost)

Kubecost's open-source core, CNCF Sandbox:

```bash
helm install opencost opencost/opencost \
  --namespace opencost --create-namespace \
  --set opencost.exporter.cloudProviderApiKey="${GCP_API_KEY}" \
  --set opencost.prometheus.internal.enabled=true
```

Grafana dashboard available at: https://grafana.com/grafana/dashboards/20568

---

## Cloud-Specific Cost Optimization

### AWS Cost Reduction Strategies

| Strategy | Savings | Implementation |
|----------|---------|----------------|
| Compute Savings Plans | 17–66% | 1-year Compute SP covers EKS, Fargate, Lambda |
| Spot for stateless workloads | 60–90% | Karpenter + `spot` instance type requirement |
| S3 Intelligent-Tiering | 40–60% on storage | Enable per bucket, auto-moves objects |
| RDS Reserved Instances | 40–60% | 1-year reserved for production DB |
| Graviton instances (ARM64) | 20–40% compute | Use for Python/Go/Java workloads |
| EBS gp3 over gp2 | 20% | Migrate with `aws ec2 modify-volume` |

#### Spot + On-Demand Mix (Karpenter)
```yaml
apiVersion: karpenter.k8s.aws/v1beta1
kind: NodePool
metadata:
  name: default
spec:
  template:
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand"]
        - key: kubernetes.io/arch
          operator: In
          values: ["arm64", "amd64"]
      nodeClassRef:
        apiVersion: karpenter.k8s.aws/v1beta1
        kind: EC2NodeClass
        name: default
  disruption:
    consolidationPolicy: WhenUnderutilized
    consolidateAfter: 30s
  limits:
    cpu: "1000"
    memory: 4000Gi
```

### GCP Cost Reduction Strategies

| Strategy | Savings | Implementation |
|----------|---------|----------------|
| Committed Use Discounts | 37–55% | 1-year CUDs for compute |
| Spot VMs (GKE) | 60–91% | GKE spot node pool |
| Autopilot vs Standard | Up to 30% | Autopilot bins-packs efficiently |
| Sustained Use Discounts | 20–30% automatic | No action needed — Google auto-applies |
| Cloud Storage Nearline/Coldline | 60–80% storage | Lifecycle policies for old data |

#### GKE Spot Node Pool
```hcl
resource "google_container_node_pool" "spot" {
  name       = "spot-pool"
  cluster    = google_container_cluster.primary.name
  node_count = 3

  node_config {
    spot          = true
    machine_type  = "e2-standard-4"
    preemptible   = false    # spot, not preemptible
  }

  autoscaling {
    min_node_count = 0
    max_node_count = 20
  }
}
```

### Azure Cost Reduction Strategies

| Strategy | Savings | Implementation |
|----------|---------|----------------|
| Reserved Instances | 32–72% | 1/3-year for AKS system nodes |
| Spot Node Pools | 60–90% | AKS spot node pools |
| Azure Hybrid Benefit | Up to 40% | For Windows Server / SQL Server |
| Dev/Test subscription | 40–55% | Dev environments only |
| Azure Advisor | Varies | Auto right-size recommendations |

---

## Budget Alerts and Governance

### AWS Budgets
```hcl
resource "aws_budgets_budget" "monthly" {
  name              = "prod-monthly-budget"
  budget_type       = "COST"
  limit_amount      = "10000"
  limit_unit        = "USD"
  time_unit         = "MONTHLY"

  cost_filter {
    name = "TagKeyValue"
    values = ["user:environment$production"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["finops@company.com"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_sns_topic_arns  = [aws_sns_topic.cost_alerts.arn]
  }
}
```

### GCP Budget Alerts
```hcl
resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account_id
  display_name    = "Prod Monthly Budget"

  budget_filter {
    projects = ["projects/${var.project_number}"]
    labels = {
      environment = "production"
    }
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = "10000"
    }
  }

  threshold_rules {
    threshold_percent = 0.8
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    pubsub_topic                     = google_pubsub_topic.cost_alerts.id
    schema_version                   = "1.0"
    enable_project_level_recipients  = true
  }
}
```

---

## Cross-Cloud Cost Dashboard (Grafana)

Prometheus scrapes from Kubecost/OpenCost on each cluster.
Thanos aggregates across clusters. Grafana shows unified view.

### Key Dashboard Panels

1. **Total cost by cloud (7d)** — bar chart per AWS/GCP/Azure
2. **Cost by team (30d)** — pie chart by `team` label
3. **Cost by service (7d)** — table with delta from last week
4. **Spot vs On-Demand ratio** — gauge (target: >60% spot)
5. **Idle resource waste** — CPU/memory over-provisioned resources
6. **Data egress costs** — often invisible until billing arrives
7. **Reserved coverage %** — how much is covered by savings plans/CUDs

---

## Data Egress Cost Management

**Often the largest hidden cost in multi-cloud.**

| Egress Type | AWS | GCP | Azure |
|-------------|-----|-----|-------|
| Internet egress | $0.09/GB | $0.08/GB | $0.087/GB |
| Cross-region same cloud | $0.02/GB | $0.01/GB | $0.02/GB |
| Cross-cloud (via internet) | $0.09/GB | $0.08/GB | $0.087/GB |
| Private interconnect | $0.02/GB | $0.02/GB | $0.025/GB |

**Strategies to reduce egress:**
1. Use private interconnect for inter-cloud traffic (reduces from $0.09 to $0.02/GB)
2. Cache frequently-requested data at the edge (Cloudflare, CloudFront)
3. Compress all API responses (gzip/brotli) — reduces egress 60–80%
4. Colocate services that exchange large data volumes in the same cloud/region
5. Monitor egress with AWS Cost Explorer (`UsageType: DataTransfer-Out-Bytes`)

---

## FinOps Governance Checklist

- [ ] All resources tagged with: `team`, `service`, `environment`, `cloud`, `tier`
- [ ] Kubecost or OpenCost deployed on all clusters
- [ ] Monthly cost review meeting scheduled (FinOps team + Engineering leads)
- [ ] Budget alerts configured for 80% + 100% thresholds per cloud
- [ ] Spot/preemptible usage > 50% for non-critical workloads
- [ ] Savings Plans / CUDs purchased for baseline compute
- [ ] Private interconnect for inter-cloud traffic
- [ ] Egress costs monitored and alerted on
- [ ] Idle resource cleanup automated (Karpenter consolidation, namespace cleanup)
- [ ] Cost anomaly detection enabled (AWS CE, GCP Budget, Azure Advisor)
