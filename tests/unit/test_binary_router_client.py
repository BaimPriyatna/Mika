"""
Unit tests for BinaryRouterClient and Version Path Mapping.

Covers:
- Version path resolution (v6 vs v7 mappings)
- Plaintext vs SSL vs Custom CA certificate options
- CRUD operations via librouteros mock
- Error mapping (authentication, trap errors, connection errors)
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from mika.router.binary import (
    BinaryRouterClient,
    _create_ssl_wrapper,
    _rows_to_list,
)
from mika.router.errors import (
    RouterApiError,
    RouterAuthenticationError,
    RouterConnectionError,
)
from mika.router.paths import (
    V6_RESOURCE_PATHS,
    V7_RESOURCE_PATHS,
    get_resource_mapping,
    is_resource_supported,
)


# ---------------------------------------------------------------------------
# Version Path Mapping Tests
# ---------------------------------------------------------------------------

def test_v6_vs_v7_path_mapping():
    # WireGuard: unsupported in v6, supported in v7
    v6_wg = get_resource_mapping("interface/wireguard", major_version=6)
    assert not v6_wg.supported

    v7_wg = get_resource_mapping("interface/wireguard", major_version=7)
    assert v7_wg.supported

    # Wireless / Wifi
    assert not is_resource_supported("interface/wifi", major_version=6)
    assert is_resource_supported("interface/wifi", major_version=7)
    assert is_resource_supported("interface/wireless", major_version=6)

    # Standard routes & firewall supported on both
    assert is_resource_supported("ip/route", major_version=6)
    assert is_resource_supported("ip/route", major_version=7)
    assert is_resource_supported("ip/firewall/filter", major_version=6)
    assert is_resource_supported("ip/firewall/filter", major_version=7)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_api_mock(responses: dict[str, list[dict]]) -> MagicMock:
    api = MagicMock()

    def _path(*parts):
        resource = MagicMock()
        key = "/".join(parts)
        rows = responses.get(key, [])

        def _call(**kwargs):
            return rows

        resource.side_effect = _call
        resource.__call__ = _call
        resource.__iter__ = lambda s: iter(rows)
        resource.add = MagicMock(return_value="*1")
        resource.update = MagicMock()
        resource.remove = MagicMock()
        return resource

    api.path = _path
    api.close = MagicMock()
    return api


async def _make_connected_client(api_mock, major_version: int = 7) -> BinaryRouterClient:
    client = BinaryRouterClient("192.168.1.1", "admin", "secret", major_version=major_version)
    client._api = api_mock
    return client


# ---------------------------------------------------------------------------
# Construction & SSL Configuration Tests
# ---------------------------------------------------------------------------

def test_default_ports_and_flags():
    client_plain = BinaryRouterClient("192.168.1.1", "admin", "pass")
    assert client_plain._port == 8728
    assert client_plain._use_ssl is False

    client_ssl = BinaryRouterClient("192.168.1.1", "admin", "pass", use_ssl=True)
    assert client_ssl._port == 8729
    assert client_ssl._use_ssl is True


def test_ssl_wrapper_builder(tmp_path):
    # Self-signed context (no cert file)
    wrapper_self_signed = _create_ssl_wrapper(ssl_cert_path=None, ssl_verify=False)
    assert callable(wrapper_self_signed)

    # Invalid cert file should raise RouterConnectionError
    bad_cert = tmp_path / "corrupt.crt"
    bad_cert.write_text("NOT A VALID CERTIFICATE")

    with pytest.raises(RouterConnectionError, match="Failed to load SSL certificate"):
        _create_ssl_wrapper(ssl_cert_path=str(bad_cert), ssl_verify=False)


# ---------------------------------------------------------------------------
# Read Operations via Mock
# ---------------------------------------------------------------------------

MOCK_SYSTEM = {"version": "7.15.3 (stable)", "board-name": "CHR", "uptime": "2d"}
MOCK_INTERFACES = [
    {".id": "*1", "name": "ether1", "type": "ether", "running": "true", "disabled": "false"},
    {".id": "*2", "name": "ether2", "type": "ether", "running": "true", "disabled": "false"},
]


@pytest.mark.asyncio
async def test_get_system_resource():
    api = _make_api_mock({"system/resource": [MOCK_SYSTEM]})
    client = await _make_connected_client(api)
    res = await client.get_system_resource()
    assert res["board-name"] == "CHR"


@pytest.mark.asyncio
async def test_get_interfaces():
    api = _make_api_mock({"interface": MOCK_INTERFACES})
    client = await _make_connected_client(api)
    ifaces = await client.get_interfaces()
    assert len(ifaces) == 2
    assert ifaces[0]["name"] == "ether1"


# ---------------------------------------------------------------------------
# Write Operations via Mock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_resource():
    api = MagicMock()
    res_mock = MagicMock()
    res_mock.add = MagicMock(return_value="*10")
    api.path = MagicMock(return_value=res_mock)
    api.close = MagicMock()

    client = await _make_connected_client(api)
    res = await client.create_resource("/ip/address", {"address": "10.10.10.1/24", "interface": "ether1"})
    assert res[".id"] == "*10"
    assert res["address"] == "10.10.10.1/24"


@pytest.mark.asyncio
async def test_update_resource():
    api = MagicMock()
    res_mock = MagicMock()
    res_mock.update = MagicMock()
    api.path = MagicMock(return_value=res_mock)
    api.close = MagicMock()

    client = await _make_connected_client(api)
    res = await client.update_resource("/ip/address", "*10", {"comment": "updated"})
    assert res[".id"] == "*10"
    res_mock.update.assert_called_once_with(**{".id": "*10", "comment": "updated"})


@pytest.mark.asyncio
async def test_delete_resource():
    api = MagicMock()
    res_mock = MagicMock()
    res_mock.remove = MagicMock()
    api.path = MagicMock(return_value=res_mock)
    api.close = MagicMock()

    client = await _make_connected_client(api)
    await client.delete_resource("/ip/address", "*10")
    res_mock.remove.assert_called_once_with("*10")


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trap_error_handled():
    import librouteros.exceptions

    api = MagicMock()
    res_mock = MagicMock()
    res_mock.side_effect = librouteros.exceptions.TrapError("syntax error in command")
    res_mock.__call__ = res_mock.side_effect
    api.path = MagicMock(return_value=res_mock)
    api.close = MagicMock()

    client = await _make_connected_client(api)
    with pytest.raises(RouterApiError, match="Binary API error"):
        await client.get_routes()
