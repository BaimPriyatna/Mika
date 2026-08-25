---
topic: subnetting
routeros: "any"
source: official_current
verified_at: 2024-06-01
---

# IPv4 subnetting concepts

A subnet mask (or CIDR prefix, e.g. `/24`) divides an IPv4 address into
a network portion and a host portion. `192.168.20.0/24` describes a
network with 256 addresses (192.168.20.0–192.168.20.255), of which the
first (network) and last (broadcast) addresses are not assignable to
hosts, leaving 254 usable addresses.

Two networks "overlap" when their address ranges intersect at all, even
partially — this is why the planner must check for overlap against every existing address and route, not just an exact
duplicate match, before proposing a new subnet.
