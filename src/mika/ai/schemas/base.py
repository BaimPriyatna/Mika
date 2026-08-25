from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mika.ai.schemas.enums import (
    INTENT_CATEGORY,
    INTENT_SAFETY_LEVEL,
    IntentCategory,
    IntentName,
    SafetyLevel,
)


class IntentBase(BaseModel):

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: IntentName

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="The LLM's self-reported confidence. Informational only -- "
        "never treated as a safety guarantee (CLAUDE.md Section 39).",
    )

    requires_confirmation: bool = Field(
        description="Must equal (category != READ). Validated, not trusted -- "
        "see IntentBase.check_requires_confirmation.",
    )

    reasoning: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional short explanation from the LLM. Never executed, "
        "never parsed as instructions -- display-only.",
    )

    @property
    def category(self) -> IntentCategory:
        return INTENT_CATEGORY[self.intent]

    @property
    def safety_level(self) -> SafetyLevel:
        return INTENT_SAFETY_LEVEL[self.intent]

    @model_validator(mode="after")
    def _check_requires_confirmation(self) -> "IntentBase":
        expected = INTENT_CATEGORY[self.intent] != IntentCategory.READ
        if self.requires_confirmation != expected:
            raise ValueError(
                f"requires_confirmation={self.requires_confirmation!r} is inconsistent "
                f"with intent '{self.intent.value}' (category={INTENT_CATEGORY[self.intent].value}); "
                f"expected requires_confirmation={expected!r}. This value is derived, not chosen "
                "by the caller -- see CLAUDE.md Section 5 and Section 39."
            )
        return self
