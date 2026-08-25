from __future__ import annotations

import pytest

from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.enums import SafetyLevel
from mika.planner.errors import (
    HotspotAlreadyExistsError,
    InterfaceNotFoundError,
    InterfaceUnavailableError,
    NetworkTooSmallError,
    SubnetConflictError,
)
from mika.planner.hotspot import plan_create_hotspot
from mika.planner.plan import OperationType, PlanStatus
from mika.router.discovery import discover
from mika.router.mock import MockRouterClient
from tests.fixtures.routers import hex_profile, rb951_profile


def _hotspot_intent(**overrides) -> CreateHotspotIntent:
    fields = {
        "confidence": 0.9,
        "requires_confirmation": True,
        "interface": "ether3",
        "network": "192.168.20.0/24",
    }
    fields.update(overrides)
    return CreateHotspotIntent(**fields)


async def _hex_context():
    return await discover(MockRouterClient(hex_profile()))


async def _rb951_context():
    return await discover(MockRouterClient(rb951_profile()))


async def test_plan_create_hotspot_happy_path():
    ctx = await _hex_context()
    intent = _hotspot_intent(rate_limit="5M/5M", dns_name="lab.hotspot.local")

    plan = plan_create_hotspot(intent, ctx)

    assert plan.plan_id.startswith("plan_")
    assert plan.status == PlanStatus.PLANNED
    assert plan.safety_level == SafetyLevel.MEDIUM_RISK
    assert plan.router_identity == ctx.identity
    assert plan.routeros_version == ctx.routeros_version
    assert plan.affected_interfaces == ("ether3",)
    assert plan.affected_networks == ("192.168.20.0/24",)
    assert plan.intent is intent


def _step_ids(plan):
    return [s.step_id for s in plan.steps]


async def test_plan_steps_are_in_dependency_order_with_rate_limit():
    ctx = await _hex_context()
    intent = _hotspot_intent(rate_limit="5M/5M")
    plan = plan_create_hotspot(intent, ctx)

    assert _step_ids(plan) == [
        "hotspot_address",
        "hotspot_pool",
        "hotspot_dhcp_network",
        "hotspot_dhcp_server",
        "hotspot_user_profile",
        "hotspot_profile",
        "hotspot_server",
    ]
    assert all(s.operation == OperationType.CREATE for s in plan.steps)
    assert all(s.resource_id is None for s in plan.steps)


async def test_plan_steps_without_rate_limit_skip_user_profile():
    ctx = await _hex_context()
    intent = _hotspot_intent()
    plan = plan_create_hotspot(intent, ctx)

    assert "hotspot_user_profile" not in _step_ids(plan)
    assert plan.warnings == ()


async def test_rate_limit_produces_warning_about_unlinked_profile():
    ctx = await _hex_context()
    intent = _hotspot_intent(rate_limit="10M/10M")
    plan = plan_create_hotspot(intent, ctx)

    assert len(plan.warnings) == 1
    assert "rate-limit" in plan.warnings[0] or "rate limit" in plan.warnings[0].lower()


async def test_resource_paths_and_data_shape():
    ctx = await _hex_context()
    intent = _hotspot_intent()
    plan = plan_create_hotspot(intent, ctx)
    by_id = {s.step_id: s for s in plan.steps}

    address_step = by_id["hotspot_address"]
    assert address_step.resource == "/ip/address"
    assert address_step.data["interface"] == "ether3"
    assert address_step.data["address"].startswith("192.168.20.1/")

    pool_step = by_id["hotspot_pool"]
    assert pool_step.resource == "/ip/pool"
    assert pool_step.data["ranges"] == "192.168.20.2-192.168.20.254"
    assert pool_step.data["name"] == "ether3-hotspot-pool"

    dhcp_net_step = by_id["hotspot_dhcp_network"]
    assert dhcp_net_step.resource == "/ip/dhcp-server/network"
    assert dhcp_net_step.data["gateway"] == "192.168.20.1"

    dhcp_srv_step = by_id["hotspot_dhcp_server"]
    assert dhcp_srv_step.resource == "/ip/dhcp-server"
    assert dhcp_srv_step.data["interface"] == "ether3"
    assert dhcp_srv_step.data["address-pool"] == "ether3-hotspot-pool"

    profile_step = by_id["hotspot_profile"]
    assert profile_step.resource == "/ip/hotspot/profile"
    assert profile_step.data["name"] == "ether3-hotspot-profile"

    server_step = by_id["hotspot_server"]
    assert server_step.resource == "/ip/hotspot"
    assert server_step.data["name"] == "ether3-hotspot"
    assert server_step.data["profile"] == "ether3-hotspot-profile"
    assert server_step.data["address-pool"] == "ether3-hotspot-pool"


async def test_dns_name_included_only_when_provided():
    ctx = await _hex_context()

    with_dns = plan_create_hotspot(_hotspot_intent(dns_name="portal.local"), ctx)
    profile_step = next(s for s in with_dns.steps if s.step_id == "hotspot_profile")
    assert profile_step.data["dns-name"] == "portal.local"

    without_dns = plan_create_hotspot(_hotspot_intent(), ctx)
    profile_step2 = next(s for s in without_dns.steps if s.step_id == "hotspot_profile")
    assert "dns-name" not in profile_step2.data


async def test_missing_interface_raises():
    ctx = await _hex_context()
    intent = _hotspot_intent(interface="ether99")
    with pytest.raises(InterfaceNotFoundError):
        plan_create_hotspot(intent, ctx)


async def test_disabled_interface_raises():
    ctx = await _hex_context()
    intent = _hotspot_intent(interface="ether4")
    with pytest.raises(InterfaceUnavailableError):
        plan_create_hotspot(intent, ctx)


async def test_existing_hotspot_on_interface_raises():
    ctx = await _rb951_context()
    intent = _hotspot_intent(interface="wlan1", network="192.168.30.0/24")
    with pytest.raises(HotspotAlreadyExistsError):
        plan_create_hotspot(intent, ctx)


async def test_subnet_overlap_raises():
    ctx = await _hex_context()
    intent = _hotspot_intent(interface="ether3", network="192.168.88.0/25")
    with pytest.raises(SubnetConflictError) as exc_info:
        plan_create_hotspot(intent, ctx)
    assert "192.168.88.1/24" in exc_info.value.conflicting_addresses


async def test_network_too_small_raises():
    ctx = await _hex_context()
    intent = _hotspot_intent(network="192.168.20.0/32")
    with pytest.raises(NetworkTooSmallError):
        plan_create_hotspot(intent, ctx)


async def test_wrong_intent_type_rejected():
    from mika.ai.schemas.read_intents import InspectRouterIntent

    ctx = None
    bad_intent = InspectRouterIntent(confidence=0.9, requires_confirmation=False)
    with pytest.raises(ValueError):
        plan_create_hotspot(bad_intent, ctx)


async def test_fingerprint_present_and_stable_for_same_state():
    ctx = await _hex_context()
    plan1 = plan_create_hotspot(_hotspot_intent(), ctx)
    plan2 = plan_create_hotspot(_hotspot_intent(network="192.168.21.0/24"), ctx)

    assert plan1.router_state_fingerprint == plan2.router_state_fingerprint
    assert len(plan1.router_state_fingerprint) == 16


async def test_fingerprint_changes_when_router_state_changes():
    profile = hex_profile()
    client = MockRouterClient(profile)
    ctx_before = await discover(client)
    plan_before = plan_create_hotspot(_hotspot_intent(), ctx_before)

    for iface in profile.interfaces:
        if iface["name"] == "ether4":
            iface["disabled"] = "false"

    ctx_after = await discover(MockRouterClient(profile))
    plan_after = plan_create_hotspot(_hotspot_intent(), ctx_after)

    assert plan_before.router_state_fingerprint != plan_after.router_state_fingerprint


async def test_plan_and_steps_are_frozen():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)

    with pytest.raises(Exception):
        plan.status = PlanStatus.CONFIRMED

    with pytest.raises(Exception):
        plan.steps[0].resource_id = "*1"
