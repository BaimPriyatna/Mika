from __future__ import annotations

import sys
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

import questionary
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

if TYPE_CHECKING:
    from mika.planner.plan import Plan
    from mika.validator.result import ValidationResult


_CONFIRM_STYLE = questionary.Style([
    ("qmark", "fg:#c084fc bold"),
    ("question", "bold white"),
    ("pointer", "fg:#c084fc bold"),
    ("highlighted", "fg:#c084fc bold"),
    ("selected", "fg:#10b981 bold"),
    ("instruction", "fg:#888888 italic"),
])


class ConfirmationStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ConfirmationState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(description="ID of the plan being confirmed")
    status: ConfirmationStatus = Field(
        default=ConfirmationStatus.PENDING,
        description="Current confirmation status",
    )
    confirmed_at: datetime | None = Field(
        default=None,
        description="Timestamp when user confirmed (if confirmed)",
    )
    confirmed_by: str | None = Field(
        default=None,
        max_length=100,
        description="Username/identifier of confirming user",
    )
    cancellation_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Reason for cancellation (if cancelled)",
    )
    feedback: str | None = Field(
        default=None,
        max_length=1000,
        description="Requested modifications or feedback from user",
    )

    @property
    def is_confirmed(self) -> bool:
        return self.status == ConfirmationStatus.CONFIRMED

    @classmethod
    def confirmed(
        cls,
        plan_id: str,
        confirmed_by: str,
    ) -> "ConfirmationState":
        return cls(
            plan_id=plan_id,
            status=ConfirmationStatus.CONFIRMED,
            confirmed_at=datetime.now(timezone.utc),
            confirmed_by=confirmed_by,
        )

    @classmethod
    def cancelled(
        cls,
        plan_id: str,
        reason: str | None = None,
        feedback: str | None = None,
    ) -> "ConfirmationState":
        return cls(
            plan_id=plan_id,
            status=ConfirmationStatus.CANCELLED,
            cancellation_reason=reason,
            feedback=feedback,
        )

    @classmethod
    def modified(
        cls,
        plan_id: str,
        feedback: str,
    ) -> "ConfirmationState":
        return cls(
            plan_id=plan_id,
            status=ConfirmationStatus.CANCELLED,
            cancellation_reason=f"User requested modification: {feedback}",
            feedback=feedback,
        )

    @classmethod
    def pending(cls, plan_id: str) -> "ConfirmationState":
        return cls(
            plan_id=plan_id,
            status=ConfirmationStatus.PENDING,
        )


class ConfirmationError(Exception):
    pass


class NonInteractiveContextError(ConfirmationError):
    pass


def prompt_for_confirmation(
    plan: Plan,
    validation_result: ValidationResult | None = None,
    console: Console | None = None,
) -> ConfirmationState:
    if not sys.stdin.isatty():
        raise NonInteractiveContextError(
            "Cannot prompt for confirmation in non-interactive context. "
            "stdin is not a TTY. Refusing to proceed without explicit user confirmation."
        )

    if console is None:
        console = Console()

    from mika.planner.diff import generate_diff

    diff_output = generate_diff(plan, validation_result, show_data=False)
    console.print(diff_output)
    console.print()

    from mika.ai.schemas.enums import SafetyLevel

    if plan.safety_level == SafetyLevel.DESTRUCTIVE:
        return _prompt_destructive_confirmation(plan, console)
    else:
        return _prompt_standard_confirmation(plan, console)


def _prompt_standard_confirmation(
    plan: Plan,
    console: Console,
) -> ConfirmationState:
    console.print("[bold #c084fc]◆ Action Confirmation[/bold #c084fc]")
    console.print()

    choices = [
        questionary.Choice(title="✓  Yes, apply changes", value="yes"),
        questionary.Choice(title="✗  No, cancel", value="no"),
        questionary.Choice(title="✎  Type manual changes desired", value="modify"),
    ]

    try:
        choice = questionary.select(
            "Select action:",
            choices=choices,
            default="yes",
            style=_CONFIRM_STYLE,
            qmark="◈",
            instruction="(Use arrow keys)",
        ).ask()

        if choice is None:
            console.print("[yellow]Confirmation cancelled by user[/yellow]")
            return ConfirmationState.cancelled(
                plan_id=plan.plan_id,
                reason="User cancelled confirmation",
            )

        if choice == "yes":
            return ConfirmationState.confirmed(
                plan_id=plan.plan_id,
                confirmed_by=_get_current_user(),
            )
        elif choice == "no":
            return ConfirmationState.cancelled(
                plan_id=plan.plan_id,
                reason="User declined at confirmation prompt",
            )
        elif choice == "modify":
            feedback = questionary.text(
                "Enter requested changes:",
                style=_CONFIRM_STYLE,
                qmark="◈",
            ).ask()
            if not feedback or not feedback.strip():
                return ConfirmationState.cancelled(
                    plan_id=plan.plan_id,
                    reason="User declined without providing modification feedback",
                )
            return ConfirmationState.modified(
                plan_id=plan.plan_id,
                feedback=feedback.strip(),
            )
        else:
            return ConfirmationState.modified(
                plan_id=plan.plan_id,
                feedback=str(choice),
            )

    except KeyboardInterrupt:
        console.print("[yellow]Confirmation cancelled by user (Ctrl+C)[/yellow]")
        return ConfirmationState.cancelled(
            plan_id=plan.plan_id,
            reason="User interrupted with Ctrl+C",
        )
    except EOFError:
        console.print("[yellow]Confirmation cancelled (EOF)[/yellow]")
        return ConfirmationState.cancelled(
            plan_id=plan.plan_id,
            reason="stdin closed",
        )


def _prompt_destructive_confirmation(
    plan: Plan,
    console: Console,
) -> ConfirmationState:
    console.print()
    console.print(
        Panel(
            "[bold red]⚠️  DESTRUCTIVE OPERATION[/bold red]\n\n"
            "This operation will DELETE or significantly modify resources.\n"
            "Active connections and services may be permanently affected.\n\n"
            "Type exactly to proceed:\n"
            "  [bold white]CONFIRM DELETE[/bold white]",
            border_style="red",
            title="[bold red]⚠️  WARNING[/bold red]",
        )
    )
    console.print()

    try:
        user_input = Prompt.ask(
            ">",
            console=console,
        )

        if user_input == "CONFIRM DELETE":
            console.print("[green]✓[/green] Confirmation accepted")
            return ConfirmationState.confirmed(
                plan_id=plan.plan_id,
                confirmed_by=_get_current_user(),
            )
        else:
            console.print(
                f"[yellow]✗[/yellow] Expected 'CONFIRM DELETE', got '{user_input}'"
            )
            console.print("[yellow]Operation cancelled[/yellow]")
            return ConfirmationState.cancelled(
                plan_id=plan.plan_id,
                reason=f"User input '{user_input}' did not match required confirmation literal",
            )

    except KeyboardInterrupt:
        console.print("[yellow]Confirmation cancelled by user (Ctrl+C)[/yellow]")
        return ConfirmationState.cancelled(
            plan_id=plan.plan_id,
            reason="User interrupted with Ctrl+C",
        )
    except EOFError:
        console.print("[yellow]Confirmation cancelled (EOF)[/yellow]")
        return ConfirmationState.cancelled(
            plan_id=plan.plan_id,
            reason="stdin closed",
        )


def _get_current_user() -> str:
    import os
    import pwd

    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except (ImportError, KeyError):
        return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


def check_confirmation_expiration(
    plan: Plan,
    confirmation: ConfirmationState,
    current_router_fingerprint: str,
) -> ConfirmationState:
    if confirmation.status != ConfirmationStatus.CONFIRMED:
        return confirmation

    if plan.router_state_fingerprint != current_router_fingerprint:
        return ConfirmationState(
            plan_id=plan.plan_id,
            status=ConfirmationStatus.EXPIRED,
            confirmed_at=confirmation.confirmed_at,
            confirmed_by=confirmation.confirmed_by,
            cancellation_reason=(
                f"Router state changed since confirmation. "
                f"Expected fingerprint: {plan.router_state_fingerprint}, "
                f"current: {current_router_fingerprint}"
            ),
        )

    return confirmation
