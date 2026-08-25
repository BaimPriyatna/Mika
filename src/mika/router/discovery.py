"""
Router Capability and Topology Discovery.

Inspects a connected RouterOS device to discover active packages,
hardware capabilities (Wireless, WireGuard, Capsman), and configuration topology.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mika.ai.context import AIContext
from mika.router.capabilities import (
    RouterCapabilities,
    detect_capabilities,
    parse_major_version,
)
from mika.router.client import RouterClient

logger = logging.getLogger(__name__)


def _parse_bool(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "yes", "1"):
            return True
        if v in ("false", "no", "0"):
            return False
    return default


def _parse_int(val: Any, default: int | None = None) -> int | None:
    if val is None:
        return default
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return default


class SystemResource(BaseModel):

    model_config = ConfigDict(frozen=True)

    version: str = Field(default="unknown")
    board_name: str = Field(default="unknown")
    architecture_name: str = Field(default="unknown")
    cpu: str | None = None
    cpu_count: int = Field(ge=1, default=1)
    cpu_frequency: int | None = None
    cpu_load: int | None = None
    free_memory: int = Field(ge=0, default=0)
    total_memory: int = Field(ge=0, default=0)
    free_hdd_space: int | None = None
    total_hdd_space: int | None = None
    uptime: str = Field(default="0s")
    platform: str | None = None


class InterfaceInfo(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="RouterOS .id (e.g. '*1')")
    name: str = Field(description="Interface name (e.g. 'ether1', 'bridge')")
    type: str = Field(description="Interface type (e.g. 'ether', 'bridge', 'wlan', 'vlan')")
    running: bool = True
    disabled: bool = False
    comment: str | None = None
    mac_address: str | None = None
    mtu: int | None = 1500


class IPAddressInfo(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="RouterOS .id")
    address: str = Field(description="IP address with prefix (e.g. '192.168.88.1/24')")
    network: str = Field(description="Network address (e.g. '192.168.88.0')")
    interface: str = Field(description="Bound interface name")
    disabled: bool = False
    comment: str | None = None

    @property
    def ip_interface(self) -> ipaddress.IPv4Interface | ipaddress.IPv6Interface | None:
        try:
            return ipaddress.ip_interface(self.address)
        except ValueError:
            return None


class RouteInfo(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="RouterOS .id")
    dst_address: str = Field(description="Destination prefix (e.g. '0.0.0.0/0')")
    gateway: str = Field(description="Gateway IP or interface name")
    distance: int = 1
    active: bool = True
    static: bool = True
    disabled: bool = False


class FirewallRuleInfo(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="RouterOS .id")
    chain: str = Field(description="Chain: input, forward, output, or custom")
    action: str = Field(description="Action: accept, drop, reject, etc.")
    disabled: bool = False
    comment: str | None = None
    in_interface: str | None = None
    out_interface: str | None = None
    src_address: str | None = None
    dst_address: str | None = None
    protocol: str | None = None
    dst_port: str | None = None
    connection_state: str | None = None


class DhcpServerInfo(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="RouterOS .id")
    name: str = Field(description="DHCP server name")
    interface: str = Field(description="Bound interface")
    address_pool: str | None = None
    lease_time: str | None = None
    disabled: bool = False


class DhcpLeaseInfo(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="RouterOS .id")
    address: str = Field(description="Leased IP address")
    mac_address: str | None = None
    server: str = Field(description="DHCP server name")
    status: str = Field(default="bound")
    host_name: str | None = None


class HotspotServerInfo(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="RouterOS .id")
    name: str = Field(description="Hotspot server name")
    interface: str = Field(description="Bound interface")
    profile: str | None = None
    address_pool: str | None = None
    disabled: bool = False


class HotspotUserInfo(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="RouterOS .id")
    name: str = Field(description="Hotspot user name")
    profile: str | None = None
    disabled: bool = False


class RouterContext(BaseModel):

    model_config = ConfigDict(frozen=True)

    identity: str = Field(description="Router hostname/identity")
    system_resource: SystemResource
    capabilities: RouterCapabilities
    interfaces: list[InterfaceInfo] = Field(default_factory=list)
    addresses: list[IPAddressInfo] = Field(default_factory=list)
    routes: list[RouteInfo] = Field(default_factory=list)
    firewall_rules: list[FirewallRuleInfo] = Field(default_factory=list)
    dhcp_servers: list[DhcpServerInfo] = Field(default_factory=list)
    dhcp_leases: list[DhcpLeaseInfo] = Field(default_factory=list)
    hotspot_servers: list[HotspotServerInfo] = Field(default_factory=list)
    hotspot_users: list[HotspotUserInfo] = Field(default_factory=list)

    @property
    def routeros_version(self) -> str:
        return self.system_resource.version

    @property
    def major_version(self) -> int:
        return self.capabilities.major_version

    @property
    def board_name(self) -> str:
        return self.system_resource.board_name

    @property
    def architecture(self) -> str:
        return self.system_resource.architecture_name

    @property
    def interface_names(self) -> list[str]:
        return [iface.name for iface in self.interfaces]

    def get_interface(self, name: str) -> InterfaceInfo | None:
        for iface in self.interfaces:
            if iface.name == name:
                return iface
        return None

    def is_interface_available(self, name: str) -> bool:
        iface = self.get_interface(name)
        if iface is None:
            return False
        return not iface.disabled

    def get_addresses_on_interface(self, name: str) -> list[IPAddressInfo]:
        return [addr for addr in self.addresses if addr.interface == name and not addr.disabled]

    def has_dhcp_on_interface(self, name: str) -> bool:
        return any(srv.interface == name and not srv.disabled for srv in self.dhcp_servers)

    def has_hotspot_on_interface(self, name: str) -> bool:
        return any(srv.interface == name and not srv.disabled for srv in self.hotspot_servers)

    def find_conflicting_subnets(self, network_str: str) -> list[str]:
        try:
            target_net = ipaddress.ip_network(network_str.strip(), strict=False)
        except ValueError:
            return []

        conflicts: list[str] = []
        for addr in self.addresses:
            if addr.disabled:
                continue
            try:
                existing_net = ipaddress.ip_network(addr.address.strip(), strict=False)
                if target_net.overlaps(existing_net):
                    conflicts.append(addr.address)
            except ValueError:
                continue
        return conflicts

    def to_ai_context(
        self,
        *,
        safety_constraints: list[str] | None = None,
        relevant_knowledge: list | None = None,
    ) -> AIContext:
        return AIContext(
            router_identity=self.identity,
            routeros_version=self.routeros_version,
            interfaces=self.interface_names,
            relevant_knowledge=relevant_knowledge or [],
            safety_constraints=safety_constraints or [],
            extra={
                "board_name": self.board_name,
                "architecture": self.architecture,
                "major_version": self.major_version,
            },
        )


async def discover(client: RouterClient) -> RouterContext:
    (
        raw_sys,
        raw_ifaces,
        raw_addrs,
        raw_routes,
        raw_fw,
        raw_dhcp,
        raw_leases,
        raw_hotspot,
        raw_hs_users,
    ) = await asyncio.gather(
        client.get_system_resource(),
        client.get_interfaces(),
        client.get_addresses(),
        client.get_routes(),
        client.get_firewall_rules(),
        client.get_dhcp_servers(),
        client.get_dhcp_leases(),
        client.get_hotspot_servers(),
        client.get_hotspot_users(),
    )

    sys_resource = SystemResource(
        version=str(raw_sys.get("version", "unknown")),
        board_name=str(raw_sys.get("board-name", raw_sys.get("platform", "unknown"))),
        architecture_name=str(raw_sys.get("architecture-name", "unknown")),
        cpu=raw_sys.get("cpu"),
        cpu_count=_parse_int(raw_sys.get("cpu-count"), default=1) or 1,
        cpu_frequency=_parse_int(raw_sys.get("cpu-frequency")),
        cpu_load=_parse_int(raw_sys.get("cpu-load")),
        free_memory=_parse_int(raw_sys.get("free-memory"), default=0) or 0,
        total_memory=_parse_int(raw_sys.get("total-memory"), default=0) or 0,
        free_hdd_space=_parse_int(raw_sys.get("free-hdd-space")),
        total_hdd_space=_parse_int(raw_sys.get("total-hdd-space")),
        uptime=str(raw_sys.get("uptime", "0s")),
        platform=raw_sys.get("platform"),
    )

    capabilities = detect_capabilities(raw_sys, raw_ifaces)

    interfaces: list[InterfaceInfo] = []
    for item in raw_ifaces:
        interfaces.append(
            InterfaceInfo(
                id=str(item.get(".id", "")),
                name=str(item.get("name", "")),
                type=str(item.get("type", "ether")),
                running=_parse_bool(item.get("running"), default=True),
                disabled=_parse_bool(item.get("disabled"), default=False),
                comment=item.get("comment"),
                mac_address=item.get("mac-address"),
                mtu=_parse_int(item.get("mtu"), default=1500),
            )
        )

    addresses: list[IPAddressInfo] = []
    for item in raw_addrs:
        addresses.append(
            IPAddressInfo(
                id=str(item.get(".id", "")),
                address=str(item.get("address", "")),
                network=str(item.get("network", "")),
                interface=str(item.get("interface", "")),
                disabled=_parse_bool(item.get("disabled"), default=False),
                comment=item.get("comment"),
            )
        )

    routes: list[RouteInfo] = []
    for item in raw_routes:
        routes.append(
            RouteInfo(
                id=str(item.get(".id", "")),
                dst_address=str(item.get("dst-address", "0.0.0.0/0")),
                gateway=str(item.get("gateway", "")),
                distance=_parse_int(item.get("distance"), default=1) or 1,
                active=_parse_bool(item.get("active"), default=True),
                static=_parse_bool(item.get("static"), default=True),
                disabled=_parse_bool(item.get("disabled"), default=False),
            )
        )

    firewall_rules: list[FirewallRuleInfo] = []
    for item in raw_fw:
        firewall_rules.append(
            FirewallRuleInfo(
                id=str(item.get(".id", "")),
                chain=str(item.get("chain", "forward")),
                action=str(item.get("action", "accept")),
                disabled=_parse_bool(item.get("disabled"), default=False),
                comment=item.get("comment"),
                in_interface=item.get("in-interface"),
                out_interface=item.get("out-interface"),
                src_address=item.get("src-address"),
                dst_address=item.get("dst-address"),
                protocol=item.get("protocol"),
                dst_port=item.get("dst-port"),
                connection_state=item.get("connection-state"),
            )
        )

    dhcp_servers: list[DhcpServerInfo] = []
    for item in raw_dhcp:
        dhcp_servers.append(
            DhcpServerInfo(
                id=str(item.get(".id", "")),
                name=str(item.get("name", "")),
                interface=str(item.get("interface", "")),
                address_pool=item.get("address-pool"),
                lease_time=item.get("lease-time"),
                disabled=_parse_bool(item.get("disabled"), default=False),
            )
        )

    dhcp_leases: list[DhcpLeaseInfo] = []
    for item in raw_leases:
        dhcp_leases.append(
            DhcpLeaseInfo(
                id=str(item.get(".id", "")),
                address=str(item.get("address", "")),
                mac_address=item.get("mac-address"),
                server=str(item.get("server", "")),
                status=str(item.get("status", "bound")),
                host_name=item.get("host-name"),
            )
        )

    hotspot_servers: list[HotspotServerInfo] = []
    for item in raw_hotspot:
        hotspot_servers.append(
            HotspotServerInfo(
                id=str(item.get(".id", "")),
                name=str(item.get("name", "")),
                interface=str(item.get("interface", "")),
                profile=item.get("profile"),
                address_pool=item.get("address-pool"),
                disabled=_parse_bool(item.get("disabled"), default=False),
            )
        )

    hotspot_users: list[HotspotUserInfo] = []
    for item in raw_hs_users:
        hotspot_users.append(
            HotspotUserInfo(
                id=str(item.get(".id", "")),
                name=str(item.get("name", "")),
                profile=item.get("profile"),
                disabled=_parse_bool(item.get("disabled"), default=False),
            )
        )

    identity = str(raw_sys.get("identity") or sys_resource.board_name or "MikroTik")

    return RouterContext(
        identity=identity,
        system_resource=sys_resource,
        capabilities=capabilities,
        interfaces=interfaces,
        addresses=addresses,
        routes=routes,
        firewall_rules=firewall_rules,
        dhcp_servers=dhcp_servers,
        dhcp_leases=dhcp_leases,
        hotspot_servers=hotspot_servers,
        hotspot_users=hotspot_users,
    )
