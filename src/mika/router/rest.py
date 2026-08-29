"""
RouterOS REST API Client.

Implements the RouterClient protocol using RouterOS v7+ REST endpoints.
Handles HTTP basic authentication, SSL verification, timeout handling,
and CRUD operations against RouterOS resource paths.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from mika.router.errors import (
    RouterApiError,
    RouterAuthenticationError,
    RouterConnectionError,
    RouterPermissionError,
    RouterTimeoutError,
)

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15.0

_READ_MAX_RETRIES = 2


class RestRouterClient:

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        port: int = 443,
        timeout: float = _DEFAULT_TIMEOUT,
        verify: bool = True,
    ) -> None:
        if not host:
            raise ValueError("host must not be empty")
        if not username:
            raise ValueError("username must not be empty")

        self._base_url = f"https://{host}:{port}/rest"
        self._auth = (username, password)
        self._timeout = timeout
        self._verify = verify
        self._client: httpx.AsyncClient | None = None


    async def __aenter__(self) -> "RestRouterClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


    async def get_system_resource(self) -> dict:
        return await self._get_one("/system/resource")

    async def get_interfaces(self) -> list[dict]:
        return await self._get_list("/interface")

    async def get_addresses(self) -> list[dict]:
        return await self._get_list("/ip/address")

    async def get_routes(self) -> list[dict]:
        return await self._get_list("/ip/route")

    async def get_firewall_rules(self) -> list[dict]:
        return await self._get_list("/ip/firewall/filter")

    async def get_nat_rules(self) -> list[dict]:
        return await self._get_list("/ip/firewall/nat")

    async def get_queues(self) -> list[dict]:
        return await self._get_list("/queue/simple")

    async def get_dhcp_servers(self) -> list[dict]:
        return await self._get_list("/ip/dhcp-server")

    async def get_dhcp_leases(self) -> list[dict]:
        return await self._get_list("/ip/dhcp-server/lease")

    async def get_hotspot_servers(self) -> list[dict]:
        return await self._get_list("/ip/hotspot")

    async def get_hotspot_users(self) -> list[dict]:
        return await self._get_list("/ip/hotspot/user")


    async def create_resource(self, resource: str, data: dict) -> dict:
        url = self._url(resource)
        response = await self._request("PUT", url, json=data)
        return self._parse_object(response, url)

    async def update_resource(self, resource: str, resource_id: str, data: dict) -> dict:
        url = self._url(resource, resource_id)
        response = await self._request("PATCH", url, json=data)
        return self._parse_object(response, url)

    async def delete_resource(self, resource: str, resource_id: str) -> None:
        url = self._url(resource, resource_id)
        await self._request("DELETE", url)


    def _client_instance(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                auth=self._auth,
                verify=self._verify,
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
        return self._client

    def _url(self, resource: str, resource_id: str | None = None) -> str:
        path = resource.lstrip("/")
        url = f"{self._base_url}/{path}"
        if resource_id is not None:
            url = f"{url}/{resource_id}"
        return url

    async def _get_list(self, resource: str) -> list[dict]:
        url = self._url(resource)
        response = await self._request("GET", url, _retryable=True)
        data = self._parse_json(response, url)
        if not isinstance(data, list):
            raise RouterApiError(
                f"Expected list from {url!r}, got {type(data).__name__}"
            )
        return data

    async def _get_one(self, resource: str) -> dict:
        url = self._url(resource)
        response = await self._request("GET", url, _retryable=True)
        return self._parse_object(response, url)

    def _parse_json(self, response: httpx.Response, url: str) -> Any:
        try:
            return response.json()
        except Exception as exc:
            raise RouterApiError(
                f"Non-JSON response from {url!r}: {exc}"
            ) from exc

    def _parse_object(self, response: httpx.Response, url: str) -> dict:
        data = self._parse_json(response, url)
        if not isinstance(data, dict):
            raise RouterApiError(
                f"Expected dict from {url!r}, got {type(data).__name__}"
            )
        return data

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        _retryable: bool = False,
    ) -> httpx.Response:
        client = self._client_instance()
        attempts = _READ_MAX_RETRIES + 1 if _retryable else 1
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                log.debug("%s %s (attempt %d/%d)", method, url, attempt, attempts)
                response = await client.request(method, url, json=json)
                self._raise_for_router_error(response, url)
                return response

            except httpx.TimeoutException as exc:
                wrapped = RouterTimeoutError(
                    f"Request timed out after {self._timeout}s: {method} {url}"
                )
                wrapped.__cause__ = exc
                last_exc = wrapped
                log.warning("Timeout on %s %s (attempt %d)", method, url, attempt)

            except httpx.ConnectError as exc:
                wrapped = RouterConnectionError(
                    f"Connection failed: {method} {url} - {exc}"
                )
                wrapped.__cause__ = exc
                last_exc = wrapped
                log.warning("Connection error on %s %s", method, url)
                break

            except (RouterAuthenticationError, RouterPermissionError, RouterApiError):
                raise

            except httpx.RequestError as exc:
                wrapped = RouterConnectionError(
                    f"Request error: {method} {url} - {exc}"
                )
                wrapped.__cause__ = exc
                last_exc = wrapped
                log.warning("Request error on %s %s", method, url)

        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _raise_for_router_error(response: httpx.Response, url: str) -> None:
        status = response.status_code

        if status in (200, 201, 204):
            return

        try:
            body = response.json()
            detail = body.get("detail") or body.get("message") or body.get("error") or ""
        except Exception:
            detail = response.text[:200]

        if status == 401:
            raise RouterAuthenticationError(
                f"Authentication failed for {url!r}: {detail}"
            )
        if status == 403:
            raise RouterPermissionError(
                f"Permission denied for {url!r}: {detail}"
            )

        raise RouterApiError(
            f"RouterOS API error {status} for {url!r}: {detail}",
            code=str(status),
        )
