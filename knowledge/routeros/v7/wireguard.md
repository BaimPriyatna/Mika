---
topic: wireguard
routeros: "7"
source: official_current
verified_at: 2024-06-01
---

# CONSTRAINTS: WIREGUARD (RouterOS 7)

## 1. DEPENDENCIES & SYNTAX
1. **Interface**: `/interface wireguard add name=wg1 listen-port=13231` (Generates keys automatically).
2. **IP Address**: `/ip address add address=<IP/CIDR> interface=wg1`
3. **Peers**: `/interface wireguard peers add interface=wg1 public-key="<KEY>" allowed-address=<IP/CIDR> endpoint-address=<IP> endpoint-port=13231`
4. **Firewall**: `/ip firewall filter add chain=input protocol=udp dst-port=13231 action=accept`

## 2. V7 SPECIFICS
- WireGuard is NATIVE in v7. Do not attempt to configure this in v6 context.
- Routing is handled automatically via `allowed-address`, which installs dynamic routes unless suppressed.
