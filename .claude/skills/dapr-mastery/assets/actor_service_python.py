"""
Dapr Virtual Actor Service — Production Template (Python)
=========================================================
Full-featured actor host with FastAPI, reentrancy, timers, reminders,
transactional state, and health endpoints.

Requirements:
    pip install dapr dapr-ext-fastapi fastapi uvicorn[standard]
"""

import logging
import json
from datetime import timedelta
from typing import Optional
from fastapi import FastAPI, Request
from dapr.actor import Actor, ActorInterface, actormethod
from dapr.actor.runtime.runtime import ActorRuntime
from dapr.actor.runtime.config import ActorRuntimeConfig, ActorReentrancyConfig
import uvicorn

logging.basicConfig(
    level=logging.WARNING,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}'
)
logger = logging.getLogger(__name__)

# ── Actor Interface ────────────────────────────────────────────────────────────

class OrderActorInterface(ActorInterface):
    """Define the public contract for OrderActor."""

    @actormethod(name="CreateOrder")
    async def create_order(self, data: dict) -> dict: ...

    @actormethod(name="GetOrder")
    async def get_order(self) -> Optional[dict]: ...

    @actormethod(name="UpdateStatus")
    async def update_status(self, new_status: str) -> bool: ...

    @actormethod(name="CancelOrder")
    async def cancel_order(self) -> bool: ...


# ── Actor Implementation ───────────────────────────────────────────────────────

class OrderActor(Actor, OrderActorInterface):
    """
    Virtual actor managing the lifecycle of a single order.

    Actor ID = Order ID (e.g., "ORDER-123456")
    State key: "order" → order document
    Reminder: "payment-timeout" → auto-cancel unpaid orders
    """

    ORDER_KEY = "order"
    TERMINAL_STATUSES = {"shipped", "delivered", "cancelled", "refunded"}

    def __init__(self, ctx, actor_id):
        super().__init__(ctx, actor_id)

    # ── Lifecycle Hooks ────────────────────────────────────────────────────────

    async def _on_activate(self) -> None:
        """Initialize state on first activation."""
        has_state = await self._state_manager.contains_state(self.ORDER_KEY)
        if not has_state:
            initial_state = {
                "id": str(self.id),
                "status": "initialized",
                "items": [],
                "total": 0.0,
                "created_at": None
            }
            await self._state_manager.set_state(self.ORDER_KEY, initial_state)
        logger.info(f"OrderActor activated: {self.id}")

    async def _on_deactivate(self) -> None:
        """Cleanup on deactivation (state already persisted by runtime)."""
        logger.info(f"OrderActor deactivated: {self.id}")

    # ── Business Methods ───────────────────────────────────────────────────────

    async def create_order(self, data: dict) -> dict:
        """Create a new order and schedule payment timeout reminder."""
        from datetime import datetime, timezone

        exists, current = await self._state_manager.try_get_state(self.ORDER_KEY)
        if exists and current.get("status") not in ("initialized",):
            return {"error": "Order already exists", "id": str(self.id)}

        order = {
            "id": str(self.id),
            "status": "pending_payment",
            "items": data.get("items", []),
            "total": data.get("total", 0.0),
            "customer_id": data.get("customer_id"),
            "shipping_address": data.get("shipping_address", {}),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Save state
        await self._state_manager.set_state(self.ORDER_KEY, order)

        # Schedule durable reminder: auto-cancel if no payment in 30 min
        # Reminder survives actor deactivation (unlike timers)
        await self.register_reminder(
            reminder_name="payment-timeout",
            state=json.dumps({"order_id": str(self.id)}).encode(),
            due_time=timedelta(minutes=30),
            period=timedelta(0),           # One-shot, no repeat
            ttl=timedelta(hours=2)         # Auto-remove after 2 hours
        )

        logger.info(f"Order created: {self.id}, total: {order['total']}")
        return {"id": str(self.id), "status": order["status"]}

    async def get_order(self) -> Optional[dict]:
        """Retrieve current order state."""
        exists, state = await self._state_manager.try_get_state(self.ORDER_KEY)
        return state if exists else None

    async def update_status(self, new_status: str) -> bool:
        """Update order status with validation."""
        exists, order = await self._state_manager.try_get_state(self.ORDER_KEY)
        if not exists:
            return False

        # Validate state transitions
        valid_transitions = {
            "pending_payment": ["paid", "cancelled"],
            "paid": ["processing", "refunded"],
            "processing": ["shipped", "failed"],
            "shipped": ["delivered"],
            "delivered": [],
            "cancelled": [],
            "failed": ["processing"],   # Allow retry
            "refunded": []
        }

        current_status = order.get("status", "unknown")
        if new_status not in valid_transitions.get(current_status, []):
            logger.warning(
                f"Invalid transition {current_status}→{new_status} for order {self.id}"
            )
            return False

        order["status"] = new_status

        # Cancel payment reminder if payment received
        if new_status == "paid":
            try:
                await self.unregister_reminder("payment-timeout")
            except Exception:
                pass  # Already fired or expired

        await self._state_manager.set_state(self.ORDER_KEY, order)
        return True

    async def cancel_order(self) -> bool:
        """Cancel order if in cancellable state."""
        return await self.update_status("cancelled")

    # ── Reminder Handler ───────────────────────────────────────────────────────

    async def receive_reminder(
        self,
        name: str,
        state: bytes,
        due_time: timedelta,
        period: timedelta,
        ttl: Optional[timedelta] = None
    ):
        """Handle durable reminders."""
        if name == "payment-timeout":
            exists, order = await self._state_manager.try_get_state(self.ORDER_KEY)
            if exists and order.get("status") == "pending_payment":
                logger.warning(f"Payment timeout for order {self.id} — auto-cancelling")
                await self.update_status("cancelled")


# ── FastAPI Application ────────────────────────────────────────────────────────

app = FastAPI(title="Order Actor Service", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    """Configure and register actors on startup."""
    config = ActorRuntimeConfig(
        actor_idle_timeout=timedelta(hours=1),        # Deactivate after 1h idle
        actor_scan_interval=timedelta(seconds=30),     # Check every 30s
        drain_rebalanced_actors=True,                   # Graceful drain on scale
        drain_ongoing_call_timeout=timedelta(seconds=60),
        reentrancy=ActorReentrancyConfig(
            enabled=True,
            max_stack_depth=32               # Max call chain depth
        )
    )
    ActorRuntime.set_actor_config(config)
    ActorRuntime.register_actor(OrderActor)
    logger.info("OrderActor registered with Dapr runtime")


@app.on_event("shutdown")
async def shutdown_event():
    await ActorRuntime.stop()


# ── Health Endpoints (Required by Dapr) ───────────────────────────────────────

@app.get("/healthz/ready")
async def readiness():
    return {"status": "ready"}


@app.get("/healthz/live")
async def liveness():
    return {"status": "alive"}


# ── Dapr Actor Router (Auto-configured by SDK) ────────────────────────────────
# Dapr expects:
#   PUT  /actors/{actorType}/{actorId}/method/{methodName}
#   PUT  /actors/{actorType}/{actorId}/reminders/{reminderName}
#   DELETE /actors/{actorType}/{actorId}/reminders/{reminderName}
#   GET  /actors/{actorType}/{actorId}/reminders/{reminderName}
#   PUT  /actors/{actorType}/{actorId}/timers/{timerName}
#   DELETE /actors/{actorType}/{actorId}/timers/{timerName}
#   GET  /dapr/config

from dapr.ext.fastapi import DaprActor

actor = DaprActor(app)


@app.on_event("startup")
async def register_actors():
    await actor.register_actor(OrderActor)


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "actor_service:app",
        host="0.0.0.0",
        port=8080,
        workers=1,             # Actor apps: single worker to avoid state races
        log_level="warning"
    )
