from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(str, Enum):

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class SystemMetrics(BaseModel):

    model_config = ConfigDict(frozen=True)

    uptime: str = Field(description="Router uptime string (e.g. '3d4h5m')")
    cpu_load: int = Field(ge=0, le=100, description="CPU load percentage")
    free_memory: int = Field(ge=0, description="Free memory in bytes")
    total_memory: int = Field(ge=0, description="Total memory in bytes")
    memory_usage_percent: float = Field(
        ge=0.0,
        le=100.0,
        description="Memory usage percentage",
    )
    free_hdd_space: int | None = Field(
        default=None,
        ge=0,
        description="Free disk space in bytes",
    )
    total_hdd_space: int | None = Field(
        default=None,
        ge=0,
        description="Total disk space in bytes",
    )
    architecture: str = Field(description="CPU architecture")
    board_name: str = Field(description="Board/hardware name")
    version: str = Field(description="RouterOS version")


class InterfaceMetrics(BaseModel):

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Interface name")
    running: bool = Field(description="Interface is operationally up")
    disabled: bool = Field(description="Interface is administratively disabled")
    rx_bytes: int = Field(ge=0, default=0, description="Received bytes")
    tx_bytes: int = Field(ge=0, default=0, description="Transmitted bytes")
    rx_packets: int = Field(ge=0, default=0, description="Received packets")
    tx_packets: int = Field(ge=0, default=0, description="Transmitted packets")
    rx_errors: int = Field(ge=0, default=0, description="Receive errors")
    tx_errors: int = Field(ge=0, default=0, description="Transmit errors")
    rx_drops: int = Field(ge=0, default=0, description="Receive drops")
    tx_drops: int = Field(ge=0, default=0, description="Transmit drops")

    @property
    def has_errors(self) -> bool:
        return (
            self.rx_errors > 0
            or self.tx_errors > 0
            or self.rx_drops > 0
            or self.tx_drops > 0
        )

    @property
    def total_traffic(self) -> int:
        return self.rx_bytes + self.tx_bytes


class RouterHealth(BaseModel):

    model_config = ConfigDict(frozen=True)

    router_identity: str = Field(description="Router hostname/identity")
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When metrics were collected",
    )
    status: HealthStatus = Field(description="Overall health status")
    system_metrics: SystemMetrics
    interface_metrics: tuple[InterfaceMetrics, ...] = Field(default_factory=tuple)

    warnings: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Health warnings (e.g. high CPU, low memory)",
    )
    errors: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Critical errors (e.g. interface down, no memory)",
    )

    @property
    def cpu_status(self) -> str:
        if self.system_metrics.cpu_load >= 90:
            return "CRITICAL"
        elif self.system_metrics.cpu_load >= 75:
            return "HIGH"
        return "OK"

    @property
    def memory_status(self) -> str:
        if self.system_metrics.memory_usage_percent >= 95:
            return "CRITICAL"
        elif self.system_metrics.memory_usage_percent >= 85:
            return "HIGH"
        return "OK"

    @property
    def interfaces_down(self) -> list[str]:
        return [
            iface.name
            for iface in self.interface_metrics
            if not iface.disabled and not iface.running
        ]

    @property
    def interfaces_with_errors(self) -> list[str]:
        return [iface.name for iface in self.interface_metrics if iface.has_errors]
