---
topic: nat
routeros: "7"
source: official_current
verified_at: 2024-06-01
---

# CONSTRAINTS: NAT (RouterOS 7)

## 1. CHAIN RULES
- `srcnat`: Outbound traffic (Masquerade, SNAT).
- `dstnat`: Inbound traffic (Port Forwarding).

## 2. SYNTAX & BEST PRACTICES
- **Internet Access (Masquerade)**:
  - `/ip firewall nat add chain=srcnat out-interface=<WAN_IFACE> action=masquerade`
  - *Safety*: ALWAYS specify `out-interface` or `out-interface-list`. Without it, you create routing loops and break local communication.
- **Port Forwarding**:
  - `/ip firewall nat add chain=dstnat protocol=<tcp/udp> dst-port=<external_port> in-interface=<WAN_IFACE> action=dst-nat to-addresses=<internal_ip> to-ports=<internal_port>`

## 3. VERSION 7 SPECIFICS
- v7 introduces `input` and `output` chains within the NAT table. Use `srcnat` and `dstnat` for standard routing scenarios.
