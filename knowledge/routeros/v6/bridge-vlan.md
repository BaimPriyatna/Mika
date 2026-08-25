---
topic: bridge-vlan
routeros: "6"
source: official_version_specific
verified_at: 2024-06-01
---

# CONSTRAINTS: BRIDGE VLAN FILTERING (RouterOS 6)

## 1. SYNTAX & WORKFLOW (v6.41+)
1. `/interface bridge add name=bridge1 vlan-filtering=no`
2. `/interface bridge port add bridge=bridge1 interface=etherX pvid=<VLAN_ID>`
3. `/interface bridge vlan add bridge=bridge1 vlan-ids=<ID> tagged=<bridge1,etherY> untagged=<etherX>`
4. `/interface bridge set bridge1 vlan-filtering=yes`

## 2. SAFETY (CRITICAL)
- The bridge interface acts as the CPU port. Ensure management traffic can reach the CPU before turning on `vlan-filtering=yes`.
