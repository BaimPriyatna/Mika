from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.enums import IntentName, SafetyLevel
from mika.executor import (
    Executor,
    prompt_for_confirmation,
)
from mika.planner.diff import generate_diff
from mika.planner.plan import OperationType, Plan, PlanStatus, PlanStep
from mika.router.client import RouterClient


@pytest.fixture(autouse=True)
def _stub_fingerprint_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise the plan/confirm/execute workflow mechanics,
    not the router-state-staleness check, so make it always match the
    plan's own fingerprint. The real staleness-detection behavior
    (re-discover and compare) is covered separately in
    tests/integration/test_full_pipeline_real_client.py against the real
    MockRouterClient, where a genuine mismatch can be constructed."""

    async def _fake_compute(self, plan):
        return plan.router_state_fingerprint

    monkeypatch.setattr(Executor, "_compute_state_fingerprint", _fake_compute)


def _make_ask_mock(value):
    m = Mock()
    m.ask.return_value = value
    return m


@pytest.fixture
def sample_plan() -> Plan:
    intent = CreateHotspotIntent(
        intent=IntentName.CREATE_HOTSPOT,
        confidence=0.95,
        requires_confirmation=True,
        interface="ether3",
        network="192.168.20.0/24",
    )

    return Plan(
        plan_id="integration_test_plan",
        intent=intent,
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.MEDIUM_RISK,
        router_identity="IntegrationTestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp_integration",
        affected_interfaces=("ether3",),
        affected_networks=("192.168.20.0/24",),
        steps=(
            PlanStep(
                step_id="add_address",
                description="Add IP address 192.168.20.1/24 on ether3",
                operation=OperationType.CREATE,
                resource="/ip/address",
                data={"address": "192.168.20.1/24", "interface": "ether3"},
            ),
            PlanStep(
                step_id="create_pool",
                description="Create IP pool hotspot-pool",
                operation=OperationType.CREATE,
                resource="/ip/pool",
                data={"name": "hotspot-pool", "ranges": "192.168.20.10-192.168.20.254"},
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
@patch("sys.stdin.isatty", return_value=True)
@patch("mika.executor.confirmation.questionary.select")
async def test_full_workflow_plan_confirm_execute(
    mock_select: Mock,
    mock_isatty: Mock,
    sample_plan: Plan,
) -> None:
    from rich.console import Console

    assert sample_plan.status == PlanStatus.VALIDATED
    assert len(sample_plan.steps) == 2

    mock_select.return_value = _make_ask_mock("yes")
    console = Console(file=StringIO())
    diff = generate_diff(sample_plan, show_data=False)
    
    assert "IntegrationTestRouter" in str(diff)
    assert "ether3" in str(diff)

    confirmation = prompt_for_confirmation(sample_plan, console=console)
    
    assert confirmation.is_confirmed is True
    assert confirmation.status.value == "confirmed"
    assert confirmation.plan_id == sample_plan.plan_id

    mock_router = AsyncMock(spec=RouterClient)
    mock_router.create_resource = AsyncMock()
    
    executor = Executor(mock_router)
    result = await executor.execute(sample_plan, confirmation)

    assert result.success is True
    assert result.commands_applied == 2
    assert result.error is None

    assert mock_router.create_resource.call_count == 2


@pytest.mark.asyncio
@patch("sys.stdin.isatty", return_value=True)
@patch("mika.executor.confirmation.questionary.select")
async def test_full_workflow_user_declines_confirmation(
    mock_select: Mock,
    mock_isatty: Mock,
    sample_plan: Plan,
) -> None:
    from rich.console import Console

    from mika.executor import ExecutionDenied

    mock_select.return_value = _make_ask_mock("no")
    console = Console(file=StringIO())
    diff = generate_diff(sample_plan, show_data=False)
    assert diff is not None

    confirmation = prompt_for_confirmation(sample_plan, console=console)
    
    assert confirmation.is_confirmed is False
    assert confirmation.status.value == "cancelled"

    mock_router = AsyncMock(spec=RouterClient)
    executor = Executor(mock_router)

    with pytest.raises(ExecutionDenied) as exc_info:
        await executor.execute(sample_plan, confirmation)

    assert "confirmation required" in str(exc_info.value).lower()
    
    mock_router.create_resource.assert_not_called()


@pytest.mark.asyncio
async def test_workflow_cannot_skip_validation_gate(sample_plan: Plan) -> None:
    from mika.executor import (
        ConfirmationState,
        ExecutionDenied,
        Executor,
    )

    unvalidated_plan = Plan(
        plan_id=sample_plan.plan_id,
        intent=sample_plan.intent,
        status=PlanStatus.PLANNED,
        safety_level=sample_plan.safety_level,
        router_identity=sample_plan.router_identity,
        routeros_version=sample_plan.routeros_version,
        router_state_fingerprint=sample_plan.router_state_fingerprint,
        affected_interfaces=sample_plan.affected_interfaces,
        affected_networks=sample_plan.affected_networks,
        steps=sample_plan.steps,
        warnings=sample_plan.warnings,
        created_at=sample_plan.created_at,
    )

    confirmation = ConfirmationState.confirmed(unvalidated_plan.plan_id, "test_user")

    mock_router = AsyncMock(spec=RouterClient)
    executor = Executor(mock_router)

    with pytest.raises(ExecutionDenied) as exc_info:
        await executor.execute(unvalidated_plan, confirmation)

    assert "not validated" in str(exc_info.value).lower()
    
    mock_router.create_resource.assert_not_called()


@pytest.mark.asyncio
@patch("sys.stdin.isatty", return_value=True)
@patch("rich.prompt.Prompt.ask", return_value="CONFIRM DELETE")
async def test_workflow_destructive_operation_requires_typed_confirmation(
    mock_prompt: Mock,
    mock_isatty: Mock,
) -> None:
    from rich.console import Console

    intent = CreateHotspotIntent(
        intent=IntentName.CREATE_HOTSPOT,
        confidence=0.95,
        requires_confirmation=True,
        interface="ether3",
        network="192.168.20.0/24",
    )

    destructive_plan = Plan(
        plan_id="destructive_plan",
        intent=intent,
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.DESTRUCTIVE,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp_dest",
        affected_interfaces=("ether3",),
        affected_networks=(),
        steps=(
            PlanStep(
                step_id="delete",
                description="Delete hotspot server",
                operation=OperationType.DELETE,
                resource="/ip/hotspot",
                resource_id="*1",
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    console = Console(file=StringIO())
    confirmation = prompt_for_confirmation(destructive_plan, console=console)

    assert confirmation.is_confirmed is True
    mock_prompt.assert_called_once()

    mock_router = AsyncMock(spec=RouterClient)
    mock_router.delete_resource = AsyncMock()
    
    executor = Executor(mock_router)
    result = await executor.execute(destructive_plan, confirmation)

    assert result.success is True
    assert result.commands_applied == 1
    mock_router.delete_resource.assert_called_once_with("/ip/hotspot", "*1")
