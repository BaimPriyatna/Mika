import pytest

from mika.router import (
    MockRouterClient,
    RouterApiError,
    RouterAuthenticationError,
    RouterConnectionError,
    RouterPermissionError,
    RouterTimeoutError,
)
from tests.fixtures.routers import chr_profile, hex_profile, rb951_profile


async def test_get_system_resource_reports_version_and_board():
    router = MockRouterClient(hex_profile())
    resource = await router.get_system_resource()
    assert resource["board-name"] == "RB750Gr3"
    assert resource["version"] == "7.15.3 (stable)"
    assert resource["architecture-name"] == "arm"


async def test_get_interfaces_returns_configured_ports():
    router = MockRouterClient(hex_profile())
    interfaces = await router.get_interfaces()
    names = {i["name"] for i in interfaces}
    assert {"ether1", "ether2", "bridge"} <= names


async def test_get_addresses():
    router = MockRouterClient(hex_profile())
    addresses = await router.get_addresses()
    assert any(a["address"] == "192.168.88.1/24" for a in addresses)


async def test_get_routes():
    router = MockRouterClient(hex_profile())
    routes = await router.get_routes()
    assert any(r["dst-address"] == "0.0.0.0/0" for r in routes)


async def test_get_firewall_rules():
    router = MockRouterClient(hex_profile())
    rules = await router.get_firewall_rules()
    assert any(r["chain"] == "input" and r["action"] == "drop" for r in rules)


async def test_get_dhcp_servers_and_leases():
    router = MockRouterClient(hex_profile())
    servers = await router.get_dhcp_servers()
    leases = await router.get_dhcp_leases()
    assert servers[0]["interface"] == "bridge"
    assert any(lease["host-name"] == "nas-server" for lease in leases)


async def test_get_hotspot_servers_and_users_on_wireless_profile():
    router = MockRouterClient(rb951_profile())
    servers = await router.get_hotspot_servers()
    users = await router.get_hotspot_users()
    assert servers[0]["interface"] == "wlan1"
    assert {"guest01", "guest02"} == {u["name"] for u in users}


async def test_hex_profile_has_no_hotspot_configured():
    router = MockRouterClient(hex_profile())
    assert await router.get_hotspot_servers() == []
    assert await router.get_hotspot_users() == []


async def test_chr_profile_has_no_dhcp_or_hotspot():
    router = MockRouterClient(chr_profile())
    assert await router.get_dhcp_servers() == []
    assert await router.get_hotspot_servers() == []
    resource = await router.get_system_resource()
    assert resource["board-name"] == "CHR"


async def test_get_interfaces_returns_a_copy_not_live_reference():
    router = MockRouterClient(hex_profile())
    interfaces = await router.get_interfaces()
    interfaces.append({".id": "*99", "name": "tampered"})
    interfaces[0]["name"] = "tampered"

    fresh = await router.get_interfaces()
    assert "tampered" not in {i["name"] for i in fresh}
    assert len(fresh) != len(interfaces)


async def test_create_resource_assigns_id_and_persists():
    router = MockRouterClient(hex_profile())
    created = await router.create_resource(
        "/ip/address", {"address": "10.0.0.1/24", "interface": "ether2"}
    )
    assert ".id" in created
    assert created["address"] == "10.0.0.1/24"

    addresses = await router.get_addresses()
    assert any(a["address"] == "10.0.0.1/24" for a in addresses)


async def test_update_resource_patches_existing_item():
    router = MockRouterClient(hex_profile())
    updated = await router.update_resource("/ip/firewall/filter", "*2", {"disabled": "true"})
    assert updated["disabled"] == "true"

    rules = await router.get_firewall_rules()
    patched = next(r for r in rules if r[".id"] == "*2")
    assert patched["disabled"] == "true"


async def test_update_resource_missing_id_raises_api_error():
    router = MockRouterClient(hex_profile())
    with pytest.raises(RouterApiError):
        await router.update_resource("/ip/firewall/filter", "*999", {"disabled": "true"})


async def test_delete_resource_removes_item():
    router = MockRouterClient(hex_profile())
    await router.delete_resource("/ip/firewall/filter", "*2")
    rules = await router.get_firewall_rules()
    assert all(r[".id"] != "*2" for r in rules)


async def test_delete_resource_missing_id_raises_api_error():
    router = MockRouterClient(hex_profile())
    with pytest.raises(RouterApiError):
        await router.delete_resource("/ip/firewall/filter", "*999")


async def test_unknown_resource_path_raises_api_error():
    router = MockRouterClient(hex_profile())
    with pytest.raises(RouterApiError):
        await router.create_resource("/ip/magic/block", {"foo": "bar"})


async def test_queued_failure_fires_once_then_recovers():
    router = MockRouterClient(hex_profile())
    router.queue_failure("get_interfaces", RouterTimeoutError("simulated timeout"))

    with pytest.raises(RouterTimeoutError):
        await router.get_interfaces()

    interfaces = await router.get_interfaces()
    assert len(interfaces) > 0


async def test_router_timeout_error_is_a_connection_error():
    assert issubclass(RouterTimeoutError, RouterConnectionError)


async def test_queued_permission_denied():
    router = MockRouterClient(hex_profile())
    router.queue_failure(
        "delete_resource", RouterPermissionError("user lacks 'write' policy")
    )
    with pytest.raises(RouterPermissionError):
        await router.delete_resource("/ip/firewall/filter", "*1")

    rules = await router.get_firewall_rules()
    assert any(r[".id"] == "*1" for r in rules)


async def test_queued_authentication_failure():
    router = MockRouterClient(hex_profile())
    router.queue_failure(
        "get_system_resource", RouterAuthenticationError("invalid credentials")
    )
    with pytest.raises(RouterAuthenticationError):
        await router.get_system_resource()


async def test_clear_failure_cancels_queued_failure():
    router = MockRouterClient(hex_profile())
    router.queue_failure("get_routes", RouterTimeoutError("would have failed"))
    router.clear_failure("get_routes")

    routes = await router.get_routes()
    assert len(routes) > 0


async def test_sever_connection_fails_every_call_until_restored():
    router = MockRouterClient(hex_profile())
    router.sever_connection()

    with pytest.raises(RouterConnectionError):
        await router.get_interfaces()
    with pytest.raises(RouterConnectionError):
        await router.get_firewall_rules()

    router.restore_connection()
    interfaces = await router.get_interfaces()
    assert len(interfaces) > 0


async def test_sever_connection_overrides_unrelated_queued_success():
    router = MockRouterClient(rb951_profile())
    router.sever_connection()
    with pytest.raises(RouterConnectionError):
        await router.get_hotspot_users()
