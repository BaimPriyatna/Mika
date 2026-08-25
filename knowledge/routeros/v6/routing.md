---
topic: routing
routeros: "6"
source: official_version_specific
verified_at: 2024-06-01
---

# CONSTRAINTS: ROUTING (RouterOS 6)

## 1. SYNTAX RULES
- **Static Default Route**: `/ip route add dst-address=0.0.0.0/0 gateway=<ip>`

## 2. POLICY-BASED ROUTING (PBR)
- **Routing Marks (V6)**: Routing marks act as implicit routing tables. No pre-declaration is needed.
- **Assigning Routes**: `/ip route add dst-address=0.0.0.0/0 gateway=<ip> routing-mark=<MARK_NAME>`
- **Routing Rules**: Defined under `/ip route rule`.
