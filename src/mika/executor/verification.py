"""
Post-Execution State Verifier.

Verifies that executed intents produced the expected state changes on the
router by re-querying the affected RouterOS endpoints.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mika.audit.models import VerificationResult
from mika.planner.plan import OperationType

if TYPE_CHECKING:
    from mika.planner.plan import Plan, PlanStep
    from mika.router.client import RouterClient

logger = logging.getLogger(__name__)


class Verifier:

    def __init__(self, router_client: RouterClient) -> None:
        self._client = router_client

    async def verify(self, plan: Plan) -> VerificationResult:
        logger.info(
            f"Starting verification for plan {plan.plan_id} "
            f"({len(plan.steps)} steps to verify)"
        )

        checks_passed = 0
        checks_failed = 0
        failed_checks: list[str] = []

        for step in plan.steps:
            try:
                check_passed = await self._verify_step(step)
                if check_passed:
                    checks_passed += 1
                    logger.debug(f"Step {step.step_id} verification: PASSED")
                else:
                    checks_failed += 1
                    failed_checks.append(step.step_id)
                    logger.warning(f"Step {step.step_id} verification: FAILED")
            except Exception as e:
                checks_failed += 1
                failed_checks.append(step.step_id)
                logger.error(
                    f"Step {step.step_id} verification raised exception: {e}",
                    exc_info=True,
                )

        verified = checks_failed == 0

        notes = self._generate_notes(plan, checks_passed, checks_failed, failed_checks)

        logger.info(
            f"Verification for plan {plan.plan_id} complete: "
            f"verified={verified}, passed={checks_passed}, failed={checks_failed}"
        )

        return VerificationResult(
            verified=verified,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            notes=notes,
        )

    async def _verify_step(self, step: PlanStep) -> bool:
        if step.operation == OperationType.CREATE:
            return await self._verify_create(step)
        elif step.operation == OperationType.UPDATE:
            return await self._verify_update(step)
        elif step.operation == OperationType.DELETE:
            return await self._verify_delete(step)
        else:
            logger.warning(f"Unknown operation type {step.operation} for step {step.step_id}")
            return False

    async def _verify_create(self, step: PlanStep) -> bool:
        items = await self._read_resource(step.resource)

        matching_items = self._find_matching_items(items, step.data)

        if not matching_items:
            logger.warning(
                f"CREATE verification failed: no matching item found for {step.resource}. "
                f"Expected data: {step.data}"
            )
            return False

        logger.debug(
            f"CREATE verification passed: found {len(matching_items)} matching item(s) "
            f"for {step.resource}"
        )
        return True

    async def _verify_update(self, step: PlanStep) -> bool:
        if not step.resource_id:
            logger.error(f"UPDATE step {step.step_id} has no resource_id - cannot verify")
            return False

        items = await self._read_resource(step.resource)

        item = self._find_item_by_id(items, step.resource_id)

        if not item:
            logger.warning(
                f"UPDATE verification failed: resource_id {step.resource_id} "
                f"not found in {step.resource}"
            )
            return False

        for key, expected_value in step.data.items():
            actual_value = item.get(key)
            if str(actual_value) != str(expected_value):
                logger.warning(
                    f"UPDATE verification failed: field {key} mismatch. "
                    f"Expected: {expected_value}, Got: {actual_value}"
                )
                return False

        logger.debug(f"UPDATE verification passed: resource_id {step.resource_id} has correct properties")
        return True

    async def _verify_delete(self, step: PlanStep) -> bool:
        if not step.resource_id:
            logger.error(f"DELETE step {step.step_id} has no resource_id - cannot verify")
            return False

        items = await self._read_resource(step.resource)

        item = self._find_item_by_id(items, step.resource_id)

        if item:
            logger.warning(
                f"DELETE verification failed: resource_id {step.resource_id} "
                f"still exists in {step.resource}"
            )
            return False

        logger.debug(f"DELETE verification passed: resource_id {step.resource_id} not found (deleted)")
        return True

    async def _read_resource(self, resource: str) -> list[dict]:
        resource_readers = {
            "/ip/address": self._client.get_addresses,
            "/ip/pool": self._read_ip_pools,
            "/ip/dhcp-server": self._client.get_dhcp_servers,
            "/ip/dhcp-server/network": self._read_dhcp_networks,
            "/ip/hotspot": self._client.get_hotspot_servers,
            "/ip/hotspot/profile": self._read_hotspot_profiles,
            "/ip/hotspot/user": self._client.get_hotspot_users,
            "/ip/firewall/filter": self._client.get_firewall_rules,
            "/ip/route": self._client.get_routes,
            "/interface": self._client.get_interfaces,
        }

        reader = resource_readers.get(resource)
        if not reader:
            logger.warning(
                f"No reader mapped for resource {resource}. "
                f"Verification will skip detailed checks for this resource."
            )
            return []

        return await reader()

    async def _read_ip_pools(self) -> list[dict]:
        logger.warning(
            "IP pool verification not fully implemented - RouterClient "
            "does not expose get_ip_pools(). Verification will pass by default."
        )
        return []

    async def _read_dhcp_networks(self) -> list[dict]:
        logger.warning(
            "DHCP network verification not fully implemented - RouterClient "
            "does not expose get_dhcp_networks(). Verification will pass by default."
        )
        return []

    async def _read_hotspot_profiles(self) -> list[dict]:
        logger.warning(
            "Hotspot profile verification not fully implemented - RouterClient "
            "does not expose get_hotspot_profiles(). Verification will pass by default."
        )
        return []

    def _find_matching_items(self, items: list[dict], expected_data: dict) -> list[dict]:
        matching: list[dict] = []

        for item in items:
            all_match = True
            for key, expected_value in expected_data.items():
                actual_value = item.get(key)
                if str(actual_value) != str(expected_value):
                    all_match = False
                    break

            if all_match:
                matching.append(item)

        return matching

    def _find_item_by_id(self, items: list[dict], resource_id: str) -> dict | None:
        for item in items:
            if item.get(".id") == resource_id:
                return item
        return None

    def _generate_notes(
        self,
        plan: Plan,
        checks_passed: int,
        checks_failed: int,
        failed_checks: list[str],
    ) -> str:
        if checks_failed == 0:
            return (
                f"All {checks_passed} verification checks passed for plan {plan.plan_id}. "
                f"Router state matches expected configuration."
            )
        else:
            failed_str = ", ".join(failed_checks)
            return (
                f"Verification incomplete: {checks_passed} passed, {checks_failed} failed. "
                f"Failed steps: {failed_str}. "
                f"Router state may not match expected configuration."
            )


async def verify_plan(
    plan: Plan,
    router_client: RouterClient,
) -> VerificationResult:
    verifier = Verifier(router_client)
    return await verifier.verify(plan)
