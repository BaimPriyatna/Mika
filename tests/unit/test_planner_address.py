from __future__ import annotations

import pytest

from mika.ai.schemas.configuration_intents import CreateAddressIntent
from mika.ai.schemas.enums import SafetyLevel
from mika.planner.address import plan_create_address
from mika.planner.errors import (
    AddressAlreadyExistsError,
    InterfaceNotFoundError,
    InterfaceUnavailableError,
    SubnetConflictError,
)
from mika.planner.plan import OperationType, PlanStatus
from mika.router.discovery import discover
from mika.router.mock import MockRouterClient
from tests.fixtures.routers import hex_profile, rb951_profile


def _address_intent(**overrides) -> CreateAddressIntent:
    fields = {
        "confidence": 0.9,
        "requires_confirmation": True,
        "interface": "ether2",
        "address": "172.16.5.1/24",
    }
    fields.update(overrides)
    return CreateAddressIntent(**fields)


async def _hex_context():
    return await discover(MockRouterClient(hex_profile()))


async def _rb951_context():
    return await discover(MockRouterClient(rb951_profile()))


async def test_plan_create_address_happy_path():
    ctx = await _hex_context()
    intent = _address_intent()

    plan = plan_create_address(intent, ctx)

    assert plan.plan_id.startswith("plan_")
    assert plan.status == PlanStatus.PLANNED
    assert plan.safety_level == SafetyLevel.LOW_RISK
    assert plan.affected_interfaces == ("ether2",)
    assert plan.affected_networks == ("172.16.5.0/24",)
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.operation == OperationType.CREATE
    assert step.resource == "/ip/address"
    assert step.data["address"] == "172.16.5.1/24"
    assert step.data["interface"] == "ether2"
    assert step.data["comment"] == "created by mika: create_address"


async def test_plan_create_address_uses_explicit_comment():
    ctx = await _hex_context()
    intent = _address_intent(comment="lab uplink")
    plan = plan_create_address(intent, ctx)
    assert plan.steps[0].data["comment"] == "lab uplink"


async def test_unknown_interface_raises():
    ctx = await _hex_context()
    intent = _address_intent(interface="ether99")
    with pytest.raises(InterfaceNotFoundError):
        plan_create_address(intent, ctx)


async def test_disabled_interface_raises():
    ctx = await _hex_context()
    # ether3 is disabled (running=false) in hex_profile fixture per hotspot tests
    intent = _address_intent(interface="ether5")
    with pytest.raises(InterfaceUnavailableError):
        plan_create_address(intent, ctx)


async def test_duplicate_exact_address_raises():
    ctx = await _hex_context()
    intent = _address_intent(interface="ether2", address="203.0.113.42/24")
    with pytest.raises(AddressAlreadyExistsError):
        plan_create_address(intent, ctx)


async def test_overlapping_subnet_raises():
    ctx = await _hex_context()
    # 203.0.113.0/24 already assigned to ether1; different host IP, same subnet
    intent = _address_intent(interface="ether2", address="203.0.113.100/24")
    with pytest.raises(SubnetConflictError):
        plan_create_address(intent, ctx)
