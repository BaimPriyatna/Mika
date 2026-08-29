from __future__ import annotations

import pytest

from mika.ai.schemas.destructive_intents import (
    DeleteAddressIntent,
    DeleteDhcpIntent,
    DeleteFirewallRuleIntent,
    DeleteHotspotIntent,
    DeleteQueueIntent,
    DeleteVlanIntent,
)
from mika.ai.schemas.enums import SafetyLevel
from mika.planner.delete_address import plan_delete_address
from mika.planner.delete_dhcp import plan_delete_dhcp
from mika.planner.delete_firewall import plan_delete_firewall_rule
from mika.planner.delete_hotspot import plan_delete_hotspot
from mika.planner.delete_queue import plan_delete_queue
from mika.planner.delete_vlan import plan_delete_vlan
from mika.planner.errors import ResourceNotFoundError
from mika.planner.plan import OperationType, PlanStatus
from mika.router.discovery import InterfaceInfo, QueueInfo, discover
from mika.router.mock import MockRouterClient
from tests.fixtures.routers import hex_profile, rb951_profile


async def _hex_ctx():
    return await discover(MockRouterClient(hex_profile()))


async def _rb951_ctx():
    return await discover(MockRouterClient(rb951_profile()))


# -- delete_address ----------------------------------------------------


async def test_delete_address_happy_path():
    ctx = await _hex_ctx()
    intent = DeleteAddressIntent(
        confidence=0.9,
        requires_confirmation=True,
        resource_id="*1",
        expected_description="ether1 address",
    )
    plan = plan_delete_address(intent, ctx)
    assert plan.status == PlanStatus.PLANNED
    assert plan.safety_level == SafetyLevel.DESTRUCTIVE
    step = plan.steps[0]
    assert step.operation == OperationType.DELETE
    assert step.resource == "/ip/address"
    assert step.resource_id == "*1"
    assert plan.affected_networks == ()


async def test_delete_address_unknown_id_raises():
    ctx = await _hex_ctx()
    intent = DeleteAddressIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*99", expected_description="x"
    )
    with pytest.raises(ResourceNotFoundError):
        plan_delete_address(intent, ctx)


# -- delete_vlan ---------------------------------------------------------


async def test_delete_vlan_happy_path():
    ctx = await _hex_ctx()
    vlan_iface = InterfaceInfo(
        id="*99", name="vlan100", type="vlan", vlan_id=100, vlan_parent="ether2"
    )
    ctx = ctx.model_copy(update={"interfaces": [*ctx.interfaces, vlan_iface]})
    intent = DeleteVlanIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*99", expected_description="vlan100"
    )
    plan = plan_delete_vlan(intent, ctx)
    assert plan.steps[0].resource == "/interface/vlan"
    assert plan.affected_interfaces == ("ether2",)


async def test_delete_vlan_unknown_id_raises():
    ctx = await _hex_ctx()
    intent = DeleteVlanIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*99", expected_description="x"
    )
    with pytest.raises(ResourceNotFoundError):
        plan_delete_vlan(intent, ctx)


# -- delete_firewall_rule ------------------------------------------------


async def test_delete_firewall_rule_happy_path():
    ctx = await _hex_ctx()
    intent = DeleteFirewallRuleIntent(
        confidence=0.9,
        requires_confirmation=True,
        resource_id="*4",
        expected_description="forward accept",
    )
    plan = plan_delete_firewall_rule(intent, ctx)
    assert plan.safety_level == SafetyLevel.DESTRUCTIVE
    assert plan.steps[0].resource == "/ip/firewall/filter"


async def test_delete_firewall_rule_unknown_id_raises():
    ctx = await _hex_ctx()
    intent = DeleteFirewallRuleIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*99", expected_description="x"
    )
    with pytest.raises(ResourceNotFoundError):
        plan_delete_firewall_rule(intent, ctx)


# -- delete_dhcp -----------------------------------------------------------


async def test_delete_dhcp_happy_path():
    ctx = await _hex_ctx()
    intent = DeleteDhcpIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", expected_description="dhcp1"
    )
    plan = plan_delete_dhcp(intent, ctx)
    assert plan.steps[0].resource == "/ip/dhcp-server"
    assert "not removed automatically" in plan.steps[0].description


async def test_delete_dhcp_unknown_id_raises():
    ctx = await _hex_ctx()
    intent = DeleteDhcpIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*99", expected_description="x"
    )
    with pytest.raises(ResourceNotFoundError):
        plan_delete_dhcp(intent, ctx)


# -- delete_hotspot ----------------------------------------------------------


async def test_delete_hotspot_happy_path():
    ctx = await _rb951_ctx()
    intent = DeleteHotspotIntent(
        confidence=0.9,
        requires_confirmation=True,
        resource_id="*1",
        expected_description="hotspot1",
    )
    plan = plan_delete_hotspot(intent, ctx)
    assert plan.steps[0].resource == "/ip/hotspot"
    assert "not removed automatically" in plan.steps[0].description


async def test_delete_hotspot_unknown_id_raises():
    ctx = await _rb951_ctx()
    intent = DeleteHotspotIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*99", expected_description="x"
    )
    with pytest.raises(ResourceNotFoundError):
        plan_delete_hotspot(intent, ctx)


# -- delete_queue --------------------------------------------------------


async def test_delete_queue_happy_path():
    ctx = await _hex_ctx()
    existing = QueueInfo(id="*1", name="q1", target="ether2", max_limit="5M/5M")
    ctx = ctx.model_copy(update={"queues": [existing]})
    intent = DeleteQueueIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", expected_description="q1"
    )
    plan = plan_delete_queue(intent, ctx)
    assert plan.steps[0].resource == "/queue/simple"
    assert plan.affected_interfaces == ("ether2",)


async def test_delete_queue_unknown_id_raises():
    ctx = await _hex_ctx()
    intent = DeleteQueueIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*99", expected_description="x"
    )
    with pytest.raises(ResourceNotFoundError):
        plan_delete_queue(intent, ctx)
