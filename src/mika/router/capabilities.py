"""
RouterOS Feature and Capability Flags.

Enumerates supported features and compatibility matrices between
RouterOS v6 and v7 configurations.
"""

from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class RouterCapabilities(BaseModel):

    model_config = ConfigDict(frozen=True)

    version: str = Field(description="Full version string, e.g. '7.15.3 (stable)'.")
    major_version: int = Field(description="RouterOS major version: 6 or 7.")
    architecture: str = Field(description="CPU architecture (e.g. 'arm', 'mipsbe', 'x86_64').")
    board_name: str = Field(description="Hardware board name or platform (e.g. 'RB750Gr3', 'CHR').")

    supports_rest_api: bool = Field(
        description="True for RouterOS v7+ which natively provides /rest/ API.",
    )
    supports_wireguard: bool = Field(
        description="True for RouterOS v7+ which includes native WireGuard support.",
    )
    supports_container: bool = Field(
        description="True for RouterOS v7+ on supported architectures (arm, arm64, x86).",
    )
    supports_hotspot: bool = Field(
        default=True,
        description="Hotspot server support (universal across standard RouterOS).",
    )
    supports_vlan_filtering: bool = Field(
        description="True for RouterOS v6.42+ bridge VLAN filtering (standard in v7).",
    )
    has_wireless: bool = Field(
        default=False,
        description="Whether router has physical or virtual wireless interfaces.",
    )

    cpu_count: int = Field(ge=1, default=1)
    total_memory_bytes: int = Field(ge=0, default=0)
    free_memory_bytes: int = Field(ge=0, default=0)

    @property
    def is_v7(self) -> bool:
        return self.major_version >= 7

    @property
    def is_v6(self) -> bool:
        return self.major_version == 6


def parse_major_version(version_str: str) -> int:
    match = re.match(r"^(\d+)", version_str.strip())
    if match:
        return int(match.group(1))
    return 7


def detect_capabilities(
    system_resource: dict[str, Any],
    interfaces: list[dict[str, Any]] | None = None,
) -> RouterCapabilities:
    raw_version = str(system_resource.get("version", "7.0"))
    major = parse_major_version(raw_version)
    arch = str(system_resource.get("architecture-name", "unknown")).lower()
    board = str(system_resource.get("board-name", system_resource.get("platform", "unknown")))

    cpu_count_str = str(system_resource.get("cpu-count", "1"))
    try:
        cpu_count = max(1, int(cpu_count_str))
    except ValueError:
        cpu_count = 1

    try:
        total_mem = int(system_resource.get("total-memory", 0))
    except (ValueError, TypeError):
        total_mem = 0

    try:
        free_mem = int(system_resource.get("free-memory", 0))
    except (ValueError, TypeError):
        free_mem = 0

    supports_rest = major >= 7
    supports_wg = major >= 7
    supports_container = major >= 7 and arch in ("arm", "arm64", "x86_64", "x86")
    supports_vlan_filt = major >= 7 or (major == 6 and "6.4" in raw_version)

    has_wlan = False
    if interfaces:
        has_wlan = any(
            str(iface.get("type", "")).lower() in ("wlan", "wifi", "wireless")
            for iface in interfaces
        )

    return RouterCapabilities(
        version=raw_version,
        major_version=major,
        architecture=arch,
        board_name=board,
        supports_rest_api=supports_rest,
        supports_wireguard=supports_wg,
        supports_container=supports_container,
        supports_hotspot=True,
        supports_vlan_filtering=supports_vlan_filt,
        has_wireless=has_wlan,
        cpu_count=cpu_count,
        total_memory_bytes=total_mem,
        free_memory_bytes=free_mem,
    )
