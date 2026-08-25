from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class FactCategory(str, Enum):

    NETWORK_PREFERENCE = "network_preference"
    INTERFACE_PROTECTION = "interface_protection"
    SECURITY_POLICY = "security_policy"
    NAMING_CONVENTION = "naming_convention"
    DEFAULT_VALUE = "default_value"
    ROUTER_CONTEXT = "router_context"
    USER_BEHAVIOR = "user_behavior"
    GENERAL = "general"


class Fact(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    category: FactCategory
    key: str = Field(..., description="Unique identifier for this fact")
    value: Any = Field(..., description="The fact value")
    description: str = Field(..., description="Human-readable description")
    source: str = Field(..., description="Where this fact came from (e.g., 'chat', 'explicit command')")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    router_specific: bool = Field(default=False, description="Whether this fact applies to a specific router only")
    router_id: Optional[str] = Field(default=None, description="Router identifier if router_specific=True")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = Field(default=0, description="How many times this fact has been used")


class MemoryEntry(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int = Field(..., description="Database ID")
    fact: Fact
    active: bool = Field(default=True, description="Whether this memory is active")
    expires_at: Optional[datetime] = Field(default=None, description="Optional expiration time")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        exp = self.expires_at if self.expires_at.tzinfo is not None else self.expires_at.replace(tzinfo=timezone.utc)
        return now > exp

    def is_valid(self) -> bool:
        return self.active and not self.is_expired()


class MemoryContext(BaseModel):

    facts: list[Fact] = Field(default_factory=list)
    router_id: Optional[str] = None

    def to_prompt_text(self) -> str:
        if not self.facts:
            return ""

        lines = ["# User Preferences and Context\n"]

        by_category: dict[FactCategory, list[Fact]] = {}
        for fact in self.facts:
            if fact.category not in by_category:
                by_category[fact.category] = []
            by_category[fact.category].append(fact)

        for category, facts_list in sorted(by_category.items()):
            lines.append(f"\n## {category.value.replace('_', ' ').title()}")
            for fact in facts_list:
                lines.append(f"- {fact.description}: {fact.value}")

        return "\n".join(lines)

    def get_by_key(self, key: str) -> Optional[Fact]:
        for fact in self.facts:
            if fact.key == key:
                return fact
        return None

    def get_by_category(self, category: FactCategory) -> list[Fact]:
        return [f for f in self.facts if f.category == category]
