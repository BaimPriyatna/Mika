from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from mika.monitoring.collector import HealthCollector, collect_health
from mika.monitoring.models import HealthStatus, InterfaceMetrics, SystemMetrics


@pytest.fixture
def mock_router_client():
    client = Mock()
    
    client.get_system_resource = AsyncMock(
        return_value={
            "identity": "TestRouter",
            "uptime": "1d2h3m",
            "cpu-load": 25,
            "free-memory": 750000000,
            "total-memory": 1000000000,
            "free-hdd-space": 500000000,
            "total-hdd-space": 1000000000,
            "architecture-name": "arm64",
            "board-name": "hEX",
            "version": "7.14.3",
        }
    )
    
    client.get_interfaces = AsyncMock(
        return_value=[
            {
                "name": "ether1",
                "running": "true",
                "disabled": "false",
                "rx-byte": 1000000,
                "tx-byte": 2000000,
                "rx-packet": 1000,
                "tx-packet": 2000,
                "rx-error": 0,
                "tx-error": 0,
                "rx-drop": 0,
                "tx-drop": 0,
            },
            {
                "name": "ether2",
                "running": "true",
                "disabled": "false",
                "rx-byte": 5000000,
                "tx-byte": 3000000,
                "rx-packet": 5000,
                "tx-packet": 3000,
                "rx-error": 0,
                "tx-error": 0,
                "rx-drop": 0,
                "tx-drop": 0,
            },
        ]
    )
    
    return client


class TestHealthCollectorBasics:

    def test_collector_init(self, mock_router_client):
        collector = HealthCollector(mock_router_client)
        assert collector._client is mock_router_client

    @pytest.mark.asyncio
    async def test_collect_healthy_router(self, mock_router_client):
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.status == HealthStatus.HEALTHY
        assert health.router_identity == "TestRouter"
        assert len(health.warnings) == 0
        assert len(health.errors) == 0

    @pytest.mark.asyncio
    async def test_convenience_function(self, mock_router_client):
        health = await collect_health(mock_router_client)
        
        assert isinstance(health.system_metrics, SystemMetrics)
        assert len(health.interface_metrics) == 2


class TestSystemMetrics:

    @pytest.mark.asyncio
    async def test_system_metrics_parsing(self, mock_router_client):
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        metrics = health.system_metrics
        assert metrics.uptime == "1d2h3m"
        assert metrics.cpu_load == 25
        assert metrics.free_memory == 750000000
        assert metrics.total_memory == 1000000000
        assert metrics.memory_usage_percent == 25.0
        assert metrics.architecture == "arm64"
        assert metrics.board_name == "hEX"
        assert metrics.version == "7.14.3"

    @pytest.mark.asyncio
    async def test_memory_usage_calculation(self, mock_router_client):
        mock_router_client.get_system_resource.return_value = {
            "free-memory": 100000000,
            "total-memory": 1000000000,
            "cpu-load": 10,
            "uptime": "1h",
            "architecture-name": "arm",
            "board-name": "test",
            "version": "7.0",
        }
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.system_metrics.memory_usage_percent == 90.0

    @pytest.mark.asyncio
    async def test_cpu_status_property(self, mock_router_client):
        collector = HealthCollector(mock_router_client)
        
        mock_router_client.get_system_resource.return_value["cpu-load"] = 50
        health = await collector.collect()
        assert health.cpu_status == "OK"
        
        mock_router_client.get_system_resource.return_value["cpu-load"] = 80
        health = await collector.collect()
        assert health.cpu_status == "HIGH"
        
        mock_router_client.get_system_resource.return_value["cpu-load"] = 95
        health = await collector.collect()
        assert health.cpu_status == "CRITICAL"

    @pytest.mark.asyncio
    async def test_memory_status_property(self, mock_router_client):
        collector = HealthCollector(mock_router_client)
        
        mock_router_client.get_system_resource.return_value.update({
            "free-memory": 500000000,
            "total-memory": 1000000000,
        })
        health = await collector.collect()
        assert health.memory_status == "OK"
        
        mock_router_client.get_system_resource.return_value.update({
            "free-memory": 100000000,
            "total-memory": 1000000000,
        })
        health = await collector.collect()
        assert health.memory_status == "HIGH"
        
        mock_router_client.get_system_resource.return_value.update({
            "free-memory": 40000000,
            "total-memory": 1000000000,
        })
        health = await collector.collect()
        assert health.memory_status == "CRITICAL"


class TestInterfaceMetrics:

    @pytest.mark.asyncio
    async def test_interface_metrics_parsing(self, mock_router_client):
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert len(health.interface_metrics) == 2
        
        iface = health.interface_metrics[0]
        assert iface.name == "ether1"
        assert iface.running is True
        assert iface.disabled is False
        assert iface.rx_bytes == 1000000
        assert iface.tx_bytes == 2000000
        assert iface.rx_packets == 1000
        assert iface.tx_packets == 2000

    def test_interface_has_errors_property(self):
        iface = InterfaceMetrics(
            name="eth1",
            running=True,
            disabled=False,
            rx_errors=0,
            tx_errors=0,
            rx_drops=0,
            tx_drops=0,
        )
        assert iface.has_errors is False
        
        iface = InterfaceMetrics(
            name="eth1",
            running=True,
            disabled=False,
            rx_errors=5,
            tx_errors=0,
            rx_drops=0,
            tx_drops=0,
        )
        assert iface.has_errors is True
        
        iface = InterfaceMetrics(
            name="eth1",
            running=True,
            disabled=False,
            rx_errors=0,
            tx_errors=0,
            rx_drops=0,
            tx_drops=10,
        )
        assert iface.has_errors is True

    def test_interface_total_traffic_property(self):
        iface = InterfaceMetrics(
            name="eth1",
            running=True,
            disabled=False,
            rx_bytes=1000000,
            tx_bytes=2000000,
        )
        assert iface.total_traffic == 3000000


class TestHealthStatusAssessment:

    @pytest.mark.asyncio
    async def test_healthy_status(self, mock_router_client):
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.status == HealthStatus.HEALTHY
        assert len(health.warnings) == 0
        assert len(health.errors) == 0

    @pytest.mark.asyncio
    async def test_warning_status_high_cpu(self, mock_router_client):
        mock_router_client.get_system_resource.return_value["cpu-load"] = 80
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.status == HealthStatus.WARNING
        assert len(health.warnings) == 1
        assert "High CPU load: 80%" in health.warnings[0]
        assert len(health.errors) == 0

    @pytest.mark.asyncio
    async def test_critical_status_cpu(self, mock_router_client):
        mock_router_client.get_system_resource.return_value["cpu-load"] = 95
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.status == HealthStatus.CRITICAL
        assert len(health.errors) == 1
        assert "Critical CPU load: 95%" in health.errors[0]

    @pytest.mark.asyncio
    async def test_warning_status_high_memory(self, mock_router_client):
        mock_router_client.get_system_resource.return_value.update({
            "free-memory": 100000000,
            "total-memory": 1000000000,
        })
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.status == HealthStatus.WARNING
        assert len(health.warnings) == 1
        assert "High memory usage" in health.warnings[0]

    @pytest.mark.asyncio
    async def test_critical_status_memory(self, mock_router_client):
        mock_router_client.get_system_resource.return_value.update({
            "free-memory": 40000000,
            "total-memory": 1000000000,
        })
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.status == HealthStatus.CRITICAL
        assert len(health.errors) == 1
        assert "Critical memory usage" in health.errors[0]

    @pytest.mark.asyncio
    async def test_critical_status_interface_down(self, mock_router_client):
        mock_router_client.get_interfaces.return_value = [
            {
                "name": "ether1",
                "running": "false",
                "disabled": "false",
                "rx-byte": 0,
                "tx-byte": 0,
                "rx-packet": 0,
                "tx-packet": 0,
                "rx-error": 0,
                "tx-error": 0,
                "rx-drop": 0,
                "tx-drop": 0,
            }
        ]
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.status == HealthStatus.CRITICAL
        assert len(health.errors) == 1
        assert "Interface ether1 is down" in health.errors[0]

    @pytest.mark.asyncio
    async def test_warning_status_interface_errors(self, mock_router_client):
        mock_router_client.get_interfaces.return_value = [
            {
                "name": "ether1",
                "running": "true",
                "disabled": "false",
                "rx-byte": 1000000,
                "tx-byte": 2000000,
                "rx-packet": 1000,
                "tx-packet": 2000,
                "rx-error": 10,
                "tx-error": 5,
                "rx-drop": 2,
                "tx-drop": 3,
            }
        ]
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.status == HealthStatus.WARNING
        assert len(health.warnings) == 1
        assert "Interface ether1 has errors/drops: 20" in health.warnings[0]

    @pytest.mark.asyncio
    async def test_disabled_interface_ignored(self, mock_router_client):
        mock_router_client.get_interfaces.return_value = [
            {
                "name": "ether1",
                "running": "false",
                "disabled": "true",
                "rx-byte": 0,
                "tx-byte": 0,
                "rx-packet": 0,
                "tx-packet": 0,
                "rx-error": 0,
                "tx-error": 0,
                "rx-drop": 0,
                "tx-drop": 0,
            }
        ]
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.status == HealthStatus.HEALTHY
        assert len(health.errors) == 0

    @pytest.mark.asyncio
    async def test_multiple_issues_all_reported(self, mock_router_client):
        mock_router_client.get_system_resource.return_value["cpu-load"] = 95
        mock_router_client.get_system_resource.return_value.update({
            "free-memory": 30000000,
            "total-memory": 1000000000,
        })
        mock_router_client.get_interfaces.return_value = [
            {
                "name": "ether1",
                "running": "false",
                "disabled": "false",
                "rx-byte": 0,
                "tx-byte": 0,
                "rx-packet": 0,
                "tx-packet": 0,
                "rx-error": 0,
                "tx-error": 0,
                "rx-drop": 0,
                "tx-drop": 0,
            }
        ]
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.status == HealthStatus.CRITICAL
        assert len(health.errors) == 3
        assert any("CPU" in e for e in health.errors)
        assert any("memory" in e for e in health.errors)
        assert any("Interface" in e for e in health.errors)


class TestRouterHealthProperties:

    @pytest.mark.asyncio
    async def test_interfaces_down_property(self, mock_router_client):
        mock_router_client.get_interfaces.return_value = [
            {"name": "ether1", "running": "true", "disabled": "false"},
            {"name": "ether2", "running": "false", "disabled": "false"},
            {"name": "ether3", "running": "false", "disabled": "true"},
        ]
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert health.interfaces_down == ["ether2"]

    @pytest.mark.asyncio
    async def test_interfaces_with_errors_property(self, mock_router_client):
        mock_router_client.get_interfaces.return_value = [
            {"name": "ether1", "running": "true", "disabled": "false", "rx-error": 0, "tx-error": 0, "rx-drop": 0, "tx-drop": 0},
            {"name": "ether2", "running": "true", "disabled": "false", "rx-error": 5, "tx-error": 0, "rx-drop": 0, "tx-drop": 0},
            {"name": "ether3", "running": "true", "disabled": "false", "rx-error": 0, "tx-error": 0, "rx-drop": 10, "tx-drop": 0},
        ]
        
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        assert set(health.interfaces_with_errors) == {"ether2", "ether3"}


class TestModelImmutability:

    def test_system_metrics_frozen(self):
        metrics = SystemMetrics(
            uptime="1h",
            cpu_load=50,
            free_memory=500000000,
            total_memory=1000000000,
            memory_usage_percent=50.0,
            architecture="arm",
            board_name="test",
            version="7.0",
        )
        
        with pytest.raises(Exception):
            metrics.cpu_load = 60

    def test_interface_metrics_frozen(self):
        metrics = InterfaceMetrics(
            name="eth1",
            running=True,
            disabled=False,
        )
        
        with pytest.raises(Exception):
            metrics.running = False

    @pytest.mark.asyncio
    async def test_router_health_frozen(self, mock_router_client):
        collector = HealthCollector(mock_router_client)
        health = await collector.collect()
        
        with pytest.raises(Exception):
            health.status = HealthStatus.CRITICAL
