---
topic: nat
routeros: "6"
source: official_version_specific
verified_at: 2024-06-01
---

# CONSTRAINTS: NAT (RouterOS 6)

## 1. CHAIN RULES
- `srcnat`: Alter source IP.
- `dstnat`: Alter destination IP.

## 2. SYNTAX & BEST PRACTICES
- **Masquerade**:
  - `/ip firewall nat add chain=srcnat out-interface=<WAN_IFACE> action=masquerade`
  - *Safety*: MUST specify `out-interface`.
- **Port Forwarding**:
  - `/ip firewall nat add chain=dstnat dst-port=<port> protocol=<tcp/udp> in-interface=<WAN_IFACE> action=dst-nat to-addresses=<ip> to-ports=<port>`
