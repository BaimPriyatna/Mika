from __future__ import annotations

import questionary
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from mika.cli import config as cli_config
from mika.cli import env_secrets, render, wizard
from mika.cli.errors import CliError, NoActiveRouterError, SessionNotFoundError
from mika.cli.input import build_status_bar
from mika.cli.session import ChatSession
from mika.router.discovery import discover
from mika.utils.printer import status_spinner

HELP_TEXT = """\
Available commands:
  /model [name]               Show or switch active AI model
  /provider                   Configure AI provider & enter API key
  /router list                List registered routers
  /router select <alias>      Select active router
  /router add                 Register a new router (interactive wizard)
  /router remove [alias]      Remove a registered router
  /router status              Show active router
  /status                     Session summary (router, provider, history)
  /inspect <target>           View read-only data: router, interfaces,
                              addresses, routes, firewall, dhcp, hotspot
  /history                    Show conversation history for this session
  /sessions                   List saved conversation sessions
  /resume <#>                 Resume a saved conversation session
  /backup                     Show last backup info
  /clear                      Clear screen & start a new session
  /reset                      Reset all configuration & saved secrets
  /help                       Show this help message
  /exit                       Exit REPL session
"""


class ExitRepl(Exception):
    pass


def is_slash_command(line: str) -> bool:
    return line.strip().startswith("/")


def _table(title: str, *columns: str, show_header: bool = True) -> Table:
    table = Table(
        title=f"[bold cyan]{title}[/bold cyan]",
        box=box.SIMPLE_HEAVY,
        show_header=show_header,
        header_style="bold #a78bfa",
        border_style="#3d3d3d",
        row_styles=("", "dim"),
        expand=False,
    )
    for column in columns:
        table.add_column(column, overflow="fold")
    return table


async def dispatch(line: str, session: ChatSession, console: Console) -> None:
    parts = line.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    handler = _HANDLERS.get(cmd)
    if handler is None:
        console.print(f"[yellow]Unknown command: {escape(cmd)}. Type /help for available commands.[/yellow]")
        return

    try:
        await handler(arg, session, console)
    except ExitRepl:
        raise
    except CliError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
    except Exception as exc:
        console.print(f"[red]Unexpected error in '{escape(cmd)}': {escape(str(exc) or type(exc).__name__)}[/red]")
        console.print("[dim]If this persists, please report it as a bug.[/dim]")


async def _cmd_help(arg: str, session: ChatSession, console: Console) -> None:
    console.print(HELP_TEXT)


async def _cmd_exit(arg: str, session: ChatSession, console: Console) -> None:
    raise ExitRepl()


async def _cmd_clear(arg: str, session: ChatSession, console: Console) -> None:
    console.clear()
    session.start_new_session()
    console.print("[dim]Screen and conversation history cleared. Started a new session.[/dim]")


async def _cmd_history(arg: str, session: ChatSession, console: Console) -> None:
    if not session.history:
        console.print("[dim](history is empty)[/dim]")
        return
    table = _table("Conversation History", "Role", "Message")
    for entry in session.history:
        table.add_row(entry.role, entry.text)
    console.print(table)


async def _cmd_sessions(arg: str, session: ChatSession, console: Console) -> None:
    if session.session_store is None:
        console.print("[yellow]Session storage is not available.[/yellow]")
        return
    summaries = session.session_store.list_sessions()
    if not summaries:
        console.print("[dim](no saved sessions)[/dim]")
        return
    table = _table("Sessions", "#", "Title", "Messages", "Updated")
    for idx, s in enumerate(summaries, 1):
        marker = " (current)" if s.id == session.session_id else ""
        table.add_row(str(idx), escape(s.title) + marker, str(s.message_count), s.updated_at)
    console.print(table)
    console.print("[dim]Use /resume <#> to switch to a session.[/dim]")


async def _cmd_resume(arg: str, session: ChatSession, console: Console) -> None:
    if session.session_store is None:
        console.print("[yellow]Session storage is not available.[/yellow]")
        return
    if not arg:
        console.print("[yellow]Usage: /resume <#>  (see /sessions for the list)[/yellow]")
        return
    resolved = session.session_store.resolve_id(arg.strip())
    if resolved is None:
        console.print(f"[yellow]No session found matching '{escape(arg)}'. Use /sessions to list.[/yellow]")
        return
    try:
        count = session.resume_session(resolved)
    except SessionNotFoundError as exc:
        console.print(f"[yellow]{escape(str(exc))}[/yellow]")
        return
    console.print(f"[green]Resumed session with {count} messages.[/green]")


async def _cmd_model(arg: str, session: ChatSession, console: Console) -> None:
    if arg:
        if session.provider_name is None:
            console.print("[yellow]No active provider. Please run /provider first.[/yellow]")
            return
        session.activate_provider(session.provider_name, arg)
        session.persist_active_selection()
        console.print(f"[green]Model switched to {escape(arg)}.[/green]")
        return

    selected = await wizard.select_model(session.config)
    if selected is None:
        return
    provider, model = selected
    session.activate_provider(provider, model)
    session.persist_active_selection()
    console.print(f"[green]Active model: {escape(provider)}: {escape(model)}[/green]")


async def _cmd_provider(arg: str, session: ChatSession, console: Console) -> None:
    provider_name, models = await wizard.run_provider_wizard()
    for model in models:
        session.config.remember_model(provider_name, model)
    cli_config.save_config(session.config, session.config_path)
    console.print(
        f"[green]Provider '{provider_name}' ready ({len(models)} models saved).[/green] "
        "Run /model to select active model."
    )


async def _cmd_router(arg: str, session: ChatSession, console: Console) -> None:
    sub_parts = arg.split(maxsplit=1)
    sub = sub_parts[0].lower() if sub_parts else ""
    sub_arg = sub_parts[1].strip() if len(sub_parts) > 1 else ""

    if sub in ("list", ""):
        if not session.config.routers:
            console.print("[dim]No routers registered yet. Use /router add.[/dim]")
            return
        table = _table("Registered Routers", "Alias", "Host", "Backend", "Active")
        for alias, profile in session.config.routers.items():
            table.add_row(
                alias,
                f"{profile.host}:{profile.effective_port}",
                profile.backend,
                "[green]active[/green]" if alias == session.router_alias else "",
            )
        console.print(table)
        return

    if sub == "select":
        if sub_arg:
            alias = sub_arg
        else:
            choice = await wizard.select_router(session.config, active_alias=session.router_alias)
            if choice is None:
                return
            if choice == "__add__":
                await _add_router(session, console)
                return
            alias = choice
        session.connect_router(alias)
        session.persist_active_selection()
        console.print(f"[green]Active router: {escape(alias)}[/green]")
        return

    if sub == "add":
        await _add_router(session, console)
        return

    if sub == "remove":
        if not session.config.routers:
            console.print("[dim]No routers registered to remove.[/dim]")
            return

        if sub_arg:
            alias = sub_arg
            if alias not in session.config.routers:
                console.print(f"[yellow]Router '{escape(alias)}' not found. Use /router list to view registered routers.[/yellow]")
                return
        else:
            choices = [
                questionary.Choice(
                    title=f"{a}  ({p.host}:{p.port}  {p.backend})",
                    value=a,
                )
                for a, p in session.config.routers.items()
            ]
            choices.append(questionary.Choice(title="Cancel", value=None))

            selected = await questionary.select(
                "Select router to remove:",
                choices=choices,
                style=wizard._WIZARD_STYLE,
                qmark="◈",
            ).ask_async()

            if not selected:
                console.print("[dim]Cancelled.[/dim]")
                return
            alias = selected

        del session.config.routers[alias]
        if session.router_alias == alias:
            session.router_alias = None
            session.router_client = None
            session.config.active_router = None

        try:
            env_secrets.delete_router_secret(alias)
        except Exception:
            pass

        cli_config.save_config(session.config, session.config_path)
        console.print(f"[green]Router '{escape(alias)}' removed.[/green]")
        return

    if sub == "status":
        if session.router_alias is None:
            console.print("[dim]No active router.[/dim]")
            return
        profile = session.config.get_router(session.router_alias)
        console.print(
            f"Active router: {session.router_alias} ({profile.host}:{profile.effective_port}, backend={profile.backend})"
        )
        return

    console.print(f"[yellow]Unknown /router subcommand: {escape(sub)}. Choices: list, select, add, remove, status.[/yellow]")


async def _add_router(session: ChatSession, console: Console) -> None:
    import questionary as _q
    from mika.router.mndp import MndpDevice

    _WIZARD_STYLE = wizard._WIZARD_STYLE

    method = await _q.select(
        "How to connect to router?",
        choices=[
            _q.Choice(title="◉  Scan local network (MNDP — auto-discover)", value="scan"),
            _q.Choice(title="✎  Enter host / IP manually", value="manual"),
        ],
        style=_WIZARD_STYLE,
        qmark="◈",
        instruction="(Use arrow keys)",
    ).ask_async()

    if method is None:
        return

    discovered: MndpDevice | None = None
    if method == "scan":
        discovered = await wizard.scan_and_select_router()

    alias, profile = await wizard.run_router_wizard(
        existing_aliases=list(session.config.routers),
        discovered=discovered,
    )
    session.config.routers[alias] = profile
    cli_config.save_config(session.config, session.config_path)
    session.connect_router(alias)
    session.persist_active_selection()
    console.print(f"[green]◆ Router '{escape(alias)}' added and activated.[/green]")


async def _cmd_inspect(arg: str, session: ChatSession, console: Console) -> None:
    if arg:
        target = arg
    else:
        target = await wizard.select_inspect_target()
        if target is None:
            return
    client = session.require_router()
    with status_spinner(f"Fetching '{target}' data from router..."):
        ctx = await discover(client)
    render.render_inspect(console, target, ctx)


async def _cmd_status(arg: str, session: ChatSession, console: Console) -> None:
    console.print(f"[dim]{escape(build_status_bar(session))}[/dim]")
    table = _table("Session Status", "Field", "Value", show_header=False)
    table.add_row("Active router", session.router_alias or "(none)")
    table.add_row("Active provider", session.provider_name or "(none)")
    table.add_row("Active model", session.model_name or "(none)")
    table.add_row("History messages", str(len(session.history)))
    console.print(table)


async def _cmd_backup(arg: str, session: ChatSession, console: Console) -> None:
    backup = session.last_backup
    if backup is None:
        console.print(
            "[dim]No backup in this session. Backups are automatically created before plan execution.[/dim]"
        )
        return
    console.print(f"Last backup: plan_id={backup.plan_id} created_at={backup.created_at}")


async def _cmd_reset(arg: str, session: ChatSession, console: Console) -> None:
    confirmed = await questionary.confirm(
        "Reset all Mika configuration, registered routers, and saved credentials?",
        default=False,
        style=wizard._WIZARD_STYLE,
        qmark="⚠️ ",
    ).ask_async()

    if not confirmed:
        console.print("[dim]Reset cancelled.[/dim]")
        return

    # Clear routers and model settings
    session.config.routers.clear()
    session.config.models.clear()
    session.config.active_router = None
    session.config.active_provider = None
    session.config.active_model = None

    session.router_alias = None
    session.router_client = None
    session.provider_name = None
    session.model_name = None
    session.provider = None
    session.start_new_session()

    cli_config.save_config(session.config, session.config_path)

    # Clean env secrets if .env exists
    env_file = env_secrets.env_path()
    if env_file.exists():
        try:
            env_file.write_text("")
        except OSError:
            pass

    console.print("[green]✓ Configuration and secrets have been reset to defaults.[/green]")


_HANDLERS = {
    "/help": _cmd_help,
    "/exit": _cmd_exit,
    "/clear": _cmd_clear,
    "/history": _cmd_history,
    "/sessions": _cmd_sessions,
    "/resume": _cmd_resume,
    "/model": _cmd_model,
    "/provider": _cmd_provider,
    "/router": _cmd_router,
    "/inspect": _cmd_inspect,
    "/status": _cmd_status,
    "/backup": _cmd_backup,
    "/reset": _cmd_reset,
}
