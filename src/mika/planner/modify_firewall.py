"""
Firewall Filter Rule Modify Planner.
"""

from __future__ import annotations

from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.ai.schemas.modification_intents import ModifyFirewallRuleIntent
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.planner.resolve import resolve_resource
from mika.router.discovery import RouterContext


def plan_modify_firewall_rule(
    intent: ModifyFirewallRuleIntent, router_context: RouterContext
) -> Plan:
    if intent.intent != IntentName.MODIFY_FIREWALL_RULE:
        raise ValueError(
            f"plan_modify_firewall_rule given non-matching intent: {intent.intent!r}"
        )

    current = resolve_resource(
        router_context.firewall_rules, intent.resource_id, resource_kind="firewall rule"
    )

    data: dict[str, str] = {}
    if intent.chain is not None:
        data["chain"] = intent.chain.value
    if intent.action is not None:
        data["action"] = intent.action.value
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
    if intent.disabled is not None:
        data["disabled"] = "yes" if intent.disabled else "no"

    step = PlanStep(
        step_id="modify_firewall_rule",
        description=f"Update firewall rule {current.id} ({current.chain}/{current.action})",
        operation=OperationType.UPDATE,
        resource="/ip/firewall/filter",
        data=data,
        resource_id=current.id,
    )

    affected = tuple(
        sorted({i for i in (current.in_interface, current.out_interface) if i is not None})
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.MODIFY_FIREWALL_RULE],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=affected,
        steps=(step,),
    )
