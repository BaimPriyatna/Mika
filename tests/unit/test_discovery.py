from __future__ import annotations

import pytest

from mika.ai.context import AIContext
from mika.router import (
    MockRouterClient,
    RouterCapabilities,
    RouterContext,
    detect_capabilities,
    discover,
    parse_major_version,
)
from tests.fixtures.routers import chr_profile, hex_profile, rb951_profile


class TestCapabilities:

    def test_parse_major_version(self):
        assert parse_major_version("7.15.3 (stable)") == 7
        assert parse_major_version("6.49.10") == 6
        assert parse_major_version("7.1rc2") == 7
        assert parse_major_version("invalid") == 7

    def test_detect_capabilities_v7_arm(self):
        sys_res = {
            "version": "7.15.3 (stable)",
            "architecture-name": "arm",
            "board-name": "RB750Gr3",
            "cpu-count": "2",
            "total-memory": "268435456",
            "free-memory": "134217728",
        }
        interfaces = [
            {"name": "ether1", "type": "ether"},
            {"name": "ether2", "type": "ether"},
        ]
        caps = detect_capabilities(sys_res, interfaces)

        assert caps.major_version == 7
        assert caps.is_v7 is True
        assert caps.is_v6 is False
        assert caps.architecture == "arm"
        assert caps.board_name == "RB750Gr3"
        assert caps.supports_rest_api is True
        assert caps.supports_wireguard is True
        assert caps.supports_container is True
        assert caps.has_wireless is False
        assert caps.cpu_count == 2
        assert caps.total_memory_bytes == 268435456

    def test_detect_capabilities_v6_mipsbe_wireless(self):
        sys_res = {
            "version": "6.49.10 (long-term)",
            "architecture-name": "mipsbe",
            "board-name": "RB951Ui-2HnD",
            "cpu-count": "1",
            "total-memory": "134217728",
            "free-memory": "67108864",
        }
        interfaces = [
            {"name": "ether1", "type": "ether"},
            {"name": "wlan1", "type": "wlan"},
        ]
        caps = detect_capabilities(sys_res, interfaces)

        assert caps.major_version == 6
        assert caps.is_v7 is False
        assert caps.is_v6 is True
        assert caps.supports_rest_api is False
        assert caps.supports_wireguard is False
        assert caps.supports_container is False
        assert caps.has_wireless is True


class TestDiscovery:

    @pytest.mark.asyncio
    async def test_discover_hex_profile(self):
        client = MockRouterClient(hex_profile())
        ctx = await discover(client)

        assert isinstance(ctx, RouterContext)
        assert ctx.major_version == 7
        assert ctx.board_name == "RB750Gr3"
        assert ctx.architecture == "arm"
        assert "7.15.3" in ctx.routeros_version

        assert len(ctx.interfaces) == 6
        assert "ether1" in ctx.interface_names
        assert "bridge" in ctx.interface_names

        eth1 = ctx.get_interface("ether1")
        assert eth1 is not None
        assert eth1.running is True
        assert eth1.disabled is False
        assert eth1.comment == "WAN"

        assert ctx.is_interface_available("ether1") is True
        assert ctx.is_interface_available("ether4") is False

        assert len(ctx.addresses) == 2
        br_addrs = ctx.get_addresses_on_interface("bridge")
        assert len(br_addrs) == 1
        assert br_addrs[0].address == "192.168.88.1/24"

        assert len(ctx.routes) == 2
        default_route = [r for r in ctx.routes if r.dst_address == "0.0.0.0/0"][0]
        assert default_route.gateway == "203.0.113.1"
        assert default_route.active is True

        assert len(ctx.firewall_rules) == 4
        assert len(ctx.dhcp_servers) == 1
        assert len(ctx.dhcp_leases) == 2
        assert ctx.has_dhcp_on_interface("bridge") is True
        assert ctx.has_dhcp_on_interface("ether1") is False

        assert ctx.has_hotspot_on_interface("bridge") is False

    @pytest.mark.asyncio
    async def test_discover_rb951_profile_with_hotspot(self):
        client = MockRouterClient(rb951_profile())
        ctx = await discover(client)

        assert ctx.board_name == "RB951Ui-2HnD"
        assert ctx.capabilities.has_wireless is True
        assert len(ctx.hotspot_servers) == 1
        assert ctx.has_hotspot_on_interface("wlan1") is True
        assert len(ctx.hotspot_users) == 2

    @pytest.mark.asyncio
    async def test_discover_chr_profile(self):
        client = MockRouterClient(chr_profile())
        ctx = await discover(client)

        assert ctx.major_version == 7
        assert ctx.capabilities.is_v7 is True
        assert ctx.board_name == "CHR"
        assert ctx.capabilities.supports_wireguard is True

    @pytest.mark.asyncio
    async def test_discover_v6_profile(self):
        prof = hex_profile()
        prof.system_resource["version"] = "6.49.10"
        client = MockRouterClient(prof)
        ctx = await discover(client)

        assert ctx.major_version == 6
        assert ctx.capabilities.is_v6 is True
        assert ctx.capabilities.supports_wireguard is False


class TestRouterContextHelpers:

    @pytest.mark.asyncio
    async def test_subnet_conflict_detection(self):
        client = MockRouterClient(hex_profile())
        ctx = await discover(client)

        conflicts = ctx.find_conflicting_subnets("192.168.88.0/24")
        assert "192.168.88.1/24" in conflicts

        conflicts_small = ctx.find_conflicting_subnets("192.168.88.128/25")
        assert "192.168.88.1/24" in conflicts_small

        no_conflicts = ctx.find_conflicting_subnets("10.50.0.0/24")
        assert no_conflicts == []

        assert ctx.find_conflicting_subnets("not-an-ip") == []

    @pytest.mark.asyncio
    async def test_to_ai_context_bridge(self):
        client = MockRouterClient(hex_profile())
        ctx = await discover(client)

        ai_ctx = ctx.to_ai_context(
            safety_constraints=["Do not modify ether1 WAN"],
        )

        assert isinstance(ai_ctx, AIContext)
        assert ai_ctx.router_identity == "RB750Gr3"
        assert "7.15.3" in ai_ctx.routeros_version
        assert "ether1" in ai_ctx.interfaces
        assert "Do not modify ether1 WAN" in ai_ctx.safety_constraints
        assert ai_ctx.extra["major_version"] == 7
