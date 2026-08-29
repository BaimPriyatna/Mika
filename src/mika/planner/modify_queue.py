"""
Simple Queue Modify Planner.
"""

from __future__ import annotations

from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.ai.schemas.modification_intents import ModifyQueueIntent
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.planner.resolve import resolve_resource
from mika.router.discovery import RouterContext


def plan_modify_queue(intent: ModifyQueueIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.MODIFY_QUEUE:
        raise ValueError(f"plan_modify_queue given non-matching intent: {intent.intent!r}")

    current = resolve_resource(router_context.queues, intent.resource_id, resource_kind="queue")

    data: dict[str, str] = {}
    if intent.max_limit is not None:
        data["max-limit"] = str(intent.max_limit)
    if intent.disabled is not None:
        data["disabled"] = "yes" if intent.disabled else "no"

    step = PlanStep(
        step_id="modify_queue",
        description=f"Update queue '{current.name}'",
        operation=OperationType.UPDATE,
        resource="/queue/simple",
        data=data,
        resource_id=current.id,
    )

    affected_interfaces: tuple[str, ...] = ()
    if router_context.get_interface(current.target) is not None:
        affected_interfaces = (current.target,)

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.MODIFY_QUEUE],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=affected_interfaces,
        steps=(step,),
    )
