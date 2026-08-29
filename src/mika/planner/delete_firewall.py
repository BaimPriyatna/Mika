from __future__ import annotations

from mika.ai.schemas.destructive_intents import DeleteFirewallRuleIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.planner.resolve import resolve_resource
from mika.router.discovery import RouterContext


def plan_delete_firewall_rule(
    intent: DeleteFirewallRuleIntent, router_context: RouterContext
) -> Plan:
    if intent.intent != IntentName.DELETE_FIREWALL_RULE:
        raise ValueError(
            f"plan_delete_firewall_rule given non-matching intent: {intent.intent!r}"
        )

    current = resolve_resource(
        router_context.firewall_rules, intent.resource_id, resource_kind="firewall rule"
    )

    step = PlanStep(
        step_id="delete_firewall_rule",
        description=f"Delete firewall rule {current.id} ({current.chain}/{current.action})",
        operation=OperationType.DELETE,
        resource="/ip/firewall/filter",
        resource_id=current.id,
    )

    affected = tuple(
        sorted({i for i in (current.in_interface, current.out_interface) if i is not None})
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.DELETE_FIREWALL_RULE],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=affected,
        steps=(step,),
    )
