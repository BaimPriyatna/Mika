"""
Hotspot Service Planner.

Generates multi-step configuration plans for MikroTik Hotspot setups,
including IP pools, DHCP servers, profiles, and firewall NAT rules.
"""

from __future__ import annotations

import ipaddress

from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, IntentName
from mika.planner.errors import (
    HotspotAlreadyExistsError,
    InterfaceNotFoundError,
    InterfaceUnavailableError,
    NetworkTooSmallError,
    SubnetConflictError,
)
from mika.planner.plan import OperationType, Plan, PlanStep, compute_router_fingerprint
from mika.router.discovery import RouterContext

_MIN_USABLE_HOSTS = 2

_DEFAULT_LEASE_TIME = "1h"


def plan_create_hotspot(intent: CreateHotspotIntent, router_context: RouterContext) -> Plan:
    if intent.intent != IntentName.CREATE_HOTSPOT:
        raise ValueError(f"plan_create_hotspot given non-matching intent: {intent.intent!r}")

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
            "before creating a hotspot on it (this planner does not enable "
            "interfaces implicitly -- CLAUDE.md Section 25)."
        )
    if router_context.has_hotspot_on_interface(intent.interface):
        raise HotspotAlreadyExistsError(
            f"An enabled hotspot server already exists on interface '{intent.interface}'. "
            "Refusing to plan a duplicate (CLAUDE.md Section 26: prefer ensure_* semantics)."
        )

    network = ipaddress.ip_network(str(intent.network), strict=False)
    hosts = list(network.hosts())
    if len(hosts) < _MIN_USABLE_HOSTS:
        raise NetworkTooSmallError(
            f"Network {network} has only {len(hosts)} usable host address(es); "
            f"a hotspot needs at least {_MIN_USABLE_HOSTS} (1 gateway + 1 pool address)."
        )
    gateway = hosts[0]
    pool_start = hosts[1]
    pool_end = hosts[-1]

    conflicts = router_context.find_conflicting_subnets(str(network))
    if conflicts:
        raise SubnetConflictError(
            f"Requested network {network} overlaps existing configured address(es): "
            f"{', '.join(conflicts)}.",
            conflicting_addresses=conflicts,
        )

    base = f"{intent.interface}-hotspot"
    pool_name = f"{base}-pool"
    dhcp_name = f"{base}-dhcp"
    hs_profile_name = f"{base}-profile"
    hs_name = base
    user_profile_name = f"{base}-user-profile"

    warnings: list[str] = []

    steps: list[PlanStep] = [
        PlanStep(
            step_id="hotspot_address",
            description=f"Assign address {gateway}/{network.prefixlen} to {intent.interface}",
            operation=OperationType.CREATE,
            resource="/ip/address",
            data={
                "address": f"{gateway}/{network.prefixlen}",
                "interface": intent.interface,
                "comment": "created by mika: create_hotspot",
            },
        ),
        PlanStep(
            step_id="hotspot_pool",
            description=f"Create IP pool {pool_name} ({pool_start}-{pool_end})",
            operation=OperationType.CREATE,
            resource="/ip/pool",
            data={"name": pool_name, "ranges": f"{pool_start}-{pool_end}"},
        ),
        PlanStep(
            step_id="hotspot_dhcp_network",
            description=f"Register DHCP network {network} (gateway {gateway})",
            operation=OperationType.CREATE,
            resource="/ip/dhcp-server/network",
            data={
                "address": str(network),
                "gateway": str(gateway),
                "dns-server": str(gateway),
            },
        ),
        PlanStep(
            step_id="hotspot_dhcp_server",
            description=f"Create DHCP server {dhcp_name} bound to {intent.interface}",
            operation=OperationType.CREATE,
            resource="/ip/dhcp-server",
            data={
                "name": dhcp_name,
                "interface": intent.interface,
                "address-pool": pool_name,
                "lease-time": _DEFAULT_LEASE_TIME,
                "disabled": "no",
            },
        ),
    ]

    if intent.rate_limit:
        steps.append(
            PlanStep(
                step_id="hotspot_user_profile",
                description=f"Create hotspot user profile {user_profile_name} (rate-limit {intent.rate_limit})",
                operation=OperationType.CREATE,
                resource="/ip/hotspot/user/profile",
                data={"name": user_profile_name, "rate-limit": intent.rate_limit},
            )
        )
        warnings.append(
            f"Rate limit profile '{user_profile_name}' was created but is not automatically "
            "applied to hotspot users -- RouterOS has no verified 'default profile' field on "
            "the hotspot server itself. Assign it explicitly when creating hotspot users "
            "(CLAUDE.md Section 57: verify against official documentation before wiring this "
            "up automatically)."
        )

    hs_profile_data = {"name": hs_profile_name, "hotspot-address": str(gateway)}
    if intent.dns_name:
        hs_profile_data["dns-name"] = intent.dns_name

    steps.append(
        PlanStep(
            step_id="hotspot_profile",
            description=f"Create hotspot profile {hs_profile_name}",
            operation=OperationType.CREATE,
            resource="/ip/hotspot/profile",
            data=hs_profile_data,
        )
    )
    steps.append(
        PlanStep(
            step_id="hotspot_server",
            description=f"Create hotspot server {hs_name} on {intent.interface}",
            operation=OperationType.CREATE,
            resource="/ip/hotspot",
            data={
                "name": hs_name,
                "interface": intent.interface,
                "address-pool": pool_name,
                "profile": hs_profile_name,
            },
        )
    )

    return Plan(
        intent=intent,
        safety_level=INTENT_SAFETY_LEVEL[IntentName.CREATE_HOTSPOT],
        router_identity=router_context.identity,
        routeros_version=router_context.routeros_version,
        router_state_fingerprint=compute_router_fingerprint(router_context),
        affected_interfaces=(intent.interface,),
        affected_networks=(str(network),),
        steps=tuple(steps),
        warnings=tuple(warnings),
    )
