from __future__ import annotations

from mika.router.profile import RouterProfile


def hex_profile() -> RouterProfile:

    return RouterProfile(
        system_resource={
            "architecture-name": "arm",
            "board-name": "RB750Gr3",
            "build-time": "2024-09-03 10:41:22",
            "cpu": "ARM",
            "cpu-count": "1",
            "cpu-frequency": "800",
            "cpu-load": "2",
            "factory-software": "6.45.9",
            "free-hdd-space": "56750080",
            "free-memory": "84213760",
            "platform": "MikroTik",
            "total-hdd-space": "67108864",
            "total-memory": "134217728",
            "uptime": "12w3d4h51m9s",
            "version": "7.15.3 (stable)",
        },
        interfaces=[
            {".id": "*1", "name": "ether1", "type": "ether", "mtu": "1500",
             "mac-address": "48:A9:8A:1B:2C:01", "running": "true",
             "disabled": "false", "comment": "WAN"},
            {".id": "*2", "name": "ether2", "type": "ether", "mtu": "1500",
             "mac-address": "48:A9:8A:1B:2C:02", "running": "true",
             "disabled": "false", "comment": ""},
            {".id": "*3", "name": "ether3", "type": "ether", "mtu": "1500",
             "mac-address": "48:A9:8A:1B:2C:03", "running": "false",
             "disabled": "false", "comment": ""},
            {".id": "*4", "name": "ether4", "type": "ether", "mtu": "1500",
             "mac-address": "48:A9:8A:1B:2C:04", "running": "false",
             "disabled": "true", "comment": "unused"},
            {".id": "*5", "name": "ether5", "type": "ether", "mtu": "1500",
             "mac-address": "48:A9:8A:1B:2C:05", "running": "false",
             "disabled": "true", "comment": "unused"},
            {".id": "*6", "name": "bridge", "type": "bridge", "mtu": "1500",
             "mac-address": "48:A9:8A:1B:2C:02", "running": "true",
             "disabled": "false", "comment": "LAN bridge (ether2-ether5)"},
        ],
        addresses=[
            {".id": "*1", "address": "203.0.113.42/24", "network": "203.0.113.0",
             "interface": "ether1", "disabled": "false"},
            {".id": "*2", "address": "192.168.88.1/24", "network": "192.168.88.0",
             "interface": "bridge", "disabled": "false"},
        ],
        routes=[
            {".id": "*1", "dst-address": "0.0.0.0/0", "gateway": "203.0.113.1",
             "distance": "1", "active": "true", "static": "true"},
            {".id": "*2", "dst-address": "192.168.88.0/24", "gateway": "bridge",
             "distance": "0", "active": "true", "static": "false"},
        ],
        firewall_rules=[
            {".id": "*1", "chain": "input", "action": "accept",
             "connection-state": "established,related", "disabled": "false"},
            {".id": "*2", "chain": "input", "action": "drop",
             "connection-state": "invalid", "disabled": "false"},
            {".id": "*3", "chain": "input", "in-interface": "ether1",
             "action": "drop", "comment": "drop all from WAN", "disabled": "false"},
            {".id": "*4", "chain": "forward", "action": "accept",
             "connection-state": "established,related", "disabled": "false"},
        ],
        dhcp_servers=[
            {".id": "*1", "name": "dhcp1", "interface": "bridge",
             "address-pool": "dhcp_pool0", "lease-time": "1d", "disabled": "false"},
        ],
        dhcp_leases=[
            {".id": "*1", "address": "192.168.88.253", "mac-address": "DC:A6:32:11:22:01",
             "server": "dhcp1", "status": "bound", "host-name": "laptop-01"},
            {".id": "*2", "address": "192.168.88.252", "mac-address": "DC:A6:32:11:22:02",
             "server": "dhcp1", "status": "bound", "host-name": "nas-server"},
        ],
        hotspot_servers=[],
        hotspot_users=[],
    )


def rb951_profile() -> RouterProfile:

    return RouterProfile(
        system_resource={
            "architecture-name": "mipsbe",
            "board-name": "RB951Ui-2HnD",
            "build-time": "2023-06-14 09:12:03",
            "cpu": "MIPS 74Kc V4.12",
            "cpu-count": "1",
            "cpu-frequency": "600",
            "cpu-load": "8",
            "factory-software": "6.30.4",
            "free-hdd-space": "8912896",
            "free-memory": "26214400",
            "platform": "MikroTik",
            "total-hdd-space": "16777216",
            "total-memory": "33554432",
            "uptime": "3w6d13h56m43s",
            "version": "6.49.10 (long-term)",
        },
        interfaces=[
            {".id": "*1", "name": "ether1", "type": "ether", "mtu": "1500",
             "mac-address": "6C:3B:6B:AA:11:01", "running": "true",
             "disabled": "false", "comment": "WAN"},
            {".id": "*2", "name": "ether2", "type": "ether", "mtu": "1500",
             "mac-address": "6C:3B:6B:AA:11:02", "running": "true",
             "disabled": "false", "comment": ""},
            {".id": "*3", "name": "ether3", "type": "ether", "mtu": "1500",
             "mac-address": "6C:3B:6B:AA:11:03", "running": "false",
             "disabled": "false", "comment": ""},
            {".id": "*4", "name": "wlan1", "type": "wlan", "mtu": "1500",
             "mac-address": "6C:3B:6B:AA:11:0A", "running": "true",
             "disabled": "false", "comment": "guest hotspot radio"},
            {".id": "*5", "name": "bridge-local", "type": "bridge", "mtu": "1500",
             "mac-address": "6C:3B:6B:AA:11:02", "running": "true",
             "disabled": "false", "comment": "ether2/ether3"},
        ],
        addresses=[
            {".id": "*1", "address": "10.10.0.5/24", "network": "10.10.0.0",
             "interface": "ether1", "disabled": "false"},
            {".id": "*2", "address": "192.168.20.1/24", "network": "192.168.20.0",
             "interface": "wlan1", "disabled": "false"},
            {".id": "*3", "address": "192.168.10.1/24", "network": "192.168.10.0",
             "interface": "bridge-local", "disabled": "false"},
        ],
        routes=[
            {".id": "*1", "dst-address": "0.0.0.0/0", "gateway": "10.10.0.1",
             "distance": "1", "active": "true", "static": "true"},
        ],
        firewall_rules=[
            {".id": "*1", "chain": "input", "action": "accept",
             "connection-state": "established,related", "disabled": "false"},
            {".id": "*2", "chain": "forward", "action": "accept",
             "connection-state": "established,related", "disabled": "false"},
            {".id": "*3", "chain": "forward", "action": "drop",
             "connection-state": "invalid", "disabled": "false"},
        ],
        dhcp_servers=[
            {".id": "*1", "name": "dhcp-local", "interface": "bridge-local",
             "address-pool": "dhcp_pool_local", "lease-time": "1d", "disabled": "false"},
            {".id": "*2", "name": "dhcp-hotspot", "interface": "wlan1",
             "address-pool": "dhcp_pool_hotspot", "lease-time": "1h", "disabled": "false"},
        ],
        dhcp_leases=[
            {".id": "*1", "address": "192.168.10.50", "mac-address": "A4:5E:60:33:44:01",
             "server": "dhcp-local", "status": "bound", "host-name": "desktop-pc"},
        ],
        hotspot_servers=[
            {".id": "*1", "name": "hotspot1", "interface": "wlan1",
             "address-pool": "dhcp_pool_hotspot", "profile": "hsprof1", "disabled": "false"},
        ],
        hotspot_users=[
            {".id": "*1", "name": "guest01", "password": "changeme01",
             "profile": "default", "disabled": "false"},
            {".id": "*2", "name": "guest02", "password": "changeme02",
             "profile": "default", "disabled": "false"},
        ],
    )


def chr_profile() -> RouterProfile:

    return RouterProfile(
        system_resource={
            "architecture-name": "x86_64",
            "board-name": "CHR",
            "build-time": "2024-11-20 08:03:41",
            "cpu": "Intel(R) Xeon(R) (KVM)",
            "cpu-count": "2",
            "cpu-frequency": "2000",
            "cpu-load": "1",
            "factory-software": "",
            "free-hdd-space": "116000768",
            "free-memory": "897234944",
            "platform": "MikroTik",
            "total-hdd-space": "134217728",
            "total-memory": "1073741824",
            "uptime": "48w1d2h10m5s",
            "version": "7.16 (stable)",
        },
        interfaces=[
            {".id": "*1", "name": "ether1", "type": "ether", "mtu": "1500",
             "mac-address": "00:0C:29:7A:1F:01", "running": "true",
             "disabled": "false", "comment": "WAN / cloud NIC"},
            {".id": "*2", "name": "ether2", "type": "ether", "mtu": "1500",
             "mac-address": "00:0C:29:7A:1F:02", "running": "true",
             "disabled": "false", "comment": "internal / VPN bridge"},
        ],
        addresses=[
            {".id": "*1", "address": "198.51.100.20/24", "network": "198.51.100.0",
             "interface": "ether1", "disabled": "false"},
            {".id": "*2", "address": "172.16.0.1/24", "network": "172.16.0.0",
             "interface": "ether2", "disabled": "false"},
        ],
        routes=[
            {".id": "*1", "dst-address": "0.0.0.0/0", "gateway": "198.51.100.1",
             "distance": "1", "active": "true", "static": "true"},
            {".id": "*2", "dst-address": "172.16.0.0/24", "gateway": "ether2",
             "distance": "0", "active": "true", "static": "false"},
        ],
        firewall_rules=[
            {".id": "*1", "chain": "input", "action": "accept", "protocol": "tcp",
             "dst-port": "22", "comment": "SSH mgmt", "disabled": "false"},
            {".id": "*2", "chain": "input", "action": "accept",
             "connection-state": "established,related", "disabled": "false"},
            {".id": "*3", "chain": "input", "action": "drop",
             "in-interface": "ether1", "comment": "default deny WAN",
             "disabled": "false"},
        ],
        dhcp_servers=[],
        dhcp_leases=[],
        hotspot_servers=[],
        hotspot_users=[],
    )


PROFILES = {
    "hex": hex_profile,
    "rb951": rb951_profile,
    "chr": chr_profile,
}
