from __future__ import annotations

from mika.ai.schemas.destructive_intents import DeleteVlanIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.errors import ResourceNotFoundError
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.router.discovery import RouterContext


def plan_delete_vlan(intent: DeleteVlanIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.DELETE_VLAN:
        raise ValueError(f"plan_delete_vlan given non-matching intent: {intent.intent!r}")

    current = next(
        (
            iface
            for iface in router_context.interfaces
            if iface.type == "vlan" and iface.id == intent.resource_id
        ),
        None,
    )
    if current is None:
        raise ResourceNotFoundError(
            f"No VLAN interface with id '{intent.resource_id}' exists on the "
            "router right now. It may have been deleted, or RouterOS may have "
            "reused this id for a different object since it was last seen -- "
            "re-inspect the router to get a current id before retrying "
            "(CLAUDE.md Section 27)."
        )

    step = PlanStep(
        step_id="delete_vlan",
        description=f"Delete VLAN interface '{current.name}' (id {current.vlan_id})",
        operation=OperationType.DELETE,
        resource="/interface/vlan",
        resource_id=current.id,
    )

    affected = (current.vlan_parent,) if current.vlan_parent else ()

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.DELETE_VLAN],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=affected,
        steps=(step,),
    )
