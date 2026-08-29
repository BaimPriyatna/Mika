from __future__ import annotations

import pytest

from mika.ai.schemas.configuration_intents import CreateFirewallRuleIntent
from mika.ai.schemas.enums import FirewallAction, FirewallChain, L4Protocol, SafetyLevel
from mika.planner.errors import DuplicateRuleError, InterfaceNotFoundError
from mika.planner.firewall import plan_create_firewall_rule
from mika.planner.plan import OperationType, PlanStatus
from mika.router.discovery import discover
from mika.router.mock import MockRouterClient
from tests.fixtures.routers import hex_profile


def _fw_intent(**overrides) -> CreateFirewallRuleIntent:
    fields = {
        "confidence": 0.9,
        "requires_confirmation": True,
        "chain": FirewallChain.FORWARD,
        "action": FirewallAction.DROP,
        "in_interface": "ether1",
    }
    fields.update(overrides)
    return CreateFirewallRuleIntent(**fields)


async def _ctx():
    return await discover(MockRouterClient(hex_profile()))


async def test_happy_path():
    ctx = await _ctx()
    intent = _fw_intent()

    plan = plan_create_firewall_rule(intent, ctx)

    assert plan.status == PlanStatus.PLANNED
    assert plan.safety_level == SafetyLevel.MEDIUM_RISK
    assert plan.affected_interfaces == ("ether1",)
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.operation == OperationType.CREATE
    assert step.resource == "/ip/firewall/filter"
    assert step.data["chain"] == "forward"
    assert step.data["action"] == "drop"
    assert step.data["in-interface"] == "ether1"
    assert step.data["comment"] == "created by mika: create_firewall_rule"


async def test_optional_fields_included_when_set():
    ctx = await _ctx()
    intent = _fw_intent(
        protocol=L4Protocol.TCP,
        dst_port=443,
        src_address="192.168.88.0/24",
        comment="allow lab https",
    )
    plan = plan_create_firewall_rule(intent, ctx)
    step = plan.steps[0]
    assert step.data["protocol"] == "tcp"
    assert step.data["dst-port"] == "443"
    assert step.data["src-address"] == "192.168.88.0/24"
    assert step.data["comment"] == "allow lab https"


async def test_unknown_in_interface_raises():
    ctx = await _ctx()
    intent = _fw_intent(in_interface="ether99")
    with pytest.raises(InterfaceNotFoundError):
        plan_create_firewall_rule(intent, ctx)


async def test_unknown_out_interface_raises():
    ctx = await _ctx()
    intent = _fw_intent(in_interface=None, out_interface="ether99")
    with pytest.raises(InterfaceNotFoundError):
        plan_create_firewall_rule(intent, ctx)


async def test_duplicate_rule_raises():
    ctx = await _ctx()
    # hex_profile already has an enabled input/drop rule on ether1.
    intent = _fw_intent(chain=FirewallChain.INPUT, action=FirewallAction.DROP, in_interface="ether1")
    with pytest.raises(DuplicateRuleError):
        plan_create_firewall_rule(intent, ctx)
