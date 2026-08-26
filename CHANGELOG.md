# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-08-27

### Fixed
- Fixed the REPL command completer showing a stale full subcommand list (e.g. `add, select, list, remove, status`) right after fully typing a subcommand and pressing space (e.g. `/router add `). Caused by a background-thread scheduling race in the completer; completion now runs synchronously since it involves no I/O.
- `/provider` no longer risks two independently-settable notions of provider availability drifting out of sync (previously a hand-maintained `available` flag could claim a provider was ready when it had no registered model fetcher). A provider is now selectable if and only if it actually has a registered fetcher.

### Added
- `/provider` now detects an existing stored API key for a provider and offers **Use existing key / Replace API key / Cancel** instead of silently reusing or ignoring it.
- Replacing an API key only overwrites the stored key after the new key is successfully validated against the provider; if the new key is rejected or the user cancels, the old key is left untouched.

### Changed
- `/provider <name>` no longer targets a specific provider by argument; `/provider` (no argument) already lists all available providers, so the extra entry point was removed.

## [0.1.1] - 2026-08-26

### Fixed
- `/provider gemini` no longer fails with "No model fetcher registered for provider 'gemini'." — the fetcher is now correctly registered.
- Fixed a startup crash when `config.toml` referenced an `active_router` profile that no longer exists; the CLI now falls back to no active router instead of crashing.
- `/router list` and `/router status` now show the correct port for `backend=binary` routers (previously showed a leftover REST-probe port instead of the actual binary API port).
- Fixed a crash (`rich.errors.MarkupError`) when AI responses, user input, or router-provided data (e.g. interface/firewall comments) contained square-bracket text such as RouterOS paths (`[/ip route]`); this content is now escaped before rendering.

### Changed
- Config, chat history, memory database, and audit log now live under a single, rebranded `~/.config/mika/` directory (previously split across `~/.config/mikrotik-ai/` and `~/.mikrotik-ai/`). No automatic migration is provided from the old locations.

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
