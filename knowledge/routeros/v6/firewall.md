---
topic: firewall
routeros: "6"
source: official_version_specific
verified_at: 2024-06-01
---

# CONSTRAINTS: FIREWALL FILTER (RouterOS 6)

## 1. CHAIN LOGIC
- `input`: To router.
- `forward`: Through router.
- `output`: From router.

## 2. SAFETY WARNINGS (CRITICAL)
- **Lockout Prevention**: Ensure management access (Winbox, SSH) is explicitly ACCEPTED on the `input` chain before adding any blanket DROP rules.

## 3. BEST PRACTICES & SYNTAX
- **Top-Down Evaluation**: Rules process sequentially.
- **Connection State Optimization**: Always accept `established,related` at the top of `input` and `forward`.
  - `/ip firewall filter add chain=input connection-state=established,related action=accept`
- **Drop Invalid**:
  - `/ip firewall filter add chain=input connection-state=invalid action=drop`
