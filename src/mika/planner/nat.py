"""
Firewall NAT Rule Planner.

Generates a single-step plan to append a rule to /ip/firewall/nat.
"""

from __future__ import annotations

from mika.ai.schemas.configuration_intents import CreateNatRuleIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName, NatAction
from mika.planner.errors import DuplicateRuleError, InterfaceNotFoundError
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.router.discovery import RouterContext


def plan_create_nat_rule(intent: CreateNatRuleIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.CREATE_NAT_RULE:
        raise ValueError(f"plan_create_nat_rule given non-matching intent: {intent.intent!r}")

    for name in (intent.in_interface, intent.out_interface):
        if name is not None and router_context.get_interface(name) is None:
            raise InterfaceNotFoundError(
                f"Interface '{name}' was not found on router "
                f"'{router_context.identity}'. Known interfaces: "
                f"{', '.join(router_context.interface_names) or '(none)'}."
            )

    if intent.action in (NatAction.DST_NAT, NatAction.SRC_NAT, NatAction.NETMAP) and (
        intent.to_addresses is None
    ):
        raise ValueError(
            f"NAT action '{intent.action.value}' requires to_addresses to be set."
        )

    match_fields: dict[str, str | None] = {
        "src_address": str(intent.src_address) if intent.src_address else None,
        "dst_address": str(intent.dst_address) if intent.dst_address else None,
        "in_interface": intent.in_interface,
        "out_interface": intent.out_interface,
        "to_addresses": str(intent.to_addresses) if intent.to_addresses else None,
    }
    duplicate = router_context.find_duplicate_nat_rule(
        chain=intent.chain.value, action=intent.action.value, **match_fields
    )
    if duplicate is not None:
        raise DuplicateRuleError(
            f"An equivalent enabled NAT rule already exists "
            f"(chain={intent.chain.value}, action={intent.action.value}, "
            f"id={duplicate.id}). Refusing to plan a duplicate (CLAUDE.md "
            "Section 26: prefer ensure_* semantics)."
        )

    data: dict[str, str] = {"chain": intent.chain.value, "action": intent.action.value}
    if intent.src_address is not None:
        data["src-address"] = str(intent.src_address)
    if intent.dst_address is not None:
        data["dst-address"] = str(intent.dst_address)
    if intent.out_interface is not None:
        data["out-interface"] = intent.out_interface
    if intent.in_interface is not None:
        data["in-interface"] = intent.in_interface
    if intent.to_addresses is not None:
        data["to-addresses"] = str(intent.to_addresses)
    data["comment"] = intent.comment or "created by mika: create_nat_rule"

    step = PlanStep(
        step_id="create_nat_rule",
        description=f"Add {intent.chain.value} rule: {intent.action.value}",
        operation=OperationType.CREATE,
        resource="/ip/firewall/nat",
        data=data,
    )

    affected_interfaces = tuple(
        sorted({i for i in (intent.in_interface, intent.out_interface) if i is not None})
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.CREATE_NAT_RULE],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=affected_interfaces,
        steps=(step,),
    )
