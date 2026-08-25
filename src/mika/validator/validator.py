"""
Configuration Safety & Capability Validator.

Validates planned intents against router capabilities, existing IP pools,
and safety policies before execution to prevent misconfigurations.
"""

from __future__ import annotations

import ipaddress

from mika.ai.schemas.enums import SafetyLevel
from mika.knowledge.retriever import KnowledgeRetriever
from mika.planner.plan import OperationType, Plan, PlanStatus, compute_router_fingerprint
from mika.router.discovery import RouterContext
from mika.validator.registry import (
    INTENT_KNOWLEDGE_TOPICS,
    KNOWN_RESOURCE_FIELDS,
    REFERENCE_FIELDS,
)
from mika.validator.result import IssueSeverity, ValidationIssue, ValidationLayer, ValidationResult

_FAIL = IssueSeverity.FAIL
_WARN = IssueSeverity.WARNING


def validate(
    plan: Plan,
    router_context: RouterContext,
    knowledge_retriever: KnowledgeRetriever,
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    safety_level = plan.safety_level

    issues += _validate_schema(plan)
    issues += _validate_syntax(plan)
    issues += _validate_version_compatibility(plan, router_context, knowledge_retriever)
    issues += _validate_resource_existence(plan, router_context)
    issues += _validate_dependencies(plan)
    issues += _validate_overlap(plan, router_context)
    issues += _validate_conflicts(plan, router_context)

    safety_issues, safety_level = _validate_safety(plan, router_context, safety_level)
    issues += safety_issues

    validated = not any(i.severity == _FAIL for i in issues)
    new_status = PlanStatus.VALIDATED if validated else PlanStatus.VALIDATION_FAILED

    result_plan = plan.model_copy(update={"status": new_status, "safety_level": safety_level})

    return ValidationResult(
        plan_id=plan.plan_id,
        validated=validated,
        issues=tuple(issues),
        plan=result_plan,
    )


def _validate_schema(plan: Plan) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not plan.steps:
        issues.append(
            ValidationIssue(
                layer=ValidationLayer.SCHEMA,
                severity=_FAIL,
                message="Plan has no steps; nothing to validate or apply.",
            )
        )

    for step in plan.steps:
        if step.operation in (OperationType.UPDATE, OperationType.DELETE) and not step.resource_id:
            issues.append(
                ValidationIssue(
                    layer=ValidationLayer.SCHEMA,
                    severity=_FAIL,
                    message=f"Step '{step.step_id}' is {step.operation.value} but has no resource_id.",
                    step_id=step.step_id,
                )
            )

    return issues


def _validate_syntax(plan: Plan) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for step in plan.steps:
        allowed_fields = KNOWN_RESOURCE_FIELDS.get(step.resource)
        if allowed_fields is None:
            issues.append(
                ValidationIssue(
                    layer=ValidationLayer.SYNTAX,
                    severity=_FAIL,
                    message=f"Resource path '{step.resource}' is not a known, verified RouterOS "
                    f"resource (step '{step.step_id}'). Refusing to guess its syntax.",
                    step_id=step.step_id,
                )
            )
            continue

        unknown_fields = set(step.data) - allowed_fields
        for field_name in sorted(unknown_fields):
            issues.append(
                ValidationIssue(
                    layer=ValidationLayer.SYNTAX,
                    severity=_FAIL,
                    message=f"Field '{field_name}' is not a verified property of '{step.resource}' "
                    f"(step '{step.step_id}').",
                    step_id=step.step_id,
                )
            )

    return issues


def _validate_version_compatibility(
    plan: Plan, router_context: RouterContext, knowledge_retriever: KnowledgeRetriever
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    topics = INTENT_KNOWLEDGE_TOPICS.get(plan.intent.intent)

    if topics is None:
        issues.append(
            ValidationIssue(
                layer=ValidationLayer.VERSION_COMPATIBILITY,
                severity=_FAIL,
                message=f"No knowledge-topic mapping is registered for intent "
                f"'{plan.intent.intent.value}'. Compatibility uncertain. Verification "
                "against RouterOS documentation is required.",
            )
        )
        return issues

    for result in knowledge_retriever.retrieve_many(list(topics), routeros_major=router_context.major_version):
        if result.is_empty:
            issues.append(
                ValidationIssue(
                    layer=ValidationLayer.VERSION_COMPATIBILITY,
                    severity=_FAIL,
                    message=f"No knowledge documents exist for topic '{result.topic}' at all. "
                    "Compatibility uncertain. Verification against RouterOS documentation is required.",
                )
            )
        elif result.version_uncertain:
            issues.append(
                ValidationIssue(
                    layer=ValidationLayer.VERSION_COMPATIBILITY,
                    severity=_FAIL,
                    message=f"Knowledge for topic '{result.topic}' exists but not for RouterOS "
                    f"{router_context.major_version}.x. Compatibility uncertain. Verification "
                    "against RouterOS documentation is required.",
                )
            )

    return issues


def _validate_resource_existence(plan: Plan, router_context: RouterContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    current_fingerprint = compute_router_fingerprint(router_context)
    if current_fingerprint != plan.router_state_fingerprint:
        issues.append(
            ValidationIssue(
                layer=ValidationLayer.RESOURCE_EXISTENCE,
                severity=_FAIL,
                message="Router state has changed since this plan was created "
                "(CLAUDE.md Section 30). Re-run discovery and regenerate the plan "
                "before confirming.",
            )
        )

    for interface_name in plan.affected_interfaces:
        iface = router_context.get_interface(interface_name)
        if iface is None:
            issues.append(
                ValidationIssue(
                    layer=ValidationLayer.RESOURCE_EXISTENCE,
                    severity=_FAIL,
                    message=f"Interface '{interface_name}' no longer exists on "
                    f"'{router_context.identity}'.",
                )
            )
        elif iface.disabled:
            issues.append(
                ValidationIssue(
                    layer=ValidationLayer.RESOURCE_EXISTENCE,
                    severity=_FAIL,
                    message=f"Interface '{interface_name}' is now disabled.",
                )
            )

    return issues


def _validate_dependencies(plan: Plan) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    created_names: set[str] = set()

    for step in plan.steps:
        for ref_field in REFERENCE_FIELDS:
            ref_name = step.data.get(ref_field)
            if ref_name is not None and ref_name not in created_names:
                issues.append(
                    ValidationIssue(
                        layer=ValidationLayer.DEPENDENCY,
                        severity=_FAIL,
                        message=f"Step '{step.step_id}' references '{ref_field}={ref_name}', "
                        "which no earlier step in this plan creates.",
                        step_id=step.step_id,
                    )
                )

        if step.operation == OperationType.CREATE and "name" in step.data:
            created_names.add(step.data["name"])

    return issues


def _validate_overlap(plan: Plan, router_context: RouterContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for network in plan.affected_networks:
        conflicts = router_context.find_conflicting_subnets(network)
        if conflicts:
            issues.append(
                ValidationIssue(
                    layer=ValidationLayer.OVERLAP,
                    severity=_FAIL,
                    message=f"Network {network} overlaps existing configured address(es): "
                    f"{', '.join(conflicts)}.",
                )
            )

    return issues


def _validate_conflicts(plan: Plan, router_context: RouterContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    existing_dhcp_names = {d.name for d in router_context.dhcp_servers}
    existing_hotspot_names = {h.name for h in router_context.hotspot_servers}

    for step in plan.steps:
        if step.operation != OperationType.CREATE:
            continue
        name = step.data.get("name")
        if name is None:
            continue
        if step.resource == "/ip/dhcp-server" and name in existing_dhcp_names:
            issues.append(
                ValidationIssue(
                    layer=ValidationLayer.CONFLICT,
                    severity=_FAIL,
                    message=f"A DHCP server named '{name}' already exists.",
                    step_id=step.step_id,
                )
            )
        if step.resource == "/ip/hotspot" and name in existing_hotspot_names:
            issues.append(
                ValidationIssue(
                    layer=ValidationLayer.CONFLICT,
                    severity=_FAIL,
                    message=f"A hotspot server named '{name}' already exists.",
                    step_id=step.step_id,
                )
            )

    return issues


def _find_default_route_interface(router_context: RouterContext) -> str | None:
    for route in router_context.routes:
        if route.disabled or route.dst_address.strip() != "0.0.0.0/0":
            continue

        gateway = route.gateway.strip()
        if gateway in router_context.interface_names:
            return gateway

        try:
            gateway_ip = ipaddress.ip_address(gateway)
        except ValueError:
            continue

        for addr in router_context.addresses:
            ip_iface = addr.ip_interface
            if ip_iface is not None and gateway_ip in ip_iface.network:
                return addr.interface

    return None


def _validate_safety(
    plan: Plan, router_context: RouterContext, safety_level: SafetyLevel
) -> tuple[list[ValidationIssue], SafetyLevel]:
    issues: list[ValidationIssue] = []

    default_route_interface = _find_default_route_interface(router_context)
    if default_route_interface is not None and default_route_interface in plan.affected_interfaces:
        issues.append(
            ValidationIssue(
                layer=ValidationLayer.SAFETY,
                severity=_WARN,
                message=f"Interface '{default_route_interface}' appears to carry the router's "
                "default route. Changes here may affect management/internet connectivity "
                "(CLAUDE.md Section 34).",
            )
        )
        if safety_level not in (SafetyLevel.HIGH_RISK, SafetyLevel.DESTRUCTIVE):
            safety_level = SafetyLevel.HIGH_RISK

    return issues, safety_level
