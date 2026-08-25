---
topic: hotspot
routeros: "7"
source: official_current
verified_at: 2024-06-01
---

# CONSTRAINTS: HOTSPOT (RouterOS 7)

## 1. DEPENDENCY ORDER
Hotspot requires existing infrastructure. Verify state before generating commands:
1. `Interface`
2. `/ip address`
3. `/ip pool`
4. `/ip dhcp-server`
5. `/ip hotspot profile`
6. `/ip hotspot` (Server)
7. `/ip hotspot user` (or User Profile)

## 2. SYNTAX & ARCHITECTURE RULES
- **Server Creation**: `/ip hotspot add name=<name> interface=<iface> profile=<profile>`
- **NAT**: Hotspot automatically generates dynamic NAT. Manual masquerade on the WAN interface is still required for internet access.

## 3. VERSION 7 SPECIFICS
- **RFC 7710**: v7 supports captive portal DHCP options natively.
- **User Manager**: Usermanager v7 is completely rewritten. Use standard `/ip hotspot user` for local users, or Radius for external authentication.
