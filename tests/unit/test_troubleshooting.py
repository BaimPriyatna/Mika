from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from mika.monitoring.models import HealthStatus, RouterHealth, SystemMetrics
from mika.troubleshoot.models import (
    DiagnosisResult,
    Hypothesis,
    HypothesisLikelihood,
    TroubleshootingSession,
)
from mika.troubleshoot.workflow import (
    TroubleshootingWorkflow,
    troubleshoot_problem,
)


@pytest.fixture
def mock_router_client():
    client = Mock()
    
    client.get_system_resource = AsyncMock(
        return_value={
            "identity": "TestRouter",
            "uptime": "1d",
            "cpu-load": 25,
            "free-memory": 750000000,
            "total-memory": 1000000000,
            "architecture-name": "arm64",
            "board-name": "hEX",
            "version": "7.14.3",
        }
    )
    
    client.get_interfaces = AsyncMock(
        return_value=[
            {"name": "ether1", "running": "true", "disabled": "false"},
            {"name": "ether2", "running": "true", "disabled": "false"},
        ]
    )
    
    client.get_addresses = AsyncMock(return_value=[])
    client.get_routes = AsyncMock(return_value=[])
    client.get_firewall_rules = AsyncMock(return_value=[])
    client.get_dhcp_servers = AsyncMock(return_value=[])
    client.get_dhcp_leases = AsyncMock(return_value=[])
    client.get_hotspot_servers = AsyncMock(return_value=[])
    client.get_hotspot_users = AsyncMock(return_value=[])
    
    return client


class TestTroubleshootingSession:

    def test_session_creation(self):
        session = TroubleshootingSession(
            session_id="test_001",
            problem_description="No internet",
            router_identity="TestRouter",
        )
        
        assert session.session_id == "test_001"
        assert session.problem_description == "No internet"
        assert session.completed is False

    def test_add_hypothesis(self):
        session = TroubleshootingSession(
            session_id="test",
            problem_description="Test",
            router_identity="TestRouter",
        )
        
        hypothesis = Hypothesis(
            description="No default route",
            likelihood=HypothesisLikelihood.VERY_LIKELY,
        )
        
        session.add_hypothesis(hypothesis)
        assert len(session.hypotheses) == 1
        assert session.hypotheses[0].description == "No default route"

    def test_complete_session(self):
        session = TroubleshootingSession(
            session_id="test",
            problem_description="No internet",
            router_identity="TestRouter",
        )
        
        session.add_hypothesis(
            Hypothesis(
                description="Hypothesis 1",
                likelihood=HypothesisLikelihood.LIKELY,
            )
        )
        session.add_fix("Fix 1")
        
        diagnosis = session.complete()
        
        assert session.completed is True
        assert session.completed_at is not None
        assert isinstance(diagnosis, DiagnosisResult)
        assert diagnosis.problem_description == "No internet"
        assert len(diagnosis.hypotheses) == 1
        assert len(diagnosis.recommended_fixes) == 1

    def test_hypotheses_sorted_by_likelihood(self):
        session = TroubleshootingSession(
            session_id="test",
            problem_description="Test",
            router_identity="TestRouter",
        )
        
        session.add_hypothesis(
            Hypothesis(
                description="Unlikely",
                likelihood=HypothesisLikelihood.UNLIKELY,
            )
        )
        session.add_hypothesis(
            Hypothesis(
                description="Very likely",
                likelihood=HypothesisLikelihood.VERY_LIKELY,
            )
        )
        session.add_hypothesis(
            Hypothesis(
                description="Possible",
                likelihood=HypothesisLikelihood.POSSIBLE,
            )
        )
        
        diagnosis = session.complete()
        
        assert diagnosis.hypotheses[0].description == "Very likely"
        assert diagnosis.hypotheses[1].description == "Possible"
        assert diagnosis.hypotheses[2].description == "Unlikely"


class TestDiagnosisResult:

    def test_most_likely_cause(self):
        diagnosis = DiagnosisResult(
            problem_description="Test",
            router_identity="TestRouter",
            hypotheses=(
                Hypothesis(
                    description="Most likely",
                    likelihood=HypothesisLikelihood.VERY_LIKELY,
                ),
                Hypothesis(
                    description="Less likely",
                    likelihood=HypothesisLikelihood.POSSIBLE,
                ),
            ),
        )
        
        assert diagnosis.most_likely_cause is not None
        assert diagnosis.most_likely_cause.description == "Most likely"

    def test_most_likely_cause_empty(self):
        diagnosis = DiagnosisResult(
            problem_description="Test",
            router_identity="TestRouter",
            hypotheses=(),
        )
        
        assert diagnosis.most_likely_cause is None


class TestTroubleshootingWorkflow:

    def test_workflow_init(self, mock_router_client):
        workflow = TroubleshootingWorkflow(mock_router_client)
        assert workflow._client is mock_router_client

    @pytest.mark.asyncio
    async def test_diagnose_basic(self, mock_router_client):
        workflow = TroubleshootingWorkflow(mock_router_client)
        diagnosis = await workflow.diagnose("No internet")
        
        assert isinstance(diagnosis, DiagnosisResult)
        assert diagnosis.problem_description == "No internet"
        assert diagnosis.router_identity == "TestRouter"
        assert len(diagnosis.hypotheses) > 0

    @pytest.mark.asyncio
    async def test_convenience_function(self, mock_router_client):
        diagnosis = await troubleshoot_problem("Interface down", mock_router_client)
        
        assert isinstance(diagnosis, DiagnosisResult)
        assert len(diagnosis.hypotheses) > 0

    @pytest.mark.asyncio
    async def test_collects_state(self, mock_router_client):
        workflow = TroubleshootingWorkflow(mock_router_client)
        diagnosis = await workflow.diagnose("Test problem")
        
        assert "health" in diagnosis.state_collected
        assert "interfaces" in diagnosis.state_collected

    @pytest.mark.asyncio
    async def test_forms_hypotheses_interface_down(self, mock_router_client):
        mock_router_client.get_interfaces.return_value = [
            {"name": "ether1", "running": "false", "disabled": "false"},
        ]
        
        workflow = TroubleshootingWorkflow(mock_router_client)
        diagnosis = await workflow.diagnose("Interface ether1 is down")
        
        assert any(
            "down" in h.description.lower()
            for h in diagnosis.hypotheses
        )

    @pytest.mark.asyncio
    async def test_forms_hypotheses_no_default_route(self, mock_router_client):
        mock_router_client.get_routes = AsyncMock(return_value=[])
        
        workflow = TroubleshootingWorkflow(mock_router_client)
        diagnosis = await workflow.diagnose("No internet connectivity")
        
        assert any(
            "default route" in h.description.lower()
            for h in diagnosis.hypotheses
        )

    @pytest.mark.asyncio
    async def test_proposes_fixes(self, mock_router_client):
        mock_router_client.get_interfaces.return_value = [
            {"name": "ether1", "running": "false", "disabled": "false"},
        ]
        
        workflow = TroubleshootingWorkflow(mock_router_client)
        diagnosis = await workflow.diagnose("Interface down")
        
        assert len(diagnosis.recommended_fixes) > 0
        assert any(
            "interface" in fix.lower() or "cable" in fix.lower()
            for fix in diagnosis.recommended_fixes
        )

    @pytest.mark.asyncio
    async def test_handles_critical_health(self, mock_router_client):
        mock_router_client.get_system_resource.return_value.update({
            "cpu-load": 95,
        })
        
        workflow = TroubleshootingWorkflow(mock_router_client)
        diagnosis = await workflow.diagnose("Router slow")
        
        assert any(
            "critical" in h.description.lower()
            for h in diagnosis.hypotheses
        )

    @pytest.mark.asyncio
    async def test_handles_dhcp_problems(self, mock_router_client):
        mock_router_client.get_dhcp_servers = AsyncMock(
            return_value=[
                {"name": "dhcp1", "interface": "ether2", "disabled": "true"}
            ]
        )
        
        workflow = TroubleshootingWorkflow(mock_router_client)
        diagnosis = await workflow.diagnose("DHCP not working")
        
        assert any(
            "dhcp" in h.description.lower() and "disabled" in h.description.lower()
            for h in diagnosis.hypotheses
        )


class TestModelImmutability:

    def test_hypothesis_frozen(self):
        hypothesis = Hypothesis(
            description="Test",
            likelihood=HypothesisLikelihood.LIKELY,
        )
        
        with pytest.raises(Exception):
            hypothesis.description = "Modified"

    def test_diagnosis_result_frozen(self):
        diagnosis = DiagnosisResult(
            problem_description="Test",
            router_identity="TestRouter",
        )
        
        with pytest.raises(Exception):
            diagnosis.problem_description = "Modified"

    def test_session_mutable_during_workflow(self):
        session = TroubleshootingSession(
            session_id="test",
            problem_description="Test",
            router_identity="TestRouter",
        )
        
        session.add_hypothesis(
            Hypothesis(
                description="Test hypothesis",
                likelihood=HypothesisLikelihood.LIKELY,
            )
        )
        
        assert len(session.hypotheses) == 1
