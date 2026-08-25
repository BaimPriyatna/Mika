"""
Router Health & Telemetry Collector.

Collects periodic metrics from RouterOS (CPU load, memory, disk usage,
and interface link/traffic states) and evaluates health statuses.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mika.monitoring.models import (
    HealthStatus,
    InterfaceMetrics,
    RouterHealth,
    SystemMetrics,
)

if TYPE_CHECKING:
    from mika.router.client import RouterClient

logger = logging.getLogger(__name__)


class HealthCollector:

    def __init__(self, router_client: RouterClient) -> None:
        self._client = router_client

    async def collect(self) -> RouterHealth:
        logger.debug("Collecting router health metrics")

        system_resource = await self._client.get_system_resource()
        system_metrics = self._parse_system_metrics(system_resource)

        interfaces = await self._client.get_interfaces()
        interface_metrics = tuple(self._parse_interface_metrics(iface) for iface in interfaces)

        warnings: list[str] = []
        errors: list[str] = []
        
        status = self._assess_health(
            system_metrics,
            interface_metrics,
            warnings,
            errors,
        )

        router_identity = system_resource.get("identity", system_metrics.board_name)

        health = RouterHealth(
            router_identity=router_identity,
            status=status,
            system_metrics=system_metrics,
            interface_metrics=interface_metrics,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

        logger.info(
            f"Health collected for {router_identity}: {status.value}, "
            f"{len(warnings)} warnings, {len(errors)} errors"
        )

        return health

    def _parse_system_metrics(self, resource: dict) -> SystemMetrics:
        free_memory = self._parse_int(resource.get("free-memory"), default=0)
        total_memory = self._parse_int(resource.get("total-memory"), default=1)

        memory_usage_percent = 0.0
        if total_memory > 0:
            memory_usage_percent = ((total_memory - free_memory) / total_memory) * 100

        return SystemMetrics(
            uptime=str(resource.get("uptime", "0s")),
            cpu_load=self._parse_int(resource.get("cpu-load"), default=0),
            free_memory=free_memory,
            total_memory=total_memory,
            memory_usage_percent=round(memory_usage_percent, 2),
            free_hdd_space=self._parse_int(resource.get("free-hdd-space")),
            total_hdd_space=self._parse_int(resource.get("total-hdd-space")),
            architecture=str(resource.get("architecture-name", "unknown")),
            board_name=str(resource.get("board-name", "unknown")),
            version=str(resource.get("version", "unknown")),
        )

    def _parse_interface_metrics(self, iface: dict) -> InterfaceMetrics:
        return InterfaceMetrics(
            name=str(iface.get("name", "")),
            running=self._parse_bool(iface.get("running"), default=True),
            disabled=self._parse_bool(iface.get("disabled"), default=False),
            rx_bytes=self._parse_int(iface.get("rx-byte"), default=0),
            tx_bytes=self._parse_int(iface.get("tx-byte"), default=0),
            rx_packets=self._parse_int(iface.get("rx-packet"), default=0),
            tx_packets=self._parse_int(iface.get("tx-packet"), default=0),
            rx_errors=self._parse_int(iface.get("rx-error"), default=0),
            tx_errors=self._parse_int(iface.get("tx-error"), default=0),
            rx_drops=self._parse_int(iface.get("rx-drop"), default=0),
            tx_drops=self._parse_int(iface.get("tx-drop"), default=0),
        )

    def _assess_health(
        self,
        system: SystemMetrics,
        interfaces: tuple[InterfaceMetrics, ...],
        warnings: list[str],
        errors: list[str],
    ) -> HealthStatus:
        if system.cpu_load >= 90:
            errors.append(f"Critical CPU load: {system.cpu_load}%")
        elif system.cpu_load >= 75:
            warnings.append(f"High CPU load: {system.cpu_load}%")

        if system.memory_usage_percent >= 95:
            errors.append(f"Critical memory usage: {system.memory_usage_percent:.1f}%")
        elif system.memory_usage_percent >= 85:
            warnings.append(f"High memory usage: {system.memory_usage_percent:.1f}%")

        if system.free_hdd_space is not None and system.total_hdd_space is not None:
            if system.total_hdd_space > 0:
                disk_usage_percent = (
                    (system.total_hdd_space - system.free_hdd_space)
                    / system.total_hdd_space
                ) * 100
                
                if disk_usage_percent >= 95:
                    errors.append(f"Critical disk usage: {disk_usage_percent:.1f}%")
                elif disk_usage_percent >= 85:
                    warnings.append(f"High disk usage: {disk_usage_percent:.1f}%")

        for iface in interfaces:
            if iface.disabled:
                continue

            if not iface.running:
                errors.append(f"Interface {iface.name} is down")

            if iface.has_errors:
                total_errors = (
                    iface.rx_errors + iface.tx_errors + iface.rx_drops + iface.tx_drops
                )
                warnings.append(
                    f"Interface {iface.name} has errors/drops: {total_errors}"
                )

        if errors:
            return HealthStatus.CRITICAL
        elif warnings:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

    def _parse_int(self, value: any, default: int | None = None) -> int | None:
        if value is None:
            return default
        try:
            return int(str(value).strip())
        except (ValueError, TypeError):
            return default

    def _parse_bool(self, value: any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("true", "yes", "1"):
                return True
            if v in ("false", "no", "0"):
                return False
        return default


async def collect_health(router_client: RouterClient) -> RouterHealth:
    collector = HealthCollector(router_client)
    return await collector.collect()
