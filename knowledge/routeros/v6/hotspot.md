---
topic: hotspot
routeros: "6"
source: official_version_specific
verified_at: 2024-06-01
---

# CONSTRAINTS: HOTSPOT (RouterOS 6)

## 1. DEPENDENCY ORDER
1. `Interface` -> 2. `/ip address` -> 3. `/ip pool` -> 4. `/ip dhcp-server` -> 5. `/ip hotspot profile` -> 6. `/ip hotspot`

## 2. SYNTAX RULES
- **Hotspot Profile**: `/ip hotspot profile add name=<name> hotspot-address=<ip>`
- **Hotspot Server**: `/ip hotspot add name=<name> interface=<iface> profile=<profile>`

## 3. SAFETY
- Check for existing DHCP servers on the target interface. DO NOT add a duplicate DHCP server for the hotspot if one already exists and handles the same subnet.
