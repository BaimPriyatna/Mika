from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from unittest.mock import Mock, patch

import pytest

from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.enums import IntentName, SafetyLevel
from mika.executor.confirmation import (
    ConfirmationState,
    ConfirmationStatus,
    NonInteractiveContextError,
    check_confirmation_expiration,
    prompt_for_confirmation,
)
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
def medium_risk_plan(sample_intent: CreateHotspotIntent) -> Plan:
    return Plan(
        plan_id="plan_medium",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.MEDIUM_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp_123",
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
def destructive_plan(sample_intent: CreateHotspotIntent) -> Plan:
    return Plan(
        plan_id="plan_destructive",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.DESTRUCTIVE,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp_456",
        affected_interfaces=("ether3",),
        affected_networks=(),
        steps=(
            PlanStep(
                step_id="delete",
                description="Delete hotspot",
                operation=OperationType.DELETE,
                resource="/ip/hotspot",
                resource_id="*1",
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
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


def test_confirmation_state_modified_factory() -> None:
    state = ConfirmationState.modified("plan_mod", "use ether2 and 10M rate limit")

    assert state.plan_id == "plan_mod"
    assert state.status == ConfirmationStatus.CANCELLED
    assert state.is_confirmed is False
    assert state.feedback == "use ether2 and 10M rate limit"
    assert "User requested modification" in state.cancellation_reason


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


def test_confirmation_state_is_confirmed_property() -> None:
    confirmed = ConfirmationState.confirmed("p1", "user")
    cancelled = ConfirmationState.cancelled("p2")
    pending = ConfirmationState.pending("p3")

    assert confirmed.is_confirmed is True
    assert cancelled.is_confirmed is False
    assert pending.is_confirmed is False


@patch("sys.stdin.isatty", return_value=False)
def test_prompt_refuses_non_interactive_context(
    mock_isatty: Mock,
    medium_risk_plan: Plan,
) -> None:
    with pytest.raises(NonInteractiveContextError) as exc_info:
        prompt_for_confirmation(medium_risk_plan)

    assert "non-interactive" in str(exc_info.value).lower()
    assert "tty" in str(exc_info.value).lower()


def _make_ask_mock(value):
    m = Mock()
    m.ask.return_value = value
    return m


@patch("sys.stdin.isatty", return_value=True)
@patch("mika.executor.confirmation.questionary.select")
def test_prompt_standard_confirmation_accepted(
    mock_select: Mock,
    mock_isatty: Mock,
    medium_risk_plan: Plan,
) -> None:
    from rich.console import Console

    mock_select.return_value = _make_ask_mock("yes")
    console = Console(file=StringIO())
    result = prompt_for_confirmation(medium_risk_plan, console=console)

    assert result.status == ConfirmationStatus.CONFIRMED
    assert result.is_confirmed is True
    assert result.plan_id == medium_risk_plan.plan_id
    assert result.confirmed_by is not None
    assert result.confirmed_at is not None


@patch("sys.stdin.isatty", return_value=True)
@patch("mika.executor.confirmation.questionary.select")
def test_prompt_standard_confirmation_declined(
    mock_select: Mock,
    mock_isatty: Mock,
    medium_risk_plan: Plan,
) -> None:
    from rich.console import Console

    mock_select.return_value = _make_ask_mock("no")
    console = Console(file=StringIO())
    result = prompt_for_confirmation(medium_risk_plan, console=console)

    assert result.status == ConfirmationStatus.CANCELLED
    assert result.is_confirmed is False
    assert result.plan_id == medium_risk_plan.plan_id
    assert "declined" in result.cancellation_reason.lower()


@patch("sys.stdin.isatty", return_value=True)
@patch("mika.executor.confirmation.questionary.text")
@patch("mika.executor.confirmation.questionary.select")
def test_prompt_standard_confirmation_modify_option(
    mock_select: Mock,
    mock_text: Mock,
    mock_isatty: Mock,
    medium_risk_plan: Plan,
) -> None:
    from rich.console import Console

    mock_select.return_value = _make_ask_mock("modify")
    mock_text.return_value = _make_ask_mock("change rate limit to 10M")
    console = Console(file=StringIO())
    result = prompt_for_confirmation(medium_risk_plan, console=console)

    assert result.status == ConfirmationStatus.CANCELLED
    assert result.is_confirmed is False
    assert result.feedback == "change rate limit to 10M"


@patch("sys.stdin.isatty", return_value=True)
@patch("mika.executor.confirmation.questionary.select")
def test_prompt_standard_confirmation_none_returned(
    mock_select: Mock,
    mock_isatty: Mock,
    medium_risk_plan: Plan,
) -> None:
    from rich.console import Console

    mock_select.return_value = _make_ask_mock(None)
    console = Console(file=StringIO())
    result = prompt_for_confirmation(medium_risk_plan, console=console)

    assert result.status == ConfirmationStatus.CANCELLED
    assert result.is_confirmed is False


@patch("sys.stdin.isatty", return_value=True)
@patch("mika.executor.confirmation.questionary.select")
def test_prompt_standard_confirmation_ctrl_c(
    mock_select: Mock,
    mock_isatty: Mock,
    medium_risk_plan: Plan,
) -> None:
    from rich.console import Console

    q = Mock()
    q.ask.side_effect = KeyboardInterrupt
    mock_select.return_value = q

    console = Console(file=StringIO())
    result = prompt_for_confirmation(medium_risk_plan, console=console)

    assert result.status == ConfirmationStatus.CANCELLED
    assert result.is_confirmed is False
    assert "ctrl+c" in result.cancellation_reason.lower() or "interrupted" in result.cancellation_reason.lower()


@patch("sys.stdin.isatty", return_value=True)
@patch("rich.prompt.Prompt.ask", return_value="CONFIRM DELETE")
def test_prompt_destructive_confirmation_correct_literal(
    mock_ask: Mock,
    mock_isatty: Mock,
    destructive_plan: Plan,
) -> None:
    from rich.console import Console

    console = Console(file=StringIO())
    result = prompt_for_confirmation(destructive_plan, console=console)

    assert result.status == ConfirmationStatus.CONFIRMED
    assert result.is_confirmed is True
    assert result.plan_id == destructive_plan.plan_id


@patch("sys.stdin.isatty", return_value=True)
@patch("rich.prompt.Prompt.ask", return_value="confirm delete")
def test_prompt_destructive_confirmation_wrong_case(
    mock_ask: Mock,
    mock_isatty: Mock,
    destructive_plan: Plan,
) -> None:
    from rich.console import Console

    console = Console(file=StringIO())
    result = prompt_for_confirmation(destructive_plan, console=console)

    assert result.status == ConfirmationStatus.CANCELLED
    assert result.is_confirmed is False
    assert "did not match" in result.cancellation_reason.lower()


@patch("sys.stdin.isatty", return_value=True)
@patch("rich.prompt.Prompt.ask", return_value="yes")
def test_prompt_destructive_confirmation_wrong_text(
    mock_ask: Mock,
    mock_isatty: Mock,
    destructive_plan: Plan,
) -> None:
    from rich.console import Console

    console = Console(file=StringIO())
    result = prompt_for_confirmation(destructive_plan, console=console)

    assert result.status == ConfirmationStatus.CANCELLED
    assert result.is_confirmed is False


@patch("sys.stdin.isatty", return_value=True)
@patch("rich.prompt.Prompt.ask", side_effect=KeyboardInterrupt)
def test_prompt_destructive_confirmation_ctrl_c(
    mock_ask: Mock,
    mock_isatty: Mock,
    destructive_plan: Plan,
) -> None:
    from rich.console import Console

    console = Console(file=StringIO())
    result = prompt_for_confirmation(destructive_plan, console=console)

    assert result.status == ConfirmationStatus.CANCELLED
    assert result.is_confirmed is False


def test_check_confirmation_expiration_unchanged_state() -> None:
    plan = Plan(
        plan_id="plan_expire_test",
        intent=CreateHotspotIntent(
            intent=IntentName.CREATE_HOTSPOT,
            confidence=0.9,
            requires_confirmation=True,
            interface="ether3",
            network="192.168.20.0/24",
        ),
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.MEDIUM_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fingerprint_abc",
        affected_interfaces=(),
        affected_networks=(),
        steps=(),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    confirmation = ConfirmationState.confirmed(plan.plan_id, "alice")

    result = check_confirmation_expiration(plan, confirmation, "fingerprint_abc")

    assert result.status == ConfirmationStatus.CONFIRMED
    assert result.is_confirmed is True


def test_check_confirmation_expiration_changed_state() -> None:
    plan = Plan(
        plan_id="plan_expire_test",
        intent=CreateHotspotIntent(
            intent=IntentName.CREATE_HOTSPOT,
            confidence=0.9,
            requires_confirmation=True,
            interface="ether3",
            network="192.168.20.0/24",
        ),
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.MEDIUM_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fingerprint_abc",
        affected_interfaces=(),
        affected_networks=(),
        steps=(),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    confirmation = ConfirmationState.confirmed(plan.plan_id, "alice")

    result = check_confirmation_expiration(plan, confirmation, "fingerprint_xyz")

    assert result.status == ConfirmationStatus.EXPIRED
    assert result.is_confirmed is False
    assert "state changed" in result.cancellation_reason.lower()


def test_check_confirmation_expiration_ignores_non_confirmed() -> None:
    plan = Plan(
        plan_id="plan_test",
        intent=CreateHotspotIntent(
            intent=IntentName.CREATE_HOTSPOT,
            confidence=0.9,
            requires_confirmation=True,
            interface="ether3",
            network="192.168.20.0/24",
        ),
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.MEDIUM_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fingerprint_abc",
        affected_interfaces=(),
        affected_networks=(),
        steps=(),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    pending = ConfirmationState.pending(plan.plan_id)
    result = check_confirmation_expiration(plan, pending, "different_fingerprint")
    assert result.status == ConfirmationStatus.PENDING

    cancelled = ConfirmationState.cancelled(plan.plan_id)
    result = check_confirmation_expiration(plan, cancelled, "different_fingerprint")
    assert result.status == ConfirmationStatus.CANCELLED


@patch("sys.stdin.isatty", return_value=True)
def test_low_risk_uses_standard_confirmation(mock_isatty: Mock) -> None:
    plan = Plan(
        plan_id="plan_low",
        intent=CreateHotspotIntent(
            intent=IntentName.CREATE_HOTSPOT,
            confidence=0.9,
            requires_confirmation=True,
            interface="ether3",
            network="192.168.20.0/24",
        ),
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.LOW_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp",
        affected_interfaces=(),
        affected_networks=(),
        steps=(),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    from rich.console import Console

    with patch("mika.executor.confirmation.questionary.select") as mock_select:
        mock_select.return_value = _make_ask_mock("yes")
        console = Console(file=StringIO())
        result = prompt_for_confirmation(plan, console=console)

        mock_select.assert_called_once()
        assert result.is_confirmed is True


@patch("sys.stdin.isatty", return_value=True)
def test_high_risk_uses_standard_confirmation(mock_isatty: Mock) -> None:
    plan = Plan(
        plan_id="plan_high",
        intent=CreateHotspotIntent(
            intent=IntentName.CREATE_HOTSPOT,
            confidence=0.9,
            requires_confirmation=True,
            interface="ether3",
            network="192.168.20.0/24",
        ),
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.HIGH_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="fp",
        affected_interfaces=(),
        affected_networks=(),
        steps=(),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    from rich.console import Console

    with patch("mika.executor.confirmation.questionary.select") as mock_select:
        mock_select.return_value = _make_ask_mock("yes")
        console = Console(file=StringIO())
        result = prompt_for_confirmation(plan, console=console)

        mock_select.assert_called_once()
        assert result.is_confirmed is True


@patch("sys.stdin.isatty", return_value=True)
def test_destructive_uses_typed_confirmation(mock_isatty: Mock, destructive_plan: Plan) -> None:
    from rich.console import Console

    with patch("rich.prompt.Prompt.ask", return_value="CONFIRM DELETE") as mock_prompt:
        console = Console(file=StringIO())
        result = prompt_for_confirmation(destructive_plan, console=console)

        mock_prompt.assert_called_once()
        assert result.is_confirmed is True


def test_prompt_for_confirmation_has_no_force_flag() -> None:
    from inspect import signature

    sig = signature(prompt_for_confirmation)
    params = set(sig.parameters.keys())

    expected_params = {"plan", "validation_result", "console"}
    assert params == expected_params, (
        f"prompt_for_confirmation has unexpected parameters: {params - expected_params}. "
        f"No --yes, --force, or bypass flags should exist."
    )
