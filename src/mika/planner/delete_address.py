from __future__ import annotations

from mika.ai.schemas.destructive_intents import DeleteAddressIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.planner.resolve import resolve_resource
from mika.router.discovery import RouterContext


def plan_delete_address(intent: DeleteAddressIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.DELETE_ADDRESS:
        raise ValueError(f"plan_delete_address given non-matching intent: {intent.intent!r}")

    current = resolve_resource(
        router_context.addresses, intent.resource_id, resource_kind="IP address"
    )

    step = PlanStep(
        step_id="delete_address",
        description=f"Delete address {current.address} on {current.interface}",
        operation=OperationType.DELETE,
        resource="/ip/address",
        resource_id=current.id,
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.DELETE_ADDRESS],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=(current.interface,),
        # No affected_networks: this network isn't a new one being
        # introduced, it's being removed -- populating it here would
        # make the validator's overlap check flag it against itself
        # (the address hasn't been deleted yet in this snapshot).
        steps=(step,),
    )
