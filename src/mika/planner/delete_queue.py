from __future__ import annotations

from mika.ai.schemas.destructive_intents import DeleteQueueIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.planner.resolve import resolve_resource
from mika.router.discovery import RouterContext


def plan_delete_queue(intent: DeleteQueueIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.DELETE_QUEUE:
        raise ValueError(f"plan_delete_queue given non-matching intent: {intent.intent!r}")

    current = resolve_resource(router_context.queues, intent.resource_id, resource_kind="queue")

    step = PlanStep(
        step_id="delete_queue",
        description=f"Delete queue '{current.name}' (target {current.target})",
        operation=OperationType.DELETE,
        resource="/queue/simple",
        resource_id=current.id,
    )

    affected_interfaces: tuple[str, ...] = ()
    if router_context.get_interface(current.target) is not None:
        affected_interfaces = (current.target,)

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.DELETE_QUEUE],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=affected_interfaces,
        steps=(step,),
    )
