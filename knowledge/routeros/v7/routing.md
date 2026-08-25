---
topic: routing
routeros: "7"
source: official_current
verified_at: 2024-06-01
---

# CONSTRAINTS: ROUTING (RouterOS 7)

## 1. SYNTAX RULES
- **Static Default Route**: `/ip route add dst-address=0.0.0.0/0 gateway=<ip>`

## 2. POLICY-BASED ROUTING (PBR) & V7 CHANGES
- **Explicit Tables (V7 ONLY)**: You MUST define a routing table before assigning routes to it.
  - `/routing table add name=<TABLE_NAME> fib` (fib is required for forwarding).
- **Assigning Routes**: `/ip route add dst-address=0.0.0.0/0 gateway=<ip> routing-table=<TABLE_NAME>`
- **Routing Rules**: Defined under `/routing rule` (NOT `/ip route rule`).

## 3. SAFETY
- If using `mangle` (`action=mark-routing`), verify it does NOT mark traffic destined to the router itself, otherwise management traffic will be misrouted.
