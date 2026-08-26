from __future__ import annotations

from collections.abc import Awaitable, Callable

import questionary
import httpx
from rich.console import Console

from mika.ai.errors import AIAuthenticationError, AIError
from mika.cli import config as cli_config
from mika.cli import env_secrets
from mika.cli.errors import CliError
from mika.router.mndp import MndpDevice, scan as mndp_scan

console = Console()

_CUSTOM_MODEL_CHOICE = "__custom__"
_MANUAL_HOST_CHOICE = "__manual__"

_PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "gemini": "Google Gemini",
    "openai": "OpenAI (coming soon)",
    "local": "Local model (coming soon)",
}

_WIZARD_STYLE = questionary.Style([
    ("qmark", "fg:#c084fc bold"),
    ("question", "bold white"),
    ("pointer", "fg:#c084fc bold"),
    ("highlighted", "fg:#c084fc bold"),
    ("selected", "fg:#10b981 bold"),
    ("instruction", "fg:#888888 italic"),
    ("disabled", "fg:#666666 italic"),
])

_MODEL_FETCHERS: dict[str, Callable[[str], Awaitable[list[str]]]] = {}


class WizardCancelled(CliError):
    pass


def register_model_fetcher(provider: str, display_name: str | None = None) -> Callable:
    """Register a provider's model fetcher.

    A provider is only ever selectable in the wizard if it has a fetcher
    registered here -- there is no separate "available" flag to fall out of
    sync. `display_name` is optional; if omitted, an existing entry in
    `_PROVIDER_DISPLAY_NAMES` (or the raw provider key) is used.
    """
    def decorator(fn: Callable[[str], Awaitable[list[str]]]) -> Callable:
        _MODEL_FETCHERS[provider] = fn
        if display_name:
            _PROVIDER_DISPLAY_NAMES[provider] = display_name
        else:
            _PROVIDER_DISPLAY_NAMES.setdefault(provider, provider)
        return fn
    return decorator


def _provider_choices() -> list[questionary.Choice]:
    """Build the provider picker choices. A provider is selectable if and
    only if it has a registered model fetcher -- this makes it structurally
    impossible for the picker to offer a provider whose fetcher is missing."""
    return [
        questionary.Choice(
            title=label,
            value=key,
            disabled=None if key in _MODEL_FETCHERS else "coming soon",
        )
        for key, label in _PROVIDER_DISPLAY_NAMES.items()
    ]


async def scan_and_select_router(timeout: float = 5.0) -> MndpDevice | None:
    console.print()
    with console.status("[bold #c084fc]◆[/bold #c084fc] Scanning local network for MikroTik devices...", spinner="dots"):
        import asyncio
        try:
            devices = await asyncio.wait_for(mndp_scan(timeout=timeout), timeout=timeout + 1)
        except asyncio.TimeoutError:
            devices = []

    if not devices:
        console.print("[yellow]◆ No MikroTik devices found on local network.[/yellow]")
        console.print("[dim]Tip: Make sure the router is connected to the same network segment.[/dim]")
        return None

    console.print(f"[bold #c084fc]◆[/bold #c084fc] Found [bold]{len(devices)}[/bold] device(s):")
    console.print()

    choices = []
    for device in devices:
        host_display = device.ip_address or device.mac_address
        label = f"{'◉' if device.ip_address else '○'}  {device.identity:<20}  {host_display:<18}  {device.board or device.platform}"
        if device.version:
            label += f"  RouterOS {device.version}"
        if not device.ip_address:
            label += "  [dim](no IP — needs manual setup)[/dim]"
        choices.append(questionary.Choice(title=label, value=device))

    choices.append(questionary.Choice(title="✎  Enter host / IP manually", value=None))

    selected = await questionary.select(
        "Select a router:",
        choices=choices,
        style=_WIZARD_STYLE,
        qmark="◈",
        instruction="(Use arrow keys)",
    ).ask_async()

    return selected


async def select_model(config: cli_config.AppConfig) -> tuple[str, str]:
    existing_choices = [
        questionary.Choice(title=f"{entry.provider}: {entry.model}", value=(entry.provider, entry.model))
        for entry in config.models
    ]
    existing_choices.append(questionary.Choice(title="+ Add new model", value="__add__"))

    selected = await questionary.select(
        "Select model:",
        choices=existing_choices,
        style=_WIZARD_STYLE,
        qmark="◈",
    ).ask_async()

    if selected is None:
        raise WizardCancelled("Model selection cancelled.")

    if selected == "__add__":
        provider, models = await run_provider_wizard()
        if len(models) == 1:
            model = models[0]
        else:
            model = await _select_fetched_model(models)
        for m in models:
            config.remember_model(provider, m)
        return provider, model

    return selected


async def select_router(config: cli_config.AppConfig, *, active_alias: str | None = None) -> str | None:
    choices = []
    for alias, profile in config.routers.items():
        label = f"{alias}  ({profile.host}:{profile.port}  {profile.backend})"
        if alias == active_alias:
            label += "  [active]"
        choices.append(questionary.Choice(title=label, value=alias))
    choices.append(questionary.Choice(title="+ Add new router", value="__add__"))

    selected = await questionary.select(
        "Select router:",
        choices=choices,
        style=_WIZARD_STYLE,
        qmark="◈",
    ).ask_async()

    return selected


async def select_inspect_target() -> str | None:
    from mika.cli.render import INSPECT_TARGETS
    return await questionary.select(
        "Select inspect target:",
        choices=list(INSPECT_TARGETS),
        style=_WIZARD_STYLE,
        qmark="◈",
    ).ask_async()


async def run_provider_wizard() -> tuple[str, list[str]]:
    provider = await questionary.select(
        "Select AI provider:",
        choices=_provider_choices(),
        style=_WIZARD_STYLE,
        qmark="◈",
    ).ask_async()
    if provider is None:
        raise WizardCancelled("Provider selection cancelled.")

    fetcher = _MODEL_FETCHERS.get(provider)
    if fetcher is None:
        # Defense-in-depth: unreachable via the picker itself (disabled
        # choices can't be selected), but kept in case this is ever called
        # with a provider key that bypasses _provider_choices().
        raise WizardCancelled(f"No model fetcher registered for provider '{provider}'.")

    existing_key = env_secrets.get_provider_secret(provider)
    api_key = existing_key
    if existing_key:
        action = await questionary.select(
            f"{provider} is already configured.",
            choices=[
                questionary.Choice(title="Use existing API key", value="use"),
                questionary.Choice(title="Replace API key", value="replace"),
                questionary.Choice(title="Cancel", value="cancel"),
            ],
            style=_WIZARD_STYLE,
            qmark="◈",
        ).ask_async()
        if action is None or action == "cancel":
            raise WizardCancelled("Provider configuration cancelled.")
        if action == "replace":
            api_key = None  # fall through to key-entry loop below; old key stays untouched until fetch succeeds

    while True:
        if api_key is None:
            api_key = await questionary.password(
                f"Enter API key for {provider}:",
                style=_WIZARD_STYLE,
                qmark="◈",
            ).ask_async()
            if api_key is None:
                raise WizardCancelled("API key input cancelled.")

        try:
            with console.status(f"Connecting to {provider} to fetch model list..."):
                models = await fetcher(api_key)
        except AIAuthenticationError as exc:
            console.print(f"[red]API key rejected by {provider}:[/red] {exc}")
            retry = await questionary.confirm(
                "Try entering a different API key?", default=True
            ).ask_async()
            if not retry:
                raise WizardCancelled("API key rejected; user declined to retry.") from exc
            api_key = None
            continue
        except AIError as exc:
            console.print(f"[yellow]Failed to fetch model list from {provider}:[/yellow] {exc}")
            fallback = await questionary.confirm(
                "Enter model name manually?", default=True
            ).ask_async()
            if not fallback:
                raise WizardCancelled("Model list fetch failed; user declined manual entry.") from exc
            model = await questionary.text("Model name:", style=_WIZARD_STYLE, qmark="◈").ask_async()
            if not model:
                raise WizardCancelled("Custom model name cancelled or empty.") from exc
            if api_key != existing_key:
                _persist_provider_secret(provider, api_key)
            return provider, [model]

        if api_key != existing_key:
            _persist_provider_secret(provider, api_key)
        console.print(f"[green]{len(models)} models available for {provider}.[/green]")
        return provider, models


async def _select_fetched_model(models: list[str]) -> str:
    choices = [questionary.Choice(title=name, value=name) for name in models]
    choices.append(questionary.Choice(title="Custom (enter model name)", value=_CUSTOM_MODEL_CHOICE))

    model = await questionary.select(
        "Select model:",
        choices=choices,
        style=_WIZARD_STYLE,
        qmark="◈",
    ).ask_async()
    if model is None:
        raise WizardCancelled("Model selection cancelled.")
    if model == _CUSTOM_MODEL_CHOICE:
        model = await questionary.text("Model name:", style=_WIZARD_STYLE, qmark="◈").ask_async()
        if not model:
            raise WizardCancelled("Custom model name cancelled or empty.")
    return model


def _persist_provider_secret(provider: str, api_key: str) -> None:
    try:
        env_secrets.set_provider_secret(provider, api_key)
        if env_secrets.ensure_gitignored():
            console.print("[dim]Added '.env' to .gitignore.[/dim]")
    except env_secrets.EnvFileError as exc:
        console.print(f"[yellow]Warning:[/yellow] {exc}")
        console.print(
            "[yellow]API key is not permanently stored -- provider remains active for this session, "
            "but you will need to run /provider again in subsequent sessions.[/yellow]"
        )


async def _probe_rest_api(host: str, port: int, verify_tls: bool) -> bool:
    url = f"https://{host}:{port}/rest/system/resource"
    try:
        async with httpx.AsyncClient(verify=verify_tls, timeout=5.0) as client:
            resp = await client.get(url, auth=("admin", ""))
            return resp.status_code in (200, 401, 403)
    except Exception:
        return False


async def run_router_wizard(
    *,
    existing_aliases: list[str] | None = None,
    discovered: MndpDevice | None = None,
) -> tuple[str, cli_config.RouterProfileConfig]:
    existing = set(existing_aliases or [])

    def _validate_alias(value: str) -> bool | str:
        if not value.strip():
            return "Alias cannot be empty."
        if value in existing:
            return f"Alias '{value}' is already in use."
        return True

    default_alias = ""
    if discovered and discovered.identity:
        slug = discovered.identity.lower().replace(" ", "-").replace("_", "-")
        default_alias = slug if slug not in existing else ""

    alias = await questionary.text(
        "Router alias (e.g. 'office', 'lab'):",
        default=default_alias,
        validate=_validate_alias,
        style=_WIZARD_STYLE,
        qmark="◈",
    ).ask_async()
    if not alias:
        raise WizardCancelled("Router alias input cancelled or empty.")

    if discovered:
        if not discovered.ip_address and not discovered.ipv6_address:
            console.print()
            console.print(
                "[bold yellow]◆ Warning:[/bold yellow] This router has [bold]no IP address[/bold] assigned."
            )
            console.print(
                "[dim]You need to assign an IP first via WinBox (using MAC address) or MAC-Telnet,[/dim]"
            )
            console.print("[dim]then run /router add again.[/dim]")
            console.print()
            proceed = await questionary.confirm(
                "Continue anyway (enter IP manually)?",
                default=False,
                style=_WIZARD_STYLE,
                qmark="◈",
            ).ask_async()
            if not proceed:
                raise WizardCancelled("Router has no IP address; user aborted.")
            host = await questionary.text(
                "Router Host / IP:",
                style=_WIZARD_STYLE,
                qmark="◈",
            ).ask_async()
            if not host:
                raise WizardCancelled("Host input cancelled or empty.")
        else:
            host = discovered.display_host
            console.print(
                f"[bold #c084fc]◆[/bold #c084fc] Using discovered host: [bold]{host}[/bold]"
            )
    else:
        host = await questionary.text(
            "Router Host / IP:",
            style=_WIZARD_STYLE,
            qmark="◈",
        ).ask_async()
        if not host:
            raise WizardCancelled("Host input cancelled or empty.")

    username = await questionary.text(
        "Username:",
        default="admin",
        style=_WIZARD_STYLE,
        qmark="◈",
    ).ask_async()
    if not username:
        raise WizardCancelled("Username input cancelled or empty.")

    password = await questionary.password(
        "Password: (leave empty if not set)",
        style=_WIZARD_STYLE,
        qmark="◈",
    ).ask_async()
    if password is None:
        raise WizardCancelled("Password input cancelled.")

    console.print("[dim]Probing router for REST API support...[/dim]")
    rest_port_raw = await questionary.text(
        "REST API Port (for v7 probe):",
        default="443",
        style=_WIZARD_STYLE,
        qmark="◈",
    ).ask_async()
    if rest_port_raw is None:
        raise WizardCancelled("Port input cancelled.")
    try:
        rest_port = int(rest_port_raw)
    except ValueError:
        raise WizardCancelled(f"Invalid port: {rest_port_raw!r}") from None

    rest_available = await _probe_rest_api(host, rest_port, verify_tls=False)

    if rest_available:
        console.print("[green]✓ RouterOS REST API detected (v7+). Using REST backend.[/green]")
        verify_tls = await questionary.confirm(
            "Verify TLS certificate?",
            default=False,
            style=_WIZARD_STYLE,
            qmark="◈",
        ).ask_async()
        if verify_tls is None:
            raise WizardCancelled("TLS confirmation cancelled.")

        backend = "rest"
        api_port = None
        api_ssl = False
        port = rest_port
    else:
        console.print(
            "[yellow]REST API not detected. Falling back to binary API "
            "(compatible with RouterOS v6 and v7).[/yellow]"
        )
        port = rest_port

        api_proto = await questionary.select(
            "Binary API connection type:",
            choices=[
                questionary.Choice(title="Plaintext (port 8728) — recommended for local/trusted networks", value="plain"),
                questionary.Choice(title="SSL / TLS (port 8729) — encrypted connection", value="ssl"),
            ],
            style=_WIZARD_STYLE,
            qmark="◈",
        ).ask_async()
        if api_proto is None:
            raise WizardCancelled("Binary API protocol selection cancelled.")

        use_ssl = api_proto == "ssl"
        api_ssl_cert = None
        api_ssl_verify = False

        if use_ssl:
            cert_mode = await questionary.select(
                "SSL certificate handling:",
                choices=[
                    questionary.Choice(title="Trust Self-Signed Certificate (Default / Auto)", value="self_signed"),
                    questionary.Choice(title="Custom CA / Certificate file (.crt / .pem)", value="custom"),
                ],
                style=_WIZARD_STYLE,
                qmark="◈",
            ).ask_async()
            if cert_mode is None:
                raise WizardCancelled("Certificate mode selection cancelled.")

            if cert_mode == "custom":
                api_ssl_cert = await questionary.text(
                    "Path to certificate/CA file:",
                    style=_WIZARD_STYLE,
                    qmark="◈",
                ).ask_async()
                if not api_ssl_cert:
                    raise WizardCancelled("Certificate path cannot be empty.")
                strict_verify = await questionary.confirm(
                    "Enable strict hostname & cert verification?",
                    default=True,
                    style=_WIZARD_STYLE,
                    qmark="◈",
                ).ask_async()
                api_ssl_verify = bool(strict_verify)

        default_api_port = 8729 if use_ssl else 8728
        api_port_raw = await questionary.text(
            "Binary API Port:",
            default=str(default_api_port),
            style=_WIZARD_STYLE,
            qmark="◈",
        ).ask_async()
        if api_port_raw is None:
            raise WizardCancelled("Binary API port input cancelled.")
        try:
            api_port = int(api_port_raw)
        except ValueError:
            raise WizardCancelled(f"Invalid binary API port: {api_port_raw!r}") from None

        backend = "binary"
        api_ssl = use_ssl
        verify_tls = False

    if password:
        try:
            env_secrets.set_router_secret(alias, password)
            if env_secrets.ensure_gitignored():
                console.print("[dim]Added '.env' to .gitignore.[/dim]")
        except env_secrets.EnvFileError as exc:
            console.print(f"[yellow]Warning:[/yellow] {exc}")

    profile = cli_config.RouterProfileConfig(
        host=host,
        username=username,
        port=port,
        verify_tls=bool(verify_tls),
        backend=backend,
        api_port=api_port,
        api_ssl=api_ssl,
        api_ssl_cert=api_ssl_cert if backend == "binary" else None,
        api_ssl_verify=api_ssl_verify if backend == "binary" else False,
    )
    return alias, profile
