"""
Router Profile Data Model.

Represents a point-in-time snapshot of router configuration and state,
including identity, RouterOS version, interfaces, IP addresses, and firewall rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RouterProfile:

    system_resource: dict
    interfaces: list[dict] = field(default_factory=list)
    addresses: list[dict] = field(default_factory=list)
    routes: list[dict] = field(default_factory=list)
    firewall_rules: list[dict] = field(default_factory=list)
    nat_rules: list[dict] = field(default_factory=list)
    queues: list[dict] = field(default_factory=list)
    dhcp_servers: list[dict] = field(default_factory=list)
    dhcp_leases: list[dict] = field(default_factory=list)
    hotspot_servers: list[dict] = field(default_factory=list)
    hotspot_users: list[dict] = field(default_factory=list)
