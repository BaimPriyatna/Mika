from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mika.executor.rollback import PlanBackup, ResourceBackup
from mika.memory.backups import BackupStore
from mika.planner.plan import OperationType


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmp:
        yield BackupStore(Path(tmp) / "backups.db")


def _backup(plan_id: str = "plan-1") -> PlanBackup:
    return PlanBackup(
        plan_id=plan_id,
        router_identity="RB5009",
        resource_backups=(
            ResourceBackup(
                resource="/ip/firewall/filter",
                resource_id="*1",
                operation=OperationType.UPDATE,
                data={"action": "accept"},
            ),
        ),
    )


def test_add_and_list_backups_after(store):
    store.add_backup("session-1", message_id=5, router_alias="lab", backup=_backup())

    results = store.list_backups_after("session-1", message_id=0)
    assert len(results) == 1
    assert results[0].plan_id == "plan-1"
    assert results[0].router_alias == "lab"
    assert results[0].backup.plan_id == "plan-1"


def test_list_backups_after_excludes_earlier_ones(store):
    store.add_backup("session-1", message_id=3, router_alias="lab", backup=_backup("plan-a"))
    store.add_backup("session-1", message_id=10, router_alias="lab", backup=_backup("plan-b"))

    results = store.list_backups_after("session-1", message_id=5)
    assert [r.plan_id for r in results] == ["plan-b"]


def test_list_backups_after_ordered_oldest_first(store):
    store.add_backup("session-1", message_id=3, router_alias="lab", backup=_backup("plan-a"))
    store.add_backup("session-1", message_id=5, router_alias="lab", backup=_backup("plan-b"))
    store.add_backup("session-1", message_id=7, router_alias="lab", backup=_backup("plan-c"))

    results = store.list_backups_after("session-1", message_id=0)
    assert [r.plan_id for r in results] == ["plan-a", "plan-b", "plan-c"]


def test_list_backups_after_scoped_to_session(store):
    store.add_backup("session-1", message_id=1, router_alias="lab", backup=_backup("plan-a"))
    store.add_backup("session-2", message_id=1, router_alias="lab", backup=_backup("plan-b"))

    results = store.list_backups_after("session-1", message_id=0)
    assert [r.plan_id for r in results] == ["plan-a"]


def test_mark_rolled_back_excludes_from_future_listing(store):
    store.add_backup("session-1", message_id=1, router_alias="lab", backup=_backup("plan-a"))
    results = store.list_backups_after("session-1", message_id=0)

    store.mark_rolled_back([r.id for r in results])

    assert store.list_backups_after("session-1", message_id=0) == []


def test_mark_rolled_back_empty_list_is_noop(store):
    store.add_backup("session-1", message_id=1, router_alias="lab", backup=_backup())
    store.mark_rolled_back([])
    assert len(store.list_backups_after("session-1", message_id=0)) == 1


def test_backup_round_trips_resource_data(store):
    store.add_backup("session-1", message_id=1, router_alias="lab", backup=_backup())
    result = store.list_backups_after("session-1", message_id=0)[0]

    assert len(result.backup.resource_backups) == 1
    rb = result.backup.resource_backups[0]
    assert rb.resource == "/ip/firewall/filter"
    assert rb.resource_id == "*1"
    assert rb.operation == OperationType.UPDATE
    assert rb.data == {"action": "accept"}
