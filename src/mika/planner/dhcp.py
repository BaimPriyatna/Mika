"""
DHCP Server Planner.

Generates a plan to create a standalone DHCP server (IP pool, network entry,
and server) bound to an interface. Requires the interface to already have an
address assigned -- this planner derives the served network from that
existing address rather than guessing a prefix (CLAUDE.md Section 25: no
implicit dependency creation).
"""

from __future__ import annotations

import ipaddress

from mika.ai.schemas.configuration_intents import CreateDhcpIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.errors import (
    DhcpAlreadyExistsError,
    GatewayNotInNetworkError,
    InterfaceNotFoundError,
    InterfaceUnavailableError,
    InvalidDhcpPoolRangeError,
    NoAddressOnInterfaceError,
)
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.router.discovery import RouterContext

_DEFAULT_LEASE_TIME = "1h"


def plan_create_dhcp(intent: CreateDhcpIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.CREATE_DHCP:
        raise ValueError(f"plan_create_dhcp given non-matching intent: {intent.intent!r}")

    iface = router_context.get_interface(intent.interface)
    if iface is None:
        raise InterfaceNotFoundError(
            f"Interface '{intent.interface}' was not found on router "
            f"'{router_context.identity}'. Known interfaces: "
            f"{', '.join(router_context.interface_names) or '(none)'}."
        )
    if iface.disabled:
        raise InterfaceUnavailableError(
            f"Interface '{intent.interface}' exists but is disabled. Enable it "
            "before creating a DHCP server on it."
        )

    if router_context.has_dhcp_on_interface(intent.interface):
        raise DhcpAlreadyExistsError(
            f"An enabled DHCP server already exists on interface '{intent.interface}'. "
            "Refusing to plan a duplicate (CLAUDE.md Section 26: prefer ensure_* semantics)."
        )

    existing = router_context.get_addresses_on_interface(intent.interface)
    if not existing:
        raise NoAddressOnInterfaceError(
            f"Interface '{intent.interface}' has no address assigned. Assign one "
            "first (e.g. via create_address) -- this planner does not create "
            "dependencies implicitly (CLAUDE.md Section 25)."
        )
    network = ipaddress.ip_network(existing[0].address, strict=False)

    gateway_ip = ipaddress.ip_address(str(intent.gateway))
    if gateway_ip not in network:
        raise GatewayNotInNetworkError(
            f"Gateway {intent.gateway} is not within {network}, the network "
            f"derived from '{intent.interface}''s existing address "
            f"({existing[0].address})."
        )

    pool_start_ip = ipaddress.ip_address(str(intent.pool_start))
    pool_end_ip = ipaddress.ip_address(str(intent.pool_end))
    if pool_start_ip not in network or pool_end_ip not in network:
        raise InvalidDhcpPoolRangeError(
            f"Pool range {intent.pool_start}-{intent.pool_end} is not fully "
            f"within {network}."
        )
    if pool_start_ip > pool_end_ip:
        raise InvalidDhcpPoolRangeError(
            f"Pool start {intent.pool_start} is after pool end {intent.pool_end}."
        )

    base = f"{intent.interface}-dhcp"
    pool_name = f"{base}-pool"
    dhcp_name = base

    dns_server = (
        ",".join(str(d) for d in intent.dns_servers) if intent.dns_servers else str(gateway_ip)
    )

    steps = (
        PlanStep(
            step_id="dhcp_pool",
            description=f"Create IP pool {pool_name} ({intent.pool_start}-{intent.pool_end})",
            operation=OperationType.CREATE,
            resource="/ip/pool",
            data={"name": pool_name, "ranges": f"{intent.pool_start}-{intent.pool_end}"},
        ),
        PlanStep(
            step_id="dhcp_network",
            description=f"Register DHCP network {network} (gateway {intent.gateway})",
            operation=OperationType.CREATE,
            resource="/ip/dhcp-server/network",
            data={
                "address": str(network),
                "gateway": str(intent.gateway),
                "dns-server": dns_server,
            },
        ),
        PlanStep(
            step_id="dhcp_server",
            description=f"Create DHCP server {dhcp_name} bound to {intent.interface}",
            operation=OperationType.CREATE,
            resource="/ip/dhcp-server",
            data={
                "name": dhcp_name,
                "interface": intent.interface,
                "address-pool": pool_name,
                "lease-time": intent.lease_time or _DEFAULT_LEASE_TIME,
                "disabled": "no",
            },
        ),
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.CREATE_DHCP],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=(intent.interface,),
        # No affected_networks: the network being served already exists
        # (derived from the interface's own address), it isn't a new
        # subnet being introduced -- populating it here would make the
        # validator's overlap check flag it against itself.
        steps=steps,
    )
