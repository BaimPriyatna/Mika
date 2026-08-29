from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from mika.ai.context import AIContext
from mika.utils.printer import (
    log_info,
    log_success,
    log_warning,
    log_error,
    status_spinner,
    print_section,
    console as rich_console,
)
from mika.ai.errors import AIError
from mika.ai.schemas.enums import IntentCategory
from mika.audit.models import AuditOutcome, ConfirmationRecord
from mika.cli import render
from mika.cli.errors import CliError
from mika.cli.input import build_prompt_session, read_line, cleanup_scroll_history
from mika.cli.session import ChatSession
from mika.cli.slash_commands import ExitRepl, dispatch, is_slash_command
from mika.executor.confirmation import (
    ConfirmationStatus,
    NonInteractiveContextError,
    prompt_for_confirmation,
)
from mika.executor.executor import execute_plan
from mika.executor.rollback import create_backup, rollback_from_backup
from mika.executor.verification import verify_plan
from mika.planner.errors import PlannerError
from mika.planner.hotspot import plan_create_hotspot
from mika.router.discovery import RouterContext, discover
from mika.validator.validator import validate

_PLANNERS = {
    "create_hotspot": plan_create_hotspot,
}


async def run_repl(session: ChatSession, console: Console | None = None) -> None:
    console = console or Console()
    
    _print_startup_message()
    _print_startup_status(session, console)

    prompt_session = build_prompt_session(session)

    while True:
        try:
            line = await read_line(prompt_session)
            cleanup_scroll_history(line)
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not line.strip():
            continue

        if is_slash_command(line):
            try:
                await dispatch(line, session, console)
            except ExitRepl:
                break
            continue

        try:
            await _handle_chat_turn(line.strip(), session, console)
        except Exception as exc:
            console.print(f"[red]Unexpected error occurred: {escape(str(exc) or type(exc).__name__)}[/red]")
            console.print("[dim]Session continues. If this persists, please report it as a bug.[/dim]")

    console.print("[dim]Goodbye.[/dim]")


def _print_startup_message() -> None:
    from mika.utils.printer.theme import Symbols
    rich_console.print()
    rich_console.print(f"[bold #c084fc]{Symbols.DIAMOND} MIKA[/bold #c084fc] [dim]— AI-assisted MikroTik RouterOS CLI[/dim]")
    rich_console.print("[dim]Type / for commands, /help for help, /exit to exit[/dim]")
    rich_console.print()


def _startup_banner() -> Panel:
    body = (
        "[bold cyan]mika[/bold cyan] [dim]-- AI-assisted MikroTik RouterOS CLI[/dim]\n"
        "[dim]Type your request in plain English, or /help for command list. "
        "Esc to cancel.[/dim]"
    )
    return Panel(body, border_style="cyan", padding=(0, 1), expand=False)


def _print_startup_status(session: ChatSession, console: Console) -> None:
    if session.router_alias is None:
        log_warning("No active router. Use /router add or /router select <alias>.")
    if session.provider is None:
        log_warning("No active AI provider. Use /provider to set up.")


async def _handle_chat_turn(request: str, session: ChatSession, console: Console) -> None:
    session.add_history("user", request)

    try:
        provider = session.require_provider()
        client = session.require_router()
    except CliError as exc:
        log_warning(str(exc))
        return

    try:
        with status_spinner("Reading router state..."):
            ctx = await discover(client)
    except Exception as exc:
        log_error(f"Failed to read router state: {exc}")
        return

    ai_context = AIContext(
        router_identity=ctx.identity,
        routeros_version=ctx.routeros_version,
        interfaces=ctx.interface_names,
        # Exclude the just-appended current request (last entry) — it's
        # already included separately as <user_request> in the prompt.
        recent_history=[
            f"{entry.role}: {entry.text}" for entry in session.recent_context_turns()[:-1]
        ],
        memory_facts_text=(
            session.memory_manager.get_context(router_id=session.router_alias).to_prompt_text()
            if session.memory_manager is not None
            else None
        ),
    )

    try:
        with status_spinner("Contacting AI provider..."):
            intent = await provider.generate_intent(request, context=ai_context)
    except AIError as exc:
        log_error(f"AI provider error: {exc}")
        session.add_history("assistant", f"(error) {exc}")
        return

    session.add_history("assistant", f"intent={intent.intent.value}")

    if intent.category == IntentCategory.READ:
        if intent.intent.value == "advise":
            message = getattr(intent, "message", intent.reasoning or "")
            options = getattr(intent, "options", [])
            suggested_action = getattr(intent, "suggested_action", None)
            render.render_advice(console, message, options, suggested_action)
            session.add_history("assistant", message)
            return

        if intent.intent.value == "troubleshoot":
            from mika.cli.troubleshoot_ui import run_troubleshoot

            fix_request = await run_troubleshoot(intent.problem_description, session, console)
            session.add_history("assistant", "(diagnosis shown)")
            if fix_request:
                await _handle_chat_turn(fix_request, session, console)
            return

        target = render.INTENT_TO_TARGET.get(intent.intent.value)
        if target is None:
            console.print(f"[yellow]Read intent '{escape(intent.intent.value)}' does not have a matching view.[/yellow]")
            return
        if intent.reasoning:
            console.print(f"\n[bold #c084fc]◆ Mika:[/bold #c084fc] {escape(intent.reasoning)}")
        render.render_inspect(console, target, ctx)
        return

    if intent.reasoning:
        console.print(f"\n[bold #c084fc]◆ Mika:[/bold #c084fc] {escape(intent.reasoning)}\n")

    planner_fn = _PLANNERS.get(intent.intent.value)
    if planner_fn is None:
        console.print(
            f"[yellow]Intent '{intent.intent.value}' detected, but planner for this "
            "is not yet implemented. Currently only 'create_hotspot' is supported.[/yellow]"
        )
        return

    try:
        plan = planner_fn(intent, ctx)
    except PlannerError as exc:
        console.print(f"[red]Plan generation failed: {escape(str(exc))}[/red]")
        return

    try:
        with status_spinner("Validating plan..."):
            fresh_ctx = await discover(client)
            result = validate(plan, fresh_ctx, session.knowledge_retriever)
    except Exception as exc:
        log_error(f"Plan validation failed: {exc}")
        return

    if not result.validated:
        from mika.planner.diff import generate_diff

        console.print(generate_diff(result.plan, result, show_data=False))
        console.print("[red]Plan is invalid, cancelled.[/red]")
        _audit(session, ctx, request, intent.model_dump(), result.plan.model_dump(), outcome=AuditOutcome.FAILED)
        return

    session.last_plan = result.plan

    try:
        confirmation = prompt_for_confirmation(result.plan, result, console)
    except NonInteractiveContextError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        return

    if confirmation.status != ConfirmationStatus.CONFIRMED:
        if confirmation.feedback:
            console.print(f"\n[cyan]Feedback received:[/cyan] {escape(confirmation.feedback)}")
            console.print("[dim]Re-planning with your requested modifications...[/dim]\n")
            _audit(
                session,
                ctx,
                request,
                intent.model_dump(),
                result.plan.model_dump(),
                confirmation=_confirmation_record(confirmation),
                outcome=AuditOutcome.CANCELLED,
            )
            await _handle_chat_turn(
                f"Previous request was: '{request}'. Please adjust the plan with these changes: {confirmation.feedback}",
                session,
                console,
            )
            return

        console.print("[yellow]Cancelled by user.[/yellow]")
        _audit(
            session,
            ctx,
            request,
            intent.model_dump(),
            result.plan.model_dump(),
            confirmation=_confirmation_record(confirmation),
            outcome=AuditOutcome.CANCELLED,
        )
        return

    try:
        with status_spinner("Creating backup before execution..."):
            backup = await create_backup(result.plan, client)
        session.last_backup = backup
    except Exception as exc:
        log_error(f"Backup creation failed, execution cancelled: {exc}")
        return

    try:
        with status_spinner("Executing plan..."):
            exec_result = await execute_plan(result.plan, confirmation, client)
    except Exception as exc:
        log_error(f"Execution failed: {exc}")
        _audit(
            session,
            ctx,
            request,
            intent.model_dump(),
            result.plan.model_dump(),
            confirmation=_confirmation_record(confirmation),
            outcome=AuditOutcome.FAILED,
        )
        return

    if not exec_result.success:
        console.print(f"[red]Execution failed: {escape(str(exec_result.error or exec_result.summary))}[/red]")
        _audit(
            session,
            ctx,
            request,
            intent.model_dump(),
            result.plan.model_dump(),
            confirmation=_confirmation_record(confirmation),
            execution_result=exec_result,
            outcome=AuditOutcome.FAILED,
        )
        return

    with status_spinner("Verifying results..."):
        verify_result = await verify_plan(result.plan, client)

    rollback_result = None
    outcome = AuditOutcome.SUCCESS
    if not verify_result.verified:
        log_warning(f"Verification failed: {verify_result.notes}")
        try:
            should_rollback = console.input("Rollback to previous state? [y/N] ").strip().lower() == "y"
        except (EOFError, KeyboardInterrupt):
            should_rollback = False
        if should_rollback:
            with status_spinner("Rolling back..."):
                rollback_result = await rollback_from_backup(backup, client)
            outcome = AuditOutcome.ROLLED_BACK if rollback_result.success else AuditOutcome.FAILED
        else:
            outcome = AuditOutcome.FAILED
    else:
        log_success("Plan successfully executed and verified.")

    message_id = session.add_history("assistant", exec_result.summary or "(completed)")
    if (
        outcome == AuditOutcome.SUCCESS
        and session.backup_store is not None
        and message_id is not None
        and session.router_alias is not None
    ):
        session.backup_store.add_backup(session.session_id, message_id, session.router_alias, backup)

    _audit(
        session,
        ctx,
        request,
        intent.model_dump(),
        result.plan.model_dump(),
        confirmation=_confirmation_record(confirmation),
        execution_result=exec_result,
        verification_result=verify_result,
        rollback_result=rollback_result,
        outcome=outcome,
    )


def _confirmation_record(confirmation) -> ConfirmationRecord:
    return ConfirmationRecord(
        confirmed=confirmation.status == ConfirmationStatus.CONFIRMED,
        method="typed confirmation" if confirmation.status == ConfirmationStatus.CONFIRMED else "declined",
        confirmed_at=confirmation.confirmed_at,
    )


def _audit(
    session: ChatSession,
    ctx: RouterContext,
    request: str,
    intent: dict,
    plan: dict,
    *,
    confirmation: ConfirmationRecord | None = None,
    execution_result=None,
    verification_result=None,
    rollback_result=None,
    outcome: AuditOutcome,
) -> None:
    session.audit_logger.record(
        user=session.current_os_user(),
        router=ctx.identity,
        request=request,
        routeros_version=ctx.routeros_version,
        intent=intent,
        plan=plan,
        confirmation=confirmation,
        execution_result=execution_result,
        verification_result=verification_result,
        rollback_result=rollback_result,
        outcome=outcome,
    )
