from __future__ import annotations

from typing import Literal

from pydantic import Field

from mika.ai.schemas.base import IntentBase
from mika.ai.schemas.enums import FirewallAction, FirewallChain, L4Protocol, NatAction, NatChain, IntentName
from mika.ai.schemas.types import (
    Comment,
    InterfaceName,
    IPv4Address,
    IPv4Interface,
    IPv4Network,
    Port,
    RateLimit,
    ResourceName,
    VlanId,
)


class CreateAddressIntent(IntentBase):
    intent: Literal[IntentName.CREATE_ADDRESS] = IntentName.CREATE_ADDRESS
    interface: InterfaceName
    address: IPv4Interface = Field(description="e.g. 192.168.1.1/24")
    comment: Comment | None = None


class CreateVlanIntent(IntentBase):
    intent: Literal[IntentName.CREATE_VLAN] = IntentName.CREATE_VLAN
    parent_interface: InterfaceName
    vlan_id: VlanId
    name: ResourceName | None = Field(default=None, description="Interface name for the VLAN; auto if omitted.")


class CreateDhcpIntent(IntentBase):
    intent: Literal[IntentName.CREATE_DHCP] = IntentName.CREATE_DHCP
    interface: InterfaceName
    pool_start: IPv4Address
    pool_end: IPv4Address
    gateway: IPv4Address
    dns_servers: list[IPv4Address] = Field(default_factory=list)
    lease_time: str | None = Field(default=None, pattern=r"^\d+[smhdw]?$")


class CreateHotspotIntent(IntentBase):
    intent: Literal[IntentName.CREATE_HOTSPOT] = IntentName.CREATE_HOTSPOT
    interface: InterfaceName
    network: IPv4Network
    rate_limit: RateLimit | None = None
    dns_name: str | None = Field(default=None, max_length=253)


class CreateFirewallRuleIntent(IntentBase):
    intent: Literal[IntentName.CREATE_FIREWALL_RULE] = IntentName.CREATE_FIREWALL_RULE
    chain: FirewallChain
    action: FirewallAction
    protocol: L4Protocol | None = None
    src_address: IPv4Network | None = None
    dst_address: IPv4Network | None = None
    src_port: Port | None = None
    dst_port: Port | None = None
    in_interface: InterfaceName | None = None
    out_interface: InterfaceName | None = None
    comment: Comment | None = None


class CreateNatRuleIntent(IntentBase):
    intent: Literal[IntentName.CREATE_NAT_RULE] = IntentName.CREATE_NAT_RULE
    chain: NatChain
    action: NatAction
    src_address: IPv4Network | None = None
    dst_address: IPv4Network | None = None
    out_interface: InterfaceName | None = None
    in_interface: InterfaceName | None = None
    to_addresses: IPv4Address | None = None
    comment: Comment | None = None


class CreateQueueIntent(IntentBase):
    intent: Literal[IntentName.CREATE_QUEUE] = IntentName.CREATE_QUEUE
    name: ResourceName
    target: IPv4Network | InterfaceName
    max_limit: RateLimit


CONFIGURATION_INTENTS = (
    CreateAddressIntent,
    CreateVlanIntent,
    CreateDhcpIntent,
    CreateHotspotIntent,
    CreateFirewallRuleIntent,
    CreateNatRuleIntent,
    CreateQueueIntent,
)
