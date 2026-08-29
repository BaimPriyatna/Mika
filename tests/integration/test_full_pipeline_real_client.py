"""
Full pipeline regression tests against the real MockRouterClient.

These exist because tests/unit/test_executor.py and
tests/integration/test_plan_confirm_execute.py both used a bare
AsyncMock() with manually-attached .add/.update/.delete methods that
didn't match the real RouterClient protocol (create_resource/
update_resource/delete_resource). That let a critical bug -- the
executor calling nonexistent client methods -- ship completely
undetected, since execution had never actually been exercised for
real against something implementing the real interface.

Every test here uses the real MockRouterClient end-to-end: plan,
validate, backup, execute, verify, and (where relevant) rollback,
then re-discovers the router to confirm the change actually landed.
"""

from __future__ import annotations

from mika.ai.schemas.configuration_intents import CreateAddressIntent, CreateVlanIntent
from mika.ai.schemas.destructive_intents import DeleteQueueIntent
from mika.executor.confirmation import ConfirmationState, ConfirmationStatus
from mika.executor.executor import Executor
from mika.executor.rollback import RollbackEngine
from mika.executor.verification import Verifier
from mika.knowledge.loader import KnowledgeLoader
from mika.knowledge.retriever import KnowledgeRetriever
from mika.planner.address import plan_create_address
from mika.planner.delete_queue import plan_delete_queue
from mika.planner.vlan import plan_create_vlan
from mika.router.discovery import discover
from mika.router.mock import MockRouterClient
from mika.validator.validator import validate
from tests.fixtures.routers import hex_profile

REPO_KNOWLEDGE_ROOT = __file__.rsplit("/tests/", 1)[0] + "/knowledge"


def _retriever() -> KnowledgeRetriever:
    return KnowledgeRetriever(KnowledgeLoader(root=REPO_KNOWLEDGE_ROOT).load_all())


async def test_create_address_full_pipeline_against_real_mock_client():
    client = MockRouterClient(hex_profile())
    ctx = await discover(client)

    intent = CreateAddressIntent(
        confidence=0.9, requires_confirmation=True, interface="ether2", address="172.16.5.1/24"
    )
    plan = plan_create_address(intent, ctx)
    validated = validate(plan, ctx, _retriever()).plan

    conf = ConfirmationState(plan_id=validated.plan_id, status=ConfirmationStatus.CONFIRMED)
    exec_result = await Executor(client).execute(validated, conf)
    assert exec_result.success is True
    assert exec_result.commands_applied == 1

    ctx_after = await discover(client)
    assert any(a.address == "172.16.5.1/24" and a.interface == "ether2" for a in ctx_after.addresses)


async def test_create_vlan_full_pipeline_including_verification():
    client = MockRouterClient(hex_profile())
    ctx = await discover(client)

    intent = CreateVlanIntent(
        confidence=0.9, requires_confirmation=True, parent_interface="ether2", vlan_id=100
    )
    plan = plan_create_vlan(intent, ctx)
    validated = validate(plan, ctx, _retriever()).plan

    conf = ConfirmationState(plan_id=validated.plan_id, status=ConfirmationStatus.CONFIRMED)
    exec_result = await Executor(client).execute(validated, conf)
    assert exec_result.success is True

    verif = await Verifier(client).verify(validated)
    assert verif.verified is True
    assert verif.checks_failed == 0

    ctx_after = await discover(client)
    vlan_ifaces = [i for i in ctx_after.interfaces if i.type == "vlan"]
    assert len(vlan_ifaces) == 1
    assert vlan_ifaces[0].vlan_id == 100
    assert vlan_ifaces[0].vlan_parent == "ether2"


async def test_delete_queue_full_pipeline_with_backup_and_rollback():
    client = MockRouterClient(hex_profile())
    client._profile.queues.append(
        {".id": "*1", "name": "q1", "target": "ether2", "max-limit": "5M/5M"}
    )
    ctx = await discover(client)

    intent = DeleteQueueIntent(
        confidence=0.9, requires_confirmation=True, resource_id="*1", expected_description="q1"
    )
    plan = plan_delete_queue(intent, ctx)
    validated = validate(plan, ctx, _retriever()).plan

    rollback_engine = RollbackEngine(client)
    backup = await rollback_engine.create_backup(validated)
    assert len(backup.resource_backups) == 1

    conf = ConfirmationState(plan_id=validated.plan_id, status=ConfirmationStatus.CONFIRMED)
    exec_result = await Executor(client).execute(validated, conf)
    assert exec_result.success is True

    ctx_after_delete = await discover(client)
    assert ctx_after_delete.queues == []

    rollback_result = await rollback_engine.rollback(backup)
    assert rollback_result.success is True

    ctx_after_rollback = await discover(client)
    assert len(ctx_after_rollback.queues) == 1
    assert ctx_after_rollback.queues[0].name == "q1"


# -- router-state staleness detection --------------------------------------


async def test_execution_refused_when_router_state_changed_since_plan():
    from mika.executor.errors import StaleConfirmationError

    client = MockRouterClient(hex_profile())
    ctx = await discover(client)

    intent = CreateAddressIntent(
        confidence=0.9, requires_confirmation=True, interface="ether2", address="172.16.5.1/24"
    )
    plan = plan_create_address(intent, ctx)
    validated = validate(plan, ctx, _retriever()).plan

    # Simulate someone else changing the router after the plan was built
    # and confirmed, but before execution actually runs.
    client._profile.addresses.append(
        {".id": "*99", "address": "10.99.99.1/24", "network": "10.99.99.0", "interface": "ether5"}
    )

    conf = ConfirmationState(plan_id=validated.plan_id, status=ConfirmationStatus.CONFIRMED)
    try:
        await Executor(client).execute(validated, conf)
        assert False, "expected StaleConfirmationError"
    except StaleConfirmationError:
        pass


async def test_execution_proceeds_when_router_state_unchanged():
    client = MockRouterClient(hex_profile())
    ctx = await discover(client)

    intent = CreateAddressIntent(
        confidence=0.9, requires_confirmation=True, interface="ether2", address="172.16.5.1/24"
    )
    plan = plan_create_address(intent, ctx)
    validated = validate(plan, ctx, _retriever()).plan

    # No changes made to the router between validation and execution.
    conf = ConfirmationState(plan_id=validated.plan_id, status=ConfirmationStatus.CONFIRMED)
    result = await Executor(client).execute(validated, conf)
    assert result.success is True
