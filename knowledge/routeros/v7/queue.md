---
topic: queue
routeros: "7"
source: official_current
verified_at: 2024-06-01
---

# CONSTRAINTS: QUEUES & QoS (RouterOS 7)

## 1. SYNTAX RULES
- **Simple Queue**: `/queue simple add name=<name> target=<ip_or_iface> max-limit=<upload>/<download>`
  - Example: `max-limit=5M/10M`

## 2. SAFETY & FASTTRACK CONFLICT (CRITICAL)
- Queues will NOT WORK if traffic is FastTracked. 
- You MUST verify that `/ip firewall filter` does not contain a broad `action=fasttrack-connection` rule, or you must bypass it for the queued targets.

## 3. VERSION 7 SPECIFICS
- v7 introduces new QoS types like `FQ_CoDel` and `CAKE`. Use these in `/queue type` for bufferbloat mitigation instead of legacy types when possible.
