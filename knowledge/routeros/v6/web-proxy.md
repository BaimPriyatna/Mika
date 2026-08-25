---
topic: web-proxy
routeros: "6"
source: official_version_specific
verified_at: 2024-06-01
---

# CONSTRAINTS: WEB PROXY (RouterOS 6)

## 1. SYNTAX
- **Enable**: `/ip proxy set enabled=yes port=8080`
- **Transparent**: `/ip firewall nat add chain=dstnat protocol=tcp dst-port=80 action=redirect to-ports=8080`
- **ACL Block**: `/ip proxy access add dst-host="*<domain>*" action=deny`

## 2. SAFETY (CRITICAL)
- **Open Proxy Prevention**: ALWAYS block access to the proxy port on the WAN interface using `/ip firewall filter chain=input action=drop dst-port=8080`.
