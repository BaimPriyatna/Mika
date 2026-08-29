"""
VLAN Interface Planner.

Generates a single-step plan to create a standalone /interface/vlan
sub-interface on a parent interface (see knowledge topic 'vlan').
"""

from __future__ import annotations

from mika.ai.schemas.configuration_intents import CreateVlanIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.errors import InterfaceNotFoundError, VlanAlreadyExistsError
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.router.discovery import RouterContext


def plan_create_vlan(intent: CreateVlanIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.CREATE_VLAN:
        raise ValueError(f"plan_create_vlan given non-matching intent: {intent.intent!r}")

    parent = router_context.get_interface(intent.parent_interface)
    if parent is None:
        raise InterfaceNotFoundError(
            f"Parent interface '{intent.parent_interface}' was not found on "
            f"router '{router_context.identity}'. Known interfaces: "
            f"{', '.join(router_context.interface_names) or '(none)'}."
        )

    name = intent.name or f"vlan{intent.vlan_id}"

    if router_context.get_interface(name) is not None:
        raise VlanAlreadyExistsError(
            f"An interface named '{name}' already exists. Refusing to plan a "
            "duplicate (CLAUDE.md Section 26: prefer ensure_* semantics)."
        )

    for iface in router_context.interfaces:
        if (
            iface.type == "vlan"
            and not iface.disabled
            and iface.vlan_id == intent.vlan_id
            and iface.vlan_parent == intent.parent_interface
        ):
            raise VlanAlreadyExistsError(
                f"VLAN id {intent.vlan_id} already exists on parent "
                f"'{intent.parent_interface}' as interface '{iface.name}'. "
                "Refusing to plan a duplicate (CLAUDE.md Section 26: prefer "
                "ensure_* semantics)."
            )

    step = PlanStep(
        step_id="create_vlan",
        description=(
            f"Create VLAN interface '{name}' (id {intent.vlan_id}) on "
            f"{intent.parent_interface}"
        ),
        operation=OperationType.CREATE,
        resource="/interface/vlan",
        data={
            "name": name,
            "vlan-id": str(intent.vlan_id),
            "interface": intent.parent_interface,
            "comment": "created by mika: create_vlan",
        },
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.CREATE_VLAN],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=(intent.parent_interface,),
        steps=(step,),
    )
