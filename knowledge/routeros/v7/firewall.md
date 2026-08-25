---
topic: firewall
routeros: "7"
source: official_current
verified_at: 2024-06-01
---

# CONSTRAINTS: FIREWALL FILTER (RouterOS 7)

## 1. CHAIN LOGIC
- `input`: Traffic to router CPU (Winbox, SSH, DNS, Ping).
- `forward`: Traffic passing through router (LAN <-> WAN).
- `output`: Traffic originated by router CPU.

## 2. SAFETY WARNINGS (CRITICAL)
- **Lockout Prevention**: NEVER emit a `drop` rule on the `input` chain without first ensuring an `accept` rule exists for the management IP/subnet (e.g., Winbox/SSH access).
- **Default Drop**: A secure firewall always drops unrecognized traffic on `input` from the WAN interface.

## 3. BEST PRACTICES & SYNTAX
- **Connection Tracking**: Place `established,related` accept rules at the VERY TOP of `input` and `forward` chains to save CPU.
  - `/ip firewall filter add chain=input connection-state=established,related action=accept`
- **Drop Invalid**: Drop invalid packets early.
  - `/ip firewall filter add chain=input connection-state=invalid action=drop`

## 4. VERSION 7 SPECIFICS
- **Routing Filters**: Do not use v6 routing filter syntax. In v7, network advertisements use `/ip firewall address-list`.
