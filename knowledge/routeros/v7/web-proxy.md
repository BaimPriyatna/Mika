---
topic: web-proxy
routeros: "7"
source: official_current
verified_at: 2024-06-01
---

# CONSTRAINTS: WEB PROXY (RouterOS 7)

## 1. SYNTAX
- **Enable**: `/ip proxy set enabled=yes port=8080`
- **Transparent Redirection**: `/ip firewall nat add chain=dstnat protocol=tcp dst-port=80 action=redirect to-ports=8080`

## 2. SAFETY (CRITICAL)
- **Open Proxy Prevention**: An open proxy is a severe vulnerability. You MUST add an `input` chain firewall rule dropping access to port 8080 from the WAN interface before enabling the proxy.
