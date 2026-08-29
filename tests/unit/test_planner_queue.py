from __future__ import annotations

import pytest

from mika.ai.schemas.configuration_intents import CreateQueueIntent
from mika.ai.schemas.enums import SafetyLevel
from mika.planner.errors import InterfaceNotFoundError, QueueAlreadyExistsError
from mika.planner.plan import OperationType, PlanStatus
from mika.planner.queue import plan_create_queue
from mika.router.discovery import discover
from mika.router.mock import MockRouterClient
from tests.fixtures.routers import hex_profile


def _queue_intent(**overrides) -> CreateQueueIntent:
    fields = {
        "confidence": 0.9,
        "requires_confirmation": True,
        "name": "lab-limit",
        "target": "172.16.5.0/24",
        "max_limit": "10M/10M",
    }
    fields.update(overrides)
    return CreateQueueIntent(**fields)


async def _ctx():
    return await discover(MockRouterClient(hex_profile()))


async def test_happy_path_subnet_target():
    ctx = await _ctx()
    intent = _queue_intent()

    plan = plan_create_queue(intent, ctx)

    assert plan.status == PlanStatus.PLANNED
    assert plan.safety_level == SafetyLevel.LOW_RISK
    assert plan.affected_interfaces == ()
    step = plan.steps[0]
    assert step.operation == OperationType.CREATE
    assert step.resource == "/queue/simple"
    assert step.data["name"] == "lab-limit"
    assert step.data["target"] == "172.16.5.0/24"
    assert step.data["max-limit"] == "10M/10M"


async def test_happy_path_interface_target():
    ctx = await _ctx()
    intent = _queue_intent(target="ether2")
    plan = plan_create_queue(intent, ctx)
    assert plan.affected_interfaces == ("ether2",)
    assert plan.steps[0].data["target"] == "ether2"


async def test_unknown_interface_target_raises():
    ctx = await _ctx()
    intent = _queue_intent(target="ether99")
    with pytest.raises(InterfaceNotFoundError):
        plan_create_queue(intent, ctx)


async def test_duplicate_queue_name_raises():
    ctx = await _ctx()
    from mika.router.discovery import QueueInfo

    existing = QueueInfo(id="*99", name="lab-limit", target="172.16.5.0/24", max_limit="5M/5M")
    ctx_with_existing = ctx.model_copy(update={"queues": [*ctx.queues, existing]})
    with pytest.raises(QueueAlreadyExistsError):
        plan_create_queue(_queue_intent(), ctx_with_existing)
