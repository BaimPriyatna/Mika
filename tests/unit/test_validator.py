from __future__ import annotations

from pathlib import Path

from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.enums import SafetyLevel
from mika.knowledge.loader import KnowledgeLoader
from mika.knowledge.retriever import KnowledgeRetriever
from mika.planner.hotspot import plan_create_hotspot
from mika.planner.plan import OperationType, PlanStatus, PlanStep
from mika.router.discovery import discover
from mika.router.mock import MockRouterClient
from mika.validator.result import IssueSeverity, ValidationLayer
from mika.validator.validator import validate
from tests.fixtures.routers import chr_profile, hex_profile

REPO_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge"


def _retriever() -> KnowledgeRetriever:
    return KnowledgeRetriever(KnowledgeLoader(root=REPO_KNOWLEDGE_ROOT).load_all())


def _hotspot_intent(**overrides) -> CreateHotspotIntent:
    fields = {
        "confidence": 0.9,
        "requires_confirmation": True,
        "interface": "ether3",
        "network": "192.168.20.0/24",
    }
    fields.update(overrides)
    return CreateHotspotIntent(**fields)


async def _hex_context():
    return await discover(MockRouterClient(hex_profile()))


async def test_valid_plan_passes_all_layers():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)

    result = validate(plan, ctx, _retriever())

    assert result.validated is True
    assert result.failures == ()
    assert result.plan.status == PlanStatus.VALIDATED
    assert result.plan_id == plan.plan_id


async def test_valid_plan_with_rate_limit_still_passes():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(rate_limit="5M/5M", dns_name="lab.local"), ctx)

    result = validate(plan, ctx, _retriever())

    assert result.validated is True
    assert result.plan.status == PlanStatus.VALIDATED


async def test_empty_plan_fails_schema_layer():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)
    empty_plan = plan.model_copy(update={"steps": ()})

    result = validate(empty_plan, ctx, _retriever())

    assert result.validated is False
    schema_fails = result.issues_for_layer(ValidationLayer.SCHEMA)
    assert any(i.severity == IssueSeverity.FAIL for i in schema_fails)


async def test_update_step_without_resource_id_fails_schema_layer():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)
    bad_step = PlanStep(
        step_id="bogus_update",
        description="bogus",
        operation=OperationType.UPDATE,
        resource="/ip/address",
        data={"comment": "x"},
    )
    bad_plan = plan.model_copy(update={"steps": plan.steps + (bad_step,)})

    result = validate(bad_plan, ctx, _retriever())

    assert result.validated is False
    assert any(i.step_id == "bogus_update" for i in result.failures)


async def test_unknown_resource_path_fails_syntax_layer():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)
    bogus_step = PlanStep(
        step_id="bogus_resource",
        description="bogus",
        operation=OperationType.CREATE,
        resource="/ip/magic/block",
        data={"name": "x"},
    )
    bad_plan = plan.model_copy(update={"steps": plan.steps + (bogus_step,)})

    result = validate(bad_plan, ctx, _retriever())

    assert result.validated is False
    syntax_fails = result.issues_for_layer(ValidationLayer.SYNTAX)
    assert any("not a known, verified RouterOS" in i.message for i in syntax_fails)


async def test_unknown_field_fails_syntax_layer():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)
    steps = list(plan.steps)
    pool_step = next(s for s in steps if s.step_id == "hotspot_pool")
    tampered = pool_step.model_copy(update={"data": {**pool_step.data, "made-up-field": "1"}})
    steps[steps.index(pool_step)] = tampered
    bad_plan = plan.model_copy(update={"steps": tuple(steps)})

    result = validate(bad_plan, ctx, _retriever())

    assert result.validated is False
    syntax_fails = result.issues_for_layer(ValidationLayer.SYNTAX)
    assert any("made-up-field" in i.message for i in syntax_fails)


async def test_intent_without_topic_mapping_is_version_uncertain():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)
    empty_retriever = KnowledgeRetriever([])

    result = validate(plan, ctx, empty_retriever)

    assert result.validated is False
    compat_fails = result.issues_for_layer(ValidationLayer.VERSION_COMPATIBILITY)
    assert any("Compatibility uncertain" in i.message for i in compat_fails)


async def test_stale_fingerprint_fails_resource_existence_layer():
    profile = hex_profile()
    client = MockRouterClient(profile)
    ctx_before = await discover(client)
    plan = plan_create_hotspot(_hotspot_intent(), ctx_before)

    for iface in profile.interfaces:
        if iface["name"] == "ether4":
            iface["disabled"] = "false"
    ctx_after = await discover(MockRouterClient(profile))

    result = validate(plan, ctx_after, _retriever())

    assert result.validated is False
    assert any(
        "changed since this plan was created" in i.message
        for i in result.issues_for_layer(ValidationLayer.RESOURCE_EXISTENCE)
    )


async def test_interface_removed_before_validation_fails():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)

    mutated = ctx.model_copy(
        update={
            "interfaces": tuple(
                i.model_copy(update={"disabled": True}) if i.name == "ether3" else i
                for i in ctx.interfaces
            )
        }
    )

    result = validate(plan, mutated, _retriever())

    assert result.validated is False
    resource_fails = result.issues_for_layer(ValidationLayer.RESOURCE_EXISTENCE)
    assert any("ether3" in i.message for i in resource_fails)


async def test_dangling_reference_fails_dependency_layer():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)
    steps = list(plan.steps)
    server_step = next(s for s in steps if s.step_id == "hotspot_server")
    tampered = server_step.model_copy(update={"data": {**server_step.data, "profile": "does-not-exist"}})
    steps[steps.index(server_step)] = tampered
    bad_plan = plan.model_copy(update={"steps": tuple(steps)})

    result = validate(bad_plan, ctx, _retriever())

    assert result.validated is False
    dep_fails = result.issues_for_layer(ValidationLayer.DEPENDENCY)
    assert any("does-not-exist" in i.message for i in dep_fails)


async def test_overlap_introduced_after_planning_fails():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)

    conflicting_addr = ctx.addresses[0].model_copy(
        update={"address": "192.168.20.5/24", "interface": "ether2"}
    )
    mutated = ctx.model_copy(update={"addresses": (*ctx.addresses, conflicting_addr)})

    result = validate(plan, mutated, _retriever())

    assert result.validated is False
    assert result.issues_for_layer(ValidationLayer.OVERLAP)


async def test_dhcp_name_collision_fails_conflict_layer():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(), ctx)

    colliding_dhcp = ctx.dhcp_servers[0].model_copy(update={"name": "ether3-hotspot-dhcp"})
    mutated = ctx.model_copy(update={"dhcp_servers": (*ctx.dhcp_servers, colliding_dhcp)})

    result = validate(plan, mutated, _retriever())

    assert result.validated is False
    assert result.issues_for_layer(ValidationLayer.CONFLICT)


async def test_hotspot_on_wan_interface_warns_and_upgrades_safety():
    from mika.router.discovery import IPAddressInfo

    base_ctx = await _hex_context()
    narrowed_addresses = tuple(
        IPAddressInfo(id=a.id, address="203.0.113.2/29", network="203.0.113.0", interface="ether1")
        if a.interface == "ether1"
        else a
        for a in base_ctx.addresses
    )
    ctx = base_ctx.model_copy(update={"addresses": narrowed_addresses})

    plan = plan_create_hotspot(_hotspot_intent(interface="ether1", network="203.0.113.16/29"), ctx)

    result = validate(plan, ctx, _retriever())

    safety_issues = result.issues_for_layer(ValidationLayer.SAFETY)
    assert any(i.severity == IssueSeverity.WARNING for i in safety_issues)
    assert result.plan.safety_level == SafetyLevel.HIGH_RISK
    assert result.validated is True


async def test_no_default_route_interface_touched_no_safety_warning():
    ctx = await _hex_context()
    plan = plan_create_hotspot(_hotspot_intent(interface="ether3"), ctx)

    result = validate(plan, ctx, _retriever())

    assert result.issues_for_layer(ValidationLayer.SAFETY) == ()
    assert result.plan.safety_level == SafetyLevel.MEDIUM_RISK


async def test_validate_against_chr_profile_clean_subnet_passes():
    ctx = await discover(MockRouterClient(chr_profile()))
    plan = plan_create_hotspot(_hotspot_intent(interface="ether2", network="10.10.10.0/24"), ctx)

    result = validate(plan, ctx, _retriever())

    assert result.validated is True
    assert result.plan.status == PlanStatus.VALIDATED
