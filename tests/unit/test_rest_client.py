from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mika.router.errors import (
    RouterApiError,
    RouterAuthenticationError,
    RouterConnectionError,
    RouterPermissionError,
    RouterTimeoutError,
)
from mika.router.rest import RestRouterClient, _READ_MAX_RETRIES


def _make_response(
    status_code: int = 200,
    body: Any = None,
    *,
    content_type: str = "application/json",
) -> httpx.Response:
    raw_body = json.dumps(body).encode() if body is not None else b""
    return httpx.Response(
        status_code=status_code,
        headers={"content-type": content_type},
        content=raw_body,
    )


def _client(host: str = "10.0.0.1", **kwargs) -> RestRouterClient:
    return RestRouterClient(host, "admin", "pass", **kwargs)


def _patch_request(client: RestRouterClient, responses: list[httpx.Response] | httpx.Response):
    if isinstance(responses, httpx.Response):
        responses = [responses]
    mock_request = AsyncMock(side_effect=responses)
    mock_httpx_client = MagicMock()
    mock_httpx_client.request = mock_request
    client._client = mock_httpx_client
    return mock_request


class TestConstructor:

    def test_empty_host_rejected(self):
        with pytest.raises(ValueError, match="host"):
            RestRouterClient("", "admin", "pass")

    def test_empty_username_rejected(self):
        with pytest.raises(ValueError, match="username"):
            RestRouterClient("10.0.0.1", "", "pass")

    def test_defaults(self):
        c = _client()
        assert "10.0.0.1:443" in c._base_url
        assert c._timeout == 15.0
        assert c._verify is True

    def test_custom_port_and_timeout(self):
        c = RestRouterClient("r1", "admin", "pass", port=8443, timeout=30.0)
        assert "r1:8443" in c._base_url
        assert c._timeout == 30.0

    def test_verify_false(self):
        c = RestRouterClient("r1", "admin", "pass", verify=False)
        assert c._verify is False


class TestUrlConstruction:

    def test_resource_only(self):
        c = _client()
        assert c._url("/ip/address") == "https://10.0.0.1:443/rest/ip/address"

    def test_resource_with_id(self):
        c = _client()
        assert c._url("/ip/address", "*1") == "https://10.0.0.1:443/rest/ip/address/*1"

    def test_leading_slash_stripped(self):
        c = _client()
        assert "/rest//ip" not in c._url("/ip/address")


class TestReadMethods:

    @pytest.mark.asyncio
    async def test_get_system_resource(self):
        c = _client()
        payload = {"version": "7.14.3", "board-name": "hEX"}
        _patch_request(c, _make_response(200, payload))
        result = await c.get_system_resource()
        assert result["version"] == "7.14.3"

    @pytest.mark.asyncio
    async def test_get_interfaces(self):
        c = _client()
        payload = [{"name": "ether1", ".id": "*1"}, {"name": "ether2", ".id": "*2"}]
        _patch_request(c, _make_response(200, payload))
        result = await c.get_interfaces()
        assert len(result) == 2
        assert result[0]["name"] == "ether1"

    @pytest.mark.asyncio
    async def test_get_addresses(self):
        c = _client()
        _patch_request(c, _make_response(200, [{"address": "192.168.1.1/24", ".id": "*1"}]))
        result = await c.get_addresses()
        assert result[0]["address"] == "192.168.1.1/24"

    @pytest.mark.asyncio
    async def test_get_routes(self):
        c = _client()
        _patch_request(c, _make_response(200, [{"dst-address": "0.0.0.0/0", ".id": "*1"}]))
        result = await c.get_routes()
        assert result[0]["dst-address"] == "0.0.0.0/0"

    @pytest.mark.asyncio
    async def test_get_firewall_rules(self):
        c = _client()
        _patch_request(c, _make_response(200, [{"action": "accept", ".id": "*1"}]))
        result = await c.get_firewall_rules()
        assert result[0]["action"] == "accept"

    @pytest.mark.asyncio
    async def test_get_dhcp_servers(self):
        c = _client()
        _patch_request(c, _make_response(200, [{"name": "dhcp1", ".id": "*1"}]))
        result = await c.get_dhcp_servers()
        assert result[0]["name"] == "dhcp1"

    @pytest.mark.asyncio
    async def test_get_dhcp_leases(self):
        c = _client()
        _patch_request(c, _make_response(200, [{"mac-address": "AA:BB:CC:DD:EE:FF", ".id": "*1"}]))
        result = await c.get_dhcp_leases()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_hotspot_servers(self):
        c = _client()
        _patch_request(c, _make_response(200, [{"name": "hotspot1", ".id": "*1"}]))
        result = await c.get_hotspot_servers()
        assert result[0]["name"] == "hotspot1"

    @pytest.mark.asyncio
    async def test_get_hotspot_users(self):
        c = _client()
        _patch_request(c, _make_response(200, [{"name": "user1", ".id": "*1"}]))
        result = await c.get_hotspot_users()
        assert len(result) == 1


class TestMutationMethods:

    @pytest.mark.asyncio
    async def test_create_resource(self):
        c = _client()
        created = {"interface": "ether3", "address": "192.168.20.1/24", ".id": "*5"}
        _patch_request(c, _make_response(201, created))
        result = await c.create_resource("/ip/address", {"address": "192.168.20.1/24", "interface": "ether3"})
        assert result[".id"] == "*5"
        assert result["address"] == "192.168.20.1/24"

    @pytest.mark.asyncio
    async def test_update_resource(self):
        c = _client()
        updated = {"address": "192.168.20.2/24", ".id": "*5"}
        _patch_request(c, _make_response(200, updated))
        result = await c.update_resource("/ip/address", "*5", {"address": "192.168.20.2/24"})
        assert result["address"] == "192.168.20.2/24"

    @pytest.mark.asyncio
    async def test_delete_resource(self):
        c = _client()
        _patch_request(c, _make_response(204))
        await c.delete_resource("/ip/address", "*5")


class TestErrorMapping:

    @pytest.mark.asyncio
    async def test_401_raises_authentication_error(self):
        c = _client()
        _patch_request(c, _make_response(401, {"detail": "invalid credentials"}))
        with pytest.raises(RouterAuthenticationError, match="Authentication failed"):
            await c.get_interfaces()

    @pytest.mark.asyncio
    async def test_403_raises_permission_error(self):
        c = _client()
        _patch_request(c, _make_response(403, {"detail": "not allowed"}))
        with pytest.raises(RouterPermissionError, match="Permission denied"):
            await c.get_addresses()

    @pytest.mark.asyncio
    async def test_404_raises_api_error(self):
        c = _client()
        _patch_request(c, _make_response(404, {"detail": "no such item"}))
        with pytest.raises(RouterApiError, match="404"):
            await c.get_routes()

    @pytest.mark.asyncio
    async def test_500_raises_api_error(self):
        c = _client()
        _patch_request(c, _make_response(500, {"detail": "internal error"}))
        with pytest.raises(RouterApiError, match="500"):
            await c.get_firewall_rules()

    @pytest.mark.asyncio
    async def test_timeout_raises_timeout_error(self):
        c = _client()
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        c._client = mock_client
        with pytest.raises(RouterTimeoutError):
            await c.create_resource("/ip/address", {"address": "1.2.3.4/24"})

    @pytest.mark.asyncio
    async def test_connect_error_raises_connection_error(self):
        c = _client()
        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        c._client = mock_client
        with pytest.raises(RouterConnectionError):
            await c.get_system_resource()

    @pytest.mark.asyncio
    async def test_non_json_body_raises_api_error(self):
        c = _client()
        _patch_request(c, httpx.Response(200, content=b"not json at all", headers={"content-type": "text/plain"}))
        with pytest.raises(RouterApiError, match="Non-JSON"):
            await c.get_system_resource()

    @pytest.mark.asyncio
    async def test_list_endpoint_returning_object_raises_api_error(self):
        c = _client()
        _patch_request(c, _make_response(200, {"error": "weird"}))
        with pytest.raises(RouterApiError, match="Expected list"):
            await c.get_interfaces()

    @pytest.mark.asyncio
    async def test_object_endpoint_returning_list_raises_api_error(self):
        c = _client()
        _patch_request(c, _make_response(200, [{"a": 1}]))
        with pytest.raises(RouterApiError, match="Expected dict"):
            await c.get_system_resource()


class TestRetryPolicy:

    @pytest.mark.asyncio
    async def test_read_retried_on_timeout(self):
        c = _client()
        payload = [{"name": "ether1", ".id": "*1"}]
        responses = [httpx.TimeoutException("timeout")] * _READ_MAX_RETRIES + [
            _make_response(200, payload)
        ]
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=responses)
        c._client = mock_client
        result = await c.get_interfaces()
        assert result[0]["name"] == "ether1"
        assert mock_client.request.call_count == _READ_MAX_RETRIES + 1

    @pytest.mark.asyncio
    async def test_read_fails_after_all_retries_exhausted(self):
        c = _client()
        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        c._client = mock_client
        with pytest.raises(RouterTimeoutError):
            await c.get_addresses()
        assert mock_client.request.call_count == _READ_MAX_RETRIES + 1

    @pytest.mark.asyncio
    async def test_mutation_not_retried_on_timeout(self):
        c = _client()
        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        c._client = mock_client
        with pytest.raises(RouterTimeoutError):
            await c.create_resource("/ip/address", {"address": "1.2.3.4/24"})
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_update_not_retried_on_timeout(self):
        c = _client()
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        c._client = mock_client
        with pytest.raises(RouterTimeoutError):
            await c.update_resource("/ip/address", "*1", {"address": "1.2.3.4/24"})
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_delete_not_retried_on_timeout(self):
        c = _client()
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        c._client = mock_client
        with pytest.raises(RouterTimeoutError):
            await c.delete_resource("/ip/address", "*1")
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_auth_error_not_retried(self):
        c = _client()
        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            return_value=_make_response(401, {"detail": "bad creds"})
        )
        c._client = mock_client
        with pytest.raises(RouterAuthenticationError):
            await c.get_interfaces()
        assert mock_client.request.call_count == 1


class TestLifecycle:

    @pytest.mark.asyncio
    async def test_aclose_closes_client(self):
        c = _client()
        mock_httpx = AsyncMock()
        c._client = mock_httpx
        await c.aclose()
        mock_httpx.aclose.assert_called_once()
        assert c._client is None

    @pytest.mark.asyncio
    async def test_aclose_noop_when_no_client(self):
        c = _client()
        await c.aclose()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        c = _client()
        mock_httpx = AsyncMock()
        c._client = mock_httpx
        async with c:
            pass
        mock_httpx.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_protocol_compliance(self):
        from mika.router.client import RouterClient
        c = _client()
        assert isinstance(c, RouterClient)
