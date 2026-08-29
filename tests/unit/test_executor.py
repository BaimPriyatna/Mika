from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.enums import IntentName
from mika.audit.models import ExecutionResult
from mika.executor import (
    ExecutionDenied,
    ExecutionError,
    Executor,
    execute_plan,
)
from mika.executor.confirmation import ConfirmationState, ConfirmationStatus
from mika.planner.plan import OperationType, Plan, PlanStatus, PlanStep


@pytest.fixture
def sample_intent() -> CreateHotspotIntent:
    return CreateHotspotIntent(
        intent=IntentName.CREATE_HOTSPOT,
        confidence=0.95,
        requires_confirmation=True,
        interface="ether3",
        network="192.168.20.0/24",
    )


@pytest.fixture
def validated_plan(sample_intent: CreateHotspotIntent) -> Plan:
    return Plan(
        plan_id="plan_exec_test",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=sample_intent.safety_level,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fingerprint_123",
        affected_interfaces=("ether3",),
        affected_networks=("192.168.20.0/24",),
        steps=(
            PlanStep(
                step_id="address",
                description="Add IP address 192.168.20.1/24 on ether3",
                operation=OperationType.CREATE,
                resource="/ip/address",
                data={"address": "192.168.20.1/24", "interface": "ether3"},
            ),
            PlanStep(
                step_id="pool",
                description="Create IP pool hotspot-pool",
                operation=OperationType.CREATE,
                resource="/ip/pool",
                data={"name": "hotspot-pool", "ranges": "192.168.20.10-192.168.20.254"},
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def unvalidated_plan(sample_intent: CreateHotspotIntent) -> Plan:
    return Plan(
        plan_id="plan_unvalidated",
        intent=sample_intent,
        status=PlanStatus.PLANNED,
        safety_level=sample_intent.safety_level,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fingerprint_123",
        affected_interfaces=("ether3",),
        affected_networks=("192.168.20.0/24",),
        steps=(
            PlanStep(
                step_id="test",
                description="Test step",
                operation=OperationType.CREATE,
                resource="/test",
                data={},
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def confirmed_state(validated_plan: Plan) -> ConfirmationState:
    return ConfirmationState.confirmed(
        plan_id=validated_plan.plan_id,
        confirmed_by="test_user",
    )


@pytest.fixture
def pending_confirmation(validated_plan: Plan) -> ConfirmationState:
    return ConfirmationState.pending(plan_id=validated_plan.plan_id)


@pytest.fixture
def cancelled_confirmation(validated_plan: Plan) -> ConfirmationState:
    return ConfirmationState.cancelled(
        plan_id=validated_plan.plan_id,
        reason="User declined",
    )


@pytest.fixture
def mock_router_client() -> AsyncMock:
    from mika.router.client import RouterClient

    client = AsyncMock(spec=RouterClient)
    client.create_resource = AsyncMock()
    client.update_resource = AsyncMock()
    client.delete_resource = AsyncMock()
    return client


@pytest.fixture(autouse=True)
def _stub_fingerprint_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise authorization/execution mechanics, not the
    router-state-staleness check, so make it always match the plan's own
    fingerprint. The real staleness-detection behavior (re-discover and
    compare) is covered separately in
    tests/integration/test_full_pipeline_real_client.py against the real
    MockRouterClient, where a genuine mismatch can be constructed."""

    async def _fake_compute(self, plan):
        return plan.router_state_fingerprint

    monkeypatch.setattr(Executor, "_compute_state_fingerprint", _fake_compute)


@pytest.mark.asyncio
async def test_executor_rejects_unvalidated_plan(
    unvalidated_plan: Plan,
    confirmed_state: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    executor = Executor(mock_router_client)

    with pytest.raises(ExecutionDenied) as exc_info:
        await executor.execute(unvalidated_plan, confirmed_state)

    assert "not validated" in str(exc_info.value).lower()
    assert "PLANNED" in str(exc_info.value)
    
    mock_router_client.create_resource.assert_not_called()
    mock_router_client.update_resource.assert_not_called()
    mock_router_client.delete_resource.assert_not_called()


@pytest.mark.asyncio
async def test_executor_rejects_unconfirmed_plan(
    validated_plan: Plan,
    pending_confirmation: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    executor = Executor(mock_router_client)

    with pytest.raises(ExecutionDenied) as exc_info:
        await executor.execute(validated_plan, pending_confirmation)

    assert "confirmation required" in str(exc_info.value).lower()
    
    mock_router_client.create_resource.assert_not_called()


@pytest.mark.asyncio
async def test_executor_rejects_cancelled_confirmation(
    validated_plan: Plan,
    cancelled_confirmation: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    executor = Executor(mock_router_client)

    with pytest.raises(ExecutionDenied) as exc_info:
        await executor.execute(validated_plan, cancelled_confirmation)

    assert "confirmation required" in str(exc_info.value).lower()
    
    mock_router_client.create_resource.assert_not_called()


@pytest.mark.asyncio
async def test_executor_applies_validated_confirmed_plan(
    validated_plan: Plan,
    confirmed_state: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    executor = Executor(mock_router_client)

    result = await executor.execute(validated_plan, confirmed_state)

    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.commands_applied == 2
    assert "Create Hotspot" in result.summary or "hotspot" in result.summary.lower()
    assert result.error is None

    assert mock_router_client.create_resource.call_count == 2
    
    call1 = mock_router_client.create_resource.call_args_list[0]
    assert call1[0][0] == "/ip/address"
    assert call1[0][1]["address"] == "192.168.20.1/24"
    assert call1[0][1]["interface"] == "ether3"
    
    call2 = mock_router_client.create_resource.call_args_list[1]
    assert call2[0][0] == "/ip/pool"
    assert call2[0][1]["name"] == "hotspot-pool"


@pytest.mark.asyncio
async def test_execute_plan_convenience_function(
    validated_plan: Plan,
    confirmed_state: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    result = await execute_plan(validated_plan, confirmed_state, mock_router_client)

    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.commands_applied == 2


@pytest.mark.asyncio
async def test_executor_applies_update_operation(
    sample_intent: CreateHotspotIntent,
    confirmed_state: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    plan = Plan(
        plan_id="plan_update",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=sample_intent.safety_level,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp_update",
        affected_interfaces=("ether3",),
        affected_networks=(),
        steps=(
            PlanStep(
                step_id="update_profile",
                description="Update hotspot profile",
                operation=OperationType.UPDATE,
                resource="/ip/hotspot/profile",
                resource_id="*1A",
                data={"dns-name": "newlab.local"},
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    confirmation = ConfirmationState.confirmed(plan.plan_id, "test_user")

    executor = Executor(mock_router_client)
    result = await executor.execute(plan, confirmation)

    assert result.success is True
    mock_router_client.update_resource.assert_called_once_with(
        "/ip/hotspot/profile",
        "*1A",
        {"dns-name": "newlab.local"},
    )


@pytest.mark.asyncio
async def test_executor_applies_delete_operation(
    sample_intent: CreateHotspotIntent,
    confirmed_state: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    plan = Plan(
        plan_id="plan_delete",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=sample_intent.safety_level,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp_delete",
        affected_interfaces=(),
        affected_networks=(),
        steps=(
            PlanStep(
                step_id="delete_hotspot",
                description="Delete hotspot server",
                operation=OperationType.DELETE,
                resource="/ip/hotspot",
                resource_id="*2B",
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    confirmation = ConfirmationState.confirmed(plan.plan_id, "test_user")

    executor = Executor(mock_router_client)
    result = await executor.execute(plan, confirmation)

    assert result.success is True
    mock_router_client.delete_resource.assert_called_once_with("/ip/hotspot", "*2B")


@pytest.mark.asyncio
async def test_executor_handles_router_error_gracefully(
    validated_plan: Plan,
    confirmed_state: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    mock_router_client.create_resource.side_effect = [
        None,
        Exception("Router API error: interface not found"),
    ]

    executor = Executor(mock_router_client)
    result = await executor.execute(validated_plan, confirmed_state)

    assert isinstance(result, ExecutionResult)
    assert result.success is False
    assert result.commands_applied == 1
    assert result.error is not None
    assert "failed at step 2" in result.error.lower()
    assert "interface not found" in result.error.lower()


@pytest.mark.asyncio
async def test_executor_requires_resource_id_for_update(
    sample_intent: CreateHotspotIntent,
    confirmed_state: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    plan = Plan(
        plan_id="plan_bad_update",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=sample_intent.safety_level,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp_bad",
        affected_interfaces=(),
        affected_networks=(),
        steps=(
            PlanStep(
                step_id="bad_update",
                description="Update without ID",
                operation=OperationType.UPDATE,
                resource="/test",
                resource_id=None,
                data={"foo": "bar"},
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    confirmation = ConfirmationState.confirmed(plan.plan_id, "test_user")

    executor = Executor(mock_router_client)
    result = await executor.execute(plan, confirmation)

    assert result.success is False
    assert "resource_id" in result.error.lower()


@pytest.mark.asyncio
async def test_executor_requires_resource_id_for_delete(
    sample_intent: CreateHotspotIntent,
    confirmed_state: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    plan = Plan(
        plan_id="plan_bad_delete",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=sample_intent.safety_level,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp_bad",
        affected_interfaces=(),
        affected_networks=(),
        steps=(
            PlanStep(
                step_id="bad_delete",
                description="Delete without ID",
                operation=OperationType.DELETE,
                resource="/test",
                resource_id=None,
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    confirmation = ConfirmationState.confirmed(plan.plan_id, "test_user")

    executor = Executor(mock_router_client)
    result = await executor.execute(plan, confirmation)

    assert result.success is False
    assert "resource_id" in result.error.lower()


def test_executor_has_no_bypass_flag() -> None:
    from inspect import signature

    init_sig = signature(Executor.__init__)
    init_params = set(init_sig.parameters.keys()) - {"self"}
    
    assert init_params == {"router_client"}, (
        f"Executor.__init__ has unexpected parameters: {init_params}. "
        f"No bypass flags should exist."
    )

    exec_sig = signature(Executor.execute)
    exec_params = set(exec_sig.parameters.keys()) - {"self"}
    
    assert exec_params == {"plan", "confirmation_state"}, (
        f"Executor.execute has unexpected parameters: {exec_params}. "
        f"No bypass, skip_validation, or force flags should exist."
    )


def test_confirmation_state_confirmed_factory() -> None:
    state = ConfirmationState.confirmed("plan_123", "alice")

    assert state.plan_id == "plan_123"
    assert state.status == ConfirmationStatus.CONFIRMED
    assert state.is_confirmed is True
    assert state.confirmed_by == "alice"
    assert state.confirmed_at is not None
    assert state.cancellation_reason is None


def test_confirmation_state_cancelled_factory() -> None:
    state = ConfirmationState.cancelled("plan_456", "User pressed Ctrl+C")

    assert state.plan_id == "plan_456"
    assert state.status == ConfirmationStatus.CANCELLED
    assert state.is_confirmed is False
    assert state.cancellation_reason == "User pressed Ctrl+C"
    assert state.confirmed_at is None


def test_confirmation_state_pending_factory() -> None:
    state = ConfirmationState.pending("plan_789")

    assert state.plan_id == "plan_789"
    assert state.status == ConfirmationStatus.PENDING
    assert state.is_confirmed is False
    assert state.confirmed_at is None


def test_confirmation_state_is_frozen() -> None:
    state = ConfirmationState.confirmed("plan_test", "bob")

    with pytest.raises(Exception):
        state.status = ConfirmationStatus.CANCELLED


@pytest.mark.asyncio
async def test_executor_handles_empty_plan(
    sample_intent: CreateHotspotIntent,
    confirmed_state: ConfirmationState,
    mock_router_client: AsyncMock,
) -> None:
    empty_plan = Plan(
        plan_id="plan_empty",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=sample_intent.safety_level,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp_empty",
        affected_interfaces=(),
        affected_networks=(),
        steps=(),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    confirmation = ConfirmationState.confirmed(empty_plan.plan_id, "test_user")

    executor = Executor(mock_router_client)
    result = await executor.execute(empty_plan, confirmation)

    assert result.success is True
    assert result.commands_applied == 0
    assert "0 steps" in result.summary or result.summary == ""
    
    mock_router_client.create_resource.assert_not_called()
    mock_router_client.update_resource.assert_not_called()
    mock_router_client.delete_resource.assert_not_called()
