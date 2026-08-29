---
topic: vlan
routeros: "6"
source: official_current
verified_at: 2026-08-29
---

# CONSTRAINTS: STANDALONE VLAN INTERFACE (RouterOS 6)

This covers the standalone 802.1Q VLAN sub-interface feature
(`/interface vlan`), NOT bridge VLAN filtering. Use this when the goal is
a single tagged VLAN sub-interface on a parent interface, not a
multi-port bridge trunk/access setup.

## 1. SYNTAX RULES

- **Create**: `/interface vlan add interface=<parent> name=<vlan-name> vlan-id=<id>`
- `interface=` is the parent (physical, bridge, or bond) interface that will carry the tagged traffic.
- `vlan-id=` is an integer from 1 to 4094.
- `name=` is the name of the new virtual interface; if omitted RouterOS auto-generates one, but an explicit descriptive name is preferred.
- The command syntax is unchanged from RouterOS 7 for this feature.

## 2. DEPENDENCY ORDER

1. `Parent interface`: must already exist and should be enabled.
2. `/interface vlan`: create the tagged sub-interface on top of it.
3. `/ip address`: assign an address to the new VLAN interface, if IP connectivity on that VLAN is needed. Not required for the VLAN interface itself to exist.

## 3. SAFETY & EDGE CASES

- The parent interface does not need an IP address of its own; it typically stays a pure Layer 2 trunk while the VLAN interface(s) carry the IP configuration.
- Reusing the same `vlan-id` on the same parent interface is a duplicate and MUST be refused. The same `vlan-id` on a *different* parent interface is a separate, valid resource.
- If the parent interface is a bridge, traffic must also be correctly tagged for that VLAN on the bridge's ports/bridge-vlan table for it to actually reach this sub-interface -- creating `/interface vlan` alone does not configure bridge port tagging.
