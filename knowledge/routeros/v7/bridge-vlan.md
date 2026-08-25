---
topic: bridge-vlan
routeros: "7"
source: official_current
verified_at: 2024-06-01
---

# CONSTRAINTS: BRIDGE VLAN FILTERING (RouterOS 7)

## 1. CONFIGURATION WORKFLOW
1. Create bridge: `/interface bridge add name=bridge1 vlan-filtering=no` (Filter must be OFF during setup).
2. Add Ports:
   - Trunk: `/interface bridge port add bridge=bridge1 interface=ether1`
   - Access: `/interface bridge port add bridge=bridge1 interface=ether2 pvid=<VLAN_ID>`
3. Define VLANs: `/interface bridge vlan add bridge=bridge1 vlan-ids=<ID> tagged=<bridge1,ether1> untagged=<ether2>`
   - *Requirement*: The bridge itself MUST be added to `tagged` if the CPU needs to route this VLAN.
4. Enable Filtering: `/interface bridge set bridge1 vlan-filtering=yes`

## 2. SAFETY (CRITICAL)
- If you enable `vlan-filtering=yes` and the bridge is not correctly tagged for the management VLAN, you will immediately lose access.
