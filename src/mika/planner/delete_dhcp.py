"""
DHCP Server Delete Planner.

Only deletes the /ip/dhcp-server resource itself. The associated
/ip/pool and /ip/dhcp-server/network entries created alongside it (see
planner/dhcp.py) are not discovered by RouterContext yet and are left in
place -- flagged clearly in the plan step description rather than
silently leaving orphaned resources unmentioned.
"""

from __future__ import annotations

from mika.ai.schemas.destructive_intents import DeleteDhcpIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.planner.resolve import resolve_resource
from mika.router.discovery import RouterContext


def plan_delete_dhcp(intent: DeleteDhcpIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.DELETE_DHCP:
        raise ValueError(f"plan_delete_dhcp given non-matching intent: {intent.intent!r}")

    current = resolve_resource(
        router_context.dhcp_servers, intent.resource_id, resource_kind="DHCP server"
    )

    step = PlanStep(
        step_id="delete_dhcp",
        description=(
            f"Delete DHCP server '{current.name}' on {current.interface} "
            "(its IP pool and network entry are not removed automatically)"
        ),
        operation=OperationType.DELETE,
        resource="/ip/dhcp-server",
        resource_id=current.id,
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.DELETE_DHCP],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=(current.interface,),
        steps=(step,),
    )
