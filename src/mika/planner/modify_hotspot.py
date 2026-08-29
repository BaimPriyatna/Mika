"""
Hotspot Server Modify Planner.

Only disabled maps directly onto the tracked /ip/hotspot resource.
rate_limit actually lives on the linked /ip/hotspot/user/profile
resource, which RouterContext does not discover yet -- rather than guess
at an unresolved id, this planner refuses that field with a clear
explanation (CLAUDE.md Section 27/25: no guessing).
"""

from __future__ import annotations

from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.ai.schemas.modification_intents import ModifyHotspotIntent
from mika.planner.errors import UnsupportedModificationError
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.planner.resolve import resolve_resource
from mika.router.discovery import RouterContext


def plan_modify_hotspot(intent: ModifyHotspotIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.MODIFY_HOTSPOT:
        raise ValueError(f"plan_modify_hotspot given non-matching intent: {intent.intent!r}")

    if intent.rate_limit is not None:
        raise UnsupportedModificationError(
            "Changing rate_limit is not yet supported -- it lives on the "
            "linked /ip/hotspot/user/profile resource, which this planner "
            "does not discover or resolve an id for. Only disabled can be "
            "modified on a hotspot server right now."
        )

    current = resolve_resource(
        router_context.hotspot_servers, intent.resource_id, resource_kind="hotspot server"
    )

    data: dict[str, str] = {}
    if intent.disabled is not None:
        data["disabled"] = "yes" if intent.disabled else "no"

    step = PlanStep(
        step_id="modify_hotspot",
        description=f"Update hotspot server '{current.name}' on {current.interface}",
        operation=OperationType.UPDATE,
        resource="/ip/hotspot",
        data=data,
        resource_id=current.id,
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.MODIFY_HOTSPOT],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=(current.interface,),
        steps=(step,),
    )
