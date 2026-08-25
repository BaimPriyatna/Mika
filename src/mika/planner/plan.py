"""
Configuration Execution Plan.

Represents an ordered sequence of plan steps to be validated and executed
against RouterOS, with tracking for verification and rollback states.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from mika.ai.schemas.base import IntentBase
from mika.ai.schemas.enums import SafetyLevel

if TYPE_CHECKING:
    from mika.router.discovery import RouterContext


def compute_router_fingerprint(router_context: "RouterContext") -> str:
    parts = [
        router_context.routeros_version,
        *sorted(f"{i.name}:{i.disabled}" for i in router_context.interfaces),
        *sorted(a.address for a in router_context.addresses),
        *sorted(d.name for d in router_context.dhcp_servers),
        *sorted(h.name for h in router_context.hotspot_servers),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


class PlanStatus(str, Enum):

    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    VALIDATED = "VALIDATED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    VERIFIED = "VERIFIED"

    VALIDATION_FAILED = "VALIDATION_FAILED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class OperationType(str, Enum):

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class PlanStep(BaseModel):

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(description="Stable local label for this step, e.g. 'hotspot_pool'.")
    description: str = Field(description="Human-readable summary for terminal diff rendering (F10).")
    operation: OperationType
    resource: str = Field(description="RouterOS REST resource path, e.g. '/ip/pool'.")
    data: dict[str, str] = Field(
        default_factory=dict,
        description="Fields to send via RouterClient.create_resource/update_resource.",
    )
    resource_id: str | None = Field(
        default=None,
        description="RouterOS .id, required for update/delete. Must be re-resolved against "
        "live state before use (Section 27) -- never trusted from an old plan.",
    )


class Plan(BaseModel):

    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    intent: IntentBase
    status: PlanStatus = PlanStatus.PLANNED
    safety_level: SafetyLevel

    router_identity: str
    routeros_version: str
    router_state_fingerprint: str

    affected_interfaces: tuple[str, ...] = Field(default_factory=tuple)
    affected_networks: tuple[str, ...] = Field(default_factory=tuple)

    steps: tuple[PlanStep, ...] = Field(default_factory=tuple)

    warnings: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Caveats the planner could not resolve deterministically "
        "(CLAUDE.md Section 39 Rule 9: never silently convert uncertainty into certainty). "
        "Must be surfaced to the user, not swallowed.",
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def resource_count(self) -> int:
        return len(self.steps)
