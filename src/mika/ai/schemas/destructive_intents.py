from __future__ import annotations

from typing import Literal

from pydantic import Field

from mika.ai.schemas.base import IntentBase
from mika.ai.schemas.enums import IntentName
from mika.ai.schemas.types import ResourceId


class _DeleteIntentBase(IntentBase):
    resource_id: ResourceId
    expected_description: str = Field(
        min_length=1,
        max_length=255,
        description="What the LLM believes this resource is (e.g. 'hotspot server hotspot-lab'). "
        "Shown in the destructive confirmation prompt; not itself a source of truth.",
    )


class DeleteAddressIntent(_DeleteIntentBase):
    intent: Literal[IntentName.DELETE_ADDRESS] = IntentName.DELETE_ADDRESS


class DeleteVlanIntent(_DeleteIntentBase):
    intent: Literal[IntentName.DELETE_VLAN] = IntentName.DELETE_VLAN


class DeleteFirewallRuleIntent(_DeleteIntentBase):
    intent: Literal[IntentName.DELETE_FIREWALL_RULE] = IntentName.DELETE_FIREWALL_RULE


class DeleteDhcpIntent(_DeleteIntentBase):
    intent: Literal[IntentName.DELETE_DHCP] = IntentName.DELETE_DHCP


class DeleteHotspotIntent(_DeleteIntentBase):
    intent: Literal[IntentName.DELETE_HOTSPOT] = IntentName.DELETE_HOTSPOT


class DeleteQueueIntent(_DeleteIntentBase):
    intent: Literal[IntentName.DELETE_QUEUE] = IntentName.DELETE_QUEUE


DESTRUCTIVE_INTENTS = (
    DeleteAddressIntent,
    DeleteVlanIntent,
    DeleteFirewallRuleIntent,
    DeleteDhcpIntent,
    DeleteHotspotIntent,
    DeleteQueueIntent,
)
