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
}

REFERENCE_FIELDS: frozenset[str] = frozenset({"address-pool", "profile"})

INTENT_KNOWLEDGE_TOPICS: dict[IntentName, tuple[str, ...]] = {
    IntentName.CREATE_HOTSPOT: ("hotspot", "dhcp"),
}
