---
topic: queue
routeros: "6"
source: official_version_specific
verified_at: 2024-06-01
---

# CONSTRAINTS: QUEUES (RouterOS 6)

## 1. SYNTAX RULES
- **Simple Queue**: `/queue simple add name=<name> target=<ip_or_iface> max-limit=<upload>/<download>`

## 2. SAFETY & FASTTRACK CONFLICT (CRITICAL)
- FastTrack (`action=fasttrack-connection` in firewall filter) completely bypasses queues. Ensure FastTrack is disabled or properly filtered for queued traffic.
- **PCQ**: Per Connection Queue is the standard method in v6 for evenly distributing bandwidth among users.
