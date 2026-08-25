"""
RouterOS Binary API Client.

Implements the RouterClient protocol using the MikroTik binary API protocol
(port 8728 for plaintext, 8729 for SSL). Compatible with RouterOS v6 and v7.

Supports custom SSL verification, self-signed certificates, and explicit
path mappings between RouterOS v6 and v7. All blocking I/O is dispatched
asynchronously via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import logging
import ssl as _ssl
from pathlib import Path
from typing import Any

from mika.router.errors import (
    RouterApiError,
    RouterAuthenticationError,
    RouterConnectionError,
    RouterTimeoutError,
)
from mika.router.paths import get_resource_mapping, normalize_resource

log = logging.getLogger(__name__)

_DEFAULT_PORT_PLAIN = 8728
_DEFAULT_PORT_SSL = 8729
_DEFAULT_TIMEOUT = 15.0


def _import_librouteros():
    """Import librouteros lazily so the package is optional at import time."""
    try:
        import librouteros
        return librouteros
    except ImportError as exc:
        raise ImportError(
            "librouteros is required for the binary API backend. "
            "Install it with: pip install librouteros"
        ) from exc


def _create_ssl_wrapper(
    ssl_cert_path: str | None = None,
    ssl_verify: bool = False,
):
    """Build an SSL socket wrapper with the specified certificate settings."""
    if ssl_cert_path and Path(ssl_cert_path).is_file():
        try:
            ssl_ctx = _ssl.create_default_context(cafile=ssl_cert_path)
        except _ssl.SSLError as exc:
            raise RouterConnectionError(
                f"Failed to load SSL certificate from {ssl_cert_path!r}: {exc}"
            ) from exc
        ssl_ctx.check_hostname = ssl_verify
        ssl_ctx.verify_mode = _ssl.CERT_REQUIRED if ssl_verify else _ssl.CERT_NONE
    else:
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE

    return ssl_ctx.wrap_socket


def _connect_sync(
    host: str,
    username: str,
    password: str,
    *,
    port: int,
    use_ssl: bool,
    ssl_cert_path: str | None,
    ssl_verify: bool,
    timeout: float,
):
    """Open a synchronous librouteros connection (runs inside to_thread)."""
    lib = _import_librouteros()

    kwargs: dict[str, Any] = {
        "host": host,
        "username": username,
        "password": password,
        "port": port,
        "timeout": timeout,
    }

    if use_ssl:
        kwargs["ssl_wrapper"] = _create_ssl_wrapper(ssl_cert_path, ssl_verify)

    try:
        return lib.connect(**kwargs)
    except lib.exceptions.TrapError as exc:
        msg = str(exc).lower()
        if "invalid user" in msg or "bad credentials" in msg or "login" in msg:
            raise RouterAuthenticationError(
                f"Binary API authentication failed for {host!r}: {exc}"
            ) from exc
        raise RouterApiError(f"Binary API trap error: {exc}") from exc
    except (OSError, ConnectionRefusedError, TimeoutError) as exc:
        raise RouterConnectionError(
            f"Binary API connection failed to {host}:{port} - {exc}"
        ) from exc
    except Exception as exc:
        raise RouterConnectionError(
            f"Binary API unexpected error connecting to {host}:{port} - {exc}"
        ) from exc


def _rows_to_list(rows) -> list[dict]:
    """Convert librouteros sentence rows to a list of plain dicts."""
    return [dict(row) for row in rows]


def _call_sync(api, path: str, **kwargs) -> list[dict]:
    """Execute a binary API call synchronously and return list of dicts."""
    try:
        resource = api.path(*normalize_resource(path).split("/"))
        return _rows_to_list(resource(**kwargs))
    except Exception as exc:
        lib = _import_librouteros()
        if isinstance(exc, lib.exceptions.TrapError):
            raise RouterApiError(f"Binary API error on {path!r}: {exc}") from exc
        raise RouterApiError(f"Unexpected error on {path!r}: {exc}") from exc


def _call_one_sync(api, path: str) -> dict:
    """Execute a binary API call expecting a single dict result."""
    rows = _call_sync(api, path)
    if not rows:
        raise RouterApiError(f"No data returned from {path!r}")
    return rows[0]


class BinaryRouterClient:
    """
    Async RouterClient implementation using the MikroTik binary API protocol.

    Compatible with RouterOS v6 and v7. Connects on port 8728 (plaintext)
    or 8729 (SSL) with support for self-signed certificates or custom CA bundles.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        port: int | None = None,
        use_ssl: bool = False,
        ssl_cert_path: str | None = None,
        ssl_verify: bool = False,
        timeout: float = _DEFAULT_TIMEOUT,
        major_version: int | None = None,
    ) -> None:
        if not host:
            raise ValueError("host must not be empty")
        if not username:
            raise ValueError("username must not be empty")

        self._host = host
        self._username = username
        self._password = password
        self._use_ssl = use_ssl
        self._port = port if port is not None else (_DEFAULT_PORT_SSL if use_ssl else _DEFAULT_PORT_PLAIN)
        self._ssl_cert_path = ssl_cert_path
        self._ssl_verify = ssl_verify
        self._timeout = timeout
        self._major_version = major_version
        self._api = None

    async def _ensure_connected(self):
        """Lazily establish the binary API connection on first use."""
        if self._api is None:
            log.debug(
                "Connecting to binary API at %s:%d (ssl=%s, cert=%s)",
                self._host, self._port, self._use_ssl, self._ssl_cert_path,
            )
            try:
                self._api = await asyncio.wait_for(
                    asyncio.to_thread(
                        _connect_sync,
                        self._host,
                        self._username,
                        self._password,
                        port=self._port,
                        use_ssl=self._use_ssl,
                        ssl_cert_path=self._ssl_cert_path,
                        ssl_verify=self._ssl_verify,
                        timeout=self._timeout,
                    ),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError as exc:
                raise RouterTimeoutError(
                    f"Binary API connection timed out after {self._timeout}s: "
                    f"{self._host}:{self._port}"
                ) from exc

    async def __aenter__(self) -> "BinaryRouterClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._api is not None:
            try:
                await asyncio.to_thread(self._api.close)
            except Exception:
                pass
            finally:
                self._api = None

    def _resolve_path(self, resource: str) -> str:
        """Resolve the appropriate path according to router major version."""
        major = self._major_version if self._major_version is not None else 7
        mapping = get_resource_mapping(resource, major)
        if not mapping.supported:
            log.warning("Resource %r is marked unsupported for v%d: %s", resource, major, mapping.notes)
        return mapping.path

    async def _call(self, path: str, **kwargs) -> list[dict]:
        await self._ensure_connected()
        resolved_path = self._resolve_path(path)
        try:
            return await asyncio.to_thread(_call_sync, self._api, resolved_path, **kwargs)
        except (RouterApiError, RouterAuthenticationError, RouterConnectionError, RouterTimeoutError):
            raise
        except Exception as exc:
            raise RouterApiError(f"Binary API call failed on {resolved_path!r}: {exc}") from exc

    async def _call_one(self, path: str) -> dict:
        await self._ensure_connected()
        resolved_path = self._resolve_path(path)
        try:
            return await asyncio.to_thread(_call_one_sync, self._api, resolved_path)
        except (RouterApiError, RouterAuthenticationError, RouterConnectionError, RouterTimeoutError):
            raise
        except Exception as exc:
            raise RouterApiError(f"Binary API call failed on {resolved_path!r}: {exc}") from exc

    
    # Protocol Read Operations
    

    async def get_system_resource(self) -> dict:
        return await self._call_one("/system/resource")

    async def get_interfaces(self) -> list[dict]:
        return await self._call("/interface")

    async def get_addresses(self) -> list[dict]:
        return await self._call("/ip/address")

    async def get_routes(self) -> list[dict]:
        return await self._call("/ip/route")

    async def get_firewall_rules(self) -> list[dict]:
        return await self._call("/ip/firewall/filter")

    async def get_dhcp_servers(self) -> list[dict]:
        return await self._call("/ip/dhcp-server")

    async def get_dhcp_leases(self) -> list[dict]:
        return await self._call("/ip/dhcp-server/lease")

    async def get_hotspot_servers(self) -> list[dict]:
        return await self._call("/ip/hotspot")

    async def get_hotspot_users(self) -> list[dict]:
        return await self._call("/ip/hotspot/user")


    # Protocol Write Operations

    async def create_resource(self, resource: str, data: dict) -> dict:
        """Create a new resource entry via binary API (equivalent to PUT in REST)."""
        await self._ensure_connected()
        target_path = self._resolve_path(resource)

        def _do_add() -> dict:
            try:
                resource_path = self._api.path(*normalize_resource(target_path).split("/"))
                result = resource_path.add(**data)
                new_id = result if isinstance(result, str) else str(result)
                return {".id": new_id, **data}
            except Exception as exc:
                lib = _import_librouteros()
                if isinstance(exc, lib.exceptions.TrapError):
                    raise RouterApiError(f"Binary API add failed on {target_path!r}: {exc}") from exc
                raise RouterApiError(f"Unexpected add error on {target_path!r}: {exc}") from exc

        return await asyncio.to_thread(_do_add)

    async def update_resource(self, resource: str, resource_id: str, data: dict) -> dict:
        """Update an existing resource entry via binary API (equivalent to PATCH in REST)."""
        await self._ensure_connected()
        target_path = self._resolve_path(resource)

        def _do_update() -> dict:
            try:
                resource_path = self._api.path(*normalize_resource(target_path).split("/"))
                resource_path.update(**{".id": resource_id, **data})
                return {".id": resource_id, **data}
            except Exception as exc:
                lib = _import_librouteros()
                if isinstance(exc, lib.exceptions.TrapError):
                    msg = str(exc)
                    if "no such item" in msg.lower():
                        raise RouterApiError(
                            f"no such item: {resource_id}", code="no such item"
                        ) from exc
                    raise RouterApiError(f"Binary API update failed on {target_path!r}: {exc}") from exc
                raise RouterApiError(f"Unexpected update error on {target_path!r}: {exc}") from exc

        return await asyncio.to_thread(_do_update)

    async def delete_resource(self, resource: str, resource_id: str) -> None:
        """Delete a resource entry via binary API (equivalent to DELETE in REST)."""
        await self._ensure_connected()
        target_path = self._resolve_path(resource)

        def _do_remove() -> None:
            try:
                resource_path = self._api.path(*normalize_resource(target_path).split("/"))
                resource_path.remove(resource_id)
            except Exception as exc:
                lib = _import_librouteros()
                if isinstance(exc, lib.exceptions.TrapError):
                    msg = str(exc)
                    if "no such item" in msg.lower():
                        raise RouterApiError(
                            f"no such item: {resource_id}", code="no such item"
                        ) from exc
                    raise RouterApiError(f"Binary API remove failed on {target_path!r}: {exc}") from exc
                raise RouterApiError(f"Unexpected remove error on {target_path!r}: {exc}") from exc

        await asyncio.to_thread(_do_remove)
