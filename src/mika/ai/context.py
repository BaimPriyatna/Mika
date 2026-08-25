"""
AI Context Assembler.

Compiles active router state, retrieved documentation, and persistent
memory into structured context for AI prompts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mika.knowledge.models import KnowledgeDocument


class AIContext(BaseModel):

    model_config = ConfigDict(extra="forbid", frozen=True)

    router_identity: str | None = Field(
        default=None,
        max_length=255,
        description="Router identity/hostname if known.",
    )
    routeros_version: str | None = Field(
        default=None,
        max_length=50,
        description="RouterOS version string (e.g. '7.14.3').",
    )
    interfaces: list[str] = Field(
        default_factory=list,
        description="List of known interface names on the router.",
    )
    relevant_knowledge: list[KnowledgeDocument] = Field(
        default_factory=list,
        description="Knowledge documents retrieved for the request topic.",
    )
    safety_constraints: list[str] = Field(
        default_factory=list,
        description="Explicit constraints (e.g. 'Do not modify ether1 WAN').",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional additional metadata.",
    )
