from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import questionary
import httpx
from prompt_toolkit.key_binding.key_bindings import KeyBindings, merge_key_bindings
from prompt_toolkit.keys import Keys
from rich.console import Console

from mika.ai.errors import AIAuthenticationError, AIError
from mika.ai.provider_registry import (
    _MODEL_FETCHERS,
    _PROVIDER_DISPLAY_NAMES,
    provider_choices as _provider_choices,
    register_model_fetcher,
)
from mika.cli import config as cli_config
from mika.cli import env_secrets
from mika.cli.errors import CliError
from mika.router.mndp import MndpDevice, scan as mndp_scan

if TYPE_CHECKING:
    from mika.cli.session import ChatSession

console = Console()

_CUSTOM_MODEL_CHOICE = "__custom__"
_MANUAL_HOST_CHOICE = "__manual__"

_WIZARD_STYLE = questionary.Style(
    [
        ("qmark", "fg:#c084fc bold"),
        ("question", "bold white"),
        ("pointer", "fg:#c084fc bold"),
        ("highlighted", "fg:#c084fc bold"),
        ("selected", "fg:#10b981 bold"),
        ("instruction", "fg:#888888 italic"),
        ("disabled", "fg:#666666 italic"),
    ]
)


async def _ask(question: questionary.Question, session: "ChatSession | None" = None) -> object:
    """Run any questionary prompt (select/confirm/text/password) with a
    fix applied consistently everywhere, instead of ad-hoc per call site:

    Escape cancels, same as Ctrl+C/Ctrl+Q (questionary only binds those
    two by default -- Escape does nothing on its own, even though the
    status line has always told the user "Esc cancel").

    `session` is accepted for backward compatibility with existing call
    sites but is otherwise unused: an earlier version of this function
    also printed a standalone status header here, but that header is
    printed *after* the triggering command line has already been echoed
    to the terminal, so it could only ever land between the command and
    the picker -- never above the command, where a status bar belongs.
    The status bar shown above the main "> " prompt while typing already
    covers that; this function doesn't need its own.
    """
    extra_bindings = KeyBindings()
    extra_bindings.add(Keys.Escape, eager=True)(lambda event: event.app.exit(result=None))
    question.application.key_bindings = merge_key_bindings([question.application.key_bindings, extra_bindings])
    return await question.ask_async()


class WizardCancelled(CliError):
    pass


async def scan_and_select_router(
    timeout: float = 5.0, session: "ChatSession | None" = None
) -> MndpDevice | None:
    console.print()
    with console.status(
        "[bold #c084fc]◆[/bold #c084fc] Scanning local network for MikroTik devices...", spinner="dots"
    ):
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

    selected = await _ask(
        questionary.select(
            "Select a router:",
            choices=choices,
            style=_WIZARD_STYLE,
            qmark="◈",
            instruction="(Use arrow keys)",
        ),
        session=session,
    )

    return selected


async def select_model(config: cli_config.AppConfig, session: "ChatSession | None" = None) -> tuple[str, str]:
    existing_choices = [
        questionary.Choice(title=f"{entry.provider}: {entry.model}", value=(entry.provider, entry.model))
        for entry in config.models
    ]
    existing_choices.append(questionary.Choice(title="+ Add new model", value="__add__"))

    selected = await _ask(
        questionary.select(
            "Select model:",
            choices=existing_choices,
            style=_WIZARD_STYLE,
            qmark="◈",
        ),
        session=session,
    )

    if selected is None:
        raise WizardCancelled("Model selection cancelled.")

    if selected == "__add__":
        provider, models = await run_provider_wizard(session=session)
        if len(models) == 1:
            model = models[0]
        else:
            model = await _select_fetched_model(models, session=session)
        for m in models:
            config.remember_model(provider, m)
        return provider, model

    return selected


async def select_router(
    config: cli_config.AppConfig, *, active_alias: str | None = None, session: "ChatSession | None" = None
) -> str | None:
    choices = []
    for alias, profile in config.routers.items():
        label = f"{alias}  ({profile.host}:{profile.port}  {profile.backend})"
        if alias == active_alias:
            label += "  [active]"
        choices.append(questionary.Choice(title=label, value=alias))
    choices.append(questionary.Choice(title="+ Add new router", value="__add__"))

    selected = await _ask(
        questionary.select(
            "Select router:",
            choices=choices,
            style=_WIZARD_STYLE,
            qmark="◈",
        ),
        session=session,
    )

    return selected


async def select_inspect_target(session: "ChatSession | None" = None) -> str | None:
    from mika.cli.render import INSPECT_TARGETS

    return await _ask(
        questionary.select(
            "Select inspect target:",
            choices=list(INSPECT_TARGETS),
            style=_WIZARD_STYLE,
            qmark="◈",
        ),
        session=session,
    )


async def run_provider_wizard(session: "ChatSession | None" = None) -> tuple[str, list[str]]:
    provider = await _ask(
        questionary.select(
            "Select AI provider:",
            choices=_provider_choices(),
            style=_WIZARD_STYLE,
            qmark="◈",
        ),
        session=session,
    )
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
        action = await _ask(
            questionary.select(
                f"{provider} is already configured.",
                choices=[
                    questionary.Choice(title="Use existing API key", value="use"),
                    questionary.Choice(title="Replace API key", value="replace"),
                    questionary.Choice(title="Cancel", value="cancel"),
                ],
                style=_WIZARD_STYLE,
                qmark="◈",
            ),
            session=session,
        )
        if action is None or action == "cancel":
            raise WizardCancelled("Provider configuration cancelled.")
        if action == "replace":
            api_key = (
                None  # fall through to key-entry loop below; old key stays untouched until fetch succeeds
            )

    while True:
        if api_key is None:
            api_key = await _ask(
                questionary.password(
                    f"Enter API key for {provider}:",
                    style=_WIZARD_STYLE,
                    qmark="◈",
                ),
                session=session,
            )
            if api_key is None:
                raise WizardCancelled("API key input cancelled.")

        try:
            with console.status(f"Connecting to {provider} to fetch model list..."):
                models = await fetcher(api_key)
        except AIAuthenticationError as exc:
            console.print(f"[red]API key rejected by {provider}:[/red] {exc}")
            retry = await _ask(
                questionary.confirm("Try entering a different API key?", default=True),
                session=session,
            )
            if not retry:
                raise WizardCancelled("API key rejected; user declined to retry.") from exc
            api_key = None
            continue
        except AIError as exc:
            console.print(f"[yellow]Failed to fetch model list from {provider}:[/yellow] {exc}")
            fallback = await _ask(
                questionary.confirm("Enter model name manually?", default=True),
                session=session,
            )
            if not fallback:
                raise WizardCancelled("Model list fetch failed; user declined manual entry.") from exc
            model = await _ask(
                questionary.text("Model name:", style=_WIZARD_STYLE, qmark="◈"),
                session=session,
            )
            if not model:
                raise WizardCancelled("Custom model name cancelled or empty.") from exc
            if api_key != existing_key:
                _persist_provider_secret(provider, api_key)
            return provider, [model]

        if api_key != existing_key:
            _persist_provider_secret(provider, api_key)
        console.print(f"[green]{len(models)} models available for {provider}.[/green]")
        return provider, models


async def _select_fetched_model(models: list[str], session: "ChatSession | None" = None) -> str:
    choices = [questionary.Choice(title=name, value=name) for name in models]
    choices.append(questionary.Choice(title="Custom (enter model name)", value=_CUSTOM_MODEL_CHOICE))

    model = await _ask(
        questionary.select(
            "Select model:",
            choices=choices,
            style=_WIZARD_STYLE,
            qmark="◈",
        ),
        session=session,
    )
    if model is None:
        raise WizardCancelled("Model selection cancelled.")
    if model == _CUSTOM_MODEL_CHOICE:
        model = await _ask(
            questionary.text("Model name:", style=_WIZARD_STYLE, qmark="◈"),
            session=session,
        )
        if not model:
            raise WizardCancelled("Custom model name cancelled or empty.")
    return model


def _persist_provider_secret(provider: str, api_key: str) -> None:
    try:
        env_secrets.set_provider_secret(provider, api_key)
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
    session: "ChatSession | None" = None,
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

    alias = await _ask(
        questionary.text(
            "Router alias (e.g. 'office', 'lab'):",
            default=default_alias,
            validate=_validate_alias,
            style=_WIZARD_STYLE,
            qmark="◈",
        ),
        session=session,
    )
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
            proceed = await _ask(
                questionary.confirm(
                    "Continue anyway (enter IP manually)?",
                    default=False,
                    style=_WIZARD_STYLE,
                    qmark="◈",
                ),
                session=session,
            )
            if not proceed:
                raise WizardCancelled("Router has no IP address; user aborted.")
            host = await _ask(
                questionary.text(
                    "Router Host / IP:",
                    style=_WIZARD_STYLE,
                    qmark="◈",
                ),
                session=session,
            )
            if not host:
                raise WizardCancelled("Host input cancelled or empty.")
        else:
            host = discovered.display_host
            console.print(f"[bold #c084fc]◆[/bold #c084fc] Using discovered host: [bold]{host}[/bold]")
    else:
        host = await _ask(
            questionary.text(
                "Router Host / IP:",
                style=_WIZARD_STYLE,
                qmark="◈",
            ),
            session=session,
        )
        if not host:
            raise WizardCancelled("Host input cancelled or empty.")

    username = await _ask(
        questionary.text(
            "Username:",
            default="admin",
            style=_WIZARD_STYLE,
            qmark="◈",
        ),
        session=session,
    )
    if not username:
        raise WizardCancelled("Username input cancelled or empty.")

    password = await _ask(
        questionary.password(
            "Password: (leave empty if not set)",
            style=_WIZARD_STYLE,
            qmark="◈",
        ),
        session=session,
    )
    if password is None:
        raise WizardCancelled("Password input cancelled.")

    console.print("[dim]Probing router for REST API support...[/dim]")
    rest_port_raw = await _ask(
        questionary.text(
            "REST API Port (for v7 probe):",
            default="443",
            style=_WIZARD_STYLE,
            qmark="◈",
        ),
        session=session,
    )
    if rest_port_raw is None:
        raise WizardCancelled("Port input cancelled.")
    try:
        rest_port = int(rest_port_raw)
    except ValueError:
        raise WizardCancelled(f"Invalid port: {rest_port_raw!r}") from None

    rest_available = await _probe_rest_api(host, rest_port, verify_tls=False)

    if rest_available:
        console.print("[green]✓ RouterOS REST API detected (v7+). Using REST backend.[/green]")
        verify_tls = await _ask(
            questionary.confirm(
                "Verify TLS certificate?",
                default=False,
                style=_WIZARD_STYLE,
                qmark="◈",
            ),
            session=session,
        )
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

        api_proto = await _ask(
            questionary.select(
                "Binary API connection type:",
                choices=[
                    questionary.Choice(
                        title="Plaintext (port 8728) — recommended for local/trusted networks", value="plain"
                    ),
                    questionary.Choice(title="SSL / TLS (port 8729) — encrypted connection", value="ssl"),
                ],
                style=_WIZARD_STYLE,
                qmark="◈",
            ),
            session=session,
        )
        if api_proto is None:
            raise WizardCancelled("Binary API protocol selection cancelled.")

        use_ssl = api_proto == "ssl"
        api_ssl_cert = None
        api_ssl_verify = False

        if use_ssl:
            cert_mode = await _ask(
                questionary.select(
                    "SSL certificate handling:",
                    choices=[
                        questionary.Choice(
                            title="Trust Self-Signed Certificate (Default / Auto)", value="self_signed"
                        ),
                        questionary.Choice(
                            title="Custom CA / Certificate file (.crt / .pem)", value="custom"
                        ),
                    ],
                    style=_WIZARD_STYLE,
                    qmark="◈",
                ),
                session=session,
            )
            if cert_mode is None:
                raise WizardCancelled("Certificate mode selection cancelled.")

            if cert_mode == "custom":
                api_ssl_cert = await _ask(
                    questionary.text(
                        "Path to certificate/CA file:",
                        style=_WIZARD_STYLE,
                        qmark="◈",
                    ),
                    session=session,
                )
                if not api_ssl_cert:
                    raise WizardCancelled("Certificate path cannot be empty.")
                strict_verify = await _ask(
                    questionary.confirm(
                        "Enable strict hostname & cert verification?",
                        default=True,
                        style=_WIZARD_STYLE,
                        qmark="◈",
                    ),
                    session=session,
                )
                api_ssl_verify = bool(strict_verify)

        default_api_port = 8729 if use_ssl else 8728
        api_port_raw = await _ask(
            questionary.text(
                "Binary API Port:",
                default=str(default_api_port),
                style=_WIZARD_STYLE,
                qmark="◈",
            ),
            session=session,
        )
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
