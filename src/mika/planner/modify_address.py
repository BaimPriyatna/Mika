"""
IP Address Modify Planner.
"""

from __future__ import annotations

from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.ai.schemas.modification_intents import ModifyAddressIntent
from mika.planner.errors import SubnetConflictError
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.planner.resolve import resolve_resource
from mika.router.discovery import RouterContext


def plan_modify_address(intent: ModifyAddressIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.MODIFY_ADDRESS:
        raise ValueError(f"plan_modify_address given non-matching intent: {intent.intent!r}")

    current = resolve_resource(
        router_context.addresses, intent.resource_id, resource_kind="IP address"
    )

    data: dict[str, str] = {}
    affected_networks: tuple[str, ...] = ()

    if intent.address is not None:
        new_address_str = str(intent.address)
        new_network_str = str(intent.address.network)
        conflicts = [
            c
            for c in router_context.find_conflicting_subnets(new_network_str)
            if c not in (current.address, new_address_str)
        ]
        if conflicts:
            raise SubnetConflictError(
                f"Requested network {new_network_str} overlaps existing "
                f"configured address(es): {', '.join(conflicts)}.",
                conflicting_addresses=conflicts,
            )
        data["address"] = new_address_str
        affected_networks = (new_network_str,)

    if intent.comment is not None:
        data["comment"] = intent.comment

    step = PlanStep(
        step_id="modify_address",
        description=f"Update address {current.address} on {current.interface}",
        operation=OperationType.UPDATE,
        resource="/ip/address",
        data=data,
        resource_id=current.id,
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.MODIFY_ADDRESS],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=(current.interface,),
        affected_networks=affected_networks,
        steps=(step,),
    )
