from __future__ import annotations

import pytest

from mika.ai.schemas.configuration_intents import CreateNatRuleIntent
from mika.ai.schemas.enums import NatAction, NatChain, SafetyLevel
from mika.planner.errors import DuplicateRuleError, InterfaceNotFoundError
from mika.planner.nat import plan_create_nat_rule
from mika.planner.plan import OperationType, PlanStatus
from mika.router.discovery import discover
from mika.router.mock import MockRouterClient
from tests.fixtures.routers import hex_profile


def _nat_intent(**overrides) -> CreateNatRuleIntent:
    fields = {
        "confidence": 0.9,
        "requires_confirmation": True,
        "chain": NatChain.SRCNAT,
        "action": NatAction.MASQUERADE,
        "out_interface": "ether1",
    }
    fields.update(overrides)
    return CreateNatRuleIntent(**fields)


async def _ctx():
    return await discover(MockRouterClient(hex_profile()))


async def test_happy_path_masquerade():
    ctx = await _ctx()
    intent = _nat_intent()

    plan = plan_create_nat_rule(intent, ctx)

    assert plan.status == PlanStatus.PLANNED
    assert plan.safety_level == SafetyLevel.MEDIUM_RISK
    assert plan.affected_interfaces == ("ether1",)
    step = plan.steps[0]
    assert step.operation == OperationType.CREATE
    assert step.resource == "/ip/firewall/nat"
    assert step.data["chain"] == "srcnat"
    assert step.data["action"] == "masquerade"
    assert step.data["out-interface"] == "ether1"
    assert step.data["comment"] == "created by mika: create_nat_rule"


async def test_dst_nat_requires_to_addresses():
    ctx = await _ctx()
    intent = _nat_intent(
        chain=NatChain.DSTNAT,
        action=NatAction.DST_NAT,
        out_interface=None,
        in_interface="ether1",
        dst_address="203.0.113.42/32",
    )
    with pytest.raises(ValueError):
        plan_create_nat_rule(intent, ctx)


async def test_dst_nat_with_to_addresses_succeeds():
    ctx = await _ctx()
    intent = _nat_intent(
        chain=NatChain.DSTNAT,
        action=NatAction.DST_NAT,
        out_interface=None,
        in_interface="ether1",
        dst_address="203.0.113.42/32",
        to_addresses="172.16.5.10",
    )
    plan = plan_create_nat_rule(intent, ctx)
    assert plan.steps[0].data["to-addresses"] == "172.16.5.10"


async def test_unknown_interface_raises():
    ctx = await _ctx()
    intent = _nat_intent(out_interface="ether99")
    with pytest.raises(InterfaceNotFoundError):
        plan_create_nat_rule(intent, ctx)


async def test_duplicate_rule_raises():
    ctx = await _ctx()
    from mika.router.discovery import NatRuleInfo

    existing = NatRuleInfo(
        id="*99",
        chain="srcnat",
        action="masquerade",
        out_interface="ether1",
    )
    ctx_with_existing = ctx.model_copy(update={"nat_rules": [*ctx.nat_rules, existing]})
    with pytest.raises(DuplicateRuleError):
        plan_create_nat_rule(_nat_intent(), ctx_with_existing)
