"""
Configuration Diff Generator.

Calculates declarative state differences before and after plan execution,
presenting human-readable diffs for user confirmation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mika.ai.schemas.enums import INTENT_SAFETY_LEVEL, SafetyLevel
from mika.planner.plan import OperationType, PlanStatus

if TYPE_CHECKING:
    from mika.planner.plan import Plan, PlanStep
    from mika.validator.result import ValidationResult


_OP_SYMBOLS = {
    OperationType.CREATE: "+",
    OperationType.UPDATE: "~",
    OperationType.DELETE: "-",
}

_OP_COLORS = {
    OperationType.CREATE: "green",
    OperationType.UPDATE: "yellow",
    OperationType.DELETE: "red",
}

_SAFETY_COLORS = {
    SafetyLevel.READ_ONLY: "green",
    SafetyLevel.LOW_RISK: "green",
    SafetyLevel.MEDIUM_RISK: "yellow",
    SafetyLevel.HIGH_RISK: "red",
    SafetyLevel.DESTRUCTIVE: "red",
}


def generate_diff(
    plan: Plan,
    validation_result: ValidationResult | None = None,
    show_data: bool = False,
) -> str:
    console = Console(record=True)

    _render_plan_header(console, plan)

    if validation_result is not None:
        _render_validation_issues(console, validation_result)

    _render_changes(console, plan, show_data=show_data)

    _render_impact(console, plan)

    if plan.warnings:
        _render_plan_warnings(console, plan)

    return console.export_text()


def _render_plan_header(console: Console, plan: Plan) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()

    table.add_row("Plan ID:", plan.plan_id)
    table.add_row("Router:", plan.router_identity)
    table.add_row("RouterOS:", plan.routeros_version)
    table.add_row("Intent:", plan.intent.intent.value)
    table.add_row(
        "Safety Level:",
        Text(plan.safety_level.value.upper(), style=_SAFETY_COLORS[plan.safety_level]),
    )
    table.add_row("Status:", plan.status.value)

    console.print(Panel(table, title="[bold]Configuration Plan[/bold]", border_style="blue"))


def _render_validation_issues(console: Console, result: ValidationResult) -> None:
    if not result.issues:
        console.print("[green]✓[/green] All validation checks passed.\n")
        return

    if result.failures:
        console.print(
            Panel(
                _format_issues(result.failures),
                title="[bold red]Validation Failures[/bold red]",
                border_style="red",
            )
        )

    if result.warnings:
        console.print(
            Panel(
                _format_issues(result.warnings),
                title="[bold yellow]Validation Warnings[/bold yellow]",
                border_style="yellow",
            )
        )

    console.print()


def _format_issues(issues: tuple) -> str:
    lines = []
    for issue in issues:
        step_label = f" (step: {issue.step_id})" if issue.step_id else ""
        lines.append(f"• [{issue.layer.value}] {issue.message}{step_label}")
    return "\n".join(lines)


def _render_changes(console: Console, plan: Plan, show_data: bool) -> None:
    if not plan.steps:
        console.print("[yellow]No configuration changes.[/yellow]\n")
        return

    console.print("[bold]Configuration Changes:[/bold]\n")

    for step in plan.steps:
        _render_step(console, step, show_data=show_data)

    console.print()


def _render_step(console: Console, step: PlanStep, show_data: bool) -> None:
    symbol = _OP_SYMBOLS[step.operation]
    color = _OP_COLORS[step.operation]

    console.print(f"[{color}]{symbol}[/{color}] {step.description}")

    if show_data or step.operation == OperationType.DELETE:
        _render_step_details(console, step)


def _render_step_details(console: Console, step: PlanStep) -> None:
    if step.operation == OperationType.DELETE:
        console.print(f"  [dim]Resource:[/dim] {step.resource}")
        if step.resource_id:
            console.print(f"  [dim]ID:[/dim] {step.resource_id}")
        return

    if step.data:
        console.print(f"  [dim]Resource:[/dim] {step.resource}")
        for key, value in step.data.items():
            console.print(f"    [dim]{key}:[/dim] {value}")


def _render_impact(console: Console, plan: Plan) -> None:
    console.print("[bold]Affected Resources:[/bold]")

    if plan.affected_interfaces:
        console.print(f"  [cyan]Interfaces:[/cyan] {', '.join(plan.affected_interfaces)}")
    else:
        console.print("  [dim]Interfaces: none[/dim]")

    if plan.affected_networks:
        console.print(f"  [cyan]Networks:[/cyan] {', '.join(plan.affected_networks)}")
    else:
        console.print("  [dim]Networks: none[/dim]")

    console.print()

    impact_messages = {
        SafetyLevel.READ_ONLY: "No impact. Read-only operation.",
        SafetyLevel.LOW_RISK: "Low impact. Additive operation with minimal risk.",
        SafetyLevel.MEDIUM_RISK: (
            "Medium impact. Existing configuration will be modified. "
            "Connected clients may experience brief connectivity loss."
        ),
        SafetyLevel.HIGH_RISK: (
            "High impact. Critical configuration will be modified. "
            "Service disruption likely for connected clients."
        ),
        SafetyLevel.DESTRUCTIVE: (
            "CRITICAL IMPACT. Resources will be DELETED or significantly modified. "
            "Active connections and services may be permanently affected."
        ),
    }

    impact_style = _SAFETY_COLORS[plan.safety_level]
    console.print(
        Panel(
            impact_messages[plan.safety_level],
            title=f"[bold {impact_style}]Potential Impact[/bold {impact_style}]",
            border_style=impact_style,
        )
    )
    console.print()


def _render_plan_warnings(console: Console, plan: Plan) -> None:
    console.print(
        Panel(
            "\n".join(f"• {w}" for w in plan.warnings),
            title="[bold yellow]Planner Warnings[/bold yellow]",
            border_style="yellow",
        )
    )
    console.print()


def generate_compact_summary(plan: Plan) -> str:
    step_count = len(plan.steps)
    safety_color = _SAFETY_COLORS[plan.safety_level]

    intent_summary = _summarize_intent(plan)

    return (
        f"[cyan]{plan.plan_id}[/cyan] "
        f"[dim]\\[{plan.status.value}][/dim] "
        f"{intent_summary} "
        f"[dim]({step_count} step{'s' if step_count != 1 else ''}, "
        f"[{safety_color}]{plan.safety_level.value.upper()}[/{safety_color}])[/dim]"
    )


def _summarize_intent(plan: Plan) -> str:
    intent = plan.intent
    intent_name = intent.intent.value.replace("_", " ").title()

    if hasattr(intent, "interface") and intent.interface:
        return f"{intent_name} on {intent.interface}"
    elif hasattr(intent, "resource") and intent.resource:
        return f"{intent_name} {intent.resource}"
    else:
        return intent_name
