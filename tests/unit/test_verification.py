from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.enums import SafetyLevel
from mika.executor.verification import Verifier, verify_plan
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
def simple_plan(sample_intent):
    return Plan(
        plan_id="test_plan_001",
        intent=sample_intent,
        status=PlanStatus.EXECUTED,
        safety_level=SafetyLevel.MEDIUM_RISK,
        router_identity="TestRouter",
        routeros_version="7.14.3",
        router_state_fingerprint="abc123",
        affected_interfaces=("ether2",),
        affected_networks=("10.5.50.0/24",),
        steps=(
            PlanStep(
                step_id="add_address",
                description="Add IP address to interface",
                operation=OperationType.CREATE,
                resource="/ip/address",
                data={
                    "address": "10.5.50.1/24",
                    "interface": "ether2",
                    "comment": "Hotspot gateway",
                },
            ),
            PlanStep(
                step_id="add_pool",
                description="Create IP pool",
                operation=OperationType.CREATE,
                resource="/ip/pool",
                data={
                    "name": "hotspot_pool",
                    "ranges": "10.5.50.100-10.5.50.200",
                },
            ),
        ),
    )


class TestVerifierBasics:

    def test_verifier_init(self, mock_router_client):
        verifier = Verifier(mock_router_client)
        assert verifier._client is mock_router_client

    @pytest.mark.asyncio
    async def test_verify_plan_convenience_function(self, simple_plan, mock_router_client):
        mock_router_client.get_addresses.return_value = [
            {
                ".id": "*1",
                "address": "10.5.50.1/24",
                "interface": "ether2",
                "comment": "Hotspot gateway",
            }
        ]
        
        result = await verify_plan(simple_plan, mock_router_client)
        
        assert result.checks_passed >= 1
        assert isinstance(result.notes, str)


class TestVerifyCreate:

    @pytest.mark.asyncio
    async def test_create_verification_success(self, simple_plan, mock_router_client):
        mock_router_client.get_addresses.return_value = [
            {
                ".id": "*1",
                "address": "10.5.50.1/24",
                "interface": "ether2",
                "comment": "Hotspot gateway",
            }
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(simple_plan)
        
        assert result.checks_passed >= 1
        assert "address" in result.notes.lower() or "verification" in result.notes.lower()

    @pytest.mark.asyncio
    async def test_create_verification_failure_missing_resource(
        self, simple_plan, mock_router_client
    ):
        mock_router_client.get_addresses.return_value = []
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(simple_plan)
        
        assert result.checks_failed >= 1
        assert result.verified is False
        assert "failed" in result.notes.lower()

    @pytest.mark.asyncio
    async def test_create_verification_failure_wrong_properties(
        self, simple_plan, mock_router_client
    ):
        mock_router_client.get_addresses.return_value = [
            {
                ".id": "*1",
                "address": "10.5.50.1/24",
                "interface": "ether3",
                "comment": "Hotspot gateway",
            }
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(simple_plan)
        
        assert result.checks_failed >= 1
        assert result.verified is False


class TestVerifyUpdate:

    @pytest.mark.asyncio
    async def test_update_verification_success(self, sample_intent, mock_router_client):
        plan = Plan(
            plan_id="test_update",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
            safety_level=SafetyLevel.LOW_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="update_comment",
                    description="Update address comment",
                    operation=OperationType.UPDATE,
                    resource="/ip/address",
                    resource_id="*5",
                    data={"comment": "Updated comment"},
                ),
            ),
        )
        
        mock_router_client.get_addresses.return_value = [
            {
                ".id": "*5",
                "address": "10.5.50.1/24",
                "interface": "ether2",
                "comment": "Updated comment",
            }
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is True
        assert result.checks_passed == 1
        assert result.checks_failed == 0

    @pytest.mark.asyncio
    async def test_update_verification_failure_missing_resource(
        self, sample_intent, mock_router_client
    ):
        plan = Plan(
            plan_id="test_update",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
            safety_level=SafetyLevel.LOW_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="update_comment",
                    description="Update address comment",
                    operation=OperationType.UPDATE,
                    resource="/ip/address",
                    resource_id="*999",
                    data={"comment": "Updated comment"},
                ),
            ),
        )
        
        mock_router_client.get_addresses.return_value = [
            {
                ".id": "*5",
                "address": "10.5.50.1/24",
                "interface": "ether2",
                "comment": "Old comment",
            }
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is False
        assert result.checks_failed == 1

    @pytest.mark.asyncio
    async def test_update_verification_failure_wrong_value(
        self, sample_intent, mock_router_client
    ):
        plan = Plan(
            plan_id="test_update",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
            safety_level=SafetyLevel.LOW_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="update_comment",
                    description="Update address comment",
                    operation=OperationType.UPDATE,
                    resource="/ip/address",
                    resource_id="*5",
                    data={"comment": "Expected comment"},
                ),
            ),
        )
        
        mock_router_client.get_addresses.return_value = [
            {
                ".id": "*5",
                "address": "10.5.50.1/24",
                "interface": "ether2",
                "comment": "Different comment",
            }
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is False
        assert result.checks_failed == 1


class TestVerifyDelete:

    @pytest.mark.asyncio
    async def test_delete_verification_success(self, sample_intent, mock_router_client):
        plan = Plan(
            plan_id="test_delete",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
            safety_level=SafetyLevel.HIGH_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="delete_address",
                    description="Delete IP address",
                    operation=OperationType.DELETE,
                    resource="/ip/address",
                    resource_id="*7",
                ),
            ),
        )
        
        mock_router_client.get_addresses.return_value = [
            {".id": "*5", "address": "10.1.1.1/24", "interface": "ether1"},
            {".id": "*6", "address": "10.2.2.1/24", "interface": "ether2"},
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is True
        assert result.checks_passed == 1
        assert result.checks_failed == 0

    @pytest.mark.asyncio
    async def test_delete_verification_failure_still_exists(
        self, sample_intent, mock_router_client
    ):
        plan = Plan(
            plan_id="test_delete",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
            safety_level=SafetyLevel.HIGH_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="delete_address",
                    description="Delete IP address",
                    operation=OperationType.DELETE,
                    resource="/ip/address",
                    resource_id="*7",
                ),
            ),
        )
        
        mock_router_client.get_addresses.return_value = [
            {".id": "*5", "address": "10.1.1.1/24", "interface": "ether1"},
            {".id": "*7", "address": "10.5.50.1/24", "interface": "ether2"},
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is False
        assert result.checks_failed == 1


class TestMultiStepVerification:

    @pytest.mark.asyncio
    async def test_all_steps_pass(self, sample_intent, mock_router_client):
        plan = Plan(
            plan_id="test_multi",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
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
            {
                ".id": "*9",
                "address": "10.5.50.1/24",
                "interface": "ether2",
            },
            {
                ".id": "*10",
                "address": "10.1.1.1/24",
                "interface": "ether1",
                "comment": "Gateway",
            },
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is True
        assert result.checks_passed == 2
        assert result.checks_failed == 0

    @pytest.mark.asyncio
    async def test_partial_failure(self, sample_intent, mock_router_client):
        plan = Plan(
            plan_id="test_partial",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
            safety_level=SafetyLevel.MEDIUM_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="add_addr1",
                    description="Add first address",
                    operation=OperationType.CREATE,
                    resource="/ip/address",
                    data={"address": "10.5.50.1/24", "interface": "ether2"},
                ),
                PlanStep(
                    step_id="add_addr2",
                    description="Add second address",
                    operation=OperationType.CREATE,
                    resource="/ip/address",
                    data={"address": "10.5.60.1/24", "interface": "ether3"},
                ),
            ),
        )
        
        mock_router_client.get_addresses.return_value = [
            {
                ".id": "*9",
                "address": "10.5.50.1/24",
                "interface": "ether2",
            },
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is False
        assert result.checks_passed == 1
        assert result.checks_failed == 1
        assert "add_addr2" in result.notes


class TestVerificationErrorHandling:

    @pytest.mark.asyncio
    async def test_read_failure_counts_as_failed_check(
        self, simple_plan, mock_router_client
    ):
        mock_router_client.get_addresses.side_effect = RuntimeError("Connection timeout")
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(simple_plan)
        
        assert result.verified is False
        assert result.checks_failed >= 1


class TestResourceReaders:

    @pytest.mark.asyncio
    async def test_firewall_rule_verification(self, sample_intent, mock_router_client):
        plan = Plan(
            plan_id="test_fw",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
            safety_level=SafetyLevel.HIGH_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="add_rule",
                    description="Add firewall rule",
                    operation=OperationType.CREATE,
                    resource="/ip/firewall/filter",
                    data={
                        "chain": "forward",
                        "action": "accept",
                        "comment": "Allow guests",
                    },
                ),
            ),
        )
        
        mock_router_client.get_firewall_rules.return_value = [
            {
                ".id": "*20",
                "chain": "forward",
                "action": "accept",
                "comment": "Allow guests",
            }
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is True
        assert result.checks_passed == 1

    @pytest.mark.asyncio
    async def test_dhcp_server_verification(self, sample_intent, mock_router_client):
        plan = Plan(
            plan_id="test_dhcp",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
            safety_level=SafetyLevel.MEDIUM_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="add_dhcp",
                    description="Add DHCP server",
                    operation=OperationType.CREATE,
                    resource="/ip/dhcp-server",
                    data={
                        "name": "dhcp_ether2",
                        "interface": "ether2",
                        "address-pool": "pool1",
                    },
                ),
            ),
        )
        
        mock_router_client.get_dhcp_servers.return_value = [
            {
                ".id": "*1",
                "name": "dhcp_ether2",
                "interface": "ether2",
                "address-pool": "pool1",
            }
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is True


class TestNotesGeneration:

    @pytest.mark.asyncio
    async def test_success_notes(self, sample_intent, mock_router_client):
        plan = Plan(
            plan_id="test_notes",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
            safety_level=SafetyLevel.LOW_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="test_step",
                    description="Test",
                    operation=OperationType.CREATE,
                    resource="/ip/address",
                    data={"address": "10.1.1.1/24", "interface": "ether1"},
                ),
            ),
        )
        
        mock_router_client.get_addresses.return_value = [
            {".id": "*1", "address": "10.1.1.1/24", "interface": "ether1"}
        ]
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is True
        assert "passed" in result.notes.lower()
        assert "test_notes" in result.notes or "plan" in result.notes.lower()

    @pytest.mark.asyncio
    async def test_failure_notes_include_failed_steps(
        self, sample_intent, mock_router_client
    ):
        plan = Plan(
            plan_id="test_fail",
            intent=sample_intent,
            status=PlanStatus.EXECUTED,
            safety_level=SafetyLevel.LOW_RISK,
            router_identity="TestRouter",
            routeros_version="7.14.3",
            router_state_fingerprint="abc123",
            steps=(
                PlanStep(
                    step_id="failed_step",
                    description="This will fail",
                    operation=OperationType.CREATE,
                    resource="/ip/address",
                    data={"address": "10.99.99.1/24", "interface": "ether99"},
                ),
            ),
        )
        
        mock_router_client.get_addresses.return_value = []
        
        verifier = Verifier(mock_router_client)
        result = await verifier.verify(plan)
        
        assert result.verified is False
        assert "failed" in result.notes.lower()
        assert "failed_step" in result.notes
