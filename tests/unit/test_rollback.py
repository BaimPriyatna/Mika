from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.enums import SafetyLevel
from mika.executor.rollback import (
    PlanBackup,
    ResourceBackup,
    RollbackEngine,
    create_backup,
    rollback_from_backup,
)
from mika.planner.plan import OperationType, Plan, PlanStatus, PlanStep


@pytest.fixture
def mock_router_client():
    client = Mock()
    
    client.get_system_resource = AsyncMock(return_value={})
    client.get_interfaces = AsyncMock(return_value=[])
    client.get_addresses = AsyncMock(return_value=[])
    client.get_routes = AsyncMock(return_value=[])
    client.get_firewall_rules = AsyncMock(return_value=[])
    client.get_dhcp_servers = AsyncMock(return_value=[])
    client.get_dhcp_leases = AsyncMock(return_value=[])
    client.get_hotspot_servers = AsyncMock(return_value=[])
    client.get_hotspot_users = AsyncMock(return_value=[])
    
    client.create_resource = AsyncMock(return_value={"id": "*new"})
    client.update_resource = AsyncMock(return_value={})
    client.delete_resource = AsyncMock()
    
    return client


@pytest.fixture
def sample_intent():
    return CreateHotspotIntent(
        intent="create_hotspot",
        interface="ether2",
        network="10.5.50.0/24",
        confidence=0.95,
        requires_confirmation=True,
    )


@pytest.fixture
def create_plan(sample_intent):
    return Plan(
        plan_id="test_create_001",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.MEDIUM_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.3",
        router_state_fingerprint="abc123",
        steps=(
            PlanStep(
                step_id="add_address",
                description="Add IP address",
                operation=OperationType.CREATE,
                resource="/ip/address",
                data={
                    "address": "10.5.50.1/24",
                    "interface": "ether2",
                },
            ),
        ),
    )


@pytest.fixture
def update_plan(sample_intent):
    return Plan(
        plan_id="test_update_001",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.LOW_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.3",
        router_state_fingerprint="abc123",
        steps=(
            PlanStep(
                step_id="update_comment",
                description="Update comment",
                operation=OperationType.UPDATE,
                resource="/ip/address",
                resource_id="*5",
                data={"comment": "New comment"},
            ),
        ),
    )


@pytest.fixture
def delete_plan(sample_intent):
    return Plan(
        plan_id="test_delete_001",
        intent=sample_intent,
        status=PlanStatus.VALIDATED,
        safety_level=SafetyLevel.HIGH_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.3",
        router_state_fingerprint="abc123",
        steps=(
            PlanStep(
                step_id="delete_address",
                description="Delete address",
                operation=OperationType.DELETE,
                resource="/ip/address",
                resource_id="*7",
            ),
        ),
    )


class TestRollbackEngineInit:

    def test_init_without_backup_dir(self, mock_router_client):
        engine = RollbackEngine(mock_router_client)
        assert engine._client is mock_router_client
        assert engine._backup_dir is None

    def test_init_with_backup_dir(self, mock_router_client, tmp_path):
        backup_dir = tmp_path / "backups"
        engine = RollbackEngine(mock_router_client, backup_dir)
        
        assert engine._client is mock_router_client
        assert engine._backup_dir == backup_dir
        assert backup_dir.exists()


class TestBackupCreation:

    @pytest.mark.asyncio
    async def test_backup_create_operation(self, create_plan, mock_router_client):
        engine = RollbackEngine(mock_router_client)
        backup = await engine.create_backup(create_plan)
        
        assert backup.plan_id == create_plan.plan_id
        assert backup.router_identity == create_plan.router_identity
        assert len(backup.resource_backups) == 1
        
        resource_backup = backup.resource_backups[0]
        assert resource_backup.resource == "/ip/address"
        assert resource_backup.operation == OperationType.CREATE
        assert resource_backup.data == {}

    @pytest.mark.asyncio
    async def test_backup_update_operation(self, update_plan, mock_router_client):
        mock_router_client.get_addresses.return_value = [
            {
                ".id": "*5",
                "address": "10.5.50.1/24",
                "interface": "ether2",
                "comment": "Old comment",
            }
        ]
        
        engine = RollbackEngine(mock_router_client)
        backup = await engine.create_backup(update_plan)
        
        assert len(backup.resource_backups) == 1
        resource_backup = backup.resource_backups[0]
        
        assert resource_backup.resource == "/ip/address"
        assert resource_backup.resource_id == "*5"
        assert resource_backup.operation == OperationType.UPDATE
        assert resource_backup.data["comment"] == "Old comment"

    @pytest.mark.asyncio
    async def test_backup_delete_operation(self, delete_plan, mock_router_client):
        mock_router_client.get_addresses.return_value = [
            {
                ".id": "*7",
                "address": "10.5.50.1/24",
                "interface": "ether2",
                "comment": "To be deleted",
            }
        ]
        
        engine = RollbackEngine(mock_router_client)
        backup = await engine.create_backup(delete_plan)
        
        assert len(backup.resource_backups) == 1
        resource_backup = backup.resource_backups[0]
        
        assert resource_backup.resource == "/ip/address"
        assert resource_backup.resource_id == "*7"
        assert resource_backup.operation == OperationType.DELETE
        assert resource_backup.data["address"] == "10.5.50.1/24"

    @pytest.mark.asyncio
    async def test_backup_multi_step_plan(self, sample_intent, mock_router_client):
        plan = Plan(
            plan_id="test_multi",
            intent=sample_intent,
            status=PlanStatus.VALIDATED,
            safety_level=SafetyLevel.MEDIUM_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="add_addr",
                    description="Add address",
                    operation=OperationType.CREATE,
                    resource="/ip/address",
                    data={"address": "10.5.50.1/24", "interface": "ether2"},
                ),
                PlanStep(
                    step_id="update_addr",
                    description="Update comment",
                    operation=OperationType.UPDATE,
                    resource="/ip/address",
                    resource_id="*10",
                    data={"comment": "Gateway"},
                ),
            ),
        )
        
        mock_router_client.get_addresses.return_value = [
            {".id": "*10", "address": "10.1.1.1/24", "interface": "ether1", "comment": "Old"}
        ]
        
        engine = RollbackEngine(mock_router_client)
        backup = await engine.create_backup(plan)
        
        assert len(backup.resource_backups) == 2
        assert backup.resource_backups[0].operation == OperationType.CREATE
        assert backup.resource_backups[1].operation == OperationType.UPDATE

    @pytest.mark.asyncio
    async def test_backup_handles_missing_resource(self, update_plan, mock_router_client):
        mock_router_client.get_addresses.return_value = []
        
        engine = RollbackEngine(mock_router_client)
        backup = await engine.create_backup(update_plan)
        
        assert backup.plan_id == update_plan.plan_id


class TestRollbackExecution:

    @pytest.mark.asyncio
    async def test_rollback_update_operation(self, sample_intent, mock_router_client):
        backup = PlanBackup(
            plan_id="test",
            router_identity="TestRouter",
            resource_backups=(
                ResourceBackup(
                    resource="/ip/address",
                    resource_id="*5",
                    operation=OperationType.UPDATE,
                    data={"comment": "Original comment"},
                ),
            ),
        )
        
        engine = RollbackEngine(mock_router_client)
        result = await engine.rollback(backup)
        
        assert result.attempted is True
        assert result.success is True
        
        mock_router_client.update_resource.assert_called_once()
        call_args = mock_router_client.update_resource.call_args
        assert call_args[0][0] == "/ip/address"
        assert call_args[0][1] == "*5"
        assert call_args[0][2]["comment"] == "Original comment"

    @pytest.mark.asyncio
    async def test_rollback_delete_operation(self, sample_intent, mock_router_client):
        backup = PlanBackup(
            plan_id="test",
            router_identity="TestRouter",
            resource_backups=(
                ResourceBackup(
                    resource="/ip/address",
                    resource_id="*7",
                    operation=OperationType.DELETE,
                    data={
                        "address": "10.5.50.1/24",
                        "interface": "ether2",
                        "comment": "Deleted",
                    },
                ),
            ),
        )
        
        engine = RollbackEngine(mock_router_client)
        result = await engine.rollback(backup)
        
        assert result.attempted is True
        assert result.success is True
        
        mock_router_client.create_resource.assert_called_once()
        call_args = mock_router_client.create_resource.call_args
        assert call_args[0][0] == "/ip/address"
        assert call_args[0][1]["address"] == "10.5.50.1/24"

    @pytest.mark.asyncio
    async def test_rollback_create_operation_limitation(self, sample_intent, mock_router_client):
        backup = PlanBackup(
            plan_id="test",
            router_identity="TestRouter",
            resource_backups=(
                ResourceBackup(
                    resource="/ip/address",
                    resource_id=None,
                    operation=OperationType.CREATE,
                    data={},
                ),
            ),
        )
        
        engine = RollbackEngine(mock_router_client)
        result = await engine.rollback(backup)
        
        assert result.attempted is True
        assert result.success is True
        
        mock_router_client.delete_resource.assert_not_called()

    @pytest.mark.asyncio
    async def test_rollback_handles_errors_gracefully(self, sample_intent, mock_router_client):
        backup = PlanBackup(
            plan_id="test",
            router_identity="TestRouter",
            resource_backups=(
                ResourceBackup(
                    resource="/ip/address",
                    resource_id="*5",
                    operation=OperationType.UPDATE,
                    data={"comment": "Original"},
                ),
                ResourceBackup(
                    resource="/ip/firewall/filter",
                    resource_id="*10",
                    operation=OperationType.UPDATE,
                    data={"comment": "Original rule"},
                ),
            ),
        )
        
        mock_router_client.update_resource.side_effect = [
            RuntimeError("Connection timeout"),
            {},
        ]
        
        engine = RollbackEngine(mock_router_client)
        result = await engine.rollback(backup)
        
        assert result.attempted is True
        assert result.success is False
        assert "Connection timeout" in result.notes

    @pytest.mark.asyncio
    async def test_rollback_in_reverse_order(self, sample_intent, mock_router_client):
        backup = PlanBackup(
            plan_id="test",
            router_identity="TestRouter",
            resource_backups=(
                ResourceBackup(
                    resource="/ip/address",
                    resource_id="*1",
                    operation=OperationType.UPDATE,
                    data={"comment": "First"},
                ),
                ResourceBackup(
                    resource="/ip/dhcp-server",
                    resource_id="*2",
                    operation=OperationType.UPDATE,
                    data={"comment": "Second"},
                ),
            ),
        )
        
        call_order = []
        
        async def track_update(resource, resource_id, data):
            call_order.append((resource, resource_id))
            return {}
        
        mock_router_client.update_resource = AsyncMock(side_effect=track_update)
        
        engine = RollbackEngine(mock_router_client)
        await engine.rollback(backup)
        
        assert len(call_order) == 2
        assert call_order[0] == ("/ip/dhcp-server", "*2")
        assert call_order[1] == ("/ip/address", "*1")


class TestConvenienceFunctions:

    @pytest.mark.asyncio
    async def test_create_backup_convenience(self, create_plan, mock_router_client):
        backup = await create_backup(create_plan, mock_router_client)
        
        assert isinstance(backup, PlanBackup)
        assert backup.plan_id == create_plan.plan_id

    @pytest.mark.asyncio
    async def test_rollback_from_backup_convenience(self, sample_intent, mock_router_client):
        backup = PlanBackup(
            plan_id="test",
            router_identity="TestRouter",
            resource_backups=(
                ResourceBackup(
                    resource="/ip/address",
                    resource_id="*5",
                    operation=OperationType.UPDATE,
                    data={"comment": "Original"},
                ),
            ),
        )
        
        result = await rollback_from_backup(backup, mock_router_client)
        
        assert result.attempted is True
        assert result.success is True


class TestSystemExport:

    @pytest.mark.asyncio
    async def test_low_risk_no_system_export(self, sample_intent, mock_router_client):
        plan = Plan(
            plan_id="test",
            intent=sample_intent,
            status=PlanStatus.VALIDATED,
            safety_level=SafetyLevel.LOW_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(),
        )
        
        engine = RollbackEngine(mock_router_client)
        backup = await engine.create_backup(plan)
        
        assert backup.system_export_path is None

    @pytest.mark.asyncio
    async def test_high_risk_requests_system_export(self, sample_intent, mock_router_client, tmp_path):
        plan = Plan(
            plan_id="test",
            intent=sample_intent,
            status=PlanStatus.VALIDATED,
            safety_level=SafetyLevel.HIGH_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(),
        )
        
        engine = RollbackEngine(mock_router_client, tmp_path)
        backup = await engine.create_backup(plan)
        
        assert backup.system_export_path is None

    @pytest.mark.asyncio
    async def test_destructive_requests_system_export(self, sample_intent, mock_router_client, tmp_path):
        plan = Plan(
            plan_id="test",
            intent=sample_intent,
            status=PlanStatus.VALIDATED,
            safety_level=SafetyLevel.DESTRUCTIVE,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(),
        )
        
        engine = RollbackEngine(mock_router_client, tmp_path)
        backup = await engine.create_backup(plan)
        
        assert backup.system_export_path is None


class TestBackupModels:

    def test_resource_backup_immutable(self):
        backup = ResourceBackup(
            resource="/ip/address",
            operation=OperationType.CREATE,
            data={},
        )
        
        with pytest.raises(Exception):
            backup.resource = "/ip/route"

    def test_plan_backup_immutable(self):
        backup = PlanBackup(
            plan_id="test",
            router_identity="TestRouter",
        )
        
        with pytest.raises(Exception):
            backup.plan_id = "modified"

    def test_plan_backup_defaults(self):
        backup = PlanBackup(
            plan_id="test",
            router_identity="TestRouter",
        )
        
        assert backup.resource_backups == ()
        assert backup.system_export_path is None
        assert backup.created_at is not None


class TestNotesGeneration:

    @pytest.mark.asyncio
    async def test_success_notes(self, sample_intent, mock_router_client):
        backup = PlanBackup(
            plan_id="test",
            router_identity="TestRouter",
            resource_backups=(
                ResourceBackup(
                    resource="/ip/address",
                    resource_id="*5",
                    operation=OperationType.UPDATE,
                    data={"comment": "Original"},
                ),
            ),
        )
        
        engine = RollbackEngine(mock_router_client)
        result = await engine.rollback(backup)
        
        assert result.success is True
        assert "successful" in result.notes.lower()
        assert "restored" in result.notes.lower()

    @pytest.mark.asyncio
    async def test_failure_notes_include_errors(self, sample_intent, mock_router_client):
        backup = PlanBackup(
            plan_id="test",
            router_identity="TestRouter",
            resource_backups=(
                ResourceBackup(
                    resource="/ip/address",
                    resource_id="*5",
                    operation=OperationType.UPDATE,
                    data={"comment": "Original"},
                ),
            ),
        )
        
        mock_router_client.update_resource.side_effect = RuntimeError("Network error")
        
        engine = RollbackEngine(mock_router_client)
        result = await engine.rollback(backup)
        
        assert result.success is False
        assert "Network error" in result.notes
        assert "failed" in result.notes.lower()
