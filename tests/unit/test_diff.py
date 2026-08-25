from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName, SafetyLevel
from mika.planner.diff import (
    generate_compact_summary,
    generate_diff,
)
from mika.planner.plan import OperationType, Plan, PlanStatus, PlanStep
from mika.validator.result import (
    IssueSeverity,
    ValidationIssue,
    ValidationLayer,
    ValidationResult,
)


@pytest.fixture
def sample_intent() -> CreateHotspotIntent:
    return CreateHotspotIntent(
        intent=IntentName.CREATE_HOTSPOT,
        confidence=0.95,
        requires_confirmation=True,
        interface="ether3",
        network="192.168.20.0/24",
        dns_name="lab.local",
    )


@pytest.fixture
def sample_plan(sample_intent: CreateHotspotIntent) -> Plan:
    return Plan(
        plan_id="plan_test123",
        intent=sample_intent,
        status=PlanStatus.PLANNED,
        safety_level=SafetyLevel.MEDIUM_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="abc123def456",
        affected_interfaces=("ether3",),
        affected_networks=("192.168.20.0/24",),
        steps=(
            PlanStep(
                step_id="address",
                description="Create IP address 192.168.20.1/24 on ether3",
                operation=OperationType.CREATE,
                resource="/ip/address",
                data={"address": "192.168.20.1/24", "interface": "ether3"},
            ),
            PlanStep(
                step_id="pool",
                description="Create IP pool hotspot-pool (192.168.20.10-192.168.20.254)",
                operation=OperationType.CREATE,
                resource="/ip/pool",
                data={
                    "name": "hotspot-pool",
                    "ranges": "192.168.20.10-192.168.20.254",
                },
            ),
            PlanStep(
                step_id="dhcp_server",
                description="Create DHCP server dhcp-ether3",
                operation=OperationType.CREATE,
                resource="/ip/dhcp-server",
                data={
                    "name": "dhcp-ether3",
                    "interface": "ether3",
                    "address-pool": "hotspot-pool",
                    "lease-time": "1h",
                },
            ),
            PlanStep(
                step_id="hotspot_profile",
                description="Create hotspot profile lab-profile",
                operation=OperationType.CREATE,
                resource="/ip/hotspot/profile",
                data={"name": "lab-profile", "dns-name": "lab.local"},
            ),
            PlanStep(
                step_id="hotspot_server",
                description="Create hotspot server lab-hotspot on ether3",
                operation=OperationType.CREATE,
                resource="/ip/hotspot",
                data={
                    "name": "lab-hotspot",
                    "interface": "ether3",
                    "profile": "lab-profile",
                    "address-pool": "hotspot-pool",
                },
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def destructive_plan(sample_intent: CreateHotspotIntent) -> Plan:
    return Plan(
        plan_id="plan_delete123",
        intent=sample_intent,
        status=PlanStatus.PLANNED,
        safety_level=SafetyLevel.DESTRUCTIVE,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="xyz789",
        affected_interfaces=("ether3",),
        affected_networks=(),
        steps=(
            PlanStep(
                step_id="delete_hotspot",
                description="Delete hotspot server lab-hotspot",
                operation=OperationType.DELETE,
                resource="/ip/hotspot",
                resource_id="*1A",
            ),
            PlanStep(
                step_id="delete_profile",
                description="Delete hotspot profile lab-profile",
                operation=OperationType.DELETE,
                resource="/ip/hotspot/profile",
                resource_id="*2B",
            ),
        ),
        warnings=("This will remove all active hotspot sessions.",),
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def validation_result_with_warnings(sample_plan: Plan) -> ValidationResult:
    return ValidationResult(
        plan_id=sample_plan.plan_id,
        validated=True,
        issues=(
            ValidationIssue(
                layer=ValidationLayer.OVERLAP,
                severity=IssueSeverity.WARNING,
                message="Network 192.168.20.0/24 overlaps with existing route",
                step_id="address",
            ),
            ValidationIssue(
                layer=ValidationLayer.SAFETY,
                severity=IssueSeverity.WARNING,
                message="Interface ether3 has active connections",
                step_id=None,
            ),
        ),
        plan=sample_plan.model_copy(update={"status": PlanStatus.VALIDATED}),
    )


@pytest.fixture
def validation_result_with_failures(sample_plan: Plan) -> ValidationResult:
    return ValidationResult(
        plan_id=sample_plan.plan_id,
        validated=False,
        issues=(
            ValidationIssue(
                layer=ValidationLayer.RESOURCE_EXISTENCE,
                severity=IssueSeverity.FAIL,
                message="Interface ether3 does not exist",
                step_id="address",
            ),
            ValidationIssue(
                layer=ValidationLayer.CONFLICT,
                severity=IssueSeverity.FAIL,
                message="DHCP server already exists on ether3",
                step_id="dhcp_server",
            ),
        ),
        plan=sample_plan.model_copy(update={"status": PlanStatus.VALIDATION_FAILED}),
    )


def test_generate_diff_basic(sample_plan: Plan) -> None:
    diff = generate_diff(sample_plan)

    assert "plan_test123" in diff
    assert "TestRouter" in diff
    assert "7.14.2" in diff
    assert "CREATE_HOTSPOT" in diff.upper() or "Create Hotspot" in diff
    assert "MEDIUM" in diff.upper() or "MEDIUM_RISK" in diff

    assert "192.168.20.1/24" in diff
    assert "hotspot-pool" in diff
    assert "dhcp-ether3" in diff
    assert "lab-profile" in diff
    assert "lab-hotspot" in diff

    assert "ether3" in diff
    assert "192.168.20.0/24" in diff


def test_generate_diff_with_validation_warnings(
    sample_plan: Plan,
    validation_result_with_warnings: ValidationResult,
) -> None:
    diff = generate_diff(sample_plan, validation_result_with_warnings)

    assert "Warning" in diff or "warning" in diff.lower()
    assert "overlaps with existing route" in diff
    assert "active connections" in diff


def test_generate_diff_with_validation_failures(
    sample_plan: Plan,
    validation_result_with_failures: ValidationResult,
) -> None:
    diff = generate_diff(sample_plan, validation_result_with_failures)

    assert "Failure" in diff or "Fail" in diff or "fail" in diff.lower()
    assert "does not exist" in diff
    assert "already exists" in diff


def test_generate_diff_with_show_data(sample_plan: Plan) -> None:
    diff = generate_diff(sample_plan, show_data=True)

    assert "/ip/address" in diff
    assert "/ip/pool" in diff
    assert "/ip/dhcp-server" in diff
    assert "/ip/hotspot/profile" in diff
    assert "/ip/hotspot" in diff

    assert "interface" in diff
    assert "address-pool" in diff
    assert "lease-time" in diff


def test_generate_diff_destructive_plan(destructive_plan: Plan) -> None:
    diff = generate_diff(destructive_plan)

    assert "DESTRUCTIVE" in diff.upper()

    assert "Delete" in diff or "delete" in diff
    assert "lab-hotspot" in diff
    assert "lab-profile" in diff

    assert "remove all active hotspot sessions" in diff

    assert "CRITICAL" in diff.upper() or "DELETED" in diff.upper()


def test_generate_diff_empty_plan(sample_intent: CreateHotspotIntent) -> None:
    empty_plan = Plan(
        plan_id="plan_empty",
        intent=sample_intent,
        status=PlanStatus.PLANNED,
        safety_level=SafetyLevel.READ_ONLY,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="empty123",
        affected_interfaces=(),
        affected_networks=(),
        steps=(),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    diff = generate_diff(empty_plan)

    assert "No configuration changes" in diff or "no changes" in diff.lower()
    assert "TestRouter" in diff


def test_generate_diff_with_planner_warnings(sample_plan: Plan) -> None:
    plan_with_warnings = sample_plan.model_copy(
        update={
            "warnings": (
                "Interface ether3 may not support hotspot hardware acceleration",
                "Default DNS servers will be used if client does not specify",
            )
        }
    )

    diff = generate_diff(plan_with_warnings)

    assert "hardware acceleration" in diff
    assert "Default DNS servers" in diff


def test_generate_diff_update_operation(sample_intent: CreateHotspotIntent) -> None:
    update_plan = Plan(
        plan_id="plan_update",
        intent=sample_intent,
        status=PlanStatus.PLANNED,
        safety_level=SafetyLevel.MEDIUM_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="update123",
        affected_interfaces=("ether3",),
        affected_networks=(),
        steps=(
            PlanStep(
                step_id="update_profile",
                description="Update hotspot profile lab-profile",
                operation=OperationType.UPDATE,
                resource="/ip/hotspot/profile",
                resource_id="*1A",
                data={"dns-name": "newlab.local"},
            ),
        ),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    diff = generate_diff(update_plan)

    assert "Update" in diff or "Modify" in diff or "modify" in diff
    assert "lab-profile" in diff


def test_generate_compact_summary(sample_plan: Plan) -> None:
    summary = generate_compact_summary(sample_plan)

    assert "plan_test123" in summary
    assert "PLANNED" in summary
    assert "5 steps" in summary
    assert "MEDIUM" in summary.upper()

    assert "Hotspot" in summary or "ether3" in summary


def test_generate_compact_summary_destructive(destructive_plan: Plan) -> None:
    summary = generate_compact_summary(destructive_plan)

    assert "plan_delete123" in summary
    assert "2 steps" in summary
    assert "DESTRUCTIVE" in summary.upper()


def test_generate_compact_summary_empty_plan(
    sample_intent: CreateHotspotIntent,
) -> None:
    empty_plan = Plan(
        plan_id="plan_empty",
        intent=sample_intent,
        status=PlanStatus.PLANNED,
        safety_level=SafetyLevel.READ_ONLY,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="empty123",
        affected_interfaces=(),
        affected_networks=(),
        steps=(),
        warnings=(),
        created_at=datetime.now(timezone.utc),
    )

    summary = generate_compact_summary(empty_plan)

    assert "plan_empty" in summary
    assert "0 step" in summary


def test_diff_contains_operation_symbols(
    sample_plan: Plan,
    destructive_plan: Plan,
) -> None:
    create_diff = generate_diff(sample_plan)
    delete_diff = generate_diff(destructive_plan)

    assert "+" in create_diff or "Create" in create_diff

    assert "-" in delete_diff or "Delete" in delete_diff


def test_diff_safety_levels() -> None:
    base_intent = CreateHotspotIntent(
        intent=IntentName.CREATE_HOTSPOT,
        confidence=0.95,
        requires_confirmation=True,
        interface="ether3",
        network="192.168.20.0/24",
    )

    for safety_level in [
        SafetyLevel.READ_ONLY,
        SafetyLevel.LOW_RISK,
        SafetyLevel.MEDIUM_RISK,
        SafetyLevel.HIGH_RISK,
        SafetyLevel.DESTRUCTIVE,
    ]:
        plan = Plan(
            plan_id=f"plan_{safety_level.value}",
            intent=base_intent,
            status=PlanStatus.PLANNED,
            safety_level=safety_level,
            router_identity="TestRouter",
            routeros_version="7.14.2",
            router_state_fingerprint="test123",
            affected_interfaces=("ether3",),
            affected_networks=(),
            steps=(),
            warnings=(),
            created_at=datetime.now(timezone.utc),
        )

        diff = generate_diff(plan)
        assert safety_level.value.replace("_", " ").upper() in diff.upper() or safety_level.value.upper() in diff.upper()


def test_diff_with_no_affected_resources(sample_intent: CreateHotspotIntent) -> None:
    plan = Plan(
        plan_id="plan_no_resources",
        intent=sample_intent,
        status=PlanStatus.PLANNED,
        safety_level=SafetyLevel.READ_ONLY,
        router_identity="TestRouter",
        routeros_version="7.14.2",
        router_state_fingerprint="test123",
        affected_interfaces=(),
        affected_networks=(),
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

    diff = generate_diff(plan)

    assert "none" in diff.lower() or "Interfaces:" in diff


def test_diff_validation_result_no_issues(sample_plan: Plan) -> None:
    clean_validation = ValidationResult(
        plan_id=sample_plan.plan_id,
        validated=True,
        issues=(),
        plan=sample_plan.model_copy(update={"status": PlanStatus.VALIDATED}),
    )

    diff = generate_diff(sample_plan, clean_validation)

    assert "passed" in diff.lower() or "✓" in diff
