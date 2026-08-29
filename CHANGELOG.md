# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.5] - 2026-08-29

### Fixed
- `_compute_state_fingerprint()` was a dead-code stub that returned the plan's own fingerprint, which the caller then compared against itself -- always true, so the "refuse execution if router state changed since confirmation" safety check never actually verified anything. Now genuinely re-discovers the router and computes a fresh fingerprint from live state before comparing.
- `compute_router_fingerprint()` extended to cover firewall rules, NAT rules, and queues (previously only interfaces, addresses, DHCP, and hotspot), and to include each resource's `disabled` state -- a human manually enabling/disabling a rule or server (e.g. via WinBox) between plan creation and execution now correctly registers as drift and blocks a now-stale plan from executing. The fingerprint deliberately still excludes anything that changes on its own from normal traffic (byte/packet counters, DHCP leases, active hotspot sessions, interface link/running state) -- only fields that reflect actual configuration a human changed.

## [0.2.4] - 2026-08-29

### Fixed
- **Critical**: no configuration change could ever actually be applied to a router. `executor.py` called `self._client.add()`/`.update()`/`.delete()`, methods that have never existed on any `RouterClient` implementation -- only `create_resource()`/`update_resource()`/`delete_resource()` exist. Every plan, including `create_hotspot`, crashed with `AttributeError` at the execution step; planning and validation worked fine and completely masked this. Went undetected because the existing executor tests mocked the router client with a bare `AsyncMock()` shaped nothing like the real `RouterClient` protocol.
- `verification.py` and `rollback.py`'s resource-reader maps were missing `/ip/firewall/nat`, `/queue/simple`, and `/interface/vlan` -- verification would silently skip or falsely fail these, and rollback backups would silently fail to capture prior state for queues and VLAN interfaces before applying a change.
- `mock.py`: `/interface/vlan` was entirely unmapped (creation raised "unknown resource path"), and had no implicit `type: vlan` field injection, so a created VLAN interface would misreport its type on the next read.

### Changed
- Router-client-mocking tests now use `AsyncMock(spec=RouterClient)` instead of a bare `AsyncMock()`, so a mock diverging from the real protocol raises immediately instead of silently masking bugs.
- New `tests/integration/test_full_pipeline_real_client.py` exercises the full plan → validate → backup → execute → verify → rollback pipeline against the real `MockRouterClient` (not a loose mock) for several resource types.

## [0.2.3] - 2026-08-29

### Added
- All 17 CONFIGURATION/MODIFICATION/DESTRUCTIVE intents now have a real planner instead of showing "planner not yet implemented": `create_address`, `create_dhcp`, `create_firewall_rule`, `create_nat_rule`, `create_queue`, `create_vlan` (create_hotspot already existed); `modify_address`, `modify_firewall_rule`, `modify_dhcp`, `modify_hotspot`, `modify_queue`; `delete_address`, `delete_vlan`, `delete_firewall_rule`, `delete_dhcp`, `delete_hotspot`, `delete_queue`.
- New knowledge documents for the standalone `/interface vlan` feature (`knowledge/routeros/v6/vlan.md`, `v7/vlan.md`), verified via web search rather than guessed from memory.
- Router discovery extended with NAT rule and simple-queue collections, and VLAN id/parent metadata on interfaces, so the new planners can check for duplicates and resolve resource ids.
- A shared `resolve_resource()` helper enforces that every modify/delete planner re-resolves a resource's id against freshly-discovered router state rather than trusting a possibly-stale id (RouterOS can recycle `.id` values after deletion).

### Known limitations
- `modify_dhcp` cannot yet change `pool_start`/`pool_end`/`gateway`, and `modify_hotspot` cannot yet change `rate_limit` -- both live on sub-resources (`/ip/dhcp-server/network`, `/ip/hotspot/user/profile`) that aren't discovered yet. Both fail clearly with an explanation rather than guessing.
- `delete_dhcp` and `delete_hotspot` only remove the primary resource; the associated IP pool and network/profile entries created alongside it are left in place and flagged in the confirmation prompt.

## [0.2.2] - 2026-08-29

### Added
- CI: GitHub Actions workflow runs the test suite on every push and pull request to `main`.

### Fixed
- `memory.db` (`SessionStore`, `BackupStore`, `MemoryStorage`) had no WAL mode or explicit `busy_timeout`, unlike `AuditLogger` which already used WAL. Under the default rollback-journal mode, running two `mika` sessions against the same database (same machine) could raise "database is locked". All three stores now connect through a shared helper that enables WAL mode and a 5s `busy_timeout`.
- A bug inside any `/slash` command handler crashed the whole REPL with a raw traceback instead of being caught — only `ExitRepl` was handled. Slash commands now recover from unexpected errors the same way natural-language requests already did: print a friendly message and keep the session running.

## [0.2.1] - 2026-08-29

### Added
- `/troubleshoot <description>` — diagnose a reported problem and suggest fixes, backed by the existing `troubleshoot` module. Natural-language requests describing a symptom (e.g. "internet is down") now also route to diagnosis instead of being misread as a configuration request. After diagnosis, you can apply the recommended fixes through the normal plan/confirm/execute pipeline.

### Fixed
- API keys and router passwords (`.env`) were stored relative to the current working directory instead of a fixed location, so the globally-installed `mika` command could silently read or write a different `.env` depending on where it was launched from, losing credentials. Now fixed at `~/.config/mika/.env`, consistent with `config.toml`; an existing `.env` in the old location is migrated automatically on next use.
- Removed the stale `.env.example` and its README setup step: `/provider` and `/router add` fully automate `.env` now, and the template's variables no longer matched what the app actually reads.

## [0.2.0] - 2026-08-27

### Added
- `/rewind` — roll back the router's actual configuration to match an earlier point in the conversation, like `git checkout` for router config. Undoes each executed plan since that point (most recent first) via the existing rollback mechanism, stopping and reporting clearly if a step fails partway through. Requires explicit confirmation before touching the router.
- Conversation sessions are now scoped per router: switching to a different router automatically starts a new session, so a session's history never mixes changes from more than one router.
- `/history` is now a two-step picker — choose a router, then a session under it — instead of a flat list.

### Fixed
- `start_new_session()` could tag a new session with the previous router instead of the one being switched to, since the switch order meant the new router wasn't recorded yet at the point the session was tagged.
- `AuditLogger` was still hardcoded to the real home directory with no override, unlike the other memory/session stores, which could pollute a real user's `~/.config/mika/` during testing.

## [0.1.3] - 2026-08-27

### Added
- Conversation sessions now persist across `mika` restarts (previously lost when the app closed). A new session starts automatically on every launch.
- `/sessions` lists saved conversation sessions; `/resume <#>` continues an earlier one.
- The AI now receives recent conversation history and long-term remembered facts (previously stored but never actually read by the AI) as part of its context for each turn.

### Changed
- `/clear` and `/reset` now start a fresh persisted session instead of only clearing the in-memory display.

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
