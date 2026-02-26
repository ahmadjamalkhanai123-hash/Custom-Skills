"""
Dapr Workflow — Saga / Compensation Pattern (Python)
=====================================================
Production-grade checkout saga with:
- Task chaining
- Compensation on failure (reverse rollback)
- External event (approval gate)
- Fan-out/Fan-in for inventory check
- continue_as_new for monitoring
- Retry policies on activities

Requirements:
    pip install dapr dapr-ext-workflow fastapi uvicorn[standard]

Dapr v1.15+ (Workflow API Stable)
"""

import logging
import uuid
from datetime import timedelta
from typing import Optional
import dapr.ext.workflow as wf
from dapr.clients import DaprClient
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Data Models ────────────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    customer_id: str
    items: list[dict]
    total: float
    shipping_address: dict
    requires_approval: bool = False   # High-value orders need approval

class WorkflowResponse(BaseModel):
    instance_id: str
    status: str


# ── Activities (Safe to do I/O) ────────────────────────────────────────────────

def validate_order(ctx: wf.ActivityContext, order: dict) -> dict:
    """Validate order data and enrich with pricing."""
    logger.info(f"Validating order for customer {order['customer_id']}")
    # Simulate validation
    if order["total"] <= 0:
        raise ValueError("Order total must be positive")
    return {**order, "validated": True, "order_id": str(uuid.uuid4())}


def check_inventory(ctx: wf.ActivityContext, item: dict) -> dict:
    """Check inventory availability for a single item."""
    logger.info(f"Checking inventory for item {item['sku']}")
    # Simulate inventory check
    return {
        "sku": item["sku"],
        "available": True,
        "reserved_qty": item["qty"]
    }


def reserve_inventory(ctx: wf.ActivityContext, data: dict) -> dict:
    """Reserve all items in inventory."""
    logger.info(f"Reserving inventory for order {data['order_id']}")
    reservation_id = str(uuid.uuid4())
    return {"reservation_id": reservation_id, "status": "reserved"}


def release_inventory_reservation(ctx: wf.ActivityContext, reservation_id: str) -> bool:
    """COMPENSATION: Release inventory reservation."""
    logger.warning(f"COMPENSATING: Releasing reservation {reservation_id}")
    return True


def charge_payment(ctx: wf.ActivityContext, data: dict) -> dict:
    """Process payment with idempotency key."""
    logger.info(f"Charging payment for order {data['order_id']}")
    # Use order_id as idempotency key to prevent double charges
    payment_id = str(uuid.uuid4())
    return {"payment_id": payment_id, "status": "charged", "amount": data["total"]}


def refund_payment(ctx: wf.ActivityContext, data: dict) -> bool:
    """COMPENSATION: Issue full refund."""
    logger.warning(f"COMPENSATING: Refunding payment {data['payment_id']}")
    return True


def create_shipment(ctx: wf.ActivityContext, data: dict) -> dict:
    """Create shipment record."""
    logger.info(f"Creating shipment for order {data['order_id']}")
    shipment_id = str(uuid.uuid4())
    return {"shipment_id": shipment_id, "status": "created", "eta_days": 3}


def cancel_shipment(ctx: wf.ActivityContext, shipment_id: str) -> bool:
    """COMPENSATION: Cancel shipment."""
    logger.warning(f"COMPENSATING: Cancelling shipment {shipment_id}")
    return True


def send_notification(ctx: wf.ActivityContext, data: dict) -> bool:
    """Send email/SMS notification to customer."""
    logger.info(f"Sending {data['type']} notification to {data['customer_id']}")
    return True


def send_approval_request(ctx: wf.ActivityContext, data: dict) -> bool:
    """Notify approvers of high-value order."""
    logger.info(f"Approval required for order {data['order_id']}, total: {data['total']}")
    return True


# ── Orchestrator (Deterministic — NO I/O here) ────────────────────────────────

def checkout_saga_workflow(ctx: wf.DaprWorkflowContext, input: dict):
    """
    Saga pattern checkout workflow.

    Steps:
    1. Validate order
    2. Check inventory (fan-out/fan-in per item)
    3. [Optional] Wait for approval (external event)
    4. Reserve inventory
    5. Charge payment
    6. Create shipment

    On any failure: compensate in reverse order.
    """
    compensation_stack = []   # Track (activity, args) for rollback

    try:
        # ── Step 1: Validate ──────────────────────────────────────────────────
        order = yield ctx.call_activity(
            validate_order,
            input=input,
            retry_policy=wf.RetryPolicy(
                max_number_of_attempts=3,
                initial_retry_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                max_retry_interval=timedelta(seconds=10)
            )
        )

        # ── Step 2: Check Inventory (Fan-Out/Fan-In) ──────────────────────────
        inventory_tasks = [
            ctx.call_activity(check_inventory, input=item)
            for item in order["items"]
        ]
        inventory_results = yield wf.when_all(inventory_tasks)

        unavailable = [r for r in inventory_results if not r["available"]]
        if unavailable:
            return {
                "order_id": order.get("order_id"),
                "status": "failed",
                "reason": "inventory_unavailable",
                "unavailable_items": [r["sku"] for r in unavailable]
            }

        # ── Step 3: Approval Gate (External Event) ────────────────────────────
        if order.get("requires_approval") or order["total"] > 10000:
            yield ctx.call_activity(send_approval_request, input=order)

            approval_timeout = ctx.current_utc_datetime + timedelta(hours=48)
            approval_task = ctx.wait_for_external_event("order-approved")
            timeout_task = ctx.create_timer(approval_timeout)

            winner = yield wf.when_any([approval_task, timeout_task])

            if winner == timeout_task:
                yield ctx.call_activity(send_notification, input={
                    "type": "approval_timeout",
                    "customer_id": order["customer_id"],
                    "order_id": order["order_id"]
                })
                return {"order_id": order["order_id"], "status": "approval_timeout"}

            approval = approval_task.result
            if not approval.get("approved"):
                return {
                    "order_id": order["order_id"],
                    "status": "rejected",
                    "reason": approval.get("reason", "manager_rejected")
                }

        # ── Step 4: Reserve Inventory ─────────────────────────────────────────
        reservation = yield ctx.call_activity(
            reserve_inventory,
            input={"order_id": order["order_id"], "items": order["items"]},
            retry_policy=wf.RetryPolicy(max_number_of_attempts=3)
        )
        # Register compensation
        compensation_stack.append(
            (release_inventory_reservation, reservation["reservation_id"])
        )

        # ── Step 5: Charge Payment ────────────────────────────────────────────
        payment = yield ctx.call_activity(
            charge_payment,
            input={
                "order_id": order["order_id"],
                "customer_id": order["customer_id"],
                "total": order["total"]
            },
            retry_policy=wf.RetryPolicy(
                max_number_of_attempts=2,   # Limited retries for payment
                initial_retry_interval=timedelta(seconds=2)
            )
        )
        # Register compensation
        compensation_stack.append(
            (refund_payment, {"payment_id": payment["payment_id"], "total": order["total"]})
        )

        # ── Step 6: Create Shipment ───────────────────────────────────────────
        shipment = yield ctx.call_activity(
            create_shipment,
            input={
                "order_id": order["order_id"],
                "address": order.get("shipping_address", {})
            }
        )
        # Register compensation
        compensation_stack.append(
            (cancel_shipment, shipment["shipment_id"])
        )

        # ── Success ───────────────────────────────────────────────────────────
        yield ctx.call_activity(send_notification, input={
            "type": "order_confirmed",
            "customer_id": order["customer_id"],
            "order_id": order["order_id"],
            "shipment_id": shipment["shipment_id"],
            "eta_days": shipment["eta_days"]
        })

        return {
            "order_id": order["order_id"],
            "status": "success",
            "payment_id": payment["payment_id"],
            "shipment_id": shipment["shipment_id"],
            "eta_days": shipment["eta_days"]
        }

    except Exception as e:
        # ── Saga Compensation: Rollback in REVERSE order ──────────────────────
        logger.error(f"Workflow failed: {e}. Compensating {len(compensation_stack)} steps...")

        for compensate_fn, compensate_args in reversed(compensation_stack):
            try:
                yield ctx.call_activity(compensate_fn, input=compensate_args)
            except Exception as comp_err:
                # Log but continue compensating remaining steps
                logger.error(f"Compensation step failed: {comp_err}")

        # Notify customer of failure
        try:
            yield ctx.call_activity(send_notification, input={
                "type": "order_failed",
                "customer_id": input.get("customer_id", "unknown"),
                "reason": str(e)
            })
        except Exception:
            pass

        return {
            "order_id": input.get("order_id", "unknown"),
            "status": "failed",
            "reason": str(e),
            "compensated": len(compensation_stack)
        }


# ── Order Monitor Workflow (Monitor Pattern) ───────────────────────────────────

def order_monitor_workflow(ctx: wf.DaprWorkflowContext, state: dict):
    """
    Eternal monitor: watches order status, alerts on anomalies.
    Uses continue_as_new to prevent history explosion.
    """
    order_id = state["order_id"]
    check_count = state.get("check_count", 0)

    # Check status via activity (safe to do I/O here)
    status = yield ctx.call_activity(
        lambda c, inp: "delivered",   # Replace with real status check
        input=order_id
    )

    if status in ("delivered", "cancelled", "refunded"):
        return {"order_id": order_id, "final_status": status, "checks": check_count}

    # Wait 10 minutes before checking again
    yield ctx.create_timer(ctx.current_utc_datetime + timedelta(minutes=10))

    # continue_as_new: restart workflow with fresh history (prevents memory growth)
    ctx.continue_as_new({
        "order_id": order_id,
        "check_count": check_count + 1
    })


# ── FastAPI Workflow API ───────────────────────────────────────────────────────

app = FastAPI(title="Checkout Workflow Service")
workflow_runtime = wf.WorkflowRuntime()


@app.on_event("startup")
async def startup():
    workflow_runtime.register_workflow(checkout_saga_workflow)
    workflow_runtime.register_activity(validate_order)
    workflow_runtime.register_activity(check_inventory)
    workflow_runtime.register_activity(reserve_inventory)
    workflow_runtime.register_activity(release_inventory_reservation)
    workflow_runtime.register_activity(charge_payment)
    workflow_runtime.register_activity(refund_payment)
    workflow_runtime.register_activity(create_shipment)
    workflow_runtime.register_activity(cancel_shipment)
    workflow_runtime.register_activity(send_notification)
    workflow_runtime.register_activity(send_approval_request)
    await workflow_runtime.start()


@app.on_event("shutdown")
async def shutdown():
    await workflow_runtime.stop()


@app.post("/checkout", response_model=WorkflowResponse)
async def start_checkout(order: OrderRequest):
    """Start checkout saga workflow."""
    instance_id = f"checkout-{order.customer_id}-{uuid.uuid4().hex[:8]}"

    with DaprClient() as d:
        d.start_workflow(
            workflow_component="dapr",
            workflow_name="checkout_saga_workflow",
            instance_id=instance_id,
            input=order.dict()
        )

    return WorkflowResponse(instance_id=instance_id, status="started")


@app.get("/checkout/{instance_id}")
async def get_checkout_status(instance_id: str):
    """Poll workflow status."""
    with DaprClient() as d:
        result = d.get_workflow(
            instance_id=instance_id,
            workflow_component="dapr"
        )
    return {
        "instance_id": instance_id,
        "status": result.runtime_status,
        "result": result.serialized_output
    }


@app.post("/checkout/{instance_id}/approve")
async def approve_order(instance_id: str, approved: bool = True, reason: str = ""):
    """Raise external approval event."""
    with DaprClient() as d:
        d.raise_workflow_event(
            instance_id=instance_id,
            workflow_component="dapr",
            event_name="order-approved",
            event_data={"approved": approved, "reason": reason}
        )
    return {"status": "event_raised"}


@app.delete("/checkout/{instance_id}")
async def terminate_checkout(instance_id: str):
    """Terminate a running workflow."""
    with DaprClient() as d:
        d.terminate_workflow(
            instance_id=instance_id,
            workflow_component="dapr"
        )
    return {"status": "terminated"}


@app.get("/healthz")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("workflow_saga:app", host="0.0.0.0", port=8080, reload=False)
