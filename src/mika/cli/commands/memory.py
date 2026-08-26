from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from mika.memory import FactCategory, MemoryManager

app = typer.Typer(
    name="memory",
    help="Manage user memory and preferences.",
)

console = Console()


def _get_memory_manager() -> MemoryManager:
    db_path = Path.home() / ".config" / "mika" / "memory.db"
    return MemoryManager.from_path(db_path)


@app.command("list")
def list_memories(
    category: Optional[str] = typer.Option(
        None,
        "--category",
        "-c",
        help="Filter by category (network_preference, interface_protection, security_policy, etc.)",
    ),
    router_id: Optional[str] = typer.Option(
        None,
        "--router",
        "-r",
        help="Filter by router ID (includes global memories)",
    ),
    show_inactive: bool = typer.Option(
        False,
        "--inactive",
        help="Show inactive/expired memories",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON",
    ),
) -> None:
    manager = _get_memory_manager()

    cat_filter = None
    if category:
        try:
            cat_filter = FactCategory(category)
        except ValueError:
            console.print(f"[red]Invalid category: {category}[/red]")
            console.print(f"Valid categories: {', '.join([c.value for c in FactCategory])}")
            raise typer.Exit(1)

    entries = manager.list_memories(
        category=cat_filter,
        router_id=router_id,
        active_only=not show_inactive,
    )

    if not entries:
        console.print("[yellow]No memories found.[/yellow]")
        return

    if json_output:
        import json
        data = [
            {
                "id": e.id,
                "category": e.fact.category.value,
                "key": e.fact.key,
                "value": e.fact.value,
                "description": e.fact.description,
                "router_specific": e.fact.router_specific,
                "router_id": e.fact.router_id,
                "confidence": e.fact.confidence,
                "source": e.fact.source,
                "active": e.active,
                "created_at": e.fact.created_at.isoformat(),
                "access_count": e.fact.access_count,
            }
            for e in entries
        ]
        console.print(json.dumps(data, indent=2))
        return

    table = Table(title="User Memory")
    table.add_column("ID", style="cyan")
    table.add_column("Category", style="magenta")
    table.add_column("Key", style="green")
    table.add_column("Description", style="white")
    table.add_column("Value", style="yellow")
    table.add_column("Scope", style="blue")
    table.add_column("Uses", style="cyan")

    for entry in entries:
        scope = "Global"
        if entry.fact.router_specific:
            scope = f"Router: {entry.fact.router_id}"

        status_marker = "" if entry.active else " [dim](inactive)[/dim]"

        table.add_row(
            str(entry.id),
            entry.fact.category.value,
            entry.fact.key + status_marker,
            entry.fact.description,
            str(entry.fact.value),
            scope,
            str(entry.fact.access_count),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(entries)} memories[/dim]")


@app.command("forget")
def forget_memory(
    key: str = typer.Argument(..., help="Key of the memory to forget"),
) -> None:
    manager = _get_memory_manager()

    entry = manager.storage.get(key)
    if not entry:
        console.print(f"[red]Memory not found: {key}[/red]")
        raise typer.Exit(1)

    console.print(f"[yellow]Forgetting memory:[/yellow]")
    console.print(f"  Key: {entry.fact.key}")
    console.print(f"  Description: {entry.fact.description}")
    console.print(f"  Value: {entry.fact.value}")

    confirm = typer.confirm("Are you sure?")
    if not confirm:
        console.print("[yellow]Cancelled.[/yellow]")
        raise typer.Exit(0)

    success = manager.forget(key)
    if success:
        console.print(f"[green]✓ Forgotten: {key}[/green]")
    else:
        console.print(f"[red]Failed to forget: {key}[/red]")
        raise typer.Exit(1)


@app.command("add")
def add_memory(
    key: str = typer.Argument(..., help="Unique key for this memory"),
    value: str = typer.Argument(..., help="Value to remember"),
    description: str = typer.Option(..., "--description", "-d", help="Description of this memory"),
    category: str = typer.Option(
        "general",
        "--category",
        "-c",
        help="Memory category",
    ),
    router_id: Optional[str] = typer.Option(
        None,
        "--router",
        "-r",
        help="Router ID (makes this memory router-specific)",
    ),
) -> None:
    manager = _get_memory_manager()

    try:
        cat = FactCategory(category)
    except ValueError:
        console.print(f"[red]Invalid category: {category}[/red]")
        console.print(f"Valid categories: {', '.join([c.value for c in FactCategory])}")
        raise typer.Exit(1)

    mem_id = manager.remember(
        category=cat,
        key=key,
        value=value,
        description=description,
        source="cli_explicit",
        router_specific=router_id is not None,
        router_id=router_id,
    )

    console.print(f"[green]✓ Memory added (ID: {mem_id})[/green]")
    console.print(f"  Key: {key}")
    console.print(f"  Description: {description}")
    console.print(f"  Value: {value}")
    console.print(f"  Category: {category}")
    if router_id:
        console.print(f"  Router: {router_id}")


@app.command("clear")
def clear_memories(
    router_id: Optional[str] = typer.Option(
        None,
        "--router",
        "-r",
        help="Only clear memories for this router",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation",
    ),
) -> None:
    manager = _get_memory_manager()

    entries = manager.list_memories(router_id=router_id, active_only=False)
    count = len(entries)

    if count == 0:
        console.print("[yellow]No memories to clear.[/yellow]")
        return

    scope = f"for router '{router_id}'" if router_id else "ALL"
    console.print(f"[red]WARNING: This will delete {count} memories {scope}.[/red]")

    if not force:
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)

    deleted = manager.clear_all(router_id=router_id)
    console.print(f"[green]✓ Cleared {deleted} memories.[/green]")


@app.command("show")
def show_memory(
    key: str = typer.Argument(..., help="Key of the memory to show"),
) -> None:
    manager = _get_memory_manager()

    entry = manager.storage.get(key)
    if not entry:
        console.print(f"[red]Memory not found: {key}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Memory Details[/bold]")
    console.print(f"  ID: {entry.id}")
    console.print(f"  Key: {entry.fact.key}")
    console.print(f"  Category: {entry.fact.category.value}")
    console.print(f"  Description: {entry.fact.description}")
    console.print(f"  Value: {entry.fact.value}")
    console.print(f"  Confidence: {entry.fact.confidence:.2f}")
    console.print(f"  Source: {entry.fact.source}")
    console.print(f"  Active: {'Yes' if entry.active else 'No'}")

    if entry.fact.router_specific:
        console.print(f"  Router: {entry.fact.router_id}")
    else:
        console.print("  Scope: Global")

    console.print(f"  Created: {entry.fact.created_at}")
    console.print(f"  Updated: {entry.updated_at}")
    console.print(f"  Last Accessed: {entry.fact.last_accessed}")
    console.print(f"  Access Count: {entry.fact.access_count}")

    if entry.expires_at:
        console.print(f"  Expires: {entry.expires_at}")
        if entry.is_expired():
            console.print("  [red]Status: EXPIRED[/red]")
    console.print()


if __name__ == "__main__":
    app()
