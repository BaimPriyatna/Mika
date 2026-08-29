"""
Hotspot Server Delete Planner.

Only deletes the /ip/hotspot resource itself. The associated user
profile and IP pool created alongside it (see planner/hotspot.py) are
not discovered by RouterContext yet and are left in place -- flagged
clearly in the plan step description.
"""

from __future__ import annotations

from mika.ai.schemas.destructive_intents import DeleteHotspotIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.planner.resolve import resolve_resource
from mika.router.discovery import RouterContext


def plan_delete_hotspot(intent: DeleteHotspotIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.DELETE_HOTSPOT:
        raise ValueError(f"plan_delete_hotspot given non-matching intent: {intent.intent!r}")

    current = resolve_resource(
        router_context.hotspot_servers, intent.resource_id, resource_kind="hotspot server"
    )

    step = PlanStep(
        step_id="delete_hotspot",
        description=(
            f"Delete hotspot server '{current.name}' on {current.interface} "
            "(its user profile and IP pool are not removed automatically)"
        ),
        operation=OperationType.DELETE,
        resource="/ip/hotspot",
        resource_id=current.id,
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.DELETE_HOTSPOT],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=(current.interface,),
        steps=(step,),
    )
