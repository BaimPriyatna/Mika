from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from mika.ai.schemas.base import IntentBase
from mika.ai.schemas.enums import FirewallAction, FirewallChain, IntentName, L4Protocol
from mika.ai.schemas.types import IPv4Address, IPv4Interface, IPv4Network, Port, RateLimit, ResourceId


def _require_at_least_one_patch_field(model: IntentBase, field_names: tuple[str, ...]) -> IntentBase:
    if not any(getattr(model, name) is not None for name in field_names):
        raise ValueError(
            "A modify intent must change at least one field; an empty patch is not a valid intent."
        )
    return model


class ModifyAddressIntent(IntentBase):
    intent: Literal[IntentName.MODIFY_ADDRESS] = IntentName.MODIFY_ADDRESS
    resource_id: ResourceId
    address: IPv4Interface | None = None
    comment: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _check_patch(self) -> "ModifyAddressIntent":
        return _require_at_least_one_patch_field(self, ("address", "comment"))


class ModifyFirewallRuleIntent(IntentBase):
    intent: Literal[IntentName.MODIFY_FIREWALL_RULE] = IntentName.MODIFY_FIREWALL_RULE
    resource_id: ResourceId
    chain: FirewallChain | None = None
    action: FirewallAction | None = None
    protocol: L4Protocol | None = None
    src_address: IPv4Network | None = None
    dst_address: IPv4Network | None = None
    src_port: Port | None = None
    dst_port: Port | None = None
    disabled: bool | None = None

    @model_validator(mode="after")
    def _check_patch(self) -> "ModifyFirewallRuleIntent":
        return _require_at_least_one_patch_field(
            self, ("chain", "action", "protocol", "src_address", "dst_address", "src_port", "dst_port", "disabled")
        )


class ModifyDhcpIntent(IntentBase):
    intent: Literal[IntentName.MODIFY_DHCP] = IntentName.MODIFY_DHCP
    resource_id: ResourceId
    pool_start: IPv4Address | None = None
    pool_end: IPv4Address | None = None
    gateway: IPv4Address | None = None
    lease_time: str | None = Field(default=None, pattern=r"^\d+[smhdw]?$")
    disabled: bool | None = None

    @model_validator(mode="after")
    def _check_patch(self) -> "ModifyDhcpIntent":
        return _require_at_least_one_patch_field(
            self, ("pool_start", "pool_end", "gateway", "lease_time", "disabled")
        )


class ModifyHotspotIntent(IntentBase):
    intent: Literal[IntentName.MODIFY_HOTSPOT] = IntentName.MODIFY_HOTSPOT
    resource_id: ResourceId
    rate_limit: RateLimit | None = None
    disabled: bool | None = None

    @model_validator(mode="after")
    def _check_patch(self) -> "ModifyHotspotIntent":
        return _require_at_least_one_patch_field(self, ("rate_limit", "disabled"))


class ModifyQueueIntent(IntentBase):
    intent: Literal[IntentName.MODIFY_QUEUE] = IntentName.MODIFY_QUEUE
    resource_id: ResourceId
    max_limit: RateLimit | None = None
    disabled: bool | None = None

    @model_validator(mode="after")
    def _check_patch(self) -> "ModifyQueueIntent":
        return _require_at_least_one_patch_field(self, ("max_limit", "disabled"))


MODIFICATION_INTENTS = (
    ModifyAddressIntent,
    ModifyFirewallRuleIntent,
    ModifyDhcpIntent,
    ModifyHotspotIntent,
    ModifyQueueIntent,
)
