---
topic: dhcp
routeros: "7"
source: official_current
verified_at: 2024-06-01
---

# CONSTRAINTS: DHCP SERVER (RouterOS 7)

## 1. DEPENDENCY ORDER
When planning a DHCP setup, resources MUST be created in this strict order. Check router state before creating to avoid duplicates:
1. `Interface`: Must exist.
2. `/ip address`: Interface MUST have a static IP assigned.
3. `/ip pool`: Define IP range.
4. `/ip dhcp-server network`: Subnet parameters (gateway, dns).
5. `/ip dhcp-server`: Bind to interface and pool.

## 2. SYNTAX RULES
- **Pool**: `/ip pool add name=<name> ranges=<start-IP>-<end-IP>`
- **Network**: `/ip dhcp-server network add address=<subnet_CIDR> gateway=<ip> dns-server=<ip>`
- **Server**: `/ip dhcp-server add name=<name> interface=<iface> address-pool=<pool_name> disabled=no`

## 3. SAFETY & EDGE CASES
- **Bridge Slave Port**: If requested to run DHCP on a port that belongs to a bridge, you MUST bind the DHCP server to the `bridge` interface itself.
- **VLANs**: DHCP server must be bound to the `vlan` interface, not the physical trunk interface.
