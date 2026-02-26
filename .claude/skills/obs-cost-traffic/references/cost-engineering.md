# Cost Engineering
## FinOps Framework, Cloud Cost Tools, Cost Attribution, Kubernetes Cost Management

---

## FinOps Framework

The FinOps Foundation defines a three-phase cycle:

```
INFORM → OPTIMIZE → OPERATE → (repeat)

INFORM:   Visibility into cloud spend, allocation, forecasting
OPTIMIZE: Identify waste, right-size resources, purchase commitments
OPERATE:  Governance, budgets, automated policies, culture
```

### Maturity Model
| Crawl | Walk | Run |
|-------|------|-----|
| Basic cost reports | Per-team allocation | Real-time cost anomaly |
| Manual tagging | Automated tagging | Automated rightsizing |
| Monthly reviews | Weekly reviews | Daily/real-time reviews |
| Cloud console only | Third-party tools | Custom FinOps platform |

---

## AWS Cost Management

### Cost Explorer
```python
# boto3 — get cost by service/tag
import boto3
from datetime import date, timedelta

ce = boto3.client('ce', region_name='us-east-1')

response = ce.get_cost_and_usage(
    TimePeriod={
        'Start': (date.today() - timedelta(days=30)).isoformat(),
        'End': date.today().isoformat()
    },
    Granularity='DAILY',
    Filter={
        'And': [
            {'Tags': {'Key': 'Environment', 'Values': ['production']}},
            {'Tags': {'Key': 'Team', 'Values': ['platform']}}
        ]
    },
    GroupBy=[
        {'Type': 'DIMENSION', 'Key': 'SERVICE'},
        {'Type': 'TAG', 'Key': 'service'}
    ],
    Metrics=['UnblendedCost', 'UsageQuantity']
)

for result in response['ResultsByTime']:
    for group in result['Groups']:
        service = group['Keys'][0]
        cost = group['Metrics']['UnblendedCost']['Amount']
        print(f"{service}: ${float(cost):.2f}")
```

### AWS Budgets
```json
{
  "BudgetName": "production-monthly-budget",
  "BudgetLimit": {"Amount": "5000", "Unit": "USD"},
  "BudgetType": "COST",
  "TimeUnit": "MONTHLY",
  "CostFilters": {
    "TagKeyValue": ["user:Environment$production"]
  },
  "NotificationsWithSubscribers": [
    {
      "Notification": {
        "NotificationType": "ACTUAL",
        "ComparisonOperator": "GREATER_THAN",
        "Threshold": 80,
        "ThresholdType": "PERCENTAGE"
      },
      "Subscribers": [
        {"SubscriptionType": "EMAIL", "Address": "finops@company.com"},
        {"SubscriptionType": "SNS", "Address": "arn:aws:sns:us-east-1:123:cost-alerts"}
      ]
    },
    {
      "Notification": {
        "NotificationType": "FORECASTED",
        "ComparisonOperator": "GREATER_THAN",
        "Threshold": 110,
        "ThresholdType": "PERCENTAGE"
      },
      "Subscribers": [
        {"SubscriptionType": "EMAIL", "Address": "finops@company.com"}
      ]
    }
  ]
}
```

### AWS Cost Optimization Actions
| Optimization | Savings | Complexity | When |
|-------------|---------|------------|------|
| Savings Plans (1yr) | 30-40% | Low | Stable baseline workloads |
| Savings Plans (3yr) | 50-66% | Low | Long-term commitment |
| Reserved Instances | 30-72% | Medium | Databases, stable EC2 |
| Spot Instances | 70-90% | High | Batch, stateless workers |
| Compute Optimizer | 10-30% | Low | Rightsizing recommendations |
| S3 Intelligent-Tiering | 40-68% | Very Low | Infrequent access data |
| RDS Multi-AZ → Backup | 50% | Medium | Dev/staging only |
| Auto Scaling schedules | 30-50% | Low | Predictable patterns |

```yaml
# AWS Cost Allocation Tags (must activate in billing console)
Required tags:
  - env: [dev, staging, production]
  - team: [platform, backend, frontend, data]
  - service: [order-api, payment-svc, user-svc]
  - project: [checkout-v2, data-pipeline]
  - cost-center: [COST-001, COST-002]
```

---

## GCP Cloud Billing

### BigQuery Cost Analysis
```sql
-- GCP Billing export to BigQuery
-- Daily cost by service and label
SELECT
  DATE(usage_start_time) AS date,
  service.description AS service,
  labels.value AS team,
  SUM(cost) AS total_cost,
  SUM(IFNULL((
    SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit
  ), 0)) AS total_credits,
  SUM(cost) + SUM(IFNULL((
    SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit
  ), 0)) AS net_cost
FROM
  `project.billing_dataset.gcp_billing_export_v1_*`,
  UNNEST(labels) AS labels
WHERE
  labels.key = 'team'
  AND DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 1, 2, 3
ORDER BY 5 DESC;
```

### GCP Budget API (Python)
```python
from google.cloud import billing_budgets_v1

client = billing_budgets_v1.BudgetServiceClient()

budget = billing_budgets_v1.Budget(
    display_name="Production Monthly Budget",
    budget_filter=billing_budgets_v1.Filter(
        projects=["projects/my-project-id"],
        labels={"environment": billing_budgets_v1.Filter.LabelsValue(
            values=["production"]
        )}
    ),
    amount=billing_budgets_v1.BudgetAmount(
        specified_amount=money_pb2.Money(currency_code="USD", units=5000)
    ),
    threshold_rules=[
        billing_budgets_v1.ThresholdRule(
            threshold_percent=0.5,
            spend_basis=billing_budgets_v1.ThresholdRule.Basis.CURRENT_SPEND
        ),
        billing_budgets_v1.ThresholdRule(threshold_percent=0.8),
        billing_budgets_v1.ThresholdRule(threshold_percent=1.0),
        billing_budgets_v1.ThresholdRule(
            threshold_percent=1.1,
            spend_basis=billing_budgets_v1.ThresholdRule.Basis.FORECASTED_SPEND
        ),
    ],
    notifications_rule=billing_budgets_v1.NotificationsRule(
        pubsub_topic="projects/my-project/topics/billing-alerts",
        monitoring_notification_channels=[
            "projects/my-project/notificationChannels/12345"
        ]
    )
)
```

### GCP Cost Optimization
- **Committed Use Discounts (CUD)**: 1yr = 37% off, 3yr = 55% off for Compute
- **Sustained Use Discounts**: Automatic after 25% of month usage (15-30% off)
- **Preemptible VMs / Spot VMs**: 60-91% off for fault-tolerant workloads
- **Cloud Run**: Scales to zero (pay per request), eliminates idle waste
- **GKE Autopilot**: Pay per pod, not per node — no over-provisioning

---

## Azure Cost Management

### Azure Cost Management REST API
```python
import requests

def get_azure_costs(subscription_id: str, access_token: str):
    url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    payload = {
        "type": "ActualCost",
        "timeframe": "MonthToDate",
        "dataset": {
            "granularity": "Daily",
            "aggregation": {
                "totalCost": {"name": "Cost", "function": "Sum"}
            },
            "grouping": [
                {"type": "Dimension", "name": "ServiceName"},
                {"type": "TagKey", "name": "team"}
            ],
            "filter": {
                "tags": {
                    "name": "environment",
                    "operator": "In",
                    "values": ["production"]
                }
            }
        }
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    return requests.post(url, json=payload, headers=headers).json()
```

### Azure Cost Optimization
- **Reserved Instances**: 1yr = up to 40% off, 3yr = up to 72% off
- **Azure Hybrid Benefit**: Use existing Windows/SQL Server licenses (40% savings)
- **Spot VMs**: Up to 90% off (interruptible workloads)
- **Azure Advisor**: Automated rightsizing recommendations
- **Dev/Test pricing**: 40-55% off for non-production workloads

---

## Kubernetes Cost Management

### Kubecost — Per-Namespace/Team/Service Cost
```yaml
# kubecost helm values
kubecostToken: ""  # Use free tier for < 10 nodes

prometheus:
  enabled: false  # Use existing prometheus
  fqdn: http://prometheus-server.monitoring.svc:80

persistentVolume:
  size: 32Gi

kubecostProductConfigs:
  clusterName: "production-eks"
  currencyCode: "USD"
  # Cloud billing integration
  cloudIntegration:
    awsAthenaBucketName: "kubecost-billing-export"
    awsAthenaRegion: "us-east-1"
    awsAthenaDatabase: "athenacurcfn"
    awsAthenaCatalog: "AwsDataCatalog"
    awsAthenaBucketPrefix: "cur-reports"

# Cost allocation by labels
reporting:
  productAnalytics: true

networkCosts:
  enabled: true   # Track cross-AZ, egress costs
  config:
    services:
      - podSelector:
          matchLabels: {}
        services:
          - name: "internet"
```

**Kubecost API queries**:
```bash
# Cost for a specific namespace in last 7 days
curl "http://kubecost.monitoring.svc/model/allocation?window=7d&aggregate=namespace&namespace=payment"

# Efficiency report (wasted resources)
curl "http://kubecost.monitoring.svc/model/savings/requestSizingV2?window=7d&minSavings=10"
```

### OpenCost (CNCF — Free, Open Source)
```yaml
# opencost helm values
opencost:
  exporter:
    cloudProviderApiKey: ""
    defaultClusterId: "production-cluster"
  prometheus:
    external:
      enabled: true
      url: http://prometheus-server.monitoring.svc:80
  ui:
    enabled: true
```

### Goldilocks — CPU/Memory Rightsizing
```bash
# Install and run VPA recommendations per deployment
helm install goldilocks fairwinds-stable/goldilocks -n goldilocks
kubectl label namespace production goldilocks.fairwinds.com/enabled=true
```

---

## Cost Attribution Strategy (Tagging)

### Mandatory Tag Policy (All Clouds)
```yaml
required_tags:
  env:
    description: "Environment"
    values: [dev, staging, production, sandbox]
  team:
    description: "Owning team"
    pattern: "^[a-z][a-z-]+[a-z]$"
  service:
    description: "Microservice name"
    pattern: "^[a-z][a-z-]+[a-z]$"
  project:
    description: "Business project"
    examples: [checkout-v2, payments-revamp]
  cost-center:
    description: "Finance cost center code"
    pattern: "^CC-[0-9]{4}$"
```

### AWS Tag Enforcement (Service Control Policy)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUntaggedResources",
      "Effect": "Deny",
      "Action": ["ec2:RunInstances", "rds:CreateDBInstance"],
      "Resource": "*",
      "Condition": {
        "Null": {
          "aws:RequestTag/team": "true",
          "aws:RequestTag/env": "true",
          "aws:RequestTag/service": "true"
        }
      }
    }
  ]
}
```

---

## Observability Cost Optimization

### Metrics Cardinality = Storage Cost
```
1,000 unique time series × 15s scrape × 15 days = ~86M samples
At $0.12/M samples (Grafana Cloud) = ~$10/month per 1K series

High-cardinality labels create exponential costs:
- user_id label with 100K users = 100K × all other labels = disaster
```

### Log Volume = Storage Cost
```
100 services × 1000 req/s × 500 bytes/log = 50 MB/s = 4.3 TB/day
CloudWatch Logs ingestion: $0.50/GB = $2,150/day!

Solutions:
- Sample INFO logs to 10% (90% reduction)
- Drop health check logs (5-20% reduction)
- Use Loki with S3 backend (<$50/TB/month vs CloudWatch)
- Enable CloudWatch Log Groups compression
```

### Trace Sampling ROI
```
1000 req/s × 100% sampling × 5KB/trace = 5 MB/s = 432 GB/day
Datadog APM: $31/host/month + $1.70/million spans → very expensive at scale

Solution: Tail-based 5-10% sampling = 90% cost reduction
with 100% capture of errors and slow traces
```

---

## Multi-Cloud Cost Tools

### CloudHealth by VMware (Enterprise)
- Unified view across AWS, GCP, Azure
- Policy-based governance and automated rightsizing
- Custom showback/chargeback reports
- Integration with JIRA for cost optimization tickets

### Apptio Cloudability
- FOCUS spec compliance (Cloud FinOps standard)
- Forecasting with ML
- Business mapping of cloud costs to products/teams

### Infracost (CI/CD Cost Estimation)
```yaml
# .github/workflows/cost-check.yml
- name: Run Infracost
  uses: infracost/actions/setup@v3
  with:
    api-key: ${{ secrets.INFRACOST_API_KEY }}

- name: Generate cost estimate
  run: |
    infracost breakdown --path=./terraform \
      --format=json \
      --out-file=/tmp/infracost.json

- name: Post cost comment on PR
  uses: infracost/actions/comment@v3
  with:
    path: /tmp/infracost.json
    behavior: update  # Update existing comment
```

### FOCUS Spec (FinOps Open Cost and Usage Specification)
- Vendor-neutral billing data format
- Normalizes AWS CUR, GCP Billing Export, Azure Cost Export
- Enables unified multi-cloud cost analysis
- Reference: https://focus.finops.org/
