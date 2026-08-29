"""
Compensating Rollback Engine.

Generates and executes inverse operations to restore previous router
configuration when a multi-step plan fails midway.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from mika.audit.models import RollbackResult
from mika.planner.plan import OperationType

if TYPE_CHECKING:
    from mika.planner.plan import Plan, PlanStep
    from mika.router.client import RouterClient

logger = logging.getLogger(__name__)


class ResourceBackup(BaseModel):

    model_config = ConfigDict(frozen=True)

    resource: str = Field(description="RouterOS REST resource path")
    resource_id: str | None = Field(
        default=None,
        description="Resource .id if this was an UPDATE/DELETE operation",
    )
    operation: OperationType
    data: dict[str, str] = Field(
        default_factory=dict,
        description="Original resource data (for UPDATE/DELETE)",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlanBackup(BaseModel):

    model_config = ConfigDict(frozen=True)

    plan_id: str
    router_identity: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resource_backups: tuple[ResourceBackup, ...] = Field(default_factory=tuple)

    system_export_path: Path | None = None


class RollbackEngine:

    def __init__(
        self,
        router_client: RouterClient,
        backup_dir: Path | None = None,
    ) -> None:
        self._client = router_client
        self._backup_dir = backup_dir

        if backup_dir:
            backup_dir.mkdir(parents=True, exist_ok=True)

    async def create_backup(self, plan: Plan) -> PlanBackup:
        logger.info(f"Creating backup for plan {plan.plan_id} ({len(plan.steps)} steps)")

        resource_backups: list[ResourceBackup] = []

        for step in plan.steps:
            try:
                backup = await self._backup_step(step)
                if backup:
                    resource_backups.append(backup)
                    logger.debug(f"Backed up step {step.step_id}")
            except Exception as e:
                logger.warning(
                    f"Failed to backup step {step.step_id}: {e}. "
                    f"Rollback may not be possible for this resource.",
                    exc_info=True,
                )

        system_export_path = None
        if self._should_create_system_export(plan):
            try:
                system_export_path = await self._create_system_export(plan)
                logger.info(f"Created system export: {system_export_path}")
            except Exception as e:
                logger.error(
                    f"Failed to create system export for plan {plan.plan_id}: {e}. "
                    f"Full system rollback may not be possible.",
                    exc_info=True,
                )

        backup = PlanBackup(
            plan_id=plan.plan_id,
            router_identity=plan.router_identity,
            resource_backups=tuple(resource_backups),
            system_export_path=system_export_path,
        )

        logger.info(
            f"Backup complete for plan {plan.plan_id}: "
            f"{len(resource_backups)} resource backups, "
            f"system export: {system_export_path is not None}"
        )

        return backup

    async def rollback(self, backup: PlanBackup) -> RollbackResult:
        logger.info(
            f"Attempting rollback for plan {backup.plan_id} "
            f"({len(backup.resource_backups)} resources)"
        )

        rolled_back = 0
        failed = 0
        errors: list[str] = []

        for resource_backup in reversed(backup.resource_backups):
            try:
                await self._rollback_resource(resource_backup)
                rolled_back += 1
                logger.debug(
                    f"Rolled back {resource_backup.operation.value} on {resource_backup.resource}"
                )
            except Exception as e:
                failed += 1
                error_msg = f"{resource_backup.resource}: {str(e)}"
                errors.append(error_msg)
                logger.error(
                    f"Failed to rollback {resource_backup.resource}: {e}",
                    exc_info=True,
                )

        success = failed == 0
        notes = self._generate_rollback_notes(rolled_back, failed, errors)

        logger.info(
            f"Rollback for plan {backup.plan_id} complete: "
            f"success={success}, rolled_back={rolled_back}, failed={failed}"
        )

        return RollbackResult(
            attempted=True,
            success=success,
            notes=notes,
        )

    async def _backup_step(self, step: PlanStep) -> ResourceBackup | None:
        if step.operation == OperationType.CREATE:
            return ResourceBackup(
                resource=step.resource,
                resource_id=None,
                operation=step.operation,
                data={},
            )

        elif step.operation == OperationType.UPDATE:
            if not step.resource_id:
                logger.warning(f"UPDATE step {step.step_id} has no resource_id")
                return None

            items = await self._read_resource(step.resource)
            current_item = self._find_item_by_id(items, step.resource_id)

            if not current_item:
                logger.warning(
                    f"UPDATE step {step.step_id}: resource {step.resource_id} not found"
                )
                return None

            return ResourceBackup(
                resource=step.resource,
                resource_id=step.resource_id,
                operation=step.operation,
                data=current_item,
            )

        elif step.operation == OperationType.DELETE:
            if not step.resource_id:
                logger.warning(f"DELETE step {step.step_id} has no resource_id")
                return None

            items = await self._read_resource(step.resource)
            current_item = self._find_item_by_id(items, step.resource_id)

            if not current_item:
                logger.warning(
                    f"DELETE step {step.step_id}: resource {step.resource_id} not found"
                )
                return None

            return ResourceBackup(
                resource=step.resource,
                resource_id=step.resource_id,
                operation=step.operation,
                data=current_item,
            )

        return None

    async def _rollback_resource(self, backup: ResourceBackup) -> None:
        if backup.operation == OperationType.CREATE:
            logger.warning(
                f"Cannot automatically rollback CREATE operation on {backup.resource}. "
                f"Manual cleanup may be required."
            )

        elif backup.operation == OperationType.UPDATE:
            if not backup.resource_id:
                raise ValueError("UPDATE rollback requires resource_id")

            await self._client.update_resource(
                backup.resource,
                backup.resource_id,
                backup.data,
            )

        elif backup.operation == OperationType.DELETE:
            await self._client.create_resource(backup.resource, backup.data)

    async def _read_resource(self, resource: str) -> list[dict]:
        resource_readers = {
            "/ip/address": self._client.get_addresses,
            "/ip/firewall/filter": self._client.get_firewall_rules,
            "/ip/firewall/nat": self._client.get_nat_rules,
            "/queue/simple": self._client.get_queues,
            "/interface/vlan": self._client.get_interfaces,
            "/ip/dhcp-server": self._client.get_dhcp_servers,
            "/ip/hotspot": self._client.get_hotspot_servers,
            "/ip/hotspot/user": self._client.get_hotspot_users,
            "/ip/route": self._client.get_routes,
            "/interface": self._client.get_interfaces,
        }

        reader = resource_readers.get(resource)
        if not reader:
            logger.warning(f"No reader for resource {resource}")
            return []

        return await reader()

    def _find_item_by_id(self, items: list[dict], resource_id: str) -> dict | None:
        for item in items:
            if item.get(".id") == resource_id:
                return item
        return None

    def _should_create_system_export(self, plan: Plan) -> bool:
        from mika.ai.schemas.enums import SafetyLevel

        return plan.safety_level in (SafetyLevel.HIGH_RISK, SafetyLevel.DESTRUCTIVE)

    async def _create_system_export(self, plan: Plan) -> Path | None:
        if not self._backup_dir:
            logger.info("System export requested but no backup_dir configured")
            return None

        logger.warning(
            f"Full system export not yet implemented for plan {plan.plan_id}. "
            f"This is a known limitation (see CLAUDE.md Section 31). "
            f"Only per-resource rollback is available."
        )

        return None

    def _generate_rollback_notes(
        self,
        rolled_back: int,
        failed: int,
        errors: list[str],
    ) -> str:
        if failed == 0:
            return (
                f"Rollback successful: {rolled_back} resource(s) restored to "
                f"pre-execution state."
            )
        else:
            error_summary = "; ".join(errors[:3])
            if len(errors) > 3:
                error_summary += f" (and {len(errors) - 3} more)"

            return (
                f"Partial rollback: {rolled_back} succeeded, {failed} failed. "
                f"Errors: {error_summary}. Manual intervention may be required."
            )


async def create_backup(
    plan: Plan,
    router_client: RouterClient,
    backup_dir: Path | None = None,
) -> PlanBackup:
    engine = RollbackEngine(router_client, backup_dir)
    return await engine.create_backup(plan)


async def rollback_from_backup(
    backup: PlanBackup,
    router_client: RouterClient,
) -> RollbackResult:
    engine = RollbackEngine(router_client)
    return await engine.rollback(backup)
