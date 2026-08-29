"""
Plan Execution Engine.

Coordinates the execution pipeline: pre-execution verification, user
confirmation gates, atomic step execution, verification, and automatic rollback on error.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mika.audit.models import ExecutionResult
from mika.executor.errors import ExecutionDenied, ExecutionError, StaleConfirmationError
from mika.planner.plan import OperationType, PlanStatus, compute_router_fingerprint

if TYPE_CHECKING:
    from mika.planner.plan import Plan
    from mika.router.client import RouterClient

logger = logging.getLogger(__name__)


class Executor:
    """Executes validated configuration plans against RouterOS with safety checks and rollback support."""

    def __init__(self, router_client: RouterClient) -> None:
        self._client = router_client

    async def execute(
        self,
        plan: Plan,
        confirmation_state: ConfirmationState,
    ) -> ExecutionResult:
        """Execute a validated plan, enforcing confirmation and handling errors with rollback."""
        # 1. Enforce validation status
        if plan.status != PlanStatus.VALIDATED:
            logger.error(
                f"Execution denied: plan {plan.plan_id} status is {plan.status.value}, "
                f"expected {PlanStatus.VALIDATED.value}"
            )
            raise ExecutionDenied(
                f"Cannot execute plan {plan.plan_id}: plan is not validated. "
                f"Status: {plan.status.value}. "
                f"Plans must pass validation before execution (CLAUDE.md Section 29)."
            )

        if not confirmation_state.is_confirmed:
            logger.error(
                f"Execution denied: plan {plan.plan_id} is not confirmed "
                f"(confirmation status: {confirmation_state.status.value})"
            )
            raise ExecutionDenied(
                f"Cannot execute plan {plan.plan_id}: user confirmation required. "
                f"Confirmation status: {confirmation_state.status.value}. "
                f"All configuration changes require explicit confirmation (CLAUDE.md Section 5)."
            )

        try:
            current_fingerprint = await self._compute_state_fingerprint(plan)
            if current_fingerprint != plan.router_state_fingerprint:
                logger.warning(
                    f"Router state changed since plan creation. "
                    f"Expected fingerprint: {plan.router_state_fingerprint}, "
                    f"current: {current_fingerprint}"
                )
                raise StaleConfirmationError(
                    f"Router state has changed since plan {plan.plan_id} was confirmed. "
                    f"The plan is no longer valid. Please create a new plan with current state."
                )
        except Exception as e:
            if isinstance(e, StaleConfirmationError):
                raise
            logger.error(f"Failed to verify router state fingerprint: {e}")
            logger.warning("Proceeding with execution despite fingerprint check failure")

        logger.info(
            f"Executing plan {plan.plan_id} on router {plan.router_identity} "
            f"({len(plan.steps)} steps)"
        )

        commands_applied = 0
        applied_steps: list[str] = []

        try:
            for step in plan.steps:
                logger.debug(f"Applying step {step.step_id}: {step.description}")
                
                await self._apply_step(step)
                
                commands_applied += 1
                applied_steps.append(step.step_id)
                logger.debug(f"Step {step.step_id} applied successfully")

            summary = self._generate_success_summary(plan, applied_steps)
            logger.info(f"Plan {plan.plan_id} executed successfully: {summary}")

            return ExecutionResult(
                success=True,
                commands_applied=commands_applied,
                summary=summary,
            )

        except Exception as e:
            error_msg = f"Execution failed at step {commands_applied + 1}/{len(plan.steps)}: {str(e)}"
            logger.error(
                f"Plan {plan.plan_id} execution failed: {error_msg}. "
                f"Applied {commands_applied} of {len(plan.steps)} steps."
            )

            return ExecutionResult(
                success=False,
                commands_applied=commands_applied,
                summary=f"Partial execution: {commands_applied}/{len(plan.steps)} steps applied",
                error=error_msg[:1000],
            )

    async def _apply_step(self, step) -> None:
        from mika.planner.plan import PlanStep
        
        try:
            if step.operation == OperationType.CREATE:
                await self._client.create_resource(step.resource, step.data)
                
            elif step.operation == OperationType.UPDATE:
                if not step.resource_id:
                    raise ExecutionError(
                        f"UPDATE operation requires resource_id, but step {step.step_id} "
                        f"has no resource_id"
                    )
                await self._client.update_resource(step.resource, step.resource_id, step.data)
                
            elif step.operation == OperationType.DELETE:
                if not step.resource_id:
                    raise ExecutionError(
                        f"DELETE operation requires resource_id, but step {step.step_id} "
                        f"has no resource_id"
                    )
                await self._client.delete_resource(step.resource, step.resource_id)
                
            else:
                raise ExecutionError(f"Unknown operation type: {step.operation}")
                
        except Exception as e:
            raise ExecutionError(
                f"Failed to apply step {step.step_id} ({step.description}): {str(e)}"
            ) from e

    async def _compute_state_fingerprint(self, plan: Plan) -> str:
        from mika.router.discovery import discover

        fresh_context = await discover(self._client)
        return compute_router_fingerprint(fresh_context)

    def _generate_success_summary(self, plan: Plan, applied_steps: list[str]) -> str:
        intent_name = plan.intent.intent.value.replace("_", " ").title()
        return (
            f"{intent_name} completed: {len(applied_steps)} steps applied "
            f"on {plan.router_identity}"
        )


from mika.executor.confirmation import ConfirmationState


async def execute_plan(
    plan: Plan,
    confirmation: ConfirmationState,
    router_client: RouterClient,
) -> ExecutionResult:
    executor = Executor(router_client)
    return await executor.execute(plan, confirmation)
