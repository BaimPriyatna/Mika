from __future__ import annotations

import pytest

from mika.ai.schemas.configuration_intents import CreateDhcpIntent
from mika.ai.schemas.enums import SafetyLevel
from mika.planner.dhcp import plan_create_dhcp
from mika.planner.errors import (
    DhcpAlreadyExistsError,
    GatewayNotInNetworkError,
    InterfaceNotFoundError,
    InterfaceUnavailableError,
    InvalidDhcpPoolRangeError,
    NoAddressOnInterfaceError,
)
from mika.planner.plan import OperationType, PlanStatus
from mika.router.discovery import discover
from mika.router.mock import MockRouterClient
from tests.fixtures.routers import hex_profile, rb951_profile


def _dhcp_intent(**overrides) -> CreateDhcpIntent:
    fields = {
        "confidence": 0.9,
        "requires_confirmation": True,
        "interface": "ether1",
        "pool_start": "10.10.0.100",
        "pool_end": "10.10.0.200",
        "gateway": "10.10.0.5",
    }
    fields.update(overrides)
    return CreateDhcpIntent(**fields)


async def _rb951_context():
    return await discover(MockRouterClient(rb951_profile()))


async def _hex_context():
    return await discover(MockRouterClient(hex_profile()))


def _step_ids(plan):
    return [s.step_id for s in plan.steps]


async def test_plan_create_dhcp_happy_path():
    ctx = await _rb951_context()
    intent = _dhcp_intent()

    plan = plan_create_dhcp(intent, ctx)

    assert plan.status == PlanStatus.PLANNED
    assert plan.safety_level == SafetyLevel.MEDIUM_RISK
    assert plan.affected_interfaces == ("ether1",)
    assert plan.affected_networks == ()
    assert _step_ids(plan) == ["dhcp_pool", "dhcp_network", "dhcp_server"]
    assert all(s.operation == OperationType.CREATE for s in plan.steps)

    network_step = plan.steps[1]
    assert network_step.data["address"] == "10.10.0.0/24"
    assert network_step.data["gateway"] == "10.10.0.5"
    assert network_step.data["dns-server"] == "10.10.0.5"

    server_step = plan.steps[2]
    assert server_step.data["lease-time"] == "1h"
    assert server_step.data["interface"] == "ether1"


async def test_dns_servers_are_joined():
    ctx = await _rb951_context()
    intent = _dhcp_intent(dns_servers=["1.1.1.1", "8.8.8.8"])
    plan = plan_create_dhcp(intent, ctx)
    assert plan.steps[1].data["dns-server"] == "1.1.1.1,8.8.8.8"


async def test_custom_lease_time():
    ctx = await _rb951_context()
    intent = _dhcp_intent(lease_time="30m")
    plan = plan_create_dhcp(intent, ctx)
    assert plan.steps[2].data["lease-time"] == "30m"


async def test_unknown_interface_raises():
    ctx = await _rb951_context()
    intent = _dhcp_intent(interface="ether99")
    with pytest.raises(InterfaceNotFoundError):
        plan_create_dhcp(intent, ctx)


async def test_disabled_interface_raises():
    ctx = await _hex_context()
    intent = _dhcp_intent(interface="ether5", pool_start="192.168.88.10", pool_end="192.168.88.20", gateway="192.168.88.1")
    with pytest.raises(InterfaceUnavailableError):
        plan_create_dhcp(intent, ctx)


async def test_existing_dhcp_server_raises():
    ctx = await _rb951_context()
    intent = _dhcp_intent(interface="wlan1", pool_start="192.168.20.10", pool_end="192.168.20.200", gateway="192.168.20.1")
    with pytest.raises(DhcpAlreadyExistsError):
        plan_create_dhcp(intent, ctx)


async def test_interface_without_address_raises():
    ctx = await _rb951_context()
    # ether-mgmt has no address assigned in rb951_profile fixture
    intent = _dhcp_intent(interface="ether-mgmt")
    with pytest.raises((InterfaceNotFoundError, NoAddressOnInterfaceError)):
        plan_create_dhcp(intent, ctx)


async def test_gateway_outside_network_raises():
    ctx = await _rb951_context()
    intent = _dhcp_intent(gateway="192.168.1.1")
    with pytest.raises(GatewayNotInNetworkError):
        plan_create_dhcp(intent, ctx)


async def test_pool_outside_network_raises():
    ctx = await _rb951_context()
    intent = _dhcp_intent(pool_start="192.168.1.10", pool_end="192.168.1.20")
    with pytest.raises(InvalidDhcpPoolRangeError):
        plan_create_dhcp(intent, ctx)


async def test_pool_start_after_end_raises():
    ctx = await _rb951_context()
    intent = _dhcp_intent(pool_start="10.10.0.200", pool_end="10.10.0.100")
    with pytest.raises(InvalidDhcpPoolRangeError):
        plan_create_dhcp(intent, ctx)
