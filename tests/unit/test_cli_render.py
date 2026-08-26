from __future__ import annotations

from unittest.mock import Mock

import pytest
from rich.console import Console

from mika.cli import render
from mika.router.capabilities import RouterCapabilities
from mika.router.discovery import (
    DhcpLeaseInfo,
    DhcpServerInfo,
    FirewallRuleInfo,
    HotspotServerInfo,
    HotspotUserInfo,
    InterfaceInfo,
    IPAddressInfo,
    RouteInfo,
    RouterContext,
    SystemResource,
)


@pytest.fixture
def console():
    return Console(file=Mock(), force_terminal=False)


@pytest.fixture
def minimal_ctx():
    return RouterContext(
        identity="test-router",
        system_resource=SystemResource(
            version="7.15.3",
            board_name="CHR",
            architecture_name="x86_64",
            uptime="1d2h3m4s",
            cpu_load=10,
            total_memory=1024,
            free_memory=512,
        ),
        capabilities=RouterCapabilities(
            version="7.15.3",
            major_version=7,
            architecture="x86_64",
            board_name="CHR",
            supports_rest_api=True,
            supports_wireguard=True,
            supports_container=True,
            supports_vlan_filtering=True,
        ),
        interfaces=[],
        addresses=[],
        routes=[],
        firewall_rules=[],
        dhcp_servers=[],
        dhcp_leases=[],
        hotspot_servers=[],
        hotspot_users=[],
    )


def test_inspect_targets_defined():
    assert "router" in render.INSPECT_TARGETS
    assert "interfaces" in render.INSPECT_TARGETS
    assert "addresses" in render.INSPECT_TARGETS
    assert "routes" in render.INSPECT_TARGETS
    assert "firewall" in render.INSPECT_TARGETS
    assert "dhcp" in render.INSPECT_TARGETS
    assert "hotspot" in render.INSPECT_TARGETS


def test_render_inspect_unknown_target(console, minimal_ctx):
    render.render_inspect(console, "unknown", minimal_ctx)


def test_render_router(console, minimal_ctx):
    render.render_inspect(console, "router", minimal_ctx)


def test_render_interfaces_empty(console, minimal_ctx):
    render.render_inspect(console, "interfaces", minimal_ctx)


def test_render_interfaces_with_data(console, minimal_ctx):
    ctx = RouterContext(
        identity=minimal_ctx.identity,
        system_resource=minimal_ctx.system_resource,
        capabilities=minimal_ctx.capabilities,
        interfaces=[
            InterfaceInfo(
                id="*1",
                name="ether1",
                type="ether",
                running=True,
                disabled=False,
                mac_address="00:11:22:33:44:55",
                comment="WAN",
            )
        ],
    )
    render.render_inspect(console, "interfaces", ctx)


def test_render_addresses(console, minimal_ctx):
    ctx = RouterContext(
        identity=minimal_ctx.identity,
        system_resource=minimal_ctx.system_resource,
        capabilities=minimal_ctx.capabilities,
        addresses=[
            IPAddressInfo(
                id="*1",
                address="192.168.88.1/24",
                interface="bridge",
                network="192.168.88.0",
                disabled=False,
            )
        ],
    )
    render.render_inspect(console, "addresses", ctx)


def test_render_routes(console, minimal_ctx):
    ctx = RouterContext(
        identity=minimal_ctx.identity,
        system_resource=minimal_ctx.system_resource,
        capabilities=minimal_ctx.capabilities,
        routes=[
            RouteInfo(
                id="*1",
                dst_address="0.0.0.0/0",
                gateway="192.168.88.1",
                distance=1,
                active=True,
                static=True,
            )
        ],
    )
    render.render_inspect(console, "routes", ctx)


def test_render_firewall(console, minimal_ctx):
    ctx = RouterContext(
        identity=minimal_ctx.identity,
        system_resource=minimal_ctx.system_resource,
        capabilities=minimal_ctx.capabilities,
        firewall_rules=[
            FirewallRuleInfo(
                id="*1",
                chain="input",
                action="accept",
                src_address="192.168.88.0/24",
                dst_address=None,
                protocol="tcp",
                disabled=False,
                comment="Allow LAN",
            )
        ],
    )
    render.render_inspect(console, "firewall", ctx)


def test_render_dhcp(console, minimal_ctx):
    ctx = RouterContext(
        identity=minimal_ctx.identity,
        system_resource=minimal_ctx.system_resource,
        capabilities=minimal_ctx.capabilities,
        dhcp_servers=[
            DhcpServerInfo(
                id="*1",
                name="dhcp1",
                interface="bridge",
                address_pool="pool1",
                lease_time="1h",
                disabled=False,
            )
        ],
        dhcp_leases=[
            DhcpLeaseInfo(
                id="*1",
                address="192.168.88.100",
                mac_address="AA:BB:CC:DD:EE:FF",
                server="dhcp1",
                status="bound",
                host_name="client1",
            )
        ],
    )
    render.render_inspect(console, "dhcp", ctx)


def test_render_hotspot(console, minimal_ctx):
    ctx = RouterContext(
        identity=minimal_ctx.identity,
        system_resource=minimal_ctx.system_resource,
        capabilities=minimal_ctx.capabilities,
        hotspot_servers=[
            HotspotServerInfo(
                id="*1",
                name="hotspot1",
                interface="ether2",
                profile="default",
                address_pool="hotspot-pool",
                disabled=False,
            )
        ],
        hotspot_users=[
            HotspotUserInfo(
                id="*1",
                name="user1",
                profile="default",
                disabled=False,
            )
        ],
    )
    render.render_inspect(console, "hotspot", ctx)


def test_intent_to_target_mapping():
    assert render.INTENT_TO_TARGET["inspect_router"] == "router"
    assert render.INTENT_TO_TARGET["inspect_interfaces"] == "interfaces"
    assert render.INTENT_TO_TARGET["inspect_ip_addresses"] == "addresses"
    assert render.INTENT_TO_TARGET["inspect_routes"] == "routes"
    assert render.INTENT_TO_TARGET["inspect_firewall"] == "firewall"
    assert render.INTENT_TO_TARGET["inspect_dhcp"] == "dhcp"
    assert render.INTENT_TO_TARGET["inspect_hotspot"] == "hotspot"


def test_render_advice(console):
    render.render_advice(
        console,
        "Here are recommendations for your router.",
        options=["Option A", "Option B"],
        suggested_action="setup hotspot",
    )


def test_render_advice_escapes_markup_like_content(console):
    """AI-generated text mentioning RouterOS paths (e.g. '[/ip route]') must
    not be interpreted as Rich markup and must not crash rendering."""
    render.render_advice(
        console,
        "I will check [/ip route] before making changes.",
        options=["Review [cyan]VLAN[/cyan] settings first"],
        suggested_action="inspect [/ip firewall filter]",
    )


def test_render_interfaces_with_markup_like_comment_does_not_crash(console, minimal_ctx):
    """A router-provided interface comment containing bracket syntax (e.g.
    '[/ip route]') is untrusted data and must not be treated as Rich markup."""
    ctx = RouterContext(
        identity=minimal_ctx.identity,
        system_resource=minimal_ctx.system_resource,
        capabilities=minimal_ctx.capabilities,
        interfaces=[
            InterfaceInfo(
                id="*1",
                name="ether1",
                type="ether",
                running=True,
                disabled=False,
                mac_address="00:11:22:33:44:55",
                comment="WAN uplink [/ip route] main",
            )
        ],
    )
    render.render_inspect(console, "interfaces", ctx)


def test_render_firewall_with_markup_like_comment_does_not_crash(console, minimal_ctx):
    ctx = RouterContext(
        identity=minimal_ctx.identity,
        system_resource=minimal_ctx.system_resource,
        capabilities=minimal_ctx.capabilities,
        firewall_rules=[
            FirewallRuleInfo(
                id="*1",
                chain="forward",
                action="accept",
                disabled=False,
                comment="allow LAN [admin] traffic",
            )
        ],
    )
    render.render_inspect(console, "firewall", ctx)
