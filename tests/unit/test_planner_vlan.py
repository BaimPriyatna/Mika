from __future__ import annotations

import pytest

from mika.ai.schemas.configuration_intents import CreateVlanIntent
from mika.ai.schemas.enums import SafetyLevel
from mika.planner.errors import InterfaceNotFoundError, VlanAlreadyExistsError
from mika.planner.plan import OperationType, PlanStatus
from mika.planner.vlan import plan_create_vlan
from mika.router.discovery import discover
from mika.router.mock import MockRouterClient
from tests.fixtures.routers import hex_profile


def _vlan_intent(**overrides) -> CreateVlanIntent:
    fields = {
        "confidence": 0.9,
        "requires_confirmation": True,
        "parent_interface": "ether2",
        "vlan_id": 100,
    }
    fields.update(overrides)
    return CreateVlanIntent(**fields)


async def _ctx():
    return await discover(MockRouterClient(hex_profile()))


async def test_happy_path_auto_name():
    ctx = await _ctx()
    intent = _vlan_intent()

    plan = plan_create_vlan(intent, ctx)

    assert plan.status == PlanStatus.PLANNED
    assert plan.safety_level == SafetyLevel.LOW_RISK
    assert plan.affected_interfaces == ("ether2",)
    step = plan.steps[0]
    assert step.operation == OperationType.CREATE
    assert step.resource == "/interface/vlan"
    assert step.data["name"] == "vlan100"
    assert step.data["vlan-id"] == "100"
    assert step.data["interface"] == "ether2"


async def test_happy_path_explicit_name():
    ctx = await _ctx()
    intent = _vlan_intent(name="guest-vlan")
    plan = plan_create_vlan(intent, ctx)
    assert plan.steps[0].data["name"] == "guest-vlan"


async def test_unknown_parent_interface_raises():
    ctx = await _ctx()
    intent = _vlan_intent(parent_interface="ether99")
    with pytest.raises(InterfaceNotFoundError):
        plan_create_vlan(intent, ctx)


async def test_explicit_name_collision_raises():
    ctx = await _ctx()
    # ether1 already exists as an interface name.
    intent = _vlan_intent(name="ether1")
    with pytest.raises(VlanAlreadyExistsError):
        plan_create_vlan(intent, ctx)


async def test_duplicate_vlan_id_on_same_parent_raises():
    ctx = await _ctx()
    from mika.router.discovery import InterfaceInfo

    existing = InterfaceInfo(
        id="*99",
        name="vlan100",
        type="vlan",
        vlan_id=100,
        vlan_parent="ether2",
    )
    ctx_with_existing = ctx.model_copy(update={"interfaces": [*ctx.interfaces, existing]})
    with pytest.raises(VlanAlreadyExistsError):
        plan_create_vlan(_vlan_intent(name="another-name"), ctx_with_existing)


async def test_same_vlan_id_different_parent_is_allowed():
    ctx = await _ctx()
    from mika.router.discovery import InterfaceInfo

    existing = InterfaceInfo(
        id="*99",
        name="vlan100-on-ether3",
        type="vlan",
        vlan_id=100,
        vlan_parent="ether3",
    )
    ctx_with_existing = ctx.model_copy(update={"interfaces": [*ctx.interfaces, existing]})
    # Same vlan_id (100) but different parent (ether2) -- should succeed.
    plan = plan_create_vlan(_vlan_intent(parent_interface="ether2"), ctx_with_existing)
    assert plan.steps[0].data["vlan-id"] == "100"
