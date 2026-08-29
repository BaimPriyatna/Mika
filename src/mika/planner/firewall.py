"""
Firewall Filter Rule Planner.

Generates a single-step plan to append a rule to /ip/firewall/filter.
"""

from __future__ import annotations

from mika.ai.schemas.configuration_intents import CreateFirewallRuleIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.errors import DuplicateRuleError, InterfaceNotFoundError
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.router.discovery import RouterContext


def plan_create_firewall_rule(
    intent: CreateFirewallRuleIntent, router_context: RouterContext
) -> Plan:
    if intent.intent != IntentName.CREATE_FIREWALL_RULE:
        raise ValueError(
            f"plan_create_firewall_rule given non-matching intent: {intent.intent!r}"
        )

    for name in (intent.in_interface, intent.out_interface):
        if name is not None and router_context.get_interface(name) is None:
            raise InterfaceNotFoundError(
                f"Interface '{name}' was not found on router "
                f"'{router_context.identity}'. Known interfaces: "
                f"{', '.join(router_context.interface_names) or '(none)'}."
            )

    match_fields: dict[str, str | None] = {
        "protocol": intent.protocol.value if intent.protocol else None,
        "src_address": str(intent.src_address) if intent.src_address else None,
        "dst_address": str(intent.dst_address) if intent.dst_address else None,
        "dst_port": str(intent.dst_port) if intent.dst_port else None,
        "in_interface": intent.in_interface,
        "out_interface": intent.out_interface,
    }
    duplicate = router_context.find_duplicate_firewall_rule(
        chain=intent.chain.value, action=intent.action.value, **match_fields
    )
    if duplicate is not None:
        raise DuplicateRuleError(
            f"An equivalent enabled firewall rule already exists "
            f"(chain={intent.chain.value}, action={intent.action.value}, "
            f"id={duplicate.id}). Refusing to plan a duplicate (CLAUDE.md "
            "Section 26: prefer ensure_* semantics)."
        )

    data: dict[str, str] = {"chain": intent.chain.value, "action": intent.action.value}
    if intent.protocol is not None:
        data["protocol"] = intent.protocol.value
    if intent.src_address is not None:
        data["src-address"] = str(intent.src_address)
    if intent.dst_address is not None:
        data["dst-address"] = str(intent.dst_address)
    if intent.src_port is not None:
        data["src-port"] = str(intent.src_port)
    if intent.dst_port is not None:
        data["dst-port"] = str(intent.dst_port)
    if intent.in_interface is not None:
        data["in-interface"] = intent.in_interface
    if intent.out_interface is not None:
        data["out-interface"] = intent.out_interface
    data["comment"] = intent.comment or "created by mika: create_firewall_rule"

    step = PlanStep(
        step_id="create_firewall_rule",
        description=(
            f"Add {intent.chain.value} rule: {intent.action.value}"
            + (f" proto={intent.protocol.value}" if intent.protocol else "")
        ),
        operation=OperationType.CREATE,
        resource="/ip/firewall/filter",
        data=data,
    )

    affected_interfaces = tuple(
        sorted({i for i in (intent.in_interface, intent.out_interface) if i is not None})
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.CREATE_FIREWALL_RULE],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=affected_interfaces,
        steps=(step,),
    )
