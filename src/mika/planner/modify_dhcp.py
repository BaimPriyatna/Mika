"""
DHCP Server Modify Planner.

Only lease_time and disabled map directly onto the tracked /ip/dhcp-server
resource. pool_start/pool_end/gateway actually live on the separate
/ip/dhcp-server/network resource, which RouterContext does not discover
yet -- rather than guess at an unresolved id, this planner refuses those
fields with a clear explanation (CLAUDE.md Section 27/25: no guessing).
"""

from __future__ import annotations

from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.ai.schemas.modification_intents import ModifyDhcpIntent
from mika.planner.errors import UnsupportedModificationError
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.planner.resolve import resolve_resource
from mika.router.discovery import RouterContext


def plan_modify_dhcp(intent: ModifyDhcpIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.MODIFY_DHCP:
        raise ValueError(f"plan_modify_dhcp given non-matching intent: {intent.intent!r}")

    unsupported = [
        name
        for name, value in (
            ("pool_start", intent.pool_start),
            ("pool_end", intent.pool_end),
            ("gateway", intent.gateway),
        )
        if value is not None
    ]
    if unsupported:
        raise UnsupportedModificationError(
            f"Changing {', '.join(unsupported)} is not yet supported -- "
            "these live on the separate /ip/dhcp-server/network resource, "
            "which this planner does not discover or resolve an id for. "
            "Only lease_time and disabled can be modified on a DHCP server "
            "right now."
        )

    current = resolve_resource(
        router_context.dhcp_servers, intent.resource_id, resource_kind="DHCP server"
    )

    data: dict[str, str] = {}
    if intent.lease_time is not None:
        data["lease-time"] = intent.lease_time
    if intent.disabled is not None:
        data["disabled"] = "yes" if intent.disabled else "no"

    step = PlanStep(
        step_id="modify_dhcp",
        description=f"Update DHCP server '{current.name}' on {current.interface}",
        operation=OperationType.UPDATE,
        resource="/ip/dhcp-server",
        data=data,
        resource_id=current.id,
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.MODIFY_DHCP],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=(current.interface,),
        steps=(step,),
    )
