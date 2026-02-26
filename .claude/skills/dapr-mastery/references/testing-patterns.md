# Dapr Testing Patterns Reference

Testing strategy for Dapr applications across all tiers.
Large/complex projects MUST have coverage at all three layers.

## Testing Pyramid for Dapr Apps

```
         ┌───────────┐
         │ E2E Tests │  Dapr + real infra (slow, few)
         ├───────────┤
         │Integration│  Dapr sidecar + test containers (medium)
         ├───────────┤
         │Unit Tests │  Mocked Dapr client (fast, many)
         └───────────┘
```

---

## 1. Unit Testing — Mock the Dapr Client

### Python (pytest + unittest.mock)

```python
# test_order_service.py
import pytest
from unittest.mock import MagicMock, patch
from dapr.clients import DaprClient

@pytest.fixture
def mock_dapr():
    """Mock Dapr client for unit tests — no sidecar needed."""
    with patch("dapr.clients.DaprClient") as mock_client:
        instance = MagicMock()
        mock_client.return_value.__enter__ = MagicMock(return_value=instance)
        mock_client.return_value.__exit__ = MagicMock(return_value=False)
        yield instance

def test_create_order_saves_state(mock_dapr):
    """Unit test: order creation saves state + publishes event."""
    from services.order_service import create_order

    order_data = {"customer_id": "cust-1", "items": [{"sku": "A1"}], "total": 99.0}
    result = create_order(order_data, dapr_client=mock_dapr)

    # Assert state was saved
    mock_dapr.save_state.assert_called_once()
    call_args = mock_dapr.save_state.call_args
    assert call_args.kwargs["store_name"] == "statestore"

    # Assert event was published
    mock_dapr.publish_event.assert_called_once()
    pub_args = mock_dapr.publish_event.call_args
    assert pub_args.kwargs["topic_name"] == "orders.created"

    assert result["status"] == "created"

def test_get_order_not_found(mock_dapr):
    """Unit test: 404 when state key missing."""
    from fastapi.testclient import TestClient
    from services.order_service import app

    mock_dapr.get_state.return_value.data = None  # Empty state

    client = TestClient(app)
    resp = client.get("/orders/missing-id")
    assert resp.status_code == 404
```

### .NET (xUnit + Moq)

```csharp
public class OrderServiceTests
{
    private readonly Mock<DaprClient> _mockDapr;
    private readonly OrderService _service;

    public OrderServiceTests()
    {
        _mockDapr = new Mock<DaprClient>();
        _service = new OrderService(_mockDapr.Object);
    }

    [Fact]
    public async Task CreateOrder_SavesToStateAndPublishes()
    {
        var request = new CreateOrderRequest { CustomerId = "c1", Total = 100m };

        _mockDapr.Setup(d => d.SaveStateAsync(
            "statestore", It.IsAny<string>(), It.IsAny<Order>(),
            null, null, default))
            .Returns(Task.CompletedTask);

        _mockDapr.Setup(d => d.PublishEventAsync(
            "pubsub", "orders.created", It.IsAny<object>(), default))
            .Returns(Task.CompletedTask);

        var result = await _service.CreateOrderAsync(request);

        Assert.Equal("created", result.Status);
        _mockDapr.Verify(d => d.SaveStateAsync(
            "statestore", It.IsAny<string>(), It.IsAny<Order>(),
            null, null, default), Times.Once);
    }
}
```

---

## 2. Unit Testing Actors

### Python Actor Unit Test

```python
# test_order_actor.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from dapr.actor import ActorId

@pytest.fixture
def mock_actor_ctx():
    ctx = MagicMock()
    ctx.actor_id = ActorId("ORDER-001")
    return ctx

@pytest.fixture
async def order_actor(mock_actor_ctx):
    """Create actor instance with mocked state manager."""
    from actor_service import OrderActor
    actor = OrderActor(mock_actor_ctx, ActorId("ORDER-001"))

    # Mock the state manager
    actor._state_manager = AsyncMock()
    actor._state_manager.contains_state = AsyncMock(return_value=False)
    actor._state_manager.try_get_state = AsyncMock(return_value=(False, None))
    actor._state_manager.set_state = AsyncMock()
    actor.register_reminder = AsyncMock()
    actor.unregister_reminder = AsyncMock()
    return actor

@pytest.mark.asyncio
async def test_create_order_sets_state(order_actor):
    data = {"items": [{"sku": "A1", "qty": 2}], "total": 50.0}
    result = await order_actor.create_order(data)

    order_actor._state_manager.set_state.assert_called_once()
    order_actor.register_reminder.assert_called_with(
        reminder_name="payment-timeout",
        state=b"",
        due_time=pytest.approx(30 * 60, abs=1),  # 30 minutes
        period=pytest.approx(0),
        ttl=pytest.approx(2 * 60 * 60)
    )
    assert result["status"] == "pending_payment"

@pytest.mark.asyncio
async def test_cancel_order_removes_reminder(order_actor):
    # Set up existing order in state
    order_actor._state_manager.try_get_state = AsyncMock(
        return_value=(True, {"status": "pending_payment", "items": []})
    )
    result = await order_actor.cancel_order()
    assert result is True
    order_actor.unregister_reminder.assert_called_once_with("payment-timeout")
```

---

## 3. Unit Testing Workflows

### Python Workflow Unit Test

```python
# test_checkout_workflow.py
import pytest
from unittest.mock import MagicMock, patch
import dapr.ext.workflow as wf

def test_checkout_saga_compensation_on_payment_failure():
    """Test that compensation runs in reverse order when payment fails."""
    compensation_calls = []

    def fake_call_activity(fn, input=None, **kwargs):
        if fn.__name__ == "charge_payment":
            raise Exception("Payment gateway timeout")
        if fn.__name__ in ("release_inventory_reservation", "refund_payment",
                           "cancel_shipment", "send_notification"):
            compensation_calls.append(fn.__name__)
        return {"status": "ok", "id": "fake-id"}

    ctx = MagicMock()
    ctx.call_activity.side_effect = fake_call_activity
    ctx.current_utc_datetime = __import__("datetime").datetime.utcnow()

    # Use dapr's workflow test harness
    with wf.WorkflowTestHarness() as harness:
        harness.register_workflow(checkout_saga_workflow)
        result = harness.run_workflow(checkout_saga_workflow, input={
            "customer_id": "c1", "items": [], "total": 500.0
        })

    assert result["status"] == "failed"
    # Compensation must run in reverse
    assert "release_inventory_reservation" in compensation_calls
```

---

## 4. Integration Testing with Dapr Test Containers

```python
# test_integration_dapr.py
# Requires: pip install testcontainers
import pytest
from testcontainers.redis import RedisContainer
import subprocess
import httpx
import time

@pytest.fixture(scope="session")
def dapr_sidecar():
    """Spin up a real Dapr sidecar for integration tests."""
    with RedisContainer("redis:7-alpine") as redis:
        redis_host = f"localhost:{redis.get_exposed_port(6379)}"

        # Start app + sidecar via dapr run
        proc = subprocess.Popen([
            "dapr", "run",
            "--app-id", "test-service",
            "--app-port", "8090",
            "--dapr-http-port", "3590",
            "--resources-path", "./test-components",
            "--",
            "uvicorn", "main:app", "--port", "8090"
        ])
        time.sleep(3)  # Wait for sidecar ready

        yield {"http_port": 3590, "app_port": 8090}
        proc.terminate()

def test_state_save_and_get(dapr_sidecar):
    """Integration: state actually persisted to Redis via Dapr sidecar."""
    base = f"http://localhost:{dapr_sidecar['http_port']}"

    # Save via Dapr HTTP API
    r = httpx.post(f"{base}/v1.0/state/statestore",
                   json=[{"key": "test-key", "value": {"data": 42}}])
    assert r.status_code == 204

    # Get back
    r = httpx.get(f"{base}/v1.0/state/statestore/test-key")
    assert r.status_code == 200
    assert r.json()["data"] == 42

def test_pubsub_publish(dapr_sidecar):
    """Integration: event published to Redis Streams."""
    base = f"http://localhost:{dapr_sidecar['http_port']}"
    r = httpx.post(f"{base}/v1.0/publish/pubsub/orders.created",
                   json={"orderId": "int-test-001"},
                   headers={"Content-Type": "application/json"})
    assert r.status_code == 204
```

### Test Components for Integration Tests

```yaml
# test-components/statestore.yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: statestore
spec:
  type: state.redis
  version: v1
  metadata:
    - name: redisHost
      value: "localhost:6379"     # plaintext OK in tests
    - name: redisPassword
      value: ""
---
# test-components/pubsub.yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: pubsub
spec:
  type: pubsub.redis
  version: v1
  metadata:
    - name: redisHost
      value: "localhost:6379"
```

---

## 5. End-to-End Testing (K8s)

```bash
# e2e/run_e2e.sh
#!/bin/bash
# Deploy test namespace with Dapr, run E2E suite

kubectl create ns dapr-e2e
kubectl apply -f e2e/components/ -n dapr-e2e
kubectl apply -f e2e/deployments/ -n dapr-e2e

# Wait for pods ready
kubectl wait --for=condition=ready pod -l app=order-service -n dapr-e2e --timeout=120s

# Run E2E tests against live cluster
pytest e2e/tests/ -v --base-url="http://$(kubectl get svc order-service -n dapr-e2e -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"

kubectl delete ns dapr-e2e
```

```python
# e2e/tests/test_order_e2e.py
import httpx
import pytest

def test_full_order_lifecycle(base_url):
    """E2E: create → get → cancel order through live Dapr stack."""
    # Create
    r = httpx.post(f"{base_url}/orders",
                   json={"customer_id": "e2e-1", "items": [], "total": 25.0})
    assert r.status_code == 200
    order_id = r.json()["orderId"]

    # Get
    r = httpx.get(f"{base_url}/orders/{order_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "pending_payment"

    # Cancel
    r = httpx.delete(f"{base_url}/orders/{order_id}")
    assert r.status_code == 200
```

---

## 6. Workflow Testing

```python
# Dapr workflow test harness (dapr-ext-workflow)
from dapr.ext.workflow.testing import WorkflowTestHarness

def test_saga_happy_path():
    with WorkflowTestHarness() as harness:
        harness.register_workflow(checkout_saga_workflow)
        harness.register_activity(validate_order, return_value={"id": "ord-1", "total": 100.0})
        harness.register_activity(reserve_inventory, return_value={"reservation_id": "res-1"})
        harness.register_activity(charge_payment, return_value={"payment_id": "pay-1"})
        harness.register_activity(create_shipment, return_value={"shipment_id": "ship-1"})
        harness.register_activity(send_notification, return_value=True)

        result = harness.run_workflow(checkout_saga_workflow, input={
            "customer_id": "c1", "items": [], "total": 100.0
        })

    assert result["status"] == "success"
    assert result["shipment_id"] == "ship-1"

def test_saga_payment_failure_compensates():
    with WorkflowTestHarness() as harness:
        harness.register_workflow(checkout_saga_workflow)
        harness.register_activity(validate_order, return_value={"id": "ord-1", "total": 100.0})
        harness.register_activity(reserve_inventory, return_value={"reservation_id": "res-1"})
        harness.register_activity(charge_payment, raise_exception=Exception("declined"))
        harness.register_activity(release_inventory_reservation, return_value=True)
        harness.register_activity(send_notification, return_value=True)

        result = harness.run_workflow(checkout_saga_workflow, input={
            "customer_id": "c1", "items": [], "total": 100.0
        })

    assert result["status"] == "failed"
    harness.assert_activity_called(release_inventory_reservation)
    harness.assert_activity_not_called(cancel_shipment)  # Never reached
```

---

## Testing Standards for Large Projects

### Coverage Requirements

| Component | Minimum Coverage | Tool |
|-----------|-----------------|------|
| Service handlers | 80% | pytest-cov / dotnet-coverage |
| Actor methods | 90% | All state transitions |
| Workflow activities | 85% | All error paths |
| Workflow orchestrator | Determinism verified | WorkflowTestHarness |
| Integration | Critical paths | Test containers |

### Test Naming Convention

```
test_<unit>_<scenario>_<expected>

Examples:
test_create_order_when_total_negative_raises_error
test_cancel_order_when_already_shipped_returns_false
test_saga_when_payment_fails_compensates_inventory
```

### Test Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Real Dapr sidecar in unit tests | Slow, flaky, requires infra | Mock `DaprClient` |
| No workflow determinism tests | Replay bugs slip to production | Use `WorkflowTestHarness` |
| Ignoring actor state transitions | Invalid states in production | Test all state machine paths |
| Testing only happy path | Compensation bugs discovered in prod | Test every failure scenario |
| No timeout test for reminders | Reminder logic untested | Use mock timer advancement |
