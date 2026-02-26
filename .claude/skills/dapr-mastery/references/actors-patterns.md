# Dapr Actors — Virtual Actor Pattern Reference

Dapr implements the **Virtual Actor pattern**: actors are activated on demand, garbage-collected
when idle, and their state persists across activations. Built on Orleans/Proto.Actor concepts.

## Core Guarantees

| Guarantee | Description |
|-----------|-------------|
| Single-threaded | Only one method executes at a time per actor instance |
| Location transparent | Caller doesn't know which pod hosts the actor |
| Automatic distribution | Placement service distributes actors across pods |
| Durable state | State stored in configured state backend |
| Garbage collection | Deactivated after `actorIdleTimeout`, state preserved |

## Actor Lifecycle

```
Activate → Execute Methods → Idle timeout → Deactivate (state saved)
              ↑__________________________________________|  (re-activate on next call)
```

## Placement Service

The **Placement service** is a Dapr control-plane component that:
- Maintains a consistent hash ring of all actor hosts
- Routes actor calls to correct pod
- Rebalances actors during scaling events
- Must have 3 replicas in production for HA

## Actor Runtime Configuration

In **Dapr Configuration** resource:
```yaml
apiVersion: dapr.io/v1alpha1
kind: Configuration
metadata:
  name: actor-config
  namespace: production
spec:
  entities:
    - OrderActor
    - PaymentActor
    - InventoryActor
  actorIdleTimeout: 1h          # Deactivate after 1 hour idle
  actorScanInterval: 30s         # How often to check for idle actors
  drainOngoingCallTimeout: 60s  # Wait for in-flight calls during rebalance
  drainRebalancedActors: true    # Graceful drain during scaling
  reentrancy:
    enabled: true
    maxStackDepth: 32             # Max reentrant call depth
  remindersStoragePartitions: 7  # Partition reminders for scale (>100k actors)
  features:
    - name: SchedulerReminders
      enabled: true               # v1.15+: use Scheduler for reminders
```

## Timers vs Reminders — Decision Guide

### Timers
```python
# Register timer — fires only while actor is ACTIVE
async def _on_activate(self):
    await self.register_timer(
        timer_name="heartbeat",
        callback="heartbeat_callback",
        due_time=timedelta(seconds=10),
        period=timedelta(minutes=1),
        ttl=timedelta(hours=24)    # Auto-remove after TTL
    )

async def heartbeat_callback(self, timer_request):
    # Ephemeral work — OK to lose on deactivation
    pass

async def _on_deactivate(self):
    await self.unregister_timer("heartbeat")
```

### Reminders (Durable)
```python
# Register reminder — survives deactivation, persisted in state store
async def schedule_payment(self, amount: float):
    await self.register_reminder(
        reminder_name="charge-card",
        state=json.dumps({"amount": amount}).encode(),
        due_time=timedelta(minutes=30),
        period=timedelta(0),       # No repeat (one-shot)
        ttl=timedelta(hours=48)
    )

async def receive_reminder(self, name: str, state: bytes,
                            due_time: timedelta, period: timedelta,
                            ttl: Optional[timedelta]):
    if name == "charge-card":
        data = json.loads(state)
        await self.process_payment(data["amount"])
```

**Rule**: Use reminders for any work that MUST happen even if actor deactivates.

## Python Actor Implementation (FastAPI)

```python
# order_actor.py
from dapr.actor import Actor, ActorInterface, actormethod
from dapr.actor.runtime.config import ActorRuntimeConfig
from typing import Optional
import json

class OrderActorInterface(ActorInterface):
    @actormethod(name="CreateOrder")
    async def create_order(self, data: dict) -> dict: ...

    @actormethod(name="GetOrder")
    async def get_order(self) -> Optional[dict]: ...

    @actormethod(name="CancelOrder")
    async def cancel_order(self) -> bool: ...


class OrderActor(Actor, OrderActorInterface):
    """Virtual actor managing a single order lifecycle."""

    def __init__(self, ctx, actor_id):
        super().__init__(ctx, actor_id)

    async def _on_activate(self) -> None:
        """Called when actor is activated."""
        has_state = await self._state_manager.contains_state("order")
        if not has_state:
            await self._state_manager.set_state("order", {"status": "new"})

    async def _on_deactivate(self) -> None:
        """Called before actor is deactivated."""
        pass  # State auto-saved by runtime

    async def create_order(self, data: dict) -> dict:
        # Transactional state update
        await self._state_manager.set_state("order", {
            "id": str(self.id),
            "status": "created",
            "items": data.get("items", []),
            "total": data.get("total", 0)
        })
        # Schedule reminder for payment timeout
        await self.register_reminder(
            "payment-timeout",
            state=b"",
            due_time=timedelta(minutes=15),
            period=timedelta(0)
        )
        return {"id": str(self.id), "status": "created"}

    async def get_order(self) -> Optional[dict]:
        exists, state = await self._state_manager.try_get_state("order")
        return state if exists else None

    async def cancel_order(self) -> bool:
        exists, state = await self._state_manager.try_get_state("order")
        if exists and state["status"] not in ("shipped", "delivered"):
            state["status"] = "cancelled"
            await self._state_manager.set_state("order", state)
            await self.unregister_reminder("payment-timeout")
            return True
        return False

    async def receive_reminder(self, name, state, due_time, period, ttl):
        if name == "payment-timeout":
            # Auto-cancel unpaid orders
            await self.cancel_order()


# FastAPI host
from fastapi import FastAPI
from dapr.actor.runtime.runtime import ActorRuntime
from dapr.actor.runtime.config import ActorRuntimeConfig, ActorReentrancyConfig

app = FastAPI()
config = ActorRuntimeConfig(
    actor_idle_timeout=timedelta(hours=1),
    actor_scan_interval=timedelta(seconds=30),
    drain_rebalanced_actors=True,
    drain_ongoing_call_timeout=timedelta(seconds=60),
    reentrancy=ActorReentrancyConfig(enabled=True, max_stack_depth=32)
)
ActorRuntime.set_actor_config(config)

@app.on_event("startup")
async def startup():
    ActorRuntime.register_actor(OrderActor)

@app.get("/healthz")
async def health(): return {"status": "ok"}
```

## .NET Actor Implementation

```csharp
// IOrderActor.cs
public interface IOrderActor : IActor
{
    Task<OrderDto> CreateOrderAsync(CreateOrderRequest request);
    Task<OrderDto?> GetOrderAsync();
    Task<bool> CancelOrderAsync();
}

// OrderActor.cs
[Actor(TypeName = "OrderActor")]
public class OrderActor : Actor, IOrderActor, IRemindable
{
    private const string OrderStateKey = "order";

    public OrderActor(ActorHost host) : base(host) { }

    protected override async Task OnActivateAsync()
    {
        var exists = await StateManager.ContainsStateAsync(OrderStateKey);
        if (!exists)
            await StateManager.SetStateAsync(OrderStateKey, new OrderDto { Status = "new" });
    }

    public async Task<OrderDto> CreateOrderAsync(CreateOrderRequest request)
    {
        var order = new OrderDto
        {
            Id = Id.GetId(),
            Status = "created",
            Items = request.Items,
            Total = request.Total
        };
        await StateManager.SetStateAsync(OrderStateKey, order);

        // Durable reminder for payment timeout
        await RegisterReminderAsync("payment-timeout", null,
            TimeSpan.FromMinutes(15), TimeSpan.Zero);

        return order;
    }

    public async Task ReceiveReminderAsync(string name, byte[] state,
        TimeSpan dueTime, TimeSpan period)
    {
        if (name == "payment-timeout")
            await CancelOrderAsync();
    }
}
```

## Transactional State (Multi-Key ACID)

```python
# Python — transactional multi-key state
from dapr.clients.grpc._state import StateItem, TransactionalStateOperation

async def transfer_funds(self, from_acc: str, to_acc: str, amount: float):
    # Read both accounts
    _, from_state = await self._state_manager.try_get_state(f"account:{from_acc}")
    _, to_state = await self._state_manager.try_get_state(f"account:{to_acc}")

    # Apply business logic
    from_state["balance"] -= amount
    to_state["balance"] += amount

    # Transactional save (atomic)
    await self._state_manager.save_state()  # Batches all pending state changes
```

## Actor Partitioning for Scale

For >1M actor instances:
```yaml
# Dapr Configuration
remindersStoragePartitions: 7   # 7 is recommended for large scale
```

```python
# Partition actors by business key
class ProductInventoryActor(Actor):
    """One actor per product SKU. Partition by SKU prefix."""
    # Actor ID format: "SKU-{sku_id}"
    # At 1M SKUs → 1M actors → reminder partitions needed
```

**Partitioning strategy**:
- `remindersStoragePartitions: 0` — all in one key (default, bad for scale)
- `remindersStoragePartitions: 7` — split across 7 state store keys
- Increase to 31 or more for millions of actor instances

## Actor Reentrancy

Without reentrancy, A→B→A deadlocks. With reentrancy:
```python
# Actor A calls Actor B which calls back Actor A — allowed with reentrancy
async def process(self):
    proxy_b = ActorProxy.create("ActorB", ActorId("b-1"), ActorBInterface)
    result = await proxy_b.compute()   # B internally calls back A — OK!
    return result
```

Config:
```yaml
reentrancy:
  enabled: true
  maxStackDepth: 32   # Prevent infinite recursion
```

## Actor Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Large state per actor | Slow serialization, memory pressure | Chunk state by key prefix |
| Missing `drainRebalancedActors` | Dropped in-flight calls during scale | Set to `true` |
| Timer for durable work | Lost on deactivation | Use reminders |
| Blocking I/O in actor | Locks turn-based access | Use async/await |
| `remindersStoragePartitions: 0` at scale | Hot key bottleneck | Set ≥7 |
| Actor per HTTP request | Millions of tiny actors | Group by domain entity |
| Sync actor-to-actor loops | Deadlock without reentrancy | Enable reentrancy |
| Missing `actorIdleTimeout` tune | Too many active actors | Tune per workload |
