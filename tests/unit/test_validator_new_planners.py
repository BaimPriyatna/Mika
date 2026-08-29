from __future__ import annotations

from pathlib import Path

from mika.ai.schemas.configuration_intents import (
    CreateAddressIntent,
    CreateDhcpIntent,
    CreateFirewallRuleIntent,
    CreateNatRuleIntent,
    CreateQueueIntent,
    CreateVlanIntent,
)
from mika.ai.schemas.enums import FirewallAction, FirewallChain, NatAction, NatChain
from mika.knowledge.loader import KnowledgeLoader
from mika.knowledge.retriever import KnowledgeRetriever
from mika.planner.address import plan_create_address
from mika.planner.dhcp import plan_create_dhcp
from mika.planner.firewall import plan_create_firewall_rule
from mika.planner.nat import plan_create_nat_rule
from mika.planner.plan import PlanStatus
from mika.planner.queue import plan_create_queue
from mika.planner.vlan import plan_create_vlan
from mika.router.discovery import discover
from mika.router.mock import MockRouterClient
from mika.validator.validator import validate
from tests.fixtures.routers import hex_profile, rb951_profile

REPO_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge"


def _retriever() -> KnowledgeRetriever:
    return KnowledgeRetriever(KnowledgeLoader(root=REPO_KNOWLEDGE_ROOT).load_all())


async def test_create_address_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = CreateAddressIntent(
        confidence=0.9, requires_confirmation=True, interface="ether2", address="172.16.5.1/24"
    )
    plan = plan_create_address(intent, ctx)

    result = validate(plan, ctx, _retriever())

    assert result.validated is True
    assert result.failures == ()
    assert result.plan.status == PlanStatus.VALIDATED


async def test_create_dhcp_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(rb951_profile()))
    intent = CreateDhcpIntent(
        confidence=0.9,
        requires_confirmation=True,
        interface="ether1",
        pool_start="10.10.0.100",
        pool_end="10.10.0.200",
        gateway="10.10.0.5",
    )
    plan = plan_create_dhcp(intent, ctx)

    result = validate(plan, ctx, _retriever())

    # ether1 carries the default route in this fixture, so a WARNING is
    # expected -- but it must not FAIL, and affected_networks being empty
    # must not trigger a self-conflict in the overlap layer.
    assert result.validated is True
    assert result.failures == ()
    assert result.plan.status == PlanStatus.VALIDATED


async def test_create_firewall_rule_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = CreateFirewallRuleIntent(
        confidence=0.9,
        requires_confirmation=True,
        chain=FirewallChain.FORWARD,
        action=FirewallAction.DROP,
        in_interface="ether2",
    )
    plan = plan_create_firewall_rule(intent, ctx)

    result = validate(plan, ctx, _retriever())

    assert result.validated is True
    assert result.failures == ()
    assert result.plan.status == PlanStatus.VALIDATED


async def test_create_nat_rule_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = CreateNatRuleIntent(
        confidence=0.9,
        requires_confirmation=True,
        chain=NatChain.SRCNAT,
        action=NatAction.MASQUERADE,
        out_interface="ether2",
    )
    plan = plan_create_nat_rule(intent, ctx)

    result = validate(plan, ctx, _retriever())

    assert result.validated is True
    assert result.failures == ()
    assert result.plan.status == PlanStatus.VALIDATED


async def test_create_queue_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = CreateQueueIntent(
        confidence=0.9,
        requires_confirmation=True,
        name="lab-limit",
        target="172.16.5.0/24",
        max_limit="10M/10M",
    )
    plan = plan_create_queue(intent, ctx)

    result = validate(plan, ctx, _retriever())

    assert result.validated is True
    assert result.failures == ()
    assert result.plan.status == PlanStatus.VALIDATED


async def test_create_vlan_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = CreateVlanIntent(
        confidence=0.9, requires_confirmation=True, parent_interface="ether2", vlan_id=100
    )
    plan = plan_create_vlan(intent, ctx)

    result = validate(plan, ctx, _retriever())

    assert result.validated is True
    assert result.failures == ()
    assert result.plan.status == PlanStatus.VALIDATED


# -- Batch 5-6: modify_* and delete_* integration --------------------------

from mika.ai.schemas.modification_intents import (
    ModifyAddressIntent,
    ModifyDhcpIntent,
    ModifyFirewallRuleIntent,
    ModifyHotspotIntent,
    ModifyQueueIntent,
)
from mika.ai.schemas.destructive_intents import (
    DeleteAddressIntent,
    DeleteDhcpIntent,
    DeleteFirewallRuleIntent,
    DeleteHotspotIntent,
    DeleteQueueIntent,
    DeleteVlanIntent,
)
from mika.planner.delete_address import plan_delete_address
from mika.planner.delete_dhcp import plan_delete_dhcp
from mika.planner.delete_firewall import plan_delete_firewall_rule
from mika.planner.delete_hotspot import plan_delete_hotspot
from mika.planner.delete_queue import plan_delete_queue
from mika.planner.delete_vlan import plan_delete_vlan
from mika.planner.modify_address import plan_modify_address
from mika.planner.modify_dhcp import plan_modify_dhcp
from mika.planner.modify_firewall import plan_modify_firewall_rule
from mika.planner.modify_hotspot import plan_modify_hotspot
from mika.planner.modify_queue import plan_modify_queue
from mika.router.discovery import InterfaceInfo, QueueInfo


async def test_modify_address_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = ModifyAddressIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*2", comment="lab bridge"
    )
    plan = plan_modify_address(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()


async def test_modify_firewall_rule_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = ModifyFirewallRuleIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*4", disabled=True
    )
    plan = plan_modify_firewall_rule(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()


async def test_modify_dhcp_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = ModifyDhcpIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", lease_time="2h"
    )
    plan = plan_modify_dhcp(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()


async def test_modify_hotspot_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(rb951_profile()))
    intent = ModifyHotspotIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", disabled=True
    )
    plan = plan_modify_hotspot(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()


async def test_modify_queue_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    ctx = ctx.model_copy(
        update={"queues": [QueueInfo(id="*1", name="q1", target="ether2", max_limit="5M/5M")]}
    )
    intent = ModifyQueueIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", max_limit="20M/20M"
    )
    plan = plan_modify_queue(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()


async def test_delete_address_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = DeleteAddressIntent(
        confidence=0.9,
        requires_confirmation=True,
        resource_id="*1",
        expected_description="ether1 address",
    )
    plan = plan_delete_address(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()


async def test_delete_vlan_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    vlan_iface = InterfaceInfo(
        id="*99", name="vlan100", type="vlan", vlan_id=100, vlan_parent="ether2"
    )
    ctx = ctx.model_copy(update={"interfaces": [*ctx.interfaces, vlan_iface]})
    intent = DeleteVlanIntent(
        confidence=0.9,
        requires_confirmation=True,
        resource_id="*99",
        expected_description="vlan100",
    )
    plan = plan_delete_vlan(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()


async def test_delete_firewall_rule_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = DeleteFirewallRuleIntent(
        confidence=0.9,
        requires_confirmation=True,
        resource_id="*4",
        expected_description="forward accept",
    )
    plan = plan_delete_firewall_rule(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()


async def test_delete_dhcp_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    intent = DeleteDhcpIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", expected_description="dhcp1"
    )
    plan = plan_delete_dhcp(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()


async def test_delete_hotspot_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(rb951_profile()))
    intent = DeleteHotspotIntent(
        confidence=0.9,
        requires_confirmation=True,
        resource_id="*1",
        expected_description="hotspot1",
    )
    plan = plan_delete_hotspot(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()


async def test_delete_queue_plan_passes_all_layers():
    ctx = await discover(MockRouterClient(hex_profile()))
    ctx = ctx.model_copy(
        update={"queues": [QueueInfo(id="*1", name="q1", target="ether2", max_limit="5M/5M")]}
    )
    intent = DeleteQueueIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", expected_description="q1"
    )
    plan = plan_delete_queue(intent, ctx)
    result = validate(plan, ctx, _retriever())
    assert result.validated is True
    assert result.failures == ()
