from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from mika.planner.plan import Plan


class ValidationLayer(str, Enum):

    SCHEMA = "schema"
    SYNTAX = "syntax"
    VERSION_COMPATIBILITY = "version_compatibility"
    RESOURCE_EXISTENCE = "resource_existence"
    DEPENDENCY = "dependency"
    OVERLAP = "overlap"
    CONFLICT = "conflict"
    SAFETY = "safety"


class IssueSeverity(str, Enum):

    FAIL = "FAIL"
    WARNING = "WARNING"


class ValidationIssue(BaseModel):

    model_config = ConfigDict(frozen=True)

    layer: ValidationLayer
    severity: IssueSeverity
    message: str
    step_id: str | None = Field(
        default=None, description="The PlanStep this issue applies to, if any."
    )


class ValidationResult(BaseModel):

    model_config = ConfigDict(frozen=True)

    plan_id: str
    validated: bool
    issues: tuple[ValidationIssue, ...] = Field(default_factory=tuple)
    plan: Plan

    @property
    def failures(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == IssueSeverity.FAIL)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == IssueSeverity.WARNING)

    def issues_for_layer(self, layer: ValidationLayer) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.layer == layer)
