from __future__ import annotations

from typing import Literal

from pydantic import Field

from mika.ai.schemas.base import IntentBase
from mika.ai.schemas.enums import IntentName
from mika.ai.schemas.types import InterfaceName


class AdviseIntent(IntentBase):
    intent: Literal[IntentName.ADVISE] = IntentName.ADVISE
    message: str = Field(description="Conversational response, recommendations, or explanation.")
    options: list[str] = Field(default_factory=list, description="Suggested options or next steps.")
    suggested_action: str | None = Field(default=None, description="Optional recommended action or command.")


class TroubleshootIntent(IntentBase):
    intent: Literal[IntentName.TROUBLESHOOT] = IntentName.TROUBLESHOOT
    problem_description: str = Field(description="The user-reported problem or symptom to diagnose.")


class InspectRouterIntent(IntentBase):
    intent: Literal[IntentName.INSPECT_ROUTER] = IntentName.INSPECT_ROUTER


class InspectInterfacesIntent(IntentBase):
    intent: Literal[IntentName.INSPECT_INTERFACES] = IntentName.INSPECT_INTERFACES
    interface: InterfaceName | None = Field(default=None, description="Optional filter.")


class InspectIpAddressesIntent(IntentBase):
    intent: Literal[IntentName.INSPECT_IP_ADDRESSES] = IntentName.INSPECT_IP_ADDRESSES
    interface: InterfaceName | None = Field(default=None, description="Optional filter.")


class InspectRoutesIntent(IntentBase):
    intent: Literal[IntentName.INSPECT_ROUTES] = IntentName.INSPECT_ROUTES


class InspectFirewallIntent(IntentBase):
    intent: Literal[IntentName.INSPECT_FIREWALL] = IntentName.INSPECT_FIREWALL
    interface: InterfaceName | None = Field(default=None, description="Optional filter.")


class InspectNatIntent(IntentBase):
    intent: Literal[IntentName.INSPECT_NAT] = IntentName.INSPECT_NAT


class InspectDhcpIntent(IntentBase):
    intent: Literal[IntentName.INSPECT_DHCP] = IntentName.INSPECT_DHCP
    interface: InterfaceName | None = Field(default=None, description="Optional filter.")


class InspectHotspotIntent(IntentBase):
    intent: Literal[IntentName.INSPECT_HOTSPOT] = IntentName.INSPECT_HOTSPOT
    interface: InterfaceName | None = Field(default=None, description="Optional filter.")


READ_INTENTS = (
    AdviseIntent,
    TroubleshootIntent,
    InspectRouterIntent,
    InspectInterfacesIntent,
    InspectIpAddressesIntent,
    InspectRoutesIntent,
    InspectFirewallIntent,
    InspectNatIntent,
    InspectDhcpIntent,
    InspectHotspotIntent,
)
