"""
Validator Rule Registry.

Central registry associating specific Intent types with their respective
validation logic and capability constraints.
"""

from __future__ import annotations

from mika.ai.schemas.enums import IntentName

KNOWN_RESOURCE_FIELDS: dict[str, frozenset[str]] = {
    "/ip/address": frozenset({"address", "interface", "comment", "disabled"}),
    "/ip/pool": frozenset({"name", "ranges", "comment"}),
    "/ip/dhcp-server/network": frozenset(
        {"address", "gateway", "dns-server", "domain", "comment"}
    ),
    "/ip/dhcp-server": frozenset(
        {"name", "interface", "address-pool", "lease-time", "disabled", "comment"}
    ),
    "/ip/hotspot/user/profile": frozenset(
        {"name", "rate-limit", "shared-users", "comment"}
    ),
    "/ip/hotspot/profile": frozenset(
        {"name", "hotspot-address", "dns-name", "html-directory", "comment"}
    ),
    "/ip/hotspot": frozenset(
        {"name", "interface", "address-pool", "profile", "disabled", "comment"}
    ),
    "/ip/firewall/filter": frozenset(
        {
            "chain",
            "action",
            "protocol",
            "src-address",
            "dst-address",
            "src-port",
            "dst-port",
            "in-interface",
            "out-interface",
            "comment",
            "disabled",
        }
    ),
    "/ip/firewall/nat": frozenset(
        {
            "chain",
            "action",
            "src-address",
            "dst-address",
            "out-interface",
            "in-interface",
            "to-addresses",
            "comment",
            "disabled",
        }
    ),
    "/queue/simple": frozenset({"name", "target", "max-limit", "comment", "disabled"}),
    "/interface/vlan": frozenset({"name", "vlan-id", "interface", "comment", "disabled"}),
}

REFERENCE_FIELDS: frozenset[str] = frozenset({"address-pool", "profile"})

INTENT_KNOWLEDGE_TOPICS: dict[IntentName, tuple[str, ...]] = {
    IntentName.CREATE_HOTSPOT: ("hotspot", "dhcp"),
    IntentName.CREATE_ADDRESS: ("subnetting",),
    IntentName.CREATE_DHCP: ("dhcp",),
    IntentName.CREATE_FIREWALL_RULE: ("firewall",),
    IntentName.CREATE_NAT_RULE: ("nat",),
    IntentName.CREATE_QUEUE: ("queue",),
    IntentName.CREATE_VLAN: ("vlan",),
    IntentName.MODIFY_ADDRESS: ("subnetting",),
    IntentName.MODIFY_FIREWALL_RULE: ("firewall",),
    IntentName.MODIFY_DHCP: ("dhcp",),
    IntentName.MODIFY_HOTSPOT: ("hotspot",),
    IntentName.MODIFY_QUEUE: ("queue",),
    IntentName.DELETE_ADDRESS: ("subnetting",),
    IntentName.DELETE_VLAN: ("vlan",),
    IntentName.DELETE_FIREWALL_RULE: ("firewall",),
    IntentName.DELETE_DHCP: ("dhcp",),
    IntentName.DELETE_HOTSPOT: ("hotspot",),
    IntentName.DELETE_QUEUE: ("queue",),
}
