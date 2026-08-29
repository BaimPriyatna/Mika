# Mika — Configure MikroTik by Talking to It

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Status: Active Development](https://img.shields.io/badge/status-active%20development-yellow.svg)](#what-mika-can-do-today)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

### An AI-Powered Assistant for MikroTik RouterOS

There is a particular kind of fatigue that comes from managing a MikroTik router by hand — the muscle memory of typing `/ip firewall filter add` for the hundredth time, the quiet dread of a misplaced `chain=` argument, the ritual of re-reading the manual before touching a production device. Mika exists to remove that fatigue without removing your control over the outcome.

Mika is a command-line assistant that lets you describe network changes in plain language — "create a guest hotspot on wlan1," "why can't clients get an IP address," "block port 25 for the accounting VLAN" — and turns that description into a concrete, reviewable, reversible set of RouterOS operations. It does not guess. It does not run commands quietly in the background. Every change it proposes is validated by deterministic code, shown to you as a diff, and applied only after you say yes.

---

## Table of Contents

- [Philosophy](#philosophy)
- [Installation](#installation)
- [Getting Started](#getting-started)
- [Router Compatibility](#router-compatibility)
- [Auto-Discovery (MNDP)](#auto-discovery-mndp)
- [How Mika Thinks](#how-mika-thinks)
- [Working in the REPL](#working-in-the-repl)
- [Project Layout](#project-layout)
- [Configuration](#configuration)
- [Supported AI Providers](#supported-ai-providers)
- [What Mika Can Do Today](#what-mika-can-do-today)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [Contributing](#contributing)
- [Acknowledgments](#acknowledgments)
- [License](#license)
- [Disclaimer](#disclaimer)

---

## Philosophy

Large language models are good at understanding intent and bad at being trusted unsupervised with production infrastructure. Mika is built around that tension rather than around it. The model's only job is to interpret what you're asking for. Every other step — validating the proposal against RouterOS's actual rules, generating a human-readable diff, executing the change through typed operations, verifying that the router ended up in the state you expected — is handled by ordinary, deterministic, testable code that never guesses.

**Before Mika**, configuring a guest hotspot looked like this:

```
/ip hotspot add name=guest interface=wlan1 address-pool=guest-pool profile=guest-profile
/ip pool add name=guest-pool ranges=192.168.88.10-192.168.88.50
/ip hotspot profile add name=guest-profile html-directory=hotspot
```

**With Mika**, it looks like this:

```
mika> create a guest hotspot on wlan1 with IP range 192.168.88.10-50
```

Mika interprets the request, builds the plan, shows you exactly what will change, and waits.

---

## Installation

### Prerequisites

Mika needs Python 3.12 or newer, the [uv](https://docs.astral.sh/uv/) package manager (pip works too, but uv is faster and what the project is built against), a MikroTik router running RouterOS v6 or v7, and an API key from one of the supported AI providers. Mika talks to your router through either its REST API (v7+) or its Binary API (v6 and v7) — it detects which one is available and adapts automatically, so you don't need to enable anything you don't already have. See [Router Compatibility](#router-compatibility) for the details.

### Setting Up

```bash
# Clone the repository
git clone https://github.com/BaimPriyatna/mika.git
cd mika

# Create a virtual environment and install dependencies
uv venv
uv pip install -e ".[dev]"
```

API keys and router passwords are set up interactively later via `/provider` and `/router add` — they're stored at `~/.config/mika/.env`, not in the project directory. There's nothing to copy or edit by hand before you start.

If you'd rather use plain pip:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

A virtual environment is recommended but not required. If you'd rather install straight into your system or global Python — common on setups where a venv isn't the usual workflow — you can skip it entirely:

```bash
# Skips the virtual environment — installs into your system/global Python.
# Faster to get started, but can conflict with other Python projects on the same machine.
pip install -e ".[dev]"
```

---

## Getting Started

Launch Mika with no arguments and it drops you straight into its interactive shell:

```bash
mika
```

On first run, a short setup wizard walks you through two things: which AI provider you want to use (and its API key), and how to reach your router. You don't need to already know its IP address — Mika scans the local network first and lets you pick from what it finds:

```
mika> /router add

Scanning local network for MikroTik routers (MNDP, 5s) ...

  ? RB4011 (192.168.88.1)      MAC 48:8F:5A:1C:9D:2E    RouterOS 7.15
  ? hAP-ax2 (192.168.88.254)   MAC D4:CA:6D:88:41:0F     RouterOS 6.49.10
  ? Enter IP manually

Use arrow keys to select, Enter to confirm.
```

Once you've picked a router (or typed its IP in by hand), Mika probes it and connects. If your router is running v7 with the REST API enabled, it connects and moves on without asking anything further. If it isn't — most commonly because you're on v6, or REST is simply switched off — Mika falls back to the Binary API automatically and asks how you'd like to connect:

```
Probing 192.168.88.254 ...
REST API not detected. Falling back to RouterOS Binary API (compatible with v6 & v7).

Choose a connection mode:
  [1] Plaintext (port 8728)         — recommended for LAN/lab environments
  [2] SSL / TLS (port 8729)

> 2

Certificate handling:
  [1] Trust self-signed certificate (default)
  [2] Provide a custom CA certificate (.crt / .pem)

> 1

Connected via Binary API (SSL, self-signed). Router profile saved.
```

Everything sensitive — the API keys and router credentials from this whole flow — is stored in a local `.env` file at `~/.config/mika/.env`, never in plaintext config, never synced anywhere.

From then on, you're just talking to it — the underlying backend is invisible to how you interact with Mika:

```
mika> create a VLAN 10 for guests on bridge1

Proposed Changes:
  CREATE /interface/vlan
    - name: vlan10-guests
    - vlan-id: 10
    - interface: bridge1

  CREATE /interface/bridge/port
    - bridge: bridge1
    - interface: vlan10-guests

◆ Action Confirmation

  ❯ ✓  Yes, apply changes
    ✗  No, cancel
    ✎  Type manual changes desired

(Use arrow keys)

Configuration applied successfully.
```

Destructive operations — deletes, or changes that could disrupt active connections — get a harder stop instead of the select menu:

```
mika> delete the guest hotspot on wlan1

Proposed Changes:
  DELETE /ip/hotspot [name=guest]
  DELETE /ip/pool [name=guest-pool]
  DELETE /ip/hotspot/profile [name=guest-profile]

┌──────────────────────── WARNING ────────────────────────┐
│ DESTRUCTIVE OPERATION                                    │
│                                                            │
│ This operation will DELETE or significantly modify       │
│ resources. Active connections and services may be        │
│ permanently affected.                                     │
│                                                            │
│ Type exactly to proceed:                                  │
│   CONFIRM DELETE                                           │
└────────────────────────────────────────────────────────┘

> CONFIRM DELETE

✓ Confirmation accepted
Configuration applied successfully.
```

There's no shortcut around this — anything less than the exact phrase cancels the operation.

You can also skip the interactive shell entirely and fire single commands:

```bash
mika chat "configure DHCP server on ether2 with range 192.168.1.100-200"
mika troubleshoot "clients can't get IP address"
mika monitor
```

---

## Router Compatibility

Not every MikroTik router speaks the same API, so Mika doesn't force you into one. It supports two backends and picks the right one automatically based on what your router actually exposes:

- **REST API** (`RestRouterClient`, via `httpx`) — available on RouterOS **v7 and newer**. Fast, modern, and the default path when it's present.
- **Binary API** (`BinaryRouterClient`, via `librouteros`) — works on **both v6 and v7**, and is what Mika falls back to when REST isn't available.

Because v6 and v7 don't share the same paths or feature set, Mika keeps an explicit mapping between them rather than guessing — the same request produces the correct resource path whether your router speaks the old wireless stack or the new WiFi package.

| | RouterOS v6 | RouterOS v7 |
|---|---|---|
| Backend | Binary API only | REST API (default) or Binary API |
| Wireless | `/interface/wireless` | `/interface/wifi` |
| Routing tables | classic `gateway` / `check-gateway` | `/routing/table` |
| WireGuard | Not supported | Supported |
| Containers | Not supported | Supported |

When Mika connects over the Binary API, it also offers a choice of transport:

| Mode | Port | Notes |
|---|---|---|
| Plaintext | 8728 | Unencrypted — fine for a trusted LAN or lab, not recommended over the open internet |
| SSL, self-signed | 8729 | Encrypted, trusts the router's built-in self-signed certificate |
| SSL, custom CA | 8729 | Encrypted, verifies against a certificate you provide (`.crt` / `.pem`) |

Unsupported operations on a given version — WireGuard on v6, for instance — are marked `unsupported` at the planning stage rather than sent to the router and failing there, so you find out before anything is attempted, not after.

---

## Auto-Discovery (MNDP)

Rather than making you look up your router's IP address before you can even start, Mika can find it for you. It speaks **MNDP** (MikroTik Neighbor Discovery Protocol) — the same Layer 2 broadcast protocol WinBox uses to list nearby routers.

Here's how it works: Mika sends an MNDP query as a UDP broadcast on port 5678, listens for replies for a few seconds, and shows you every router that answered — name, IP, MAC address, and RouterOS version — as a selectable list. Pick one with the arrow keys and Mika carries that choice straight into the normal connection flow (probing REST, falling back to Binary API if needed, and so on).

A few things worth knowing:

- **Local network only.** MNDP is a broadcast protocol, so it only discovers routers on the same Layer 2 segment as the machine running Mika — it won't find anything across a routed network or the internet.
- **Read-only and passive.** The scan doesn't authenticate, configure, or change anything; it's purely "who's out there."
- **Always optional.** If nothing turns up, or you already know the IP, `Enter IP manually` is right there in the same list — discovery never blocks you from just typing the address in.
- **Timeout is configurable.** The default scan window is a few seconds; if your network is large or slow to respond, this can be extended in configuration.

---

## How Mika Thinks

Every request you make passes through the same seven-stage pipeline, regardless of how simple or complex it is:

1. **Propose** — the language model reads your request and drafts an intended change.
2. **Validate** — deterministic code checks the proposal against RouterOS's actual constraints. Nothing here is guessed from memory; RouterOS syntax is looked up, not recalled.
3. **Diff** — the exact before-and-after state is rendered so you can see precisely what will move.
4. **Confirm** — you approve or reject. There is no flag to skip this step.
5. **Execute** — approved changes run through typed, validated operations, never raw strings.
6. **Verify** — the router's actual resulting state is checked against what was expected.
7. **Rollback** — if verification fails, Mika reverts automatically rather than leaving the router in an unknown state.

Destructive operations carry extra weight. A `CREATE` or `UPDATE` shows an interactive Yes / No / Modify menu. A `DELETE` requires you to type `CONFIRM DELETE` in full — a small piece of friction that exists on purpose.

---

## Working in the REPL

| Command | What it does |
|---|---|
| `/help` | List every available command |
| `/router` | Reconfigure the active router connection |
| `/provider` | Change or add an AI provider |
| `/inspect` | Show the details of the current execution plan |
| `/status` | Check router connectivity |
| `/history` | Review past commands in this session |
| `/backup` | Take a manual configuration backup |
| `/clear` | Clear the screen |
| `/exit` | Leave Mika |

And beyond the slash commands, Mika understands requests like:

- "Configure a hotspot on wlan1 for guests"
- "Add a firewall rule to block port 25"
- "Create a DHCP server on ether2 with range 10.0.0.100-150"
- "Show me the current NAT configuration"
- "Why is my internet not working?"
- "Add a static route to 10.10.0.0/24 via 192.168.1.1"

---

## Project Layout

```
mika/
├── src/mika/
│   ├── ai/              AI provider abstraction, prompts, schemas
│   ├── audit/            Full operation logging
│   ├── cli/               CLI interface, REPL, and slash commands
│   ├── executor/       Command execution, confirmation, verification
│   ├── knowledge/     RouterOS documentation and knowledge base
│   ├── memory/          Conversation context management
│   ├── monitoring/    Health metrics and system monitoring
│   ├── planner/          Deterministic planning and diff generation
│   ├── router/           REST & Binary API clients, discovery, v6/v7 path mapping
│   ├── troubleshoot/  Diagnostic and troubleshooting workflows
│   ├── utils/             Utilities and terminal output formatting
│   └── validator/       Configuration validation engine
├── tests/
│   ├── unit/                Unit tests for every component
│   ├── integration/     End-to-end tests
│   └── fixtures/           Test fixtures and a mock router
├── knowledge/
│   ├── concepts/          Networking concepts (VLANs, subnetting, etc.)
│   └── routeros/           RouterOS-specific reference material
└── pyproject.toml
```

---

## Configuration

Mika is configured through two files, both created and managed for you automatically:

- `~/.config/mika/config.toml` — non-sensitive settings: last-used model, provider, router profiles (host, username, backend, port, TLS). Set up via the `/provider` and `/router add` wizards; you rarely need to touch it by hand.
- `~/.config/mika/.env` — sensitive secrets only: `MIKA_PROVIDER_<NAME>_API_KEY` and `MIKA_ROUTER_<ALIAS>_PASSWORD`. Written by `/provider` and `/router add`; the file is created with owner-only (`0600`) permissions. There's no template to copy — the wizards write it for you.

REST vs Binary API, TLS verification, and Binary API port/SSL settings are all picked automatically by the `/router add` wizard based on what your router exposes — you don't need to set them manually.

---

## Supported AI Providers

| Provider | Models | Notes |
|---|---|---|
| Google Gemini | gemini-1.5-flash, gemini-1.5-pro | Recommended for cost efficiency |
| OpenAI | gpt-4, gpt-3.5-turbo | Strong general-purpose performance |
| Anthropic | claude-3-opus, claude-3-sonnet | Best suited for complex reasoning |

---

## What Mika Can Do Today

At a high level, Mika currently handles:

- **Natural language configuration** — describe what you want; Mika turns it into a structured intent and a concrete plan.
- **Auto-discovery on the local network** — scans for MikroTik routers via MNDP, no need to already know the IP. See [Auto-Discovery (MNDP)](#auto-discovery-mndp).
- **Multi-backend router connectivity** — REST API for RouterOS v7+, Binary API for v6 and v7, auto-detected. See [Router Compatibility](#router-compatibility).
- **Deterministic validation and diff preview** — every proposed change is checked against real RouterOS constraints and shown as a before/after diff, never applied blindly.
- **Safety-gated execution** — standard confirmations for creates and updates, an explicit typed confirmation for deletes, no bypass flags.
- **Post-execution verification and automatic rollback** — Mika checks that the router actually ended up in the expected state, and reverts if it didn't.
- **Interactive REPL** — a full conversational shell with history, autocomplete, and slash commands.
- **Troubleshooting workflows** — diagnostic assistance for common problems ("clients can't get an IP address").
- **Health monitoring** — real-time system metrics and interface statistics.
- **Full audit logging** — every operation is recorded and traceable.

This list changes only when a genuinely new capability ships, not with every incremental commit — for a history of what's shipped, see [`CHANGELOG.md`](CHANGELOG.md).

---

## Development

```bash
# Run the full test suite
pytest

# Run a single test file
pytest tests/unit/test_planner_hotspot.py

# Run with coverage
pytest --cov=mika --cov-report=html

# Integration tests only
pytest tests/integration/

# Lint and format
ruff check src/ tests/
ruff format src/ tests/
```

Mika is built on a small set of non-negotiable principles: every data structure is a Pydantic model, no AI reasoning ever enters the validation or execution path, every state-changing action requires explicit user approval, every operation is audited, and every failure mode degrades gracefully rather than silently.

---

## Troubleshooting

**API connection failed** — confirm the router's REST API is actually enabled:

```
/ip service print
/ip service enable api
```

**Authentication error** — double-check the credentials in `.env`, and make sure the router user has sufficient permissions.

**AI provider error** — verify the API key is valid and has remaining quota, check connectivity to the provider, or switch providers with `/provider`.

**Import error** — reinstall dependencies from a clean slate:

```bash
uv pip install -e ".[dev]" --force-reinstall
```

---

## Security

API keys and router credentials belong in `.env`, never in version control. Review audit logs periodically for changes you don't recognize. Prefer a VPN or otherwise secured network path when managing routers remotely. And where possible, create a dedicated router account scoped to only the permissions Mika actually needs — least privilege isn't a formality here, it's the second line of defense after the confirmation prompt.

---

## Contributing

Fork the repository, branch off for your feature, and bring tests with you — code without tests doesn't get merged. Match the existing style, make sure the full suite passes, update documentation where it's affected, and open a pull request that explains the *why*, not just the *what*.

Every function carries type hints, every public API carries a docstring, and every change to the safety architecture gets extra scrutiny in review.

---

## Acknowledgments

Mika stands on the shoulders of a few excellent open-source projects: [Typer](https://typer.tiangolo.com/) for the CLI framework, [Rich](https://rich.readthedocs.io/) for terminal output that doesn't look like 1998, [Pydantic](https://docs.pydantic.dev/) for data validation, [httpx](https://www.python-httpx.org/) for async HTTP, and [questionary](https://github.com/tmbo/questionary) for interactive prompts that feel like part of a conversation rather than a form.

---

## Support

Bugs and feature requests go through [GitHub Issues](https://github.com/BaimPriyatna/mika/issues). Broader conversation lives in [GitHub Discussions](https://github.com/BaimPriyatna/mika/discussions).

---

## License

MIT — see [LICENSE](LICENSE) for the full text.

---

## Disclaimer

Mika is an independent, third-party tool and is not affiliated with or endorsed by MikroTik. Test configuration changes in a non-production environment before trusting them on live infrastructure. Mika's safety mechanisms reduce risk; they do not eliminate it, and you remain responsible for every change applied to your network.

---

*Built for network administrators who want automation without giving up the wheel.*