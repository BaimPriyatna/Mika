from __future__ import annotations

from collections.abc import Iterable

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from mika.router.discovery import RouterContext
from mika.troubleshoot.models import DiagnosisResult, HypothesisLikelihood

INSPECT_TARGETS = (
    "router",
    "interfaces",
    "addresses",
    "routes",
    "firewall",
    "dhcp",
    "hotspot",
)


def render_advice(
    console: Console,
    message: str,
    options: list[str] | None = None,
    suggested_action: str | None = None,
) -> None:
    console.print()
    panel_body = f"[bold #c084fc]◆ Mika:[/bold #c084fc] {escape(message)}"
    if options:
        panel_body += "\n\n[bold cyan]Suggested Options:[/bold cyan]"
        for idx, opt in enumerate(options, 1):
            panel_body += f"\n  [bold white]{idx}.[/bold white] {escape(opt)}"
    if suggested_action:
        panel_body += f"\n\n[dim]Tip: You can say '[bold white]{escape(suggested_action)}[/bold white]' to proceed.[/dim]"

    console.print(Panel(panel_body, border_style="#7c3aed", padding=(0, 1), expand=False))


_LIKELIHOOD_STYLE = {
    HypothesisLikelihood.VERY_LIKELY: "bold red",
    HypothesisLikelihood.LIKELY: "yellow",
    HypothesisLikelihood.POSSIBLE: "cyan",
    HypothesisLikelihood.UNLIKELY: "dim",
}


def render_diagnosis(console: Console, diagnosis: DiagnosisResult) -> None:
    console.print()
    body = f"[bold #c084fc]◆ Diagnosis:[/bold #c084fc] {escape(diagnosis.problem_description)}"

    if diagnosis.hypotheses:
        body += "\n\n[bold cyan]Possible Causes:[/bold cyan]"
        for h in diagnosis.hypotheses:
            style = _LIKELIHOOD_STYLE.get(h.likelihood, "white")
            body += f"\n  [{style}]● {escape(h.description)} ({h.likelihood.value})[/{style}]"
            for ev in h.evidence:
                body += f"\n      [dim]- {escape(ev)}[/dim]"

    if diagnosis.recommended_fixes:
        body += "\n\n[bold green]Recommended Fixes:[/bold green]"
        for idx, fix in enumerate(diagnosis.recommended_fixes, 1):
            body += f"\n  [bold white]{idx}.[/bold white] {escape(fix)}"

    console.print(Panel(body, border_style="#7c3aed", padding=(0, 1), expand=False))


def render_inspect(console: Console, target: str, ctx: RouterContext) -> None:
    target = target.strip().lower()
    renderer = _RENDERERS.get(target)
    if renderer is None:
        console.print(
            f"[yellow]Unknown target '{target}'. Choices: {', '.join(INSPECT_TARGETS)}[/yellow]"
        )
        return

    console.print()
    renderer(console, ctx)


def _table(title: str, columns: Iterable[str], *, show_header: bool = True) -> Table:
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


def _empty(console: Console, title: str, message: str = "No data to display.") -> None:
    console.print(Panel(f"[dim]{message}[/dim]", title=f"[bold cyan]{title}[/bold cyan]", border_style="#3d3d3d"))


def _yes_no(value: bool) -> str:
    return "[green]yes[/green]" if value else "[dim]no[/dim]"


def _enabled(disabled: bool) -> str:
    return "[red]disabled[/red]" if disabled else "[green]enabled[/green]"


def _render_router(console: Console, ctx: RouterContext) -> None:
    table = _table(f"Router: {escape(ctx.identity)}", ("Field", "Value"), show_header=False)
    table.add_row("RouterOS version", escape(ctx.routeros_version))
    table.add_row("Board", escape(ctx.board_name))
    table.add_row("Architecture", escape(ctx.architecture))
    table.add_row("Uptime", escape(ctx.system_resource.uptime))
    cpu = f"{ctx.system_resource.cpu_load}%" if ctx.system_resource.cpu_load is not None else "-"
    table.add_row("CPU load", cpu)
    console.print(table)


def _render_interfaces(console: Console, ctx: RouterContext) -> None:
    if not ctx.interfaces:
        _empty(console, "Interfaces")
        return

    table = _table("Interfaces", ("Name", "Type", "Run", "State", "MAC", "Comment"))
    for iface in ctx.interfaces:
        table.add_row(
            escape(iface.name),
            escape(iface.type),
            _yes_no(iface.running),
            _enabled(iface.disabled),
            escape(iface.mac_address) if iface.mac_address else "-",
            escape(iface.comment) if iface.comment else "-",
        )
    console.print(table)


def _render_addresses(console: Console, ctx: RouterContext) -> None:
    if not ctx.addresses:
        _empty(console, "IP Addresses")
        return

    table = _table("IP Addresses", ("Address", "Interface", "Network", "State"))
    for addr in ctx.addresses:
        table.add_row(escape(addr.address), escape(addr.interface), escape(addr.network), _enabled(addr.disabled))
    console.print(table)


def _render_routes(console: Console, ctx: RouterContext) -> None:
    if not ctx.routes:
        _empty(console, "Routes")
        return

    table = _table("Routes", ("Destination", "Gateway", "Distance", "Active", "Static"))
    for route in ctx.routes:
        table.add_row(
            escape(route.dst_address),
            escape(route.gateway),
            str(route.distance),
            _yes_no(route.active),
            _yes_no(route.static),
        )
    console.print(table)


def _render_firewall(console: Console, ctx: RouterContext) -> None:
    if not ctx.firewall_rules:
        _empty(console, "Firewall Rules")
        return

    table = _table("Firewall Rules", ("Chain", "Action", "Src", "Dst", "Protocol", "State", "Comment"))
    for rule in ctx.firewall_rules:
        table.add_row(
            escape(rule.chain),
            escape(rule.action),
            escape(rule.src_address) if rule.src_address else "-",
            escape(rule.dst_address) if rule.dst_address else "-",
            escape(rule.protocol) if rule.protocol else "-",
            _enabled(rule.disabled),
            escape(rule.comment) if rule.comment else "-",
        )
    console.print(table)


def _render_dhcp(console: Console, ctx: RouterContext) -> None:
    if ctx.dhcp_servers:
        table = _table("DHCP Servers", ("Name", "Interface", "Pool", "Lease Time", "State"))
        for server in ctx.dhcp_servers:
            table.add_row(
                escape(server.name),
                escape(server.interface),
                escape(server.address_pool) if server.address_pool else "-",
                escape(server.lease_time) if server.lease_time else "-",
                _enabled(server.disabled),
            )
        console.print(table)
    else:
        _empty(console, "DHCP Servers")

    if ctx.dhcp_leases:
        leases = _table("DHCP Leases", ("Address", "MAC", "Server", "Status", "Hostname"))
        for lease in ctx.dhcp_leases:
            leases.add_row(
                escape(lease.address),
                escape(lease.mac_address) if lease.mac_address else "-",
                escape(lease.server),
                escape(lease.status),
                escape(lease.host_name) if lease.host_name else "-",
            )
        console.print(leases)
    else:
        _empty(console, "DHCP Leases")


def _render_hotspot(console: Console, ctx: RouterContext) -> None:
    if ctx.hotspot_servers:
        table = _table("Hotspot Servers", ("Name", "Interface", "Profile", "Pool", "State"))
        for server in ctx.hotspot_servers:
            table.add_row(
                escape(server.name),
                escape(server.interface),
                escape(server.profile) if server.profile else "-",
                escape(server.address_pool) if server.address_pool else "-",
                _enabled(server.disabled),
            )
        console.print(table)
    else:
        _empty(console, "Hotspot Servers")

    if ctx.hotspot_users:
        users = _table("Hotspot Users", ("Name", "Profile", "State"))
        for user in ctx.hotspot_users:
            users.add_row(escape(user.name), escape(user.profile) if user.profile else "-", _enabled(user.disabled))
        console.print(users)
    else:
        _empty(console, "Hotspot Users")


_RENDERERS = {
    "router": _render_router,
    "interfaces": _render_interfaces,
    "addresses": _render_addresses,
    "routes": _render_routes,
    "firewall": _render_firewall,
    "dhcp": _render_dhcp,
    "hotspot": _render_hotspot,
}


INTENT_TO_TARGET: dict[str, str] = {
    "inspect_router": "router",
    "inspect_interfaces": "interfaces",
    "inspect_ip_addresses": "addresses",
    "inspect_routes": "routes",
    "inspect_firewall": "firewall",
    "inspect_nat": "firewall",
    "inspect_dhcp": "dhcp",
    "inspect_hotspot": "hotspot",
}
