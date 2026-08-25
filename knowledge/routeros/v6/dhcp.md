---
topic: dhcp
routeros: "6"
source: official_version_specific
verified_at: 2024-06-01
---

# CONSTRAINTS: DHCP SERVER (RouterOS 6)

## 1. DEPENDENCY ORDER
Strict creation sequence:
1. `Interface`
2. `/ip address` (Assign static IP)
3. `/ip pool`
4. `/ip dhcp-server network`
5. `/ip dhcp-server`

## 2. SYNTAX RULES
- **Pool**: `/ip pool add name=<name> ranges=<start-IP>-<end-IP>`
- **Network**: `/ip dhcp-server network add address=<subnet_CIDR> gateway=<ip> dns-server=<ip>`
- **Server**: `/ip dhcp-server add name=<name> interface=<iface> address-pool=<pool_name> disabled=no`

## 3. SAFETY & EDGE CASES
- **Bridge Port Rule**: Never attach a DHCP server to a bridge slave port. Always attach to the bridge master interface.
