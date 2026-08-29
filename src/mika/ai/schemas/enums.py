from __future__ import annotations

from enum import Enum


class IntentCategory(str, Enum):
    READ = "READ"
    CONFIGURATION = "CONFIGURATION"
    MODIFICATION = "MODIFICATION"
    DESTRUCTIVE = "DESTRUCTIVE"


class SafetyLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    DESTRUCTIVE = "DESTRUCTIVE"


class IntentName(str, Enum):
    ADVISE = "advise"
    TROUBLESHOOT = "troubleshoot"

    INSPECT_ROUTER = "inspect_router"
    INSPECT_INTERFACES = "inspect_interfaces"
    INSPECT_IP_ADDRESSES = "inspect_ip_addresses"
    INSPECT_ROUTES = "inspect_routes"
    INSPECT_FIREWALL = "inspect_firewall"
    INSPECT_NAT = "inspect_nat"
    INSPECT_DHCP = "inspect_dhcp"
    INSPECT_HOTSPOT = "inspect_hotspot"

    CREATE_ADDRESS = "create_address"
    CREATE_VLAN = "create_vlan"
    CREATE_DHCP = "create_dhcp"
    CREATE_HOTSPOT = "create_hotspot"
    CREATE_FIREWALL_RULE = "create_firewall_rule"
    CREATE_NAT_RULE = "create_nat_rule"
    CREATE_QUEUE = "create_queue"

    MODIFY_ADDRESS = "modify_address"
    MODIFY_FIREWALL_RULE = "modify_firewall_rule"
    MODIFY_DHCP = "modify_dhcp"
    MODIFY_HOTSPOT = "modify_hotspot"
    MODIFY_QUEUE = "modify_queue"

    DELETE_ADDRESS = "delete_address"
    DELETE_VLAN = "delete_vlan"
    DELETE_FIREWALL_RULE = "delete_firewall_rule"
    DELETE_DHCP = "delete_dhcp"
    DELETE_HOTSPOT = "delete_hotspot"
    DELETE_QUEUE = "delete_queue"


INTENT_CATEGORY: dict[IntentName, IntentCategory] = {
    **{name: IntentCategory.READ for name in (
        IntentName.ADVISE,
        IntentName.TROUBLESHOOT,
        IntentName.INSPECT_ROUTER,
        IntentName.INSPECT_INTERFACES,
        IntentName.INSPECT_IP_ADDRESSES,
        IntentName.INSPECT_ROUTES,
        IntentName.INSPECT_FIREWALL,
        IntentName.INSPECT_NAT,
        IntentName.INSPECT_DHCP,
        IntentName.INSPECT_HOTSPOT,
    )},
    **{name: IntentCategory.CONFIGURATION for name in (
        IntentName.CREATE_ADDRESS,
        IntentName.CREATE_VLAN,
        IntentName.CREATE_DHCP,
        IntentName.CREATE_HOTSPOT,
        IntentName.CREATE_FIREWALL_RULE,
        IntentName.CREATE_NAT_RULE,
        IntentName.CREATE_QUEUE,
    )},
    **{name: IntentCategory.MODIFICATION for name in (
        IntentName.MODIFY_ADDRESS,
        IntentName.MODIFY_FIREWALL_RULE,
        IntentName.MODIFY_DHCP,
        IntentName.MODIFY_HOTSPOT,
        IntentName.MODIFY_QUEUE,
    )},
    **{name: IntentCategory.DESTRUCTIVE for name in (
        IntentName.DELETE_ADDRESS,
        IntentName.DELETE_VLAN,
        IntentName.DELETE_FIREWALL_RULE,
        IntentName.DELETE_DHCP,
        IntentName.DELETE_HOTSPOT,
        IntentName.DELETE_QUEUE,
    )},
}

INTENT_SAFETY_LEVEL: dict[IntentName, SafetyLevel] = {
    **{name: SafetyLevel.READ_ONLY for name in INTENT_CATEGORY if INTENT_CATEGORY[name] == IntentCategory.READ},
    IntentName.CREATE_ADDRESS: SafetyLevel.LOW_RISK,
    IntentName.CREATE_VLAN: SafetyLevel.LOW_RISK,
    IntentName.CREATE_QUEUE: SafetyLevel.LOW_RISK,
    IntentName.CREATE_DHCP: SafetyLevel.MEDIUM_RISK,
    IntentName.CREATE_HOTSPOT: SafetyLevel.MEDIUM_RISK,
    IntentName.CREATE_FIREWALL_RULE: SafetyLevel.MEDIUM_RISK,
    IntentName.CREATE_NAT_RULE: SafetyLevel.MEDIUM_RISK,
    IntentName.MODIFY_ADDRESS: SafetyLevel.MEDIUM_RISK,
    IntentName.MODIFY_QUEUE: SafetyLevel.MEDIUM_RISK,
    IntentName.MODIFY_DHCP: SafetyLevel.MEDIUM_RISK,
    IntentName.MODIFY_HOTSPOT: SafetyLevel.MEDIUM_RISK,
    IntentName.MODIFY_FIREWALL_RULE: SafetyLevel.HIGH_RISK,
    IntentName.DELETE_ADDRESS: SafetyLevel.DESTRUCTIVE,
    IntentName.DELETE_VLAN: SafetyLevel.DESTRUCTIVE,
    IntentName.DELETE_FIREWALL_RULE: SafetyLevel.DESTRUCTIVE,
    IntentName.DELETE_DHCP: SafetyLevel.DESTRUCTIVE,
    IntentName.DELETE_HOTSPOT: SafetyLevel.DESTRUCTIVE,
    IntentName.DELETE_QUEUE: SafetyLevel.DESTRUCTIVE,
}


class FirewallChain(str, Enum):
    INPUT = "input"
    FORWARD = "forward"
    OUTPUT = "output"


class NatChain(str, Enum):
    SRCNAT = "srcnat"
    DSTNAT = "dstnat"


class FirewallAction(str, Enum):
    ACCEPT = "accept"
    DROP = "drop"
    REJECT = "reject"
    LOG = "log"
    PASSTHROUGH = "passthrough"
    RETURN = "return"
    JUMP = "jump"


class NatAction(str, Enum):
    MASQUERADE = "masquerade"
    DST_NAT = "dst-nat"
    SRC_NAT = "src-nat"
    NETMAP = "netmap"
    SAME = "same"
    REDIRECT = "redirect"


class L4Protocol(str, Enum):
    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
