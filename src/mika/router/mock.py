"""
In-Memory Mock Router Client.

Simulates RouterOS state and operations in-memory for testing without
physical hardware. Supports fault injection (simulating timeouts, errors)
to test retry, rollback, and recovery mechanisms.
"""

from __future__ import annotations

import copy

from mika.router.errors import RouterApiError, RouterConnectionError
from mika.router.profile import RouterProfile


class MockRouterClient:
    """In-memory RouterClient implementation for hardware-free testing."""

    def __init__(self, profile: RouterProfile) -> None:
        self._profile = profile
        self._connected = True
        self._pending_failures: dict[str, Exception] = {}


    def queue_failure(self, method: str, exc: Exception) -> None:
        """Queue a one-shot exception to be raised on the next call to `method`."""
        self._pending_failures[method] = exc

    def clear_failure(self, method: str) -> None:
        self._pending_failures.pop(method, None)

    def sever_connection(self) -> None:
        """Simulate total connection loss to the router."""
        self._connected = False

    def restore_connection(self) -> None:
        """Restore simulated router connection."""
        self._connected = True


    async def _check(self, method: str) -> None:
        if not self._connected:
            raise RouterConnectionError(f"{method}: connection lost")
        if method in self._pending_failures:
            raise self._pending_failures.pop(method)

    _RESOURCE_TABLES = {
        "/interface": "interfaces",
        "/ip/address": "addresses",
        "/ip/route": "routes",
        "/ip/firewall/filter": "firewall_rules",
        "/ip/dhcp-server": "dhcp_servers",
        "/ip/dhcp-server/lease": "dhcp_leases",
        "/ip/hotspot": "hotspot_servers",
        "/ip/hotspot/user": "hotspot_users",
    }

    def _table(self, resource: str) -> list[dict]:
        attr = self._RESOURCE_TABLES.get(resource)
        if attr is None:
            raise RouterApiError(f"unknown resource path: {resource!r}")
        return getattr(self._profile, attr)

    @staticmethod
    def _next_id(table: list[dict]) -> str:
        return f"*{len(table) + 1:X}"


    async def get_system_resource(self) -> dict:
        await self._check("get_system_resource")
        return copy.deepcopy(self._profile.system_resource)

    async def get_interfaces(self) -> list[dict]:
        await self._check("get_interfaces")
        return copy.deepcopy(self._profile.interfaces)

    async def get_addresses(self) -> list[dict]:
        await self._check("get_addresses")
        return copy.deepcopy(self._profile.addresses)

    async def get_routes(self) -> list[dict]:
        await self._check("get_routes")
        return copy.deepcopy(self._profile.routes)

    async def get_firewall_rules(self) -> list[dict]:
        await self._check("get_firewall_rules")
        return copy.deepcopy(self._profile.firewall_rules)

    async def get_dhcp_servers(self) -> list[dict]:
        await self._check("get_dhcp_servers")
        return copy.deepcopy(self._profile.dhcp_servers)

    async def get_dhcp_leases(self) -> list[dict]:
        await self._check("get_dhcp_leases")
        return copy.deepcopy(self._profile.dhcp_leases)

    async def get_hotspot_servers(self) -> list[dict]:
        await self._check("get_hotspot_servers")
        return copy.deepcopy(self._profile.hotspot_servers)

    async def get_hotspot_users(self) -> list[dict]:
        await self._check("get_hotspot_users")
        return copy.deepcopy(self._profile.hotspot_users)


    async def create_resource(self, resource: str, data: dict) -> dict:
        await self._check("create_resource")
        table = self._table(resource)
        record = {".id": self._next_id(table), **data}
        table.append(record)
        return copy.deepcopy(record)

    async def update_resource(self, resource: str, resource_id: str, data: dict) -> dict:
        await self._check("update_resource")
        table = self._table(resource)
        for record in table:
            if record.get(".id") == resource_id:
                record.update(data)
                return copy.deepcopy(record)
        raise RouterApiError(f"no such item: {resource_id}", code="no such item")

    async def delete_resource(self, resource: str, resource_id: str) -> None:
        await self._check("delete_resource")
        table = self._table(resource)
        for i, record in enumerate(table):
            if record.get(".id") == resource_id:
                del table[i]
                return
        raise RouterApiError(f"no such item: {resource_id}", code="no such item")
