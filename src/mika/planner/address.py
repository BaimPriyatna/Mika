"""
IP Address Planner.

Generates a single-step plan to assign an IPv4 address to an interface.
"""

from __future__ import annotations

from mika.ai.schemas.configuration_intents import CreateAddressIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.errors import (
    AddressAlreadyExistsError,
    InterfaceNotFoundError,
    InterfaceUnavailableError,
    SubnetConflictError,
)
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.router.discovery import RouterContext


def plan_create_address(intent: CreateAddressIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.CREATE_ADDRESS:
        raise ValueError(f"plan_create_address given non-matching intent: {intent.intent!r}")

    iface = router_context.get_interface(intent.interface)
    if iface is None:
        raise InterfaceNotFoundError(
            f"Interface '{intent.interface}' was not found on router "
            f"'{router_context.identity}'. Known interfaces: "
            f"{', '.join(router_context.interface_names) or '(none)'}."
        )

    if iface.disabled:
        raise InterfaceUnavailableError(
            f"Interface '{intent.interface}' exists but is disabled. Enable it "
            "before assigning an address to it (this planner does not enable "
            "interfaces implicitly -- CLAUDE.md Section 25)."
        )

    address_str = str(intent.address)
    network_str = str(intent.address.network)

    for addr in router_context.addresses:
        if addr.address == address_str and not addr.disabled:
            raise AddressAlreadyExistsError(
                f"Address {address_str} is already assigned to interface "
                f"'{addr.interface}'. Refusing to plan a duplicate (CLAUDE.md "
                "Section 26: prefer ensure_* semantics)."
            )

    conflicts = [
        c
        for c in router_context.find_conflicting_subnets(network_str)
        if c != address_str
    ]
    if conflicts:
        raise SubnetConflictError(
            f"Requested network {network_str} overlaps existing configured "
            f"address(es): {', '.join(conflicts)}.",
            conflicting_addresses=conflicts,
        )

    data = {"address": address_str, "interface": intent.interface}
    if intent.comment:
        data["comment"] = intent.comment
    else:
        data["comment"] = "created by mika: create_address"

    step = PlanStep(
        step_id="create_address",
        description=f"Assign address {address_str} to {intent.interface}",
        operation=OperationType.CREATE,
        resource="/ip/address",
        data=data,
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.CREATE_ADDRESS],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=(intent.interface,),
        affected_networks=(network_str,),
        steps=(step,),
    )
