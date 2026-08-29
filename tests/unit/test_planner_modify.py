from __future__ import annotations

import pytest

from mika.ai.schemas.enums import SafetyLevel
from mika.ai.schemas.modification_intents import (
    ModifyAddressIntent,
    ModifyDhcpIntent,
    ModifyFirewallRuleIntent,
    ModifyHotspotIntent,
    ModifyQueueIntent,
)
from mika.planner.errors import (
    ResourceNotFoundError,
    SubnetConflictError,
    UnsupportedModificationError,
)
from mika.planner.modify_address import plan_modify_address
from mika.planner.modify_dhcp import plan_modify_dhcp
from mika.planner.modify_firewall import plan_modify_firewall_rule
from mika.planner.modify_hotspot import plan_modify_hotspot
from mika.planner.modify_queue import plan_modify_queue
from mika.planner.plan import OperationType, PlanStatus
from mika.router.discovery import QueueInfo, discover
from mika.router.mock import MockRouterClient
from tests.fixtures.routers import hex_profile, rb951_profile


async def _hex_ctx():
    return await discover(MockRouterClient(hex_profile()))


async def _rb951_ctx():
    return await discover(MockRouterClient(rb951_profile()))


# -- modify_address ----------------------------------------------------


async def test_modify_address_comment_only():
    ctx = await _hex_ctx()
    intent = ModifyAddressIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*2", comment="lab bridge"
    )
    plan = plan_modify_address(intent, ctx)
    assert plan.status == PlanStatus.PLANNED
    assert plan.safety_level == SafetyLevel.MEDIUM_RISK
    step = plan.steps[0]
    assert step.operation == OperationType.UPDATE
    assert step.resource_id == "*2"
    assert step.data == {"comment": "lab bridge"}


async def test_modify_address_new_address_conflicts():
    ctx = await _hex_ctx()
    # *2 is on 'bridge' (192.168.88.1/24); moving it into ether1's subnet
    # (203.0.113.0/24) should be rejected as an overlap with *1.
    intent = ModifyAddressIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*2", address="203.0.113.99/24"
    )
    with pytest.raises(SubnetConflictError):
        plan_modify_address(intent, ctx)


async def test_modify_address_unknown_id_raises():
    ctx = await _hex_ctx()
    intent = ModifyAddressIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*99", comment="x"
    )
    with pytest.raises(ResourceNotFoundError):
        plan_modify_address(intent, ctx)


# -- modify_firewall_rule ------------------------------------------------


async def test_modify_firewall_rule_disable():
    ctx = await _hex_ctx()
    intent = ModifyFirewallRuleIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*4", disabled=True
    )
    plan = plan_modify_firewall_rule(intent, ctx)
    assert plan.safety_level == SafetyLevel.HIGH_RISK
    assert plan.steps[0].data == {"disabled": "yes"}
    assert plan.steps[0].resource_id == "*4"


async def test_modify_firewall_rule_unknown_id_raises():
    ctx = await _hex_ctx()
    intent = ModifyFirewallRuleIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*99", disabled=True
    )
    with pytest.raises(ResourceNotFoundError):
        plan_modify_firewall_rule(intent, ctx)


# -- modify_dhcp -----------------------------------------------------------


async def test_modify_dhcp_lease_time_and_disabled():
    ctx = await _hex_ctx()
    intent = ModifyDhcpIntent(
        confidence=0.9,
        requires_confirmation=True,
        resource_id="*1",
        lease_time="2h",
        disabled=True,
    )
    plan = plan_modify_dhcp(intent, ctx)
    assert plan.steps[0].data == {"lease-time": "2h", "disabled": "yes"}


async def test_modify_dhcp_gateway_unsupported():
    ctx = await _hex_ctx()
    intent = ModifyDhcpIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", gateway="192.168.88.5"
    )
    with pytest.raises(UnsupportedModificationError):
        plan_modify_dhcp(intent, ctx)


async def test_modify_dhcp_pool_fields_unsupported():
    ctx = await _hex_ctx()
    intent = ModifyDhcpIntent(
        confidence=0.9,
        requires_confirmation=True,
        resource_id="*1",
        pool_start="192.168.88.50",
        pool_end="192.168.88.60",
    )
    with pytest.raises(UnsupportedModificationError):
        plan_modify_dhcp(intent, ctx)


# -- modify_hotspot ----------------------------------------------------------


async def test_modify_hotspot_disable():
    ctx = await _rb951_ctx()
    intent = ModifyHotspotIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", disabled=True
    )
    plan = plan_modify_hotspot(intent, ctx)
    assert plan.steps[0].data == {"disabled": "yes"}


async def test_modify_hotspot_rate_limit_unsupported():
    ctx = await _rb951_ctx()
    intent = ModifyHotspotIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", rate_limit="5M/5M"
    )
    with pytest.raises(UnsupportedModificationError):
        plan_modify_hotspot(intent, ctx)


# -- modify_queue --------------------------------------------------------


async def test_modify_queue_max_limit():
    ctx = await _hex_ctx()
    existing = QueueInfo(id="*1", name="q1", target="ether2", max_limit="5M/5M")
    ctx = ctx.model_copy(update={"queues": [existing]})
    intent = ModifyQueueIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", max_limit="20M/20M"
    )
    plan = plan_modify_queue(intent, ctx)
    assert plan.steps[0].data == {"max-limit": "20M/20M"}
    assert plan.affected_interfaces == ("ether2",)


async def test_modify_queue_unknown_id_raises():
    ctx = await _hex_ctx()
    intent = ModifyQueueIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*99", disabled=True
    )
    with pytest.raises(ResourceNotFoundError):
        plan_modify_queue(intent, ctx)
