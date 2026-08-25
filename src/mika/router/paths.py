"""
RouterOS Resource Path and Version Mapping.

Provides explicit path mapping and feature matrices for RouterOS v6 and v7,
ensuring consistent command execution across both legacy and modern firmware.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class RouterOSMajor(int, Enum):
    V6 = 6
    V7 = 7


class ResourceMapping(NamedTuple):
    path: str
    supported: bool = True
    notes: str = ""


# Core resource mappings for RouterOS v6
V6_RESOURCE_PATHS: dict[str, ResourceMapping] = {
    "system/resource": ResourceMapping("system/resource"),
    "interface": ResourceMapping("interface"),
    "interface/wireless": ResourceMapping("interface/wireless"),
    "interface/wifi": ResourceMapping("interface/wifi", supported=False, notes="Use /interface/wireless in v6"),
    "interface/wireguard": ResourceMapping("interface/wireguard", supported=False, notes="WireGuard is v7+ only"),
    "ip/address": ResourceMapping("ip/address"),
    "ip/route": ResourceMapping("ip/route"),
    "routing/table": ResourceMapping("routing/table", supported=False, notes="Routing tables syntax is v7+ only"),
    "ip/firewall/filter": ResourceMapping("ip/firewall/filter"),
    "ip/firewall/nat": ResourceMapping("ip/firewall/nat"),
    "ip/dhcp-server": ResourceMapping("ip/dhcp-server"),
    "ip/dhcp-server/lease": ResourceMapping("ip/dhcp-server/lease"),
    "ip/hotspot": ResourceMapping("ip/hotspot"),
    "ip/hotspot/user": ResourceMapping("ip/hotspot/user"),
    "container": ResourceMapping("container", supported=False, notes="Containers are v7+ only"),
}

# Core resource mappings for RouterOS v7
V7_RESOURCE_PATHS: dict[str, ResourceMapping] = {
    "system/resource": ResourceMapping("system/resource"),
    "interface": ResourceMapping("interface"),
    "interface/wireless": ResourceMapping("interface/wireless"),
    "interface/wifi": ResourceMapping("interface/wifi"),
    "interface/wireguard": ResourceMapping("interface/wireguard"),
    "ip/address": ResourceMapping("ip/address"),
    "ip/route": ResourceMapping("ip/route"),
    "routing/table": ResourceMapping("routing/table"),
    "ip/firewall/filter": ResourceMapping("ip/firewall/filter"),
    "ip/firewall/nat": ResourceMapping("ip/firewall/nat"),
    "ip/dhcp-server": ResourceMapping("ip/dhcp-server"),
    "ip/dhcp-server/lease": ResourceMapping("ip/dhcp-server/lease"),
    "ip/hotspot": ResourceMapping("ip/hotspot"),
    "ip/hotspot/user": ResourceMapping("ip/hotspot/user"),
    "container": ResourceMapping("container"),
}


def normalize_resource(resource: str) -> str:
    """Normalize a resource path by stripping slashes."""
    return resource.strip("/")


def get_resource_mapping(resource: str, major_version: int = 7) -> ResourceMapping:
    """
    Resolve a resource path for the specified RouterOS major version.
    Returns ResourceMapping containing the actual path and support status.
    """
    norm = normalize_resource(resource)
    mapping_table = V6_RESOURCE_PATHS if major_version == 6 else V7_RESOURCE_PATHS

    if norm in mapping_table:
        return mapping_table[norm]

    # Fallback to direct path if not explicitly listed in matrix
    return ResourceMapping(path=norm, supported=True)


def is_resource_supported(resource: str, major_version: int = 7) -> bool:
    """Check whether a given resource path is supported in the target version."""
    return get_resource_mapping(resource, major_version).supported
