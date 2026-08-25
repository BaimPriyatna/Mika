# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-25

### Added
- Initial release of MIKA (AI-assisted MikroTik RouterOS CLI).
- Dual backend architecture supporting both RouterOS v7+ REST API and RouterOS v6/v7 Binary API (port 8728/8729).
- Explicit version mapping for RouterOS v6 and v7 resource paths and features.
- Interactive setup wizard for AI providers and MikroTik router connections with SSL certificate management.
- Natural language intent parsing with automated safety verification and dry-run diff preview.
- Pre-execution snapshot backups and automated rollback capability.
- Read-only router inspection commands (`/inspect`).
- Comprehensive audit logging and system health collector.
