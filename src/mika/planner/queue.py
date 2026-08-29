"""
Simple Queue Planner.

Generates a single-step plan to create a /queue/simple entry, rate-limiting
traffic to/from an address, subnet, or interface.
"""

from __future__ import annotations

import ipaddress

from mika.ai.schemas.configuration_intents import CreateQueueIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.errors import InterfaceNotFoundError, QueueAlreadyExistsError
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.router.discovery import RouterContext


def plan_create_queue(intent: CreateQueueIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.CREATE_QUEUE:
        raise ValueError(f"plan_create_queue given non-matching intent: {intent.intent!r}")

    if router_context.has_queue_named(intent.name):
        raise QueueAlreadyExistsError(
            f"A queue named '{intent.name}' already exists. Refusing to plan a "
            "duplicate (CLAUDE.md Section 26: prefer ensure_* semantics)."
        )

    target_str = str(intent.target)
    affected_interfaces: tuple[str, ...] = ()
    if isinstance(intent.target, (ipaddress.IPv4Network, ipaddress.IPv4Address)):
        pass  # subnet/address target, no specific interface to check
    else:
        # Bare interface name -- must exist on the router.
        if router_context.get_interface(target_str) is None:
            raise InterfaceNotFoundError(
                f"Interface '{target_str}' was not found on router "
                f"'{router_context.identity}'. Known interfaces: "
                f"{', '.join(router_context.interface_names) or '(none)'}."
            )
        affected_interfaces = (target_str,)

    step = PlanStep(
        step_id="create_queue",
        description=f"Create queue '{intent.name}' limiting {target_str} to {intent.max_limit}",
        operation=OperationType.CREATE,
        resource="/queue/simple",
        data={
            "name": intent.name,
            "target": target_str,
            "max-limit": intent.max_limit,
            "comment": "created by mika: create_queue",
        },
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.CREATE_QUEUE],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=affected_interfaces,
        steps=(step,),
    )
