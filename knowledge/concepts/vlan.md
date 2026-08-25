---
topic: vlan
routeros: "any"
source: official_current
verified_at: 2024-06-01
---

# VLAN concepts

> Status: seed document covering the version-agnostic concept only.
> RouterOS-version-specific configuration syntax belongs in
> `routeros/v6/` or `routeros/v7/` documents, not here.

A VLAN (IEEE 802.1Q) tags Ethernet frames with a 12-bit VLAN ID (1–4094)
so that multiple logically separate broadcast domains can share the
same physical link. A "trunk" port carries tagged traffic for more than
one VLAN; an "access" port carries untagged traffic for exactly one
VLAN, with tagging added/removed at the switch boundary.

On MikroTik devices, VLAN interfaces are virtual interfaces layered on
top of a physical or bridge interface, and typically need their own IP
addressing, firewall consideration, and (if routing between VLANs is
required) a route or bridge configuration — none of which happens
automatically just from creating the VLAN interface itself.
