"""
RouterClient Protocol.

Defines the abstract asynchronous interface for communicating with
MikroTik RouterOS devices across different backends (REST API, Mock, etc.).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RouterClient(Protocol):


    async def get_system_resource(self) -> dict:
        ...

    async def get_interfaces(self) -> list[dict]:
        ...

    async def get_addresses(self) -> list[dict]:
        ...

    async def get_routes(self) -> list[dict]:
        ...

    async def get_firewall_rules(self) -> list[dict]:
        ...

    async def get_dhcp_servers(self) -> list[dict]:
        ...

    async def get_dhcp_leases(self) -> list[dict]:
        ...

    async def get_hotspot_servers(self) -> list[dict]:
        ...

    async def get_hotspot_users(self) -> list[dict]:
        ...


    async def create_resource(self, resource: str, data: dict) -> dict:
        ...

    async def update_resource(self, resource: str, resource_id: str, data: dict) -> dict:
        ...

    async def delete_resource(self, resource: str, resource_id: str) -> None:
        ...
