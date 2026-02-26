# Dapr Workflow Patterns Reference

Dapr Workflow provides **durable execution** — workflows survive crashes, restarts, and scaling.
Built on DurableTask-Go. **Stable as of Dapr v1.15.**

## Architecture

```
Orchestrator (your code) ──→ DurableTask Engine ──→ Dapr State Store
        ↓                           ↑
   Schedule Activities         Replay history on restart
        ↓
   Activity Worker (your code) ──→ External systems (DB, APIs, services)
```

**Key**: Orchestrator is replayed from history on restart → must be **deterministic**.

## The Golden Rule of Workflow Orchestrators

```
✅ SAFE in orchestrator:              ❌ NEVER in orchestrator:
─────────────────────────────         ──────────────────────────────────
- Call ctx.call_activity()            - HTTP calls, DB queries, file I/O
- Call ctx.call_child_workflow()      - Random numbers / GUIDs
- ctx.current_utc_datetime            - datetime.now() / Date.now()
- ctx.wait_for_external_event()       - Non-deterministic branches
- ctx.create_timer()                  - Logging side effects
- ctx.continue_as_new()              - Infinite while/for loops
```

## Pattern 1: Task Chaining

Execute steps sequentially, passing output as input.

```python
# Python SDK
import dapr.ext.workflow as wf

def order_workflow(ctx: wf.DaprWorkflowContext, input: dict):
    # Step 1: Validate order
    validated = yield ctx.call_activity(validate_order, input=input)

    # Step 2: Reserve inventory
    reservation = yield ctx.call_activity(reserve_inventory, input={
        "orderId": validated["id"],
        "items": validated["items"]
    })

    # Step 3: Process payment
    payment = yield ctx.call_activity(process_payment, input={
        "orderId": validated["id"],
        "amount": validated["total"],
        "reservationId": reservation["id"]
    })

    # Step 4: Ship order
    result = yield ctx.call_activity(ship_order, input={
        "orderId": validated["id"],
        "paymentId": payment["id"]
    })
    return result


def validate_order(ctx: wf.ActivityContext, data: dict) -> dict:
    """Activity: validate and enrich order."""
    # Safe to do I/O here
    order = db.get_order(data["id"])
    if not order:
        raise ValueError(f"Order {data['id']} not found")
    return {"id": order.id, "items": order.items, "total": order.total}
```

## Pattern 2: Fan-Out / Fan-In

Execute tasks in parallel, aggregate results.

```python
def batch_processor_workflow(ctx: wf.DaprWorkflowContext, items: list):
    """Process N items in parallel, collect results."""

    # Fan-Out: schedule all activities concurrently
    tasks = [
        ctx.call_activity(process_item, input=item)
        for item in items
    ]

    # Fan-In: wait for ALL to complete
    results = yield wf.when_all(tasks)

    # Aggregate
    successful = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] == "error"]

    yield ctx.call_activity(send_batch_report, input={
        "total": len(items),
        "successful": len(successful),
        "failed": len(failed)
    })
    return {"processed": len(successful), "errors": len(failed)}
```

## Pattern 3: Monitor (Polling Loop)

Recurring check with `continue_as_new` — avoids infinite history growth.

```python
def order_monitor_workflow(ctx: wf.DaprWorkflowContext, order_id: str):
    """Poll order status until terminal state or timeout."""

    # Check current status
    status = yield ctx.call_activity(check_order_status, input=order_id)

    if status in ("delivered", "cancelled", "failed"):
        # Terminal state — end workflow
        return {"orderId": order_id, "finalStatus": status}

    # Non-terminal — wait and check again
    deadline = ctx.current_utc_datetime + timedelta(hours=24)
    if ctx.current_utc_datetime >= deadline:
        # Timed out monitoring
        return {"orderId": order_id, "finalStatus": "timeout"}

    # Wait 5 minutes, then restart with continue_as_new
    yield ctx.create_timer(ctx.current_utc_datetime + timedelta(minutes=5))
    ctx.continue_as_new(order_id)   # Clears history, starts fresh


def check_order_status(ctx: wf.ActivityContext, order_id: str) -> str:
    return db.get_order_status(order_id)
```

## Pattern 4: External Events (Human Approval)

Pause workflow until external system raises an event.

```python
def approval_workflow(ctx: wf.DaprWorkflowContext, request: dict):
    """Pause for human approval before proceeding."""

    # Step 1: Send approval request
    yield ctx.call_activity(send_approval_request, input=request)

    # Step 2: Wait for approval (with timeout)
    approval_timeout = ctx.current_utc_datetime + timedelta(days=3)
    approval_task = ctx.wait_for_external_event("approval-response")
    timeout_task = ctx.create_timer(approval_timeout)

    winner = yield wf.when_any([approval_task, timeout_task])

    if winner == timeout_task:
        yield ctx.call_activity(notify_timeout, input=request)
        return {"status": "timeout"}

    approval = approval_task.result
    if approval["approved"]:
        yield ctx.call_activity(execute_request, input=request)
        return {"status": "approved"}
    else:
        return {"status": "rejected", "reason": approval.get("reason")}


# Raise external event (from another service)
async def approve_request(workflow_id: str, approved: bool):
    with DaprClient() as d:
        d.raise_workflow_event(
            instance_id=workflow_id,
            workflow_component="dapr",
            event_name="approval-response",
            event_data={"approved": approved}
        )
```

## Pattern 5: Compensation / Saga (Critical for Microservices)

Rollback completed steps in **reverse order** on failure.

```python
def checkout_saga_workflow(ctx: wf.DaprWorkflowContext, order: dict):
    """Saga pattern: compensate on failure."""

    compensation_stack = []  # Track completed steps for rollback

    try:
        # Step 1: Reserve inventory
        reservation = yield ctx.call_activity(reserve_inventory, input=order)
        compensation_stack.append(
            (release_inventory_reservation, {"reservationId": reservation["id"]})
        )

        # Step 2: Charge payment
        payment = yield ctx.call_activity(charge_payment, input={
            "orderId": order["id"],
            "amount": order["total"],
            "customerId": order["customerId"]
        })
        compensation_stack.append(
            (refund_payment, {"paymentId": payment["id"], "amount": order["total"]})
        )

        # Step 3: Create shipment
        shipment = yield ctx.call_activity(create_shipment, input={
            "orderId": order["id"],
            "address": order["shippingAddress"]
        })
        compensation_stack.append(
            (cancel_shipment, {"shipmentId": shipment["id"]})
        )

        return {"orderId": order["id"], "status": "success",
                "shipmentId": shipment["id"]}

    except Exception as e:
        # Compensate in REVERSE ORDER
        for compensate_activity, compensate_input in reversed(compensation_stack):
            try:
                yield ctx.call_activity(compensate_activity, input=compensate_input)
            except Exception as comp_err:
                # Log but continue compensating remaining steps
                pass  # In production: use structured logging activity

        return {"orderId": order["id"], "status": "failed", "error": str(e)}
```

## Pattern 6: Child Workflows

Decompose complex orchestrations into reusable sub-workflows.

```python
def master_workflow(ctx: wf.DaprWorkflowContext, batch: dict):
    """Orchestrate multiple sub-workflows."""

    # Launch child workflows for each order
    child_tasks = [
        ctx.call_child_workflow(order_fulfillment_workflow, input=order)
        for order in batch["orders"]
    ]

    results = yield wf.when_all(child_tasks)
    return {"batchId": batch["id"], "results": results}


def order_fulfillment_workflow(ctx: wf.DaprWorkflowContext, order: dict):
    """Reusable child workflow for single order."""
    yield ctx.call_activity(validate_order, input=order)
    yield ctx.call_activity(fulfill_order, input=order)
    return {"orderId": order["id"], "status": "fulfilled"}
```

## Pattern 7: Long-Running Eternal Workflow

Use `continue_as_new` to prevent history accumulation.

```python
def eternal_aggregator_workflow(ctx: wf.DaprWorkflowContext, state: dict):
    """Process events indefinitely with fresh history each cycle."""

    # Process current batch of events
    events = yield ctx.call_activity(fetch_pending_events, input=state)
    processed = yield ctx.call_activity(process_events, input=events)

    # Update running state
    new_state = {
        "totalProcessed": state.get("totalProcessed", 0) + processed["count"],
        "lastProcessed": ctx.current_utc_datetime.isoformat()
    }

    # Wait 1 minute before next cycle
    yield ctx.create_timer(ctx.current_utc_datetime + timedelta(minutes=1))

    # Restart with fresh history (NEVER use while True!)
    ctx.continue_as_new(new_state)
```

## Workflow HTTP API (Async HTTP API Pattern)

```python
# Start workflow
POST /v1.0-beta1/workflows/dapr/{workflowType}/start
Body: { "input": {...} }
Response: { "instanceID": "uuid" }

# Query status
GET /v1.0-beta1/workflows/dapr/{instanceID}
Response: {
  "instanceID": "uuid",
  "workflowName": "checkout_saga_workflow",
  "runtimeStatus": "RUNNING",  // RUNNING|COMPLETED|FAILED|TERMINATED|SUSPENDED
  "createdAt": "...",
  "lastUpdatedAt": "...",
  "serializedOutput": "..."
}

# Raise event
POST /v1.0-beta1/workflows/dapr/{instanceID}/raiseEvent/{eventName}

# Terminate
POST /v1.0-beta1/workflows/dapr/{instanceID}/terminate

# Pause / Resume
POST /v1.0-beta1/workflows/dapr/{instanceID}/pause
POST /v1.0-beta1/workflows/dapr/{instanceID}/resume
```

## .NET Workflow Example

```csharp
// Workflow definition
public class CheckoutWorkflow : Workflow<OrderInput, OrderResult>
{
    public override async Task<OrderResult> RunAsync(
        WorkflowContext context, OrderInput input)
    {
        var compensations = new Stack<Func<Task>>();
        try
        {
            // Step 1
            var reservation = await context.CallActivityAsync<ReservationResult>(
                nameof(ReserveInventoryActivity), input);
            compensations.Push(async () =>
                await context.CallActivityAsync(
                    nameof(ReleaseInventoryActivity), reservation.Id));

            // Step 2
            var payment = await context.CallActivityAsync<PaymentResult>(
                nameof(ChargePaymentActivity), new { input.OrderId, input.Total });
            compensations.Push(async () =>
                await context.CallActivityAsync(
                    nameof(RefundPaymentActivity), payment.Id));

            return new OrderResult { Status = "success" };
        }
        catch
        {
            while (compensations.TryPop(out var compensate))
                await compensate();
            return new OrderResult { Status = "failed" };
        }
    }
}

// Activity
public class ReserveInventoryActivity : WorkflowActivity<OrderInput, ReservationResult>
{
    public override async Task<ReservationResult> RunAsync(
        WorkflowActivityContext context, OrderInput input)
    {
        // Safe to do I/O here
        return await inventoryService.ReserveAsync(input.Items);
    }
}
```

## Workflow Scaling (v1.15+)

```yaml
# Scale from 0 to N — Dapr Scheduler manages durability
apiVersion: apps/v1
kind: Deployment
metadata:
  name: workflow-service
spec:
  replicas: 3           # Minimum 2 for HA
  template:
    metadata:
      annotations:
        dapr.io/enabled: "true"
        dapr.io/app-id: "workflow-service"
        # Workflow apps need higher sidecar resources
        dapr.io/sidecar-memory-limit: "512Mi"
        dapr.io/sidecar-cpu-limit: "500m"
```

## Activity Retry Configuration

```python
def order_workflow(ctx: wf.DaprWorkflowContext, input: dict):
    # With retry policy on activity
    result = yield ctx.call_activity(
        process_payment,
        input=input,
        retry_policy=wf.RetryPolicy(
            max_number_of_attempts=3,
            initial_retry_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            max_retry_interval=timedelta(seconds=30)
        )
    )
```

## Workflow Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| I/O in orchestrator | Non-deterministic, breaks replay | Move to activity |
| `datetime.now()` in orchestrator | Non-deterministic | Use `ctx.current_utc_datetime` |
| `while True:` loop | Unbounded history growth | Use `continue_as_new` |
| No compensation | Partial failures leave inconsistent state | Implement saga pattern |
| Blocking activity without timeout | Workflow hangs forever | Set activity timeout |
| Large payload in workflow input | Memory pressure, slow serialization | Pass reference IDs, load in activity |
| Logging in orchestrator | Logs duplicated on replay | Log only in activities |
| Random/UUID in orchestrator | Different on replay → wrong behavior | Generate in activity, pass to orchestrator |
